"""Home Assistant event subscription and dispatch.

Subscribes to the HA event bus and routes events to registered handlers.
Each event class (frigate, state_changed, doorbell, etc.) gets its own
handler pipeline, and handlers can decide to: ignore, respond deterministically,
or escalate to the brain.

TODO:
- Implement typed event models (FrigateEvent, StateChangedEvent, etc.)
- Implement handler registration and dispatch
- Add event filtering by entity pattern
- Add event deduplication/debouncing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger(__name__)

# Handler callback type: receives typed event data, returns action or None
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventType(str, Enum):
    """Known HA event types that Clanker subscribes to."""

    STATE_CHANGED = "state_changed"
    FRIGATE = "frigate/events"
    CALL_SERVICE = "call_service"
    AUTOMATION_TRIGGERED = "automation_triggered"


@dataclass
class EventDispatcher:
    """Routes HA events to registered handlers.

    Usage::

        dispatcher = EventDispatcher()
        dispatcher.register("state_changed", my_handler)
        # Then wire dispatcher.dispatch as the callback for ha_client.subscribe_events
    """

    _handlers: dict[str, list[EventHandler]] = field(default_factory=dict)

    def register(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type.

        Args:
            event_type: HA event type string.
            handler: Async callback to invoke.
        """
        self._handlers.setdefault(event_type, []).append(handler)
        logger.info("event_dispatcher.registered", event_type=event_type)

    async def dispatch(self, event: dict[str, Any]) -> None:
        """Dispatch an event to all registered handlers.

        Args:
            event: Raw HA event dict from the WebSocket stream.
        """
        event_type = event.get("event_type", "")
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            return

        logger.debug("event_dispatcher.dispatch", event_type=event_type, handler_count=len(handlers))

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("event_dispatcher.handler_error", event_type=event_type)
