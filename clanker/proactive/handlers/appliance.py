"""Appliance state change handler — laundry-done style announcements.

Monitors configured appliance entities for state transitions (e.g.
washer running→idle, dryer active→standby) and announces completion
to occupied rooms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from clanker.announce.quiet_hours import Priority

if TYPE_CHECKING:
    from clanker.announce.deliver import Announcer

logger = structlog.get_logger(__name__)

# Default appliance state transitions that indicate completion.
# key = entity_id substring, value = (from_states, to_states, message)
_DEFAULT_TRANSITIONS: list[dict[str, Any]] = [
    {
        "pattern": "wash",
        "from": ["washing", "running", "active"],
        "to": ["idle", "off", "standby", "complete"],
        "message": "The washing machine has finished.",
    },
    {
        "pattern": "dryer",
        "from": ["drying", "running", "active"],
        "to": ["idle", "off", "standby", "complete"],
        "message": "The dryer has finished.",
    },
    {
        "pattern": "dishwasher",
        "from": ["washing", "running", "active"],
        "to": ["idle", "off", "standby", "complete"],
        "message": "The dishwasher has finished.",
    },
]


class ApplianceHandler:
    """Announces appliance state transitions (e.g. laundry done).

    Registered on the EventDispatcher for ``state_changed`` events.
    Checks entity IDs against known appliance patterns and triggers
    announcements on matching transitions.
    """

    def __init__(
        self,
        announcer: Announcer,
        *,
        transitions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._announcer = announcer
        self._transitions = transitions or _DEFAULT_TRANSITIONS

    async def handle_event(self, event: dict[str, Any]) -> None:
        """Process a state_changed event for appliance completion."""
        data = event.get("data", {})
        entity_id: str = data.get("entity_id", "")
        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})

        if not old_state or not new_state:
            return

        old_val = (old_state.get("state") or "").lower()
        new_val = (new_state.get("state") or "").lower()

        if old_val == new_val:
            return

        eid_lower = entity_id.lower()

        for transition in self._transitions:
            if transition["pattern"] not in eid_lower:
                continue
            if old_val in transition["from"] and new_val in transition["to"]:
                friendly = new_state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )
                message = transition.get("message", f"{friendly} has finished.")

                logger.info(
                    "appliance.done",
                    entity_id=entity_id,
                    from_state=old_val,
                    to_state=new_val,
                )

                await self._announcer.say(message, Priority.NORMAL)
                return
