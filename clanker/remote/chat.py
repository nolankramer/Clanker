"""Telegram bot — bidirectional chat + push notifications.

Provides:
- Incoming: user texts Clanker → routed through conversation agent
- Outgoing: alerts/announcements → sent as Telegram messages
- Images: camera snapshots attached to alerts
- Actions: inline keyboard buttons for doorbell/critical responses

Uses the Telegram Bot API directly via httpx (no python-telegram-bot
dependency).  Requires a bot token from @BotFather and the user's
chat ID.

Setup::

    1. Message @BotFather on Telegram → /newbot → get token
    2. Message your bot → run ``clanker-setup`` to auto-detect chat ID
    3. Add token + chat_id to config
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from clanker.conversation.agent import ConversationAgent

logger = structlog.get_logger(__name__)

_API_BASE = "https://api.telegram.org/bot"


class TelegramBot:
    """Telegram bot for chat and push notifications.

    Runs a long-polling loop to receive messages and exposes
    :meth:`send` / :meth:`send_photo` for outbound notifications.
    """

    def __init__(
        self,
        token: str,
        chat_ids: list[int],
        *,
        agent: ConversationAgent | None = None,
        allowed_chat_ids: list[int] | None = None,
    ) -> None:
        """Initialize the Telegram bot.

        Args:
            token: Bot API token from @BotFather.
            chat_ids: Default chat IDs for outbound messages.
            agent: Conversation agent for processing incoming messages.
            allowed_chat_ids: Chat IDs allowed to interact (security).
                If None, only ``chat_ids`` are allowed.
        """
        self._token = token
        self._chat_ids = chat_ids
        self._agent = agent
        self._allowed = set(allowed_chat_ids or chat_ids)
        self._api = f"{_API_BASE}{token}"
        self._client = httpx.AsyncClient(timeout=60.0)
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False
        self._offset = 0

    async def start(self) -> None:
        """Start the long-polling loop for incoming messages."""
        # Verify token
        me = await self._api_call("getMe")
        if not me.get("ok"):
            logger.error("telegram.invalid_token")
            return

        bot_name = me.get("result", {}).get("username", "unknown")
        logger.info("telegram.connected", bot=bot_name)
        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="telegram_poll"
        )

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
        await self._client.aclose()
        logger.info("telegram.stopped")

    # ------------------------------------------------------------------
    # Outbound — push notifications
    # ------------------------------------------------------------------

    async def send(
        self,
        text: str,
        *,
        chat_id: int | None = None,
        parse_mode: str = "HTML",
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> bool:
        """Send a text message to one or all configured chat IDs.

        Args:
            text: Message text (HTML supported).
            chat_id: Specific chat ID, or None to send to all.
            parse_mode: Telegram parse mode (HTML, Markdown, etc.).
            buttons: Inline keyboard rows, each button is
                ``{"text": "Label", "callback_data": "action"}``.

        Returns:
            True if at least one message was sent successfully.
        """
        targets = [chat_id] if chat_id else self._chat_ids
        payload: dict[str, Any] = {"text": text, "parse_mode": parse_mode}

        if buttons:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": buttons}
            )

        ok = False
        for cid in targets:
            payload["chat_id"] = cid
            result = await self._api_call("sendMessage", payload)
            if result.get("ok"):
                ok = True
            else:
                logger.warning(
                    "telegram.send_failed",
                    chat_id=cid,
                    error=result.get("description"),
                )
        return ok

    async def send_photo(
        self,
        photo: bytes,
        *,
        caption: str = "",
        chat_id: int | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> bool:
        """Send a photo (e.g. camera snapshot) to Telegram.

        Args:
            photo: JPEG image bytes.
            caption: Optional caption text.
            chat_id: Specific chat ID, or None to send to all.
            buttons: Inline keyboard buttons.

        Returns:
            True if at least one message was sent.
        """
        targets = [chat_id] if chat_id else self._chat_ids
        ok = False

        for cid in targets:
            data: dict[str, Any] = {"chat_id": str(cid)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            if buttons:
                data["reply_markup"] = json.dumps(
                    {"inline_keyboard": buttons}
                )
            files = {"photo": ("snapshot.jpg", photo, "image/jpeg")}

            try:
                resp = await self._client.post(
                    f"{self._api}/sendPhoto", data=data, files=files
                )
                result = resp.json()
                if result.get("ok"):
                    ok = True
            except Exception:
                logger.exception("telegram.send_photo_error", chat_id=cid)

        return ok

    # ------------------------------------------------------------------
    # Inbound — message polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Long-poll for incoming messages and route to the agent."""
        logger.info("telegram.polling_started")
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("telegram.poll_error")
                await asyncio.sleep(5.0)

    async def _get_updates(self) -> list[dict[str, Any]]:
        """Fetch new updates via long polling."""
        result = await self._api_call(
            "getUpdates",
            {
                "offset": self._offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        updates = result.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def _handle_update(self, update: dict[str, Any]) -> None:
        """Process a single Telegram update."""
        # Callback query (inline button press)
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)
            return

        # Regular message
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return

        # Security: only allow configured chat IDs
        if chat_id not in self._allowed:
            logger.warning("telegram.unauthorized", chat_id=chat_id)
            await self.send(
                "Unauthorized. Your chat ID is not in the allowed list.",
                chat_id=chat_id,
            )
            return

        logger.info(
            "telegram.message_received",
            chat_id=chat_id,
            text=text[:80],
        )

        # Special commands
        if text.startswith("/"):
            await self._handle_command(text, chat_id)
            return

        # Route through conversation agent
        if self._agent:
            try:
                result = await self._agent.process(
                    text, conversation_id=f"telegram:{chat_id}"
                )
                await self.send(result["speech"], chat_id=chat_id)
            except Exception:
                logger.exception("telegram.agent_error")
                await self.send(
                    "Sorry, something went wrong.", chat_id=chat_id
                )
        else:
            await self.send(
                "Clanker brain is not connected.", chat_id=chat_id
            )

    async def _handle_command(self, text: str, chat_id: int) -> None:
        """Handle slash commands."""
        cmd = text.split()[0].lower()

        if cmd == "/start":
            await self.send(
                "<b>Clanker</b> is connected.\n\n"
                "Send me a message and I'll control your smart home.\n"
                f"Your chat ID: <code>{chat_id}</code>",
                chat_id=chat_id,
            )
        elif cmd == "/status":
            await self.send("Clanker is running.", chat_id=chat_id)
        elif cmd == "/chatid":
            await self.send(
                f"Your chat ID: <code>{chat_id}</code>",
                chat_id=chat_id,
            )
        else:
            await self.send(
                f"Unknown command: {cmd}", chat_id=chat_id
            )

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        """Handle inline keyboard button presses."""
        data = callback.get("data", "")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        user = callback.get("from", {}).get("first_name", "User")

        logger.info(
            "telegram.callback",
            action=data,
            chat_id=chat_id,
            user=user,
        )

        # Acknowledge the callback
        await self._api_call(
            "answerCallbackQuery",
            {"callback_query_id": callback["id"], "text": f"Action: {data}"},
        )

        # Route callback to agent
        if self._agent and chat_id:
            try:
                result = await self._agent.process(
                    f"[Button pressed: {data}]",
                    conversation_id=f"telegram:{chat_id}",
                )
                await self.send(result["speech"], chat_id=chat_id)
            except Exception:
                logger.exception("telegram.callback_error")

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    async def _api_call(
        self, method: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a Telegram Bot API call."""
        try:
            resp = await self._client.post(
                f"{self._api}/{method}", json=data or {}
            )
            return resp.json()  # type: ignore[no-any-return]
        except Exception:
            logger.exception("telegram.api_error", method=method)
            return {"ok": False, "description": "Request failed"}


# ------------------------------------------------------------------
# Helper: get chat ID from a bot token (for setup wizard)
# ------------------------------------------------------------------


def get_bot_info(token: str) -> dict[str, Any]:
    """Verify a bot token and get bot info."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(f"{_API_BASE}{token}/getMe")
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            return {
                "ok": True,
                "username": bot.get("username"),
                "name": bot.get("first_name"),
            }
        return {"ok": False, "message": data.get("description", "Invalid token")}


def get_chat_id(token: str, timeout: float = 60.0) -> dict[str, Any]:
    """Wait for a message to the bot and return the sender's chat ID.

    Used during setup: user sends any message to the bot, we capture
    their chat ID.

    Args:
        token: Bot API token.
        timeout: How long to wait for a message (seconds).

    Returns:
        Dict with ``ok``, ``chat_id``, and ``username``.
    """
    with httpx.Client(timeout=timeout + 5) as client:
        resp = client.post(
            f"{_API_BASE}{token}/getUpdates",
            json={"timeout": int(timeout), "allowed_updates": ["message"]},
        )
        data = resp.json()
        updates = data.get("result", [])
        if updates:
            msg = updates[-1].get("message", {})
            chat = msg.get("chat", {})
            return {
                "ok": True,
                "chat_id": chat.get("id"),
                "username": chat.get("username", ""),
                "first_name": chat.get("first_name", ""),
            }
        return {"ok": False, "message": "No messages received within timeout"}
