"""Unknown person event handler.

Triggered when Frigate detects a person that Double Take cannot identify.
Uses VLM to describe the person and their behavior, then alerts
based on time-of-day and location context.

TODO:
- Subscribe to Frigate person events where face is unrecognized
- Pull snapshot and run VLM description
- Assess threat level based on time, location, behavior
- Route alert via AnnouncementRouter with appropriate priority
- Send push with snapshot and [Call 911, Monitor, Ignore] actions
"""

from __future__ import annotations
