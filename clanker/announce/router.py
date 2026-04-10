"""Announcement router — decides where to deliver a message.

Given a message, priority, and audience rules, the router:
1. Checks quiet hours — suppress non-critical TTS if active
2. Queries occupancy sensors — which rooms have people
3. Maps occupied rooms → speaker entity IDs
4. Returns target list: TTS speakers and/or push notification targets

For critical alerts, all speakers and push targets are included regardless
of occupancy or quiet hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from clanker.announce.occupancy import get_occupied_rooms, get_speakers_for_rooms
from clanker.announce.quiet_hours import Priority, should_suppress

if TYPE_CHECKING:
    from clanker.config import AnnounceConfig
    from clanker.ha.client import HAClient

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AnnouncementTarget:
    """Resolved delivery targets for an announcement."""

    tts_speakers: list[str] = field(default_factory=list)
    push_targets: list[str] = field(default_factory=list)
    suppressed: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AudienceRules:
    """Rules for who should receive an announcement.

    If ``rooms`` is set, only those rooms are considered (even if
    other rooms are occupied). If empty, all occupied rooms are targets.
    """

    rooms: list[str] = field(default_factory=list)
    adults_only: bool = False
    include_push: bool = True


class AnnouncementRouter:
    """Routes announcements to the right speakers and push targets.

    Usage::

        router = AnnouncementRouter(ha_client, announce_config)
        targets = await router.route(
            message="The laundry is done.",
            priority=Priority.NORMAL,
        )
        # Then deliver to targets.tts_speakers and targets.push_targets
    """

    def __init__(self, ha_client: HAClient, config: AnnounceConfig) -> None:
        """Initialize the router.

        Args:
            ha_client: Connected HA client for occupancy queries.
            config: Announcement configuration.
        """
        self._ha_client = ha_client
        self._config = config

    async def route(
        self,
        message: str,
        priority: Priority = Priority.NORMAL,
        *,
        audience: AudienceRules | None = None,
        now: datetime | None = None,
    ) -> AnnouncementTarget:
        """Determine where to deliver an announcement.

        Args:
            message: The message text (used for logging, not routing).
            priority: Message priority level.
            audience: Optional audience rules.
            now: Override current time (for testing).

        Returns:
            Resolved delivery targets.
        """
        if audience is None:
            audience = AudienceRules()

        # Critical alerts go everywhere
        if priority >= Priority.CRITICAL:
            return self._critical_targets(message)

        # Check quiet hours
        if should_suppress(self._config.quiet_hours, priority, now=now):
            logger.info("announce.suppressed_quiet_hours", message=message[:80])
            # During quiet hours, fall back to push only for NORMAL priority
            if priority >= Priority.NORMAL and audience.include_push:
                return AnnouncementTarget(
                    push_targets=list(self._config.fallback_push_targets),
                    suppressed=True,
                    reason="quiet_hours_push_fallback",
                )
            return AnnouncementTarget(suppressed=True, reason="quiet_hours")

        # Query occupancy
        occupancy = await get_occupied_rooms(self._ha_client, self._config)
        occupied_room_names = [r.room for r in occupancy if r.occupied]

        # Apply audience room filter
        if audience.rooms:
            target_rooms = [r for r in audience.rooms if r in occupied_room_names]
        else:
            target_rooms = occupied_room_names

        # Get speakers for target rooms
        speakers = get_speakers_for_rooms(target_rooms, self._config)

        # Determine push targets
        push_targets: list[str] = []
        if not speakers and audience.include_push:
            # No one home or no speakers found — fall back to push
            push_targets = list(self._config.fallback_push_targets)
        elif audience.include_push and priority >= Priority.HIGH:
            # High priority: push in addition to TTS
            push_targets = list(self._config.fallback_push_targets)

        logger.info(
            "announce.routed",
            message=message[:80],
            priority=priority.name,
            occupied_rooms=occupied_room_names,
            target_rooms=target_rooms,
            speakers=speakers,
            push_targets=push_targets,
        )

        return AnnouncementTarget(
            tts_speakers=speakers,
            push_targets=push_targets,
        )

    def _critical_targets(self, message: str) -> AnnouncementTarget:
        """For critical alerts: target ALL speakers and ALL push targets.

        Args:
            message: The message text (for logging).

        Returns:
            Targets including every configured speaker and push target.
        """
        all_speakers: list[str] = []
        for rs in self._config.room_speakers:
            all_speakers.extend(rs.speaker_entity_ids)

        logger.warning(
            "announce.critical",
            message=message[:80],
            speakers=all_speakers,
            push_targets=list(self._config.fallback_push_targets),
        )

        return AnnouncementTarget(
            tts_speakers=all_speakers,
            push_targets=list(self._config.fallback_push_targets),
        )
