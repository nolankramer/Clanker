"""Tests for proactive event handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from clanker.proactive.handlers.appliance import ApplianceHandler
from clanker.proactive.handlers.critical import CriticalEventHandler


@pytest.fixture
def announcer() -> AsyncMock:
    return AsyncMock()


# ------------------------------------------------------------------
# CriticalEventHandler
# ------------------------------------------------------------------


def _state_event(
    entity_id: str,
    new_state: str = "on",
    old_state: str = "off",
    friendly_name: str = "",
) -> dict:
    return {
        "data": {
            "entity_id": entity_id,
            "new_state": {
                "state": new_state,
                "attributes": {"friendly_name": friendly_name or entity_id},
            },
            "old_state": {"state": old_state},
        }
    }


async def test_critical_smoke(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.smoke_detector_kitchen")
    )
    announcer.say.assert_awaited_once()
    call_args = announcer.say.call_args
    assert "SMOKE" in call_args[0][0]


async def test_critical_co(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.co_detector_basement")
    )
    announcer.say.assert_awaited_once()
    assert "CARBON MONOXIDE" in announcer.say.call_args[0][0]


async def test_critical_flood(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.water_leak_laundry")
    )
    announcer.say.assert_awaited_once()
    assert "WATER LEAK" in announcer.say.call_args[0][0]


async def test_critical_ignores_non_binary_sensor(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("sensor.smoke_level")
    )
    announcer.say.assert_not_awaited()


async def test_critical_ignores_off_state(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.smoke_detector", new_state="off")
    )
    announcer.say.assert_not_awaited()


async def test_critical_ignores_already_on(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.smoke_detector", old_state="on")
    )
    announcer.say.assert_not_awaited()


async def test_critical_ignores_non_critical_sensor(announcer: AsyncMock) -> None:
    handler = CriticalEventHandler(announcer)
    await handler.handle_event(
        _state_event("binary_sensor.front_door_contact")
    )
    announcer.say.assert_not_awaited()


# ------------------------------------------------------------------
# ApplianceHandler
# ------------------------------------------------------------------


async def test_appliance_washer_done(announcer: AsyncMock) -> None:
    handler = ApplianceHandler(announcer)
    await handler.handle_event(
        _state_event("sensor.washing_machine", new_state="idle", old_state="washing")
    )
    announcer.say.assert_awaited_once()
    assert "washing" in announcer.say.call_args[0][0].lower()


async def test_appliance_dryer_done(announcer: AsyncMock) -> None:
    handler = ApplianceHandler(announcer)
    await handler.handle_event(
        _state_event("sensor.dryer_status", new_state="off", old_state="running")
    )
    announcer.say.assert_awaited_once()


async def test_appliance_ignores_non_appliance(announcer: AsyncMock) -> None:
    handler = ApplianceHandler(announcer)
    await handler.handle_event(
        _state_event("light.kitchen", new_state="off", old_state="on")
    )
    announcer.say.assert_not_awaited()


async def test_appliance_ignores_same_state(announcer: AsyncMock) -> None:
    handler = ApplianceHandler(announcer)
    await handler.handle_event(
        _state_event("sensor.washer", new_state="idle", old_state="idle")
    )
    announcer.say.assert_not_awaited()


async def test_appliance_ignores_wrong_transition(announcer: AsyncMock) -> None:
    handler = ApplianceHandler(announcer)
    # idle → running is not a completion transition
    await handler.handle_event(
        _state_event("sensor.washer", new_state="running", old_state="idle")
    )
    announcer.say.assert_not_awaited()
