"""Unified push notification interface.

Routes notifications through available channels:
- Telegram (preferred — supports images, inline buttons, bidirectional)
- HA mobile app (fallback — via HA notify services)

The :class:`PushNotifier` is used by the :class:`Announcer` and can
also be called directly by handlers for rich notifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.ha.services import HAServices
    from clanker.remote.chat import TelegramBot

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PushAction:
    """An actionable button on a push notification."""

    label: str
    action_id: str


@dataclass(frozen=True, slots=True)
class PushNotification:
    """A push notification payload."""

    message: str
    title: str = ""
    image: bytes | None = None
    image_url: str | None = None
    actions: list[PushAction] = field(default_factory=list)
    priority: str = "normal"


class PushNotifier:
    """Unified push notification sender.

    Tries Telegram first (richer UX), falls back to HA mobile push.
    Can be configured to use both simultaneously.

    Usage::

        notifier = PushNotifier(telegram=bot, ha_services=services, ha_targets=[...])
        await notifier.notify(PushNotification(
            message="Person at front door",
            title="Doorbell",
            image=snapshot_bytes,
            actions=[PushAction("Talk", "TALK"), PushAction("Ignore", "IGNORE")],
        ))
    """

    def __init__(
        self,
        *,
        telegram: TelegramBot | None = None,
        ha_services: HAServices | None = None,
        ha_targets: list[str] | None = None,
    ) -> None:
        self._telegram = telegram
        self._ha = ha_services
        self._ha_targets = ha_targets or []

    async def notify(self, notification: PushNotification) -> bool:
        """Send a push notification through available channels.

        Returns:
            True if delivered via at least one channel.
        """
        delivered = False

        # Telegram (preferred)
        if self._telegram:
            ok = await self._send_telegram(notification)
            if ok:
                delivered = True

        # HA mobile push (fallback or additional)
        if self._ha and self._ha_targets:
            ok = await self._send_ha(notification)
            if ok:
                delivered = True

        if not delivered:
            logger.warning(
                "push.no_channels",
                message=notification.message[:80],
            )

        return delivered

    async def _send_telegram(self, n: PushNotification) -> bool:
        """Send via Telegram bot."""
        assert self._telegram is not None

        # Build inline keyboard from actions
        buttons = None
        if n.actions:
            buttons = [
                [{"text": a.label, "callback_data": a.action_id}]
                for a in n.actions
            ]

        # Build message text
        text = n.message
        if n.title:
            text = f"<b>{n.title}</b>\n{n.message}"

        try:
            # Send with image if available
            if n.image:
                return await self._telegram.send_photo(
                    n.image, caption=text, buttons=buttons
                )
            return await self._telegram.send(text, buttons=buttons)
        except Exception:
            logger.exception("push.telegram_error")
            return False

    async def _send_ha(self, n: PushNotification) -> bool:
        """Send via HA notify services."""
        assert self._ha is not None

        data: dict[str, Any] = {}
        if n.actions:
            data["actions"] = [
                {"action": a.action_id, "title": a.label}
                for a in n.actions
            ]
        if n.image_url:
            data["image"] = n.image_url
        if n.priority == "critical":
            data["push"] = {
                "sound": {"name": "default", "critical": 1, "volume": 1.0}
            }

        ok = False
        for target in self._ha_targets:
            try:
                await self._ha.notify(
                    target,
                    n.message,
                    title=n.title or None,
                    data=data if data else None,
                )
                ok = True
            except Exception:
                logger.exception("push.ha_error", target=target)

        return ok
