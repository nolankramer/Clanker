"""Doorbell event handler.

Flow: Frigate detects person at door camera → snapshot is pulled →
VLM describes the scene → face recognition checks identity →
announcement is composed and delivered → push notification sent
with actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from clanker.announce.quiet_hours import Priority

if TYPE_CHECKING:
    from clanker.announce.deliver import Announcer
    from clanker.vision.faces import FaceRecognizer
    from clanker.vision.frigate import FrigateEvent, FrigateEventHandler
    from clanker.vision.vlm import VLMProvider

logger = structlog.get_logger(__name__)

# Camera names typically associated with doorbells / front entrance
_DOOR_CAMERAS = {"front_door", "doorbell", "front", "porch", "entrance"}


class DoorbellHandler:
    """Handles person detection at door cameras.

    Registered as a callback on :class:`FrigateEventHandler`. When a
    person is detected at a door camera, it:
    1. Fetches the snapshot
    2. Runs VLM description
    3. Checks face recognition
    4. Composes and delivers an announcement
    """

    def __init__(
        self,
        announcer: Announcer,
        frigate: FrigateEventHandler,
        vlm: VLMProvider | None = None,
        face_recognizer: FaceRecognizer | None = None,
        door_cameras: set[str] | None = None,
    ) -> None:
        self._announcer = announcer
        self._frigate = frigate
        self._vlm = vlm
        self._faces = face_recognizer
        self._door_cameras = door_cameras or _DOOR_CAMERAS

    async def handle_event(self, event: FrigateEvent) -> None:
        """Process a Frigate event for doorbell activity."""
        # Only handle person detections at door cameras
        if event.label != "person":
            return
        if event.camera not in self._door_cameras:
            return
        if event.event_type == "end":
            return

        logger.info(
            "doorbell.person_detected",
            camera=event.camera,
            score=event.top_score,
            event_id=event.id,
        )

        # Fetch snapshot
        snapshot = await self._frigate.fetch_snapshot(event.id) if event.has_snapshot else None

        # VLM description
        description = None
        if snapshot and self._vlm:
            try:
                description = await self._vlm.describe(
                    snapshot,
                    "Describe who is at the front door. Include their appearance, "
                    "what they're carrying, and any relevant details. One sentence.",
                )
            except Exception:
                logger.exception("doorbell.vlm_error")

        # Face recognition
        person_name = None
        if self._faces:
            try:
                match = await self._faces.identify(
                    face_name=None,
                    confidence=event.top_score,
                    camera=event.camera,
                    snapshot=snapshot,
                )
                person_name = match.person_name
                if not description and match.description:
                    description = match.description
            except Exception:
                logger.exception("doorbell.face_error")

        # Compose announcement
        message = self._compose_message(person_name, description)

        await self._announcer.say(
            message,
            Priority.HIGH,
            title="Doorbell",
            push_data={
                "actions": [
                    {"action": "TALK", "title": "Talk"},
                    {"action": "IGNORE", "title": "Ignore"},
                ],
                "image": f"/api/frigate/notifications/{event.id}/snapshot.jpg",
            },
        )

    @staticmethod
    def _compose_message(
        person_name: str | None, description: str | None
    ) -> str:
        """Build a natural doorbell announcement."""
        if person_name and description:
            return f"Someone is at the front door. It looks like {person_name}. {description}"
        if person_name:
            return f"{person_name} is at the front door."
        if description:
            return f"Someone is at the front door. {description}"
        return "Someone is at the front door."
