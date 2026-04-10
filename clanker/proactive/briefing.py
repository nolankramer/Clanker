"""Morning briefing — generates and delivers a daily summary via TTS.

Triggered by first motion in the configured room after the configured
hour.  Gathers state data from HA, generates a concise briefing via
the brain, and delivers it to the configured speaker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from clanker.brain.base import Message, Role

if TYPE_CHECKING:
    from clanker.brain.base import LLMProvider
    from clanker.config import ProactiveConfig
    from clanker.ha.client import HAClient
    from clanker.ha.services import HAServices

logger = structlog.get_logger(__name__)

_BRIEFING_PROMPT = """\
Generate a concise morning briefing (under 30 seconds when spoken).
Include:
- A friendly greeting with the day and date
- Weather summary (if available)
- Any notable overnight events from the smart home
- A brief motivational or fun closing line

Keep it natural and conversational — this will be spoken aloud.
"""


class MorningBriefing:
    """Generates and delivers a morning briefing via TTS.

    Listens for motion events on a configured sensor. On first
    trigger after the briefing hour, generates and speaks the briefing.
    A flag prevents repeat delivery within the same day.
    """

    def __init__(
        self,
        brain: LLMProvider,
        ha_client: HAClient,
        ha_services: HAServices,
        config: ProactiveConfig,
    ) -> None:
        self._brain = brain
        self._ha = ha_client
        self._services = ha_services
        self._config = config
        self._delivered_date: str | None = None

    async def check_trigger(self, event: dict[str, Any]) -> None:
        """Check a state_changed event to see if briefing should fire.

        Called by the event dispatcher for motion sensor events.
        """
        if not self._config.briefing_motion_sensor:
            return

        entity_id = event.get("data", {}).get("entity_id", "")
        new_state = event.get("data", {}).get("new_state", {})

        if entity_id != self._config.briefing_motion_sensor:
            return
        if new_state.get("state") != "on":
            return

        now = datetime.now(tz=UTC)
        today = now.strftime("%Y-%m-%d")

        # Already delivered today?
        if self._delivered_date == today:
            return

        # Too early?
        if now.hour < self._config.morning_briefing_after_hour:
            return

        logger.info("briefing.triggered", sensor=entity_id)
        await self.deliver()

    async def deliver(self) -> None:
        """Generate and speak the morning briefing."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if self._delivered_date == today:
            return

        # Gather context from HA
        context = await self._gather_context()

        # Generate briefing
        messages = [
            Message(role=Role.USER, content=f"{_BRIEFING_PROMPT}\n\nContext:\n{context}"),
        ]
        response = await self._brain.chat(messages, max_tokens=300)
        briefing_text = response.content

        logger.info("briefing.generated", length=len(briefing_text))

        # Speak via TTS
        if self._config.briefing_speaker:
            await self._services.tts_speak(self._config.briefing_speaker, briefing_text)
            logger.info("briefing.delivered", speaker=self._config.briefing_speaker)

        self._delivered_date = today

    async def _gather_context(self) -> str:
        """Gather home state for the briefing."""
        lines: list[str] = []
        now = datetime.now(tz=UTC)
        lines.append(f"Date: {now.strftime('%A, %B %d, %Y')}")
        lines.append(f"Time: {now.strftime('%I:%M %p')}")

        # Try to get weather
        try:
            weather = await self._ha.get_state("weather.home")
            state = weather.get("state", "unknown")
            attrs = weather.get("attributes", {})
            temp = attrs.get("temperature", "?")
            unit = attrs.get("temperature_unit", "°F")
            lines.append(f"Weather: {state}, {temp}{unit}")
            forecast = attrs.get("forecast", [])
            if forecast:
                high = forecast[0].get("temperature", "?")
                low = forecast[0].get("templow", "?")
                lines.append(f"Today: High {high}{unit}, Low {low}{unit}")
        except Exception:
            lines.append("Weather: unavailable")

        # Open doors/windows
        try:
            states = await self._ha.get_states()
            open_contacts = [
                s.get("attributes", {}).get("friendly_name", s["entity_id"])
                for s in states
                if (s.get("entity_id", "").startswith("binary_sensor.")
                and "door" in s.get("entity_id", ""))
                or ("window" in s.get("entity_id", "")
                and s.get("state") == "on")
            ]
            if open_contacts:
                lines.append(f"Open: {', '.join(open_contacts[:5])}")
        except Exception:
            pass

        return "\n".join(lines)
