"""Tests for the announcement router logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from clanker.announce.occupancy import get_speakers_for_rooms
from clanker.announce.quiet_hours import Priority, is_quiet_hours, should_suppress
from clanker.announce.router import AnnouncementRouter, AudienceRules
from clanker.config import (
    AnnounceConfig,
    OccupancySensor,
    QuietHoursConfig,
    RoomSpeaker,
)


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------


def test_quiet_hours_overnight() -> None:
    """22:00–07:00 range detects quiet hours correctly."""
    config = QuietHoursConfig(enabled=True, start_hour=22, end_hour=7)

    assert is_quiet_hours(config, now=datetime(2025, 1, 1, 23, 0, tzinfo=timezone.utc))
    assert is_quiet_hours(config, now=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
    assert is_quiet_hours(config, now=datetime(2025, 1, 1, 3, 30, tzinfo=timezone.utc))
    assert is_quiet_hours(config, now=datetime(2025, 1, 1, 6, 59, tzinfo=timezone.utc))
    assert not is_quiet_hours(config, now=datetime(2025, 1, 1, 7, 0, tzinfo=timezone.utc))
    assert not is_quiet_hours(config, now=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert not is_quiet_hours(config, now=datetime(2025, 1, 1, 21, 59, tzinfo=timezone.utc))


def test_quiet_hours_disabled() -> None:
    """Disabled quiet hours never suppress."""
    config = QuietHoursConfig(enabled=False, start_hour=22, end_hour=7)
    assert not is_quiet_hours(config, now=datetime(2025, 1, 1, 23, 0, tzinfo=timezone.utc))


def test_should_suppress_critical() -> None:
    """Critical priority is never suppressed."""
    config = QuietHoursConfig(enabled=True, start_hour=22, end_hour=7)
    midnight = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert not should_suppress(config, Priority.CRITICAL, now=midnight)
    assert not should_suppress(config, Priority.HIGH, now=midnight)
    assert should_suppress(config, Priority.NORMAL, now=midnight)
    assert should_suppress(config, Priority.LOW, now=midnight)


# ---------------------------------------------------------------------------
# Speaker mapping
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> AnnounceConfig:
    """Build a test AnnounceConfig."""
    defaults = {
        "room_speakers": [
            RoomSpeaker(room="kitchen", speaker_entity_ids=["media_player.kitchen"]),
            RoomSpeaker(room="office", speaker_entity_ids=["media_player.office"]),
            RoomSpeaker(
                room="living_room",
                speaker_entity_ids=["media_player.living_room_1", "media_player.living_room_2"],
            ),
        ],
        "occupancy_sensors": [
            OccupancySensor(room="kitchen", sensor_entity_id="binary_sensor.kitchen_occ"),
            OccupancySensor(room="office", sensor_entity_id="binary_sensor.office_occ"),
            OccupancySensor(
                room="living_room", sensor_entity_id="binary_sensor.living_room_occ"
            ),
        ],
        "fallback_push_targets": ["notify.mobile_app_phone"],
        "tts_service": "tts.speak",
    }
    defaults.update(overrides)
    return AnnounceConfig(**defaults)


def test_get_speakers_for_rooms() -> None:
    """Maps room names to speaker entities."""
    config = _make_config()
    speakers = get_speakers_for_rooms(["kitchen", "living_room"], config)
    assert "media_player.kitchen" in speakers
    assert "media_player.living_room_1" in speakers
    assert "media_player.living_room_2" in speakers
    assert "media_player.office" not in speakers


def test_get_speakers_unknown_room() -> None:
    """Unknown rooms produce no speakers."""
    config = _make_config()
    speakers = get_speakers_for_rooms(["garage"], config)
    assert speakers == []


# ---------------------------------------------------------------------------
# AnnouncementRouter
# ---------------------------------------------------------------------------


def _mock_ha_client(occupied_rooms: list[str]) -> AsyncMock:
    """Create a mock HA client that returns specific occupancy states."""
    client = AsyncMock()

    async def get_state(entity_id: str):
        for room in occupied_rooms:
            if room in entity_id:
                return {"state": "on"}
        return {"state": "off"}

    client.get_state = AsyncMock(side_effect=get_state)
    return client


@pytest.fixture
def announce_config() -> AnnounceConfig:
    return _make_config()


async def test_route_normal_occupied(announce_config: AnnounceConfig) -> None:
    """Normal priority message goes to occupied rooms' speakers."""
    ha = _mock_ha_client(["kitchen", "office"])
    router = AnnouncementRouter(ha, announce_config)

    targets = await router.route(
        "Laundry is done",
        Priority.NORMAL,
        now=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
    )

    assert not targets.suppressed
    assert "media_player.kitchen" in targets.tts_speakers
    assert "media_player.office" in targets.tts_speakers
    assert "media_player.living_room_1" not in targets.tts_speakers


async def test_route_no_one_home_falls_back_to_push(announce_config: AnnounceConfig) -> None:
    """When no rooms are occupied, fall back to push."""
    ha = _mock_ha_client([])  # nobody home
    router = AnnouncementRouter(ha, announce_config)

    targets = await router.route(
        "Package delivered",
        Priority.NORMAL,
        now=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
    )

    assert targets.tts_speakers == []
    assert "notify.mobile_app_phone" in targets.push_targets


async def test_route_quiet_hours_suppresses_tts(announce_config: AnnounceConfig) -> None:
    """During quiet hours, normal messages fall back to push only."""
    ha = _mock_ha_client(["kitchen"])
    router = AnnouncementRouter(ha, announce_config)

    targets = await router.route(
        "Laundry done",
        Priority.NORMAL,
        now=datetime(2025, 1, 1, 23, 30, tzinfo=timezone.utc),
    )

    assert targets.suppressed
    assert targets.tts_speakers == []
    assert "notify.mobile_app_phone" in targets.push_targets


async def test_route_critical_goes_everywhere(announce_config: AnnounceConfig) -> None:
    """Critical alerts go to ALL speakers and push, regardless of occupancy/quiet."""
    ha = _mock_ha_client([])  # nobody home
    router = AnnouncementRouter(ha, announce_config)

    targets = await router.route(
        "FIRE ALARM",
        Priority.CRITICAL,
        now=datetime(2025, 1, 1, 3, 0, tzinfo=timezone.utc),  # quiet hours
    )

    assert not targets.suppressed
    assert "media_player.kitchen" in targets.tts_speakers
    assert "media_player.office" in targets.tts_speakers
    assert "media_player.living_room_1" in targets.tts_speakers
    assert "notify.mobile_app_phone" in targets.push_targets


async def test_route_audience_room_filter(announce_config: AnnounceConfig) -> None:
    """Audience rules can restrict to specific rooms."""
    ha = _mock_ha_client(["kitchen", "office", "living_room"])
    router = AnnouncementRouter(ha, announce_config)

    targets = await router.route(
        "Office-only message",
        Priority.NORMAL,
        audience=AudienceRules(rooms=["office"]),
        now=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
    )

    assert targets.tts_speakers == ["media_player.office"]
