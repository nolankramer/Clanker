"""Tests for the Frigate event handler."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clanker.vision.frigate import FrigateEvent, FrigateEventHandler


def _make_ha_event(
    *,
    event_type: str = "new",
    event_id: str = "evt_001",
    camera: str = "front_door",
    label: str = "person",
    score: float = 0.9,
    top_score: float = 0.95,
    zones: list[str] | None = None,
) -> dict[str, Any]:
    """Build a mock HA event dict matching Frigate's format."""
    return {
        "data": {
            "type": event_type,
            "before": {},
            "after": {
                "id": event_id,
                "camera": camera,
                "label": label,
                "sub_label": None,
                "score": score,
                "top_score": top_score,
                "zones": zones or ["front_yard"],
                "current_zones": zones or ["front_yard"],
                "entered_zones": zones or ["front_yard"],
                "has_snapshot": True,
                "has_clip": False,
                "start_time": time.time(),
                "end_time": None,
                "thumbnail": None,
            },
        }
    }


@pytest.fixture
def ha_client() -> AsyncMock:
    client = AsyncMock()
    client.subscribe_events = AsyncMock(return_value=1)
    return client


@pytest.fixture
def handler(ha_client: AsyncMock) -> FrigateEventHandler:
    return FrigateEventHandler(
        ha_client=ha_client,
        frigate_url="http://frigate:5000",
        cooldown_seconds=5.0,
        min_score=0.5,
    )


# ------------------------------------------------------------------
# Event parsing
# ------------------------------------------------------------------


async def test_dispatches_valid_event(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event())

    callback.assert_awaited_once()
    event: FrigateEvent = callback.call_args[0][0]
    assert event.camera == "front_door"
    assert event.label == "person"
    assert event.top_score == 0.95


async def test_filters_low_score(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event(top_score=0.3))

    callback.assert_not_awaited()


async def test_deduplication_cooldown(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event(event_id="e1"))
    await handler._on_ha_event(_make_ha_event(event_id="e2"))

    # Second event with same camera+label should be suppressed by cooldown
    assert callback.await_count == 1


async def test_end_events_bypass_cooldown(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event(event_id="e1"))
    await handler._on_ha_event(_make_ha_event(event_id="e1", event_type="end"))

    assert callback.await_count == 2


async def test_different_labels_not_deduped(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event(label="person"))
    await handler._on_ha_event(_make_ha_event(label="car"))

    assert callback.await_count == 2


async def test_camera_filter(ha_client: AsyncMock) -> None:
    handler = FrigateEventHandler(
        ha_client=ha_client,
        frigate_url="http://frigate:5000",
        cameras=["front_door"],
    )
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event(_make_ha_event(camera="back_yard"))
    callback.assert_not_awaited()

    await handler._on_ha_event(_make_ha_event(camera="front_door"))
    callback.assert_awaited_once()


async def test_ignores_empty_after(handler: FrigateEventHandler) -> None:
    callback = AsyncMock()
    handler.on_event(callback)

    await handler._on_ha_event({"data": {"type": "new", "after": {}}})
    # Empty after dict is still processed (all fields default)
    # but the id will be empty — the callback still fires if score >= min
    # Actually, top_score defaults to 0.0 which is below min_score of 0.5
    callback.assert_not_awaited()


async def test_callback_error_doesnt_crash(handler: FrigateEventHandler) -> None:
    bad_callback = AsyncMock(side_effect=RuntimeError("boom"))
    good_callback = AsyncMock()
    handler.on_event(bad_callback)
    handler.on_event(good_callback)

    await handler._on_ha_event(_make_ha_event())

    bad_callback.assert_awaited_once()
    good_callback.assert_awaited_once()


# ------------------------------------------------------------------
# Snapshot fetching
# ------------------------------------------------------------------


async def test_fetch_snapshot(handler: FrigateEventHandler) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"\xff\xd8fake-jpeg"

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    handler._http = mock_http

    result = await handler.fetch_snapshot("evt_001")
    assert result == b"\xff\xd8fake-jpeg"


async def test_fetch_snapshot_not_found(handler: FrigateEventHandler) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    handler._http = mock_http

    result = await handler.fetch_snapshot("missing")
    assert result is None


async def test_fetch_snapshot_no_client(handler: FrigateEventHandler) -> None:
    handler._http = None
    result = await handler.fetch_snapshot("evt_001")
    assert result is None


async def test_fetch_latest(handler: FrigateEventHandler) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"\xff\xd8latest"

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    handler._http = mock_http

    result = await handler.fetch_latest("front_door")
    assert result == b"\xff\xd8latest"
