"""Announcement delivery — combines routing with TTS and push delivery.

This is the single module that handlers call to announce something.
It routes via :class:`AnnouncementRouter`, then delivers via
:class:`HAServices` TTS and push notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from clanker.announce.quiet_hours import Priority

if TYPE_CHECKING:
    from clanker.announce.router import AnnouncementRouter, AudienceRules
    from clanker.ha.services import HAServices

logger = structlog.get_logger(__name__)


class Announcer:
    """High-level announce API used by proactive handlers.

    Usage::

        await announcer.say("The laundry is done.", Priority.NORMAL)
        await announcer.alert("SMOKE DETECTED", Priority.CRITICAL)
    """

    def __init__(self, router: AnnouncementRouter, services: HAServices) -> None:
        self._router = router
        self._services = services

    async def say(
        self,
        message: str,
        priority: Priority = Priority.NORMAL,
        *,
        audience: AudienceRules | None = None,
        title: str | None = None,
        push_data: dict | None = None,
    ) -> None:
        """Route and deliver an announcement.

        Args:
            message: Text to speak / push.
            priority: Priority level.
            audience: Optional audience restrictions.
            title: Push notification title.
            push_data: Extra push data (actions, image URL, etc.).
        """
        targets = await self._router.route(message, priority, audience=audience)

        if targets.suppressed:
            logger.info("announcer.suppressed", reason=targets.reason)

        # TTS to speakers
        for speaker in targets.tts_speakers:
            try:
                await self._services.tts_speak(speaker, message)
            except Exception:
                logger.exception("announcer.tts_error", speaker=speaker)

        # Push notifications
        for push_target in targets.push_targets:
            try:
                await self._services.notify(
                    push_target, message, title=title, data=push_data
                )
            except Exception:
                logger.exception("announcer.push_error", target=push_target)

        logger.info(
            "announcer.delivered",
            message=message[:80],
            tts_count=len(targets.tts_speakers),
            push_count=len(targets.push_targets),
        )
