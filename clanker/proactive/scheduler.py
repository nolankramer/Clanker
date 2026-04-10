"""Proactive scheduler — wires APScheduler for cron and event-driven tasks.

Manages scheduled tasks (morning briefing, periodic checks) and
coordinates with event handlers for reactive proactive actions
(laundry done, doorbell, etc.).

TODO:
- Initialize APScheduler with asyncio backend
- Register scheduled jobs from config
- Add job management (pause, resume, list)
- Wire event-triggered handlers
"""

from __future__ import annotations


# TODO: Implement scheduler
# class ProactiveScheduler:
#     async def start(self) -> None: ...
#     async def stop(self) -> None: ...
#     def add_job(self, ...) -> None: ...
