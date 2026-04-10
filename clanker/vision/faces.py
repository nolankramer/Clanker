"""Face recognition integration via Double Take and structured memory.

Listens for ``doubletake`` events on the HA event bus.  When a face is
recognised it is looked up in :class:`StructuredMemory` to resolve the
person's name and context.  Unknown faces can optionally be described
via a :class:`VLMProvider`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.ha.client import HAClient
    from clanker.memory.structured import StructuredMemory
    from clanker.vision.vlm import VLMProvider

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FaceMatch:
    """Result of face identification."""

    person_name: str | None
    confidence: float
    camera: str
    description: str | None = None  # VLM description for unknown faces


@dataclass
class FaceRecognizer:
    """Identifies people from Double Take recognition events.

    Subscribes to the HA ``doubletake`` event type.  For known faces the
    name is resolved via structured memory.  For unknowns a VLM fallback
    provides a brief appearance description.
    """

    ha_client: HAClient
    memory: StructuredMemory
    vlm: VLMProvider | None = None
    _subscription_id: int | None = field(default=None, repr=False)

    async def start(self) -> None:
        """Subscribe to Double Take events on the HA bus."""
        self._subscription_id = await self.ha_client.subscribe_events(
            self._on_event, event_type="doubletake"
        )
        logger.info("faces.subscribed", subscription_id=self._subscription_id)

    async def _on_event(self, event: dict[str, Any]) -> None:
        """Handle a raw Double Take recognition event."""
        data = event.get("data", {})
        match_data = data.get("match", {})

        face_name = match_data.get("name", "")
        confidence = match_data.get("confidence", 0.0)
        camera = match_data.get("camera", "unknown")

        logger.info(
            "faces.event", name=face_name, confidence=confidence, camera=camera
        )

        if face_name:
            face = await self.memory.get_face(face_name)
            if face:
                logger.info(
                    "faces.known", name=face_name, person_id=face.get("person_id")
                )

    async def identify(
        self,
        face_name: str | None,
        confidence: float,
        camera: str,
        snapshot: bytes | None = None,
    ) -> FaceMatch:
        """Identify a person from face recognition data.

        Args:
            face_name: Name from Double Take, or ``None`` if unknown.
            confidence: Recognition confidence (0-1).
            camera: Camera that captured the face.
            snapshot: Optional snapshot for VLM description of unknowns.

        Returns:
            :class:`FaceMatch` with person name and/or description.
        """
        if face_name:
            face = await self.memory.get_face(face_name)
            if face:
                person_id = face.get("person_id")
                if person_id:
                    person = await self.memory.get_person(str(person_id))
                    if person:
                        return FaceMatch(
                            person_name=person.get("name", face_name),
                            confidence=confidence,
                            camera=camera,
                        )
            return FaceMatch(
                person_name=face_name, confidence=confidence, camera=camera
            )

        # Unknown face — try VLM description fallback
        description = None
        if snapshot and self.vlm:
            try:
                description = await self.vlm.describe(
                    snapshot,
                    "Briefly describe this person's appearance (age range, clothing, "
                    "distinguishing features). Be concise — one sentence.",
                )
            except Exception:
                logger.exception("faces.vlm_error")

        return FaceMatch(
            person_name=None,
            confidence=confidence,
            camera=camera,
            description=description,
        )
