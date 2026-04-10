"""Unknown person event handler.

Triggered when Frigate detects a person that Double Take cannot
identify (or no face match).  Uses VLM to describe the person
and assesses context (time of day, location) to determine
alert priority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from clanker.announce.quiet_hours import Priority

if TYPE_CHECKING:
    from clanker.announce.deliver import Announcer
    from clanker.vision.frigate import FrigateEvent, FrigateEventHandler
    from clanker.vision.vlm import VLMProvider

logger = structlog.get_logger(__name__)

# Cameras in "perimeter" areas get higher alert priority for unknowns
_PERIMETER_CAMERAS = {
    "front_door", "back_door", "side_gate", "garage",
    "driveway", "porch", "entrance",
}


class UnknownPersonHandler:
    """Handles unidentified person detections from Frigate.

    Uses time-of-day and camera location to assess priority:
    - Night + perimeter camera → HIGH (likely concerning)
    - Day + perimeter camera → NORMAL (probably delivery/visitor)
    - Interior cameras → NORMAL (may be guest)
    """

    def __init__(
        self,
        announcer: Announcer,
        frigate: FrigateEventHandler,
        vlm: VLMProvider | None = None,
        perimeter_cameras: set[str] | None = None,
    ) -> None:
        self._announcer = announcer
        self._frigate = frigate
        self._vlm = vlm
        self._perimeter = perimeter_cameras or _PERIMETER_CAMERAS

    async def handle_event(self, event: FrigateEvent) -> None:
        """Process an unidentified person event."""
        if event.label != "person":
            return
        if event.event_type == "end":
            return

        logger.info(
            "unknown_person.detected",
            camera=event.camera,
            score=event.top_score,
            zones=event.zones,
        )

        # Fetch snapshot + VLM description
        snapshot = (
            await self._frigate.fetch_snapshot(event.id)
            if event.has_snapshot
            else None
        )
        description = None
        if snapshot and self._vlm:
            try:
                description = await self._vlm.describe(
                    snapshot,
                    "Describe this person briefly: approximate age, clothing, "
                    "what they're doing, anything they're carrying. One sentence.",
                )
            except Exception:
                logger.exception("unknown_person.vlm_error")

        # Assess priority based on time + location
        priority = self._assess_priority(event.camera)

        # Compose message
        camera_name = event.camera.replace("_", " ").title()
        if description:
            message = f"Unidentified person seen on {camera_name} camera. {description}"
        else:
            message = f"Unidentified person detected on {camera_name} camera."

        await self._announcer.say(
            message,
            priority,
            title="Unknown Person",
            push_data={
                "actions": [
                    {"action": "MONITOR", "title": "Monitor"},
                    {"action": "IGNORE", "title": "Ignore"},
                ],
                "image": f"/api/frigate/notifications/{event.id}/snapshot.jpg",
            },
        )

    def _assess_priority(self, camera: str) -> Priority:
        """Determine alert priority from time and camera location."""
        hour = datetime.now(tz=UTC).hour
        is_night = hour >= 22 or hour < 6
        is_perimeter = camera in self._perimeter

        if is_night and is_perimeter:
            return Priority.HIGH
        return Priority.NORMAL
