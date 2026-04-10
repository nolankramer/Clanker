"""Appliance state change handler (laundry-done style announcements).

Monitors appliance entities for state transitions (e.g. washer
running → idle) and announces completion to occupied rooms.

TODO:
- Subscribe to state_changed events for configured appliances
- Detect relevant state transitions (power drop, state change)
- Look up appliance in StructuredMemory for announcement template
- Route announcement via AnnouncementRouter
- Log delivery to memory
"""

from __future__ import annotations
