"""Double Take / CompreFace face recognition integration.

Receives "known face" metadata from Frigate events (via Double Take)
and enriches event context with identity information from structured memory.

TODO:
- Parse Double Take event data from HA event bus
- Look up recognized faces in StructuredMemory
- Provide personalized context for announcements (e.g. "Your neighbor Jim")
- Handle unknown faces with description fallback via VLM
"""

from __future__ import annotations


# TODO: Implement face recognition integration
# class FaceRecognizer:
#     async def identify(self, event_data: dict) -> str | None: ...
