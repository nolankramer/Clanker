"""Occupancy detection — queries HA binary sensors to determine who's where.

Each room maps to one or more occupancy sensors via config. This module
provides a simple interface to check which rooms are currently occupied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from clanker.config import AnnounceConfig
    from clanker.ha.client import HAClient

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RoomOccupancy:
    """Occupancy state for a single room."""

    room: str
    occupied: bool
    sensor_entity_id: str


async def get_occupied_rooms(
    ha_client: HAClient,
    config: AnnounceConfig,
) -> list[RoomOccupancy]:
    """Query HA sensors and return occupancy state for all configured rooms.

    Args:
        ha_client: Connected HA client.
        config: Announce config with occupancy sensor mappings.

    Returns:
        List of RoomOccupancy for every configured room.
    """
    results: list[RoomOccupancy] = []

    for sensor in config.occupancy_sensors:
        try:
            state = await ha_client.get_state(sensor.sensor_entity_id)
            occupied = state.get("state") == "on"
        except Exception:
            logger.warning(
                "occupancy.sensor_error",
                room=sensor.room,
                sensor=sensor.sensor_entity_id,
                exc_info=True,
            )
            occupied = False

        results.append(
            RoomOccupancy(
                room=sensor.room,
                occupied=occupied,
                sensor_entity_id=sensor.sensor_entity_id,
            )
        )

    return results


def get_speakers_for_rooms(
    occupied_rooms: list[str],
    config: AnnounceConfig,
) -> list[str]:
    """Map occupied room names to their speaker entity IDs.

    Args:
        occupied_rooms: List of room names that are occupied.
        config: Announce config with room-to-speaker mappings.

    Returns:
        Flat list of media_player entity IDs for the occupied rooms.
    """
    speakers: list[str] = []
    room_map = {rs.room: rs.speaker_entity_ids for rs in config.room_speakers}

    for room in occupied_rooms:
        if room in room_map:
            speakers.extend(room_map[room])

    return speakers
