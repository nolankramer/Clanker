"""Doorbell event handler.

Flow: Frigate detects person → Double Take identifies face →
Clanker pulls snapshot → VLM describes scene → checks memory →
announces to occupied rooms → sends push with actions.

TODO:
- Subscribe to doorbell/Frigate person events
- Pull snapshot and run VLM description
- Check face recognition results against memory
- Compose natural announcement with context
- Route through AnnouncementRouter
- Send actionable push notification [Text, Intercom, Ignore]
"""

from __future__ import annotations
