"""Mobile push notifications via HA companion app.

Generates actionable notification payloads with callback buttons.
Callbacks return as HA events which Clanker handles to complete
the interaction loop.

TODO:
- Build notification payloads with action buttons
- Subscribe to mobile_app callback events
- Route callbacks to appropriate handlers
- Support notification categories (alert, info, question)
- Support image attachments (camera snapshots)
"""

from __future__ import annotations
