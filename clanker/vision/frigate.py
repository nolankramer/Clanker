"""Frigate event subscription, snapshot fetching, and event deduplication.

Subscribes to ``frigate_events`` on the HA event bus.  When a detection
arrives it is parsed, deduplicated (per camera+label with a configurable
cooldown), and dispatched to registered callbacks.  Snapshots are fetched
from Frigate's HTTP API on demand.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from clanker.ha.client import HAClient

logger = structlog.get_logger(__name__)

FrigateCallback = Callable[["FrigateEvent"], Coroutine[Any, Any, None]]


@dataclass(frozen=True, slots=True)
class FrigateEvent:
    """Parsed Frigate detection event."""

    id: str
    event_type: str  # "new", "update", "end"
    camera: str
    label: str
    sub_label: str | None
    score: float
    top_score: float
    zones: list[str]
    current_zones: list[str]
    entered_zones: list[str]
    has_snapshot: bool
    has_clip: bool
    start_time: float
    end_time: float | None
    thumbnail: str | None  # base64 thumbnail if provided


@dataclass
class FrigateEventHandler:
    """Subscribes to Frigate events via the HA event bus.

    Features:
    * Deduplication via per-camera+label cooldown.
    * Minimum-score filtering.
    * Snapshot fetching from Frigate HTTP API.
    * Callback dispatch for downstream processing (VLM, announcements, etc.).
    """

    ha_client: HAClient
    frigate_url: str
    cooldown_seconds: float = 30.0
    min_score: float = 0.6
    cameras: list[str] = field(default_factory=list)

    _callbacks: list[FrigateCallback] = field(default_factory=list, repr=False)
    _last_event_time: dict[str, float] = field(default_factory=dict, repr=False)
    _http: httpx.AsyncClient | None = field(default=None, repr=False)
    _subscription_id: int | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to Frigate events on the HA event bus."""
        base = self.frigate_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=base, timeout=30.0)
        self._subscription_id = await self.ha_client.subscribe_events(
            self._on_ha_event, event_type="frigate_events"
        )
        logger.info(
            "frigate.subscribed",
            subscription_id=self._subscription_id,
            cameras=self.cameras or "all",
        )

    def on_event(self, callback: FrigateCallback) -> None:
        """Register a callback for processed Frigate events."""
        self._callbacks.append(callback)

    async def close(self) -> None:
        """Release HTTP client resources."""
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("frigate.closed")

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def _on_ha_event(self, event: dict[str, Any]) -> None:
        """Handle raw HA ``frigate_events`` event."""
        data = event.get("data", {})
        event_type = data.get("type", "")
        after = data.get("after", {})

        if not after:
            return

        frigate_event = FrigateEvent(
            id=after.get("id", ""),
            event_type=event_type,
            camera=after.get("camera", ""),
            label=after.get("label", ""),
            sub_label=after.get("sub_label"),
            score=after.get("score", 0.0),
            top_score=after.get("top_score", 0.0),
            zones=after.get("zones", []),
            current_zones=after.get("current_zones", []),
            entered_zones=after.get("entered_zones", []),
            has_snapshot=after.get("has_snapshot", False),
            has_clip=after.get("has_clip", False),
            start_time=after.get("start_time", 0.0),
            end_time=after.get("end_time"),
            thumbnail=after.get("thumbnail"),
        )

        # Camera filter
        if self.cameras and frigate_event.camera not in self.cameras:
            return

        # Minimum score filter
        if frigate_event.top_score < self.min_score:
            logger.debug(
                "frigate.low_score",
                event_id=frigate_event.id,
                score=frigate_event.top_score,
            )
            return

        # Deduplication cooldown (skip for "end" events)
        dedup_key = f"{frigate_event.camera}:{frigate_event.label}"
        now = time.monotonic()
        last_seen = self._last_event_time.get(dedup_key, 0.0)
        if event_type != "end" and now - last_seen < self.cooldown_seconds:
            logger.debug("frigate.cooldown", key=dedup_key, elapsed=now - last_seen)
            return
        self._last_event_time[dedup_key] = now

        logger.info(
            "frigate.event",
            event_id=frigate_event.id,
            type=event_type,
            camera=frigate_event.camera,
            label=frigate_event.label,
            score=frigate_event.top_score,
            zones=frigate_event.zones,
        )

        for callback in self._callbacks:
            try:
                await callback(frigate_event)
            except Exception:
                logger.exception("frigate.callback_error")

    # ------------------------------------------------------------------
    # Snapshot fetching
    # ------------------------------------------------------------------

    async def fetch_snapshot(self, event_id: str) -> bytes | None:
        """Fetch a snapshot JPEG for the given Frigate event.

        Returns:
            Image bytes or ``None`` if unavailable.
        """
        if not self._http:
            return None
        try:
            resp = await self._http.get(f"/api/events/{event_id}/snapshot.jpg")
            if resp.status_code == 200:
                return resp.content
            logger.warning(
                "frigate.snapshot_failed", event_id=event_id, status=resp.status_code
            )
        except httpx.HTTPError:
            logger.exception("frigate.snapshot_error", event_id=event_id)
        return None

    async def fetch_latest(self, camera: str) -> bytes | None:
        """Fetch the latest snapshot from a camera.

        Returns:
            Image bytes or ``None`` if unavailable.
        """
        if not self._http:
            return None
        try:
            resp = await self._http.get(f"/api/{camera}/latest.jpg")
            if resp.status_code == 200:
                return resp.content
            logger.warning(
                "frigate.latest_failed", camera=camera, status=resp.status_code
            )
        except httpx.HTTPError:
            logger.exception("frigate.latest_error", camera=camera)
        return None
