"""Clanker entrypoint — wires all modules together and manages lifecycle.

Loads config, initializes subsystems (HA client, memory, brain, MCP server,
event dispatcher, announcement router), subscribes to HA events, starts
the proactive scheduler, and handles graceful shutdown on SIGTERM/SIGINT.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

import structlog

from clanker.config import load_settings
from clanker.ha.client import HAClient
from clanker.ha.events import EventDispatcher
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
    logger.info("clanker.starting", version="0.1.0")

    # Initialize memory
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

    # Initialize HA client
    ha_client = HAClient(url=settings.ha.url, token=settings.ha.token)

    try:
        await ha_client.connect()
    except Exception:
        logger.exception("clanker.ha_connect_failed")
        await structured_memory.close()
        await semantic_memory.close()
        sys.exit(1)

    # Initialize brain router
    from clanker.brain.router import BrainRouter

    brain = BrainRouter(settings)

    # Initialize event dispatcher
    dispatcher = EventDispatcher()

    # Subscribe to HA events
    try:
        await ha_client.subscribe_events(dispatcher.dispatch, event_type="state_changed")
        logger.info("clanker.subscribed", event_type="state_changed")
    except Exception:
        logger.exception("clanker.subscribe_failed")

    # Initialize announcement router
    from clanker.announce.router import AnnouncementRouter

    _announcement_router = AnnouncementRouter(ha_client, settings.announce)

    # TODO: Initialize proactive scheduler
    # from clanker.proactive.scheduler import ProactiveScheduler
    # scheduler = ProactiveScheduler(...)
    # await scheduler.start()

    # TODO: Start MCP server (in a separate task or process for stdio mode)
    # The MCP server is available for external brain connections:
    # from clanker.mcp.server import create_mcp_server
    # mcp_server = create_mcp_server(ha_client, memory_tools)

    logger.info("clanker.ready")

    # Wait for shutdown signal
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("clanker.shutdown_signal")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    # Graceful shutdown
    logger.info("clanker.shutting_down")

    # TODO: Stop scheduler
    # await scheduler.stop()

    await brain.close()
    await ha_client.close()
    await structured_memory.close()
    await semantic_memory.close()

    logger.info("clanker.stopped")


def main() -> None:
    """Sync entrypoint for the ``clanker`` console script."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
