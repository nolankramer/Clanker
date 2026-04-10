"""Clanker conversation entity for Home Assistant.

This is a thin proxy — it forwards voice/text input to Clanker's
HTTP API and returns the response.  All intelligence lives in Clanker,
not in this component.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.components.conversation import (
    AbstractConversationAgent,
    ConversationInput,
    ConversationResult,
)
from homeassistant.helpers.intent import IntentResponse

from . import DEFAULT_URL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: Any,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the Clanker conversation platform."""
    url = hass.data.get(DOMAIN, {}).get("url", DEFAULT_URL)
    async_add_entities([ClankerConversationAgent(hass, url)])


class ClankerConversationAgent(AbstractConversationAgent):
    """Conversation agent that proxies to Clanker's HTTP API."""

    def __init__(self, hass: HomeAssistant, url: str) -> None:
        """Initialize the agent."""
        self.hass = hass
        self._url = url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    @property
    def attribution(self) -> dict[str, str]:
        """Return attribution info."""
        return {"name": "Clanker", "url": "https://github.com/nolankramer/clanker"}

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return ["en"]

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Process a conversation turn by calling Clanker's API."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        payload = {
            "text": user_input.text,
            "conversation_id": user_input.conversation_id,
            "language": user_input.language,
            "device_id": user_input.device_id,
        }

        try:
            async with self._session.post(
                f"{self._url}/api/conversation/process",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error("Clanker API returned %s", resp.status)
                    return self._error_result(
                        "Sorry, I couldn't reach my brain right now.",
                        user_input.conversation_id,
                    )
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.exception("Failed to reach Clanker at %s", self._url)
            return self._error_result(
                "Sorry, I'm having trouble connecting. Please try again.",
                user_input.conversation_id,
            )

        speech = data.get("speech", "I'm not sure how to respond.")
        conversation_id = data.get("conversation_id", user_input.conversation_id)

        response = IntentResponse(language=user_input.language)
        response.async_set_speech(speech)

        return ConversationResult(
            response=response,
            conversation_id=conversation_id,
        )

    @staticmethod
    def _error_result(message: str, conversation_id: str | None) -> ConversationResult:
        """Build an error ConversationResult."""
        response = IntentResponse(language="en")
        response.async_set_error(
            IntentResponse.ERROR_UNKNOWN,
            message,
        )
        return ConversationResult(
            response=response,
            conversation_id=conversation_id,
        )
