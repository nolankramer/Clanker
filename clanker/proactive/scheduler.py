"""Proactive scheduler — APScheduler-based task runner.

Manages scheduled tasks (morning briefing, periodic checks) and
coordinates with event-triggered handlers.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = structlog.get_logger(__name__)

JobFunc = Callable[..., Coroutine[Any, Any, None]]


class ProactiveScheduler:
    """Async scheduler for proactive automations.

    Wraps APScheduler's ``AsyncIOScheduler`` with a simple API for
    adding cron and interval jobs.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, str] = {}  # name → job_id

    async def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        logger.info("scheduler.started", job_count=len(self._jobs))

    async def stop(self) -> None:
        """Shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")

    def add_cron_job(
        self,
        name: str,
        func: JobFunc,
        *,
        hour: int | str = "*",
        minute: int | str = 0,
        day_of_week: str = "*",
        **kwargs: Any,
    ) -> None:
        """Add a cron-triggered job.

        Args:
            name: Human-readable job name.
            func: Async function to execute.
            hour: Hour (0-23 or '*').
            minute: Minute (0-59 or '*').
            day_of_week: Day filter ('mon-fri', '*', etc.).
            **kwargs: Extra args passed to the function.
        """
        job = self._scheduler.add_job(
            func,
            "cron",
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
            kwargs=kwargs,
            name=name,
        )
        self._jobs[name] = job.id
        logger.info("scheduler.job_added", name=name, type="cron", hour=hour, minute=minute)

    def add_interval_job(
        self,
        name: str,
        func: JobFunc,
        *,
        minutes: int = 60,
        **kwargs: Any,
    ) -> None:
        """Add an interval-triggered job.

        Args:
            name: Human-readable job name.
            func: Async function to execute.
            minutes: Interval in minutes.
            **kwargs: Extra args passed to the function.
        """
        job = self._scheduler.add_job(
            func,
            "interval",
            minutes=minutes,
            kwargs=kwargs,
            name=name,
        )
        self._jobs[name] = job.id
        logger.info("scheduler.job_added", name=name, type="interval", minutes=minutes)

    def remove_job(self, name: str) -> None:
        """Remove a job by name."""
        job_id = self._jobs.pop(name, None)
        if job_id:
            self._scheduler.remove_job(job_id)
            logger.info("scheduler.job_removed", name=name)

    def list_jobs(self) -> list[str]:
        """Return names of all registered jobs."""
        return list(self._jobs.keys())
