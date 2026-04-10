"""Clanker entrypoint — wires all modules together and manages lifecycle.

Loads config, initializes all subsystems, subscribes to HA events,
starts the conversation API server, proactive scheduler, and handles
graceful shutdown on SIGTERM/SIGINT.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

import structlog

from clanker.config import TaskType, load_settings
from clanker.ha.client import HAClient
from clanker.ha.events import EventDispatcher
from clanker.ha.services import HAServices
from clanker.logging import setup_logging
from clanker.memory.semantic import SemanticMemory
from clanker.memory.structured import StructuredMemory
from clanker.memory.tools import MemoryTools

logger = structlog.get_logger(__name__)


async def run() -> None:
    """Main async entrypoint — initialize, connect, serve, shutdown."""
    # Load config
    config_path = Path("config/clanker.yaml")
    settings = load_settings(config_path)

    # Setup logging
    setup_logging(level=settings.log_level, json_output=settings.log_json)
    logger.info("clanker.starting", version="0.1.1")

    # ---- Memory ----
    structured_memory = StructuredMemory(settings.memory.db_path)
    await structured_memory.initialize()

    semantic_memory = SemanticMemory(
        markdown_dir=settings.memory.markdown_dir,
        chromadb_path=settings.memory.chromadb_path,
        embedding_model=settings.memory.embedding_model,
        embedding_base_url=settings.memory.embedding_base_url,
    )
    await semantic_memory.initialize()

    memory_tools = MemoryTools(structured=structured_memory, semantic=semantic_memory)

    # ---- Home Assistant ----
    ha_client = HAClient(url=settings.ha.url, token=settings.ha.token)

    try:
        await ha_client.connect()
    except Exception:
        logger.exception("clanker.ha_connect_failed")
        await structured_memory.close()
        await semantic_memory.close()
        sys.exit(1)

    ha_services = HAServices(ha_client)

    # ---- Brain Router ----
    from clanker.brain.router import BrainRouter

    brain = BrainRouter(settings)

    # ---- Event Dispatcher ----
    dispatcher = EventDispatcher()

    try:
        await ha_client.subscribe_events(dispatcher.dispatch, event_type="state_changed")
        logger.info("clanker.subscribed", event_type="state_changed")
    except Exception:
        logger.exception("clanker.subscribe_failed")

    # ---- Telegram Bot ----
    from clanker.remote.chat import TelegramBot

    telegram: TelegramBot | None = None
    tg_cfg = settings.remote.telegram
    if tg_cfg.enabled and tg_cfg.bot_token and tg_cfg.chat_ids:
        telegram = TelegramBot(
            token=tg_cfg.bot_token,
            chat_ids=tg_cfg.chat_ids,
            # agent wired later after ConversationAgent is created
        )

    # ---- SMS Adapter ----
    from clanker.remote.sms import SMSAdapter

    sms: SMSAdapter | None = None
    sms_cfg = settings.remote.sms
    if sms_cfg.enabled and sms_cfg.account_sid and sms_cfg.from_number:
        sms = SMSAdapter(
            account_sid=sms_cfg.account_sid,
            auth_token=sms_cfg.auth_token,
            from_number=sms_cfg.from_number,
            to_numbers=sms_cfg.to_numbers,
        )

    # ---- Announcement Router + Delivery ----
    from clanker.announce.deliver import Announcer
    from clanker.announce.router import AnnouncementRouter

    announcement_router = AnnouncementRouter(ha_client, settings.announce)
    announcer = Announcer(
        announcement_router, ha_services, telegram=telegram, sms=sms
    )

    # ---- VLM ----
    from clanker.vision.vlm import BrainVLM

    vision_provider = brain.for_task(TaskType.VISION)
    vlm = BrainVLM(vision_provider) if vision_provider.supports_vision else None

    # ---- Frigate ----
    from clanker.vision.frigate import FrigateEventHandler

    frigate: FrigateEventHandler | None = None
    if settings.frigate.enabled:
        frigate = FrigateEventHandler(
            ha_client=ha_client,
            frigate_url=settings.frigate.url,
            cooldown_seconds=settings.frigate.cooldown_seconds,
            min_score=settings.frigate.min_score,
            cameras=settings.frigate.cameras,
        )
        await frigate.start()
        logger.info("clanker.frigate_started")

    # ---- Face Recognizer ----
    from clanker.vision.faces import FaceRecognizer

    face_recognizer = FaceRecognizer(
        ha_client=ha_client, memory=structured_memory, vlm=vlm
    )
    try:
        await face_recognizer.start()
        logger.info("clanker.faces_started")
    except Exception:
        logger.warning("clanker.faces_subscribe_failed", exc_info=True)

    # ---- Proactive Event Handlers ----
    from clanker.proactive.handlers.appliance import ApplianceHandler
    from clanker.proactive.handlers.critical import CriticalEventHandler

    critical_handler = CriticalEventHandler(announcer)
    dispatcher.register("state_changed", critical_handler.handle_event)

    appliance_handler = ApplianceHandler(announcer)
    dispatcher.register("state_changed", appliance_handler.handle_event)

    if frigate:
        from clanker.proactive.handlers.doorbell import DoorbellHandler
        from clanker.proactive.handlers.unknown_person import UnknownPersonHandler

        doorbell_handler = DoorbellHandler(
            announcer=announcer,
            frigate=frigate,
            vlm=vlm,
            face_recognizer=face_recognizer,
        )
        frigate.on_event(doorbell_handler.handle_event)

        unknown_handler = UnknownPersonHandler(
            announcer=announcer, frigate=frigate, vlm=vlm
        )
        frigate.on_event(unknown_handler.handle_event)
        logger.info("clanker.vision_handlers_registered")

    # ---- Conversation Agent + HTTP Server ----
    from clanker.conversation.agent import ConversationAgent
    from clanker.conversation.server import ConversationServer

    conversation_brain = brain.for_task(TaskType.CONVERSATION)
    system_prompt = settings.conversation.system_prompt or None

    conversation_agent = ConversationAgent(
        brain=conversation_brain,
        ha_client=ha_client,
        memory_tools=memory_tools,
        ha_services=ha_services,
        **({"system_prompt": system_prompt} if system_prompt else {}),
        session_ttl=settings.conversation.session_ttl_seconds,
        db_path=settings.memory.db_path.replace(".db", "_sessions.db"),
    )
    await conversation_agent.initialize()

    # Wire agent into SMS for inbound message handling
    if sms:
        sms._agent = conversation_agent

    conversation_server = ConversationServer(
        agent=conversation_agent,
        host=settings.conversation.host,
        port=settings.conversation.port,
        sms_adapter=sms,
    )
    await conversation_server.start()

    # ---- Start Telegram bot (with agent now available) ----
    if telegram:
        telegram._agent = conversation_agent
        await telegram.start()
        logger.info("clanker.telegram_started")

    # ---- Proactive Scheduler ----
    from clanker.proactive.briefing import MorningBriefing
    from clanker.proactive.scheduler import ProactiveScheduler

    scheduler = ProactiveScheduler()

    briefing = MorningBriefing(
        brain=brain.for_task(TaskType.SUMMARIZATION),
        ha_client=ha_client,
        ha_services=ha_services,
        config=settings.proactive,
    )

    # Register briefing motion trigger
    if settings.proactive.briefing_motion_sensor:
        dispatcher.register("state_changed", briefing.check_trigger)
        logger.info(
            "clanker.briefing_armed",
            sensor=settings.proactive.briefing_motion_sensor,
        )

    await scheduler.start()

    # ---- MCP Server (run in background task) ----
    from clanker.mcp.server import create_mcp_server

    _mcp_server = create_mcp_server(ha_client, memory_tools)
    # MCP stdio server would block; it's available for external connections
    # when run separately: python -m clanker.mcp.server
    logger.info("clanker.mcp_available")

    # ---- Ready ----
    logger.info(
        "clanker.ready",
        conversation_api=f"http://{settings.conversation.host}:{settings.conversation.port}",
    )

    # ---- Shutdown handling ----
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("clanker.shutdown_signal")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    # ---- Graceful shutdown ----
    logger.info("clanker.shutting_down")

    await scheduler.stop()
    if telegram:
        await telegram.stop()
    if sms:
        await sms.close()
    await conversation_server.stop()
    await conversation_agent.close()
    if frigate:
        await frigate.close()
    await brain.close()
    await ha_client.close()
    await structured_memory.close()
    await semantic_memory.close()

    logger.info("clanker.stopped")


def main() -> None:
    """Sync entrypoint for the ``clanker`` console script."""
    import contextlib

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
