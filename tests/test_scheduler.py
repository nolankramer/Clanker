"""Tests for the proactive scheduler."""

from __future__ import annotations

from clanker.proactive.scheduler import ProactiveScheduler


async def test_start_stop() -> None:
    scheduler = ProactiveScheduler()
    await scheduler.start()
    await scheduler.stop()


async def test_add_and_list_jobs() -> None:
    scheduler = ProactiveScheduler()
    await scheduler.start()

    async def dummy_job() -> None:
        pass

    scheduler.add_cron_job("morning", dummy_job, hour=7, minute=0)
    scheduler.add_interval_job("check", dummy_job, minutes=30)

    jobs = scheduler.list_jobs()
    assert "morning" in jobs
    assert "check" in jobs
    assert len(jobs) == 2

    await scheduler.stop()


async def test_remove_job() -> None:
    scheduler = ProactiveScheduler()
    await scheduler.start()

    async def dummy_job() -> None:
        pass

    scheduler.add_cron_job("temp", dummy_job, hour=12)
    assert "temp" in scheduler.list_jobs()

    scheduler.remove_job("temp")
    assert "temp" not in scheduler.list_jobs()

    await scheduler.stop()


async def test_remove_nonexistent_job() -> None:
    scheduler = ProactiveScheduler()
    await scheduler.start()
    scheduler.remove_job("nope")  # should not raise
    await scheduler.stop()
