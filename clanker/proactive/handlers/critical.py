"""Critical event handler — smoke, CO, glass break, flood.

These events skip the brain entirely for the initial response
(deterministic, fast, reliable).  Alerts go to ALL speakers and
push targets immediately.  The brain is called afterward only for
supplementary context (camera summaries, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from clanker.announce.quiet_hours import Priority

if TYPE_CHECKING:
    from clanker.announce.deliver import Announcer

logger = structlog.get_logger(__name__)

# Entity ID substrings that indicate a critical safety sensor
_CRITICAL_PATTERNS = {
    "smoke": "SMOKE DETECTED",
    "co_": "CARBON MONOXIDE DETECTED",
    "carbon_monoxide": "CARBON MONOXIDE DETECTED",
    "gas": "GAS LEAK DETECTED",
    "flood": "WATER LEAK DETECTED",
    "water_leak": "WATER LEAK DETECTED",
    "moisture": "WATER LEAK DETECTED",
    "glass_break": "GLASS BREAK DETECTED",
}


class CriticalEventHandler:
    """Handles life-safety sensor triggers with immediate alerts.

    No LLM call for the initial response — speed and reliability matter
    most.  The alert is fully deterministic.
    """

    def __init__(self, announcer: Announcer) -> None:
        self._announcer = announcer

    async def handle_event(self, event: dict[str, Any]) -> None:
        """Process a state_changed event for critical sensors.

        Should be registered on the EventDispatcher for ``state_changed``.
        """
        data = event.get("data", {})
        entity_id: str = data.get("entity_id", "")
        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})

        if not entity_id.startswith("binary_sensor."):
            return

        # Only trigger on off→on transitions
        if new_state.get("state") != "on":
            return
        if old_state and old_state.get("state") == "on":
            return

        # Match against critical patterns
        alert_message = self._match_critical(entity_id)
        if not alert_message:
            return

        friendly = new_state.get("attributes", {}).get("friendly_name", entity_id)
        full_message = f"ALERT: {alert_message}! Sensor: {friendly}. Check immediately."

        logger.critical(
            "critical.alert",
            entity_id=entity_id,
            alert=alert_message,
        )

        await self._announcer.say(
            full_message,
            Priority.CRITICAL,
            title="CRITICAL ALERT",
            push_data={
                "actions": [
                    {"action": "CALL_911", "title": "Call 911"},
                    {"action": "SAFE", "title": "I'm safe"},
                    {"action": "FALSE_ALARM", "title": "False alarm"},
                ],
                "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}},
            },
        )

    @staticmethod
    def _match_critical(entity_id: str) -> str | None:
        """Check if an entity ID matches a critical sensor pattern."""
        eid_lower = entity_id.lower()
        for pattern, message in _CRITICAL_PATTERNS.items():
            if pattern in eid_lower:
                return message
        return None
