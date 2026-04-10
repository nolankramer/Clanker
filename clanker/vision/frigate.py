"""Frigate event subscription and snapshot fetching.

Subscribes to Frigate events via the HA event bus and pulls snapshots
for vision processing.

TODO:
- Subscribe to frigate/events on the HA event bus
- Parse FrigateEvent model (camera, label, score, snapshot_url, zones)
- Fetch snapshots via Frigate's HTTP API
- Route events to VLM for description
- Implement event deduplication and cooldown
"""

from __future__ import annotations


# TODO: Implement Frigate event handler
# class FrigateEventHandler:
#     async def handle_event(self, event: dict) -> None: ...
#     async def fetch_snapshot(self, event_id: str) -> bytes: ...
