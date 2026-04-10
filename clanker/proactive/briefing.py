"""Morning briefing — generates and delivers a daily summary.

Triggered by first motion in the office after the configured hour.
Gathers calendar, weather, email summary, and overnight events,
then uses the brain to generate a concise briefing delivered via TTS.

TODO:
- Implement motion trigger detection (subscribe to office motion sensor)
- Gather data via tools (calendar, weather, email, overnight events)
- Generate briefing via brain
- Deliver via TTS to office speaker
- Set "briefing delivered today" flag to prevent repeats
"""

from __future__ import annotations


# TODO: Implement morning briefing
# class MorningBriefing:
#     async def check_trigger(self, event: dict) -> None: ...
#     async def generate(self) -> str: ...
#     async def deliver(self, text: str) -> None: ...
