"""Quiet hours logic — determines whether TTS announcements should be suppressed.

Non-critical announcements are suppressed during quiet hours. Critical
alerts (fire, break-in, etc.) always go through.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clanker.config import QuietHoursConfig


class Priority(IntEnum):
    """Announcement priority levels.

    LOW and NORMAL are suppressed during quiet hours.
    HIGH and CRITICAL always go through.
    """

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


def is_quiet_hours(
    config: QuietHoursConfig,
    *,
    now: datetime | None = None,
) -> bool:
    """Check whether the current time falls within quiet hours.

    Handles overnight ranges (e.g. 22:00-07:00) correctly.

    Args:
        config: Quiet hours configuration.
        now: Override for the current time (for testing).

    Returns:
        True if it's currently quiet hours.
    """
    if not config.enabled:
        return False

    if now is None:
        now = datetime.now(tz=UTC)

    hour = now.hour

    if config.start_hour > config.end_hour:
        # Overnight range: e.g. 22-7 means 22,23,0,1,2,3,4,5,6
        return hour >= config.start_hour or hour < config.end_hour
    # Same-day range: e.g. 13-15
    return config.start_hour <= hour < config.end_hour


def should_suppress(
    config: QuietHoursConfig,
    priority: Priority,
    *,
    now: datetime | None = None,
) -> bool:
    """Determine whether an announcement should be suppressed.

    Args:
        config: Quiet hours configuration.
        priority: Announcement priority.
        now: Override for current time (for testing).

    Returns:
        True if the announcement should be suppressed (quiet + not critical).
    """
    if priority >= Priority.HIGH:
        return False
    return is_quiet_hours(config, now=now)
