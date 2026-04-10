"""Intent fast-path — skip the LLM for simple HA commands.

Routes simple commands (turn on/off, set brightness, get state, etc.)
through HA's built-in intent handler, which resolves in <50ms.  Only
falls back to the LLM brain if HA can't match the intent.

This cuts response time from ~1-3s to <200ms for the ~80% of voice
commands that are simple device control.

HA's built-in intents include:
  HassTurnOn, HassTurnOff, HassToggle, HassLightSet, HassSetPosition,
  HassClimateSetTemperature, HassGetState, HassSetVolume, HassMediaPause,
  HassOpenCover, HassCloseCover, HassStartTimer, HassGetWeather, etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.ha.client import HAClient

logger = structlog.get_logger(__name__)

# HA's built-in conversation agent ID
HA_BUILTIN_AGENT = "conversation.home_assistant"


class FastIntentResult:
    """Result of a fast-intent attempt."""

    __slots__ = ("data", "matched", "response_type", "speech")

    def __init__(
        self,
        *,
        matched: bool,
        speech: str = "",
        response_type: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.matched = matched
        self.speech = speech
        self.response_type = response_type
        self.data = data or {}


class FastIntentMatcher:
    """Attempts to handle voice commands via HA's built-in intent system.

    Usage in the conversation agent::

        matcher = FastIntentMatcher(ha_client)
        result = await matcher.try_match("turn off the kitchen lights")
        if result.matched:
            return result.speech  # done in <50ms
        # else: fall through to LLM brain
    """

    def __init__(
        self,
        ha_client: HAClient,
        *,
        language: str = "en",
        enabled: bool = True,
    ) -> None:
        self._ha = ha_client
        self._language = language
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def try_match(
        self,
        text: str,
        *,
        language: str | None = None,
        device_id: str | None = None,
    ) -> FastIntentResult:
        """Try to handle the text via HA's built-in intent matcher.

        Args:
            text: User's spoken text.
            language: Language code override.
            device_id: Originating device (for area context).

        Returns:
            FastIntentResult with ``matched=True`` if HA handled it,
            ``matched=False`` if the brain should take over.
        """
        if not self._enabled:
            return FastIntentResult(matched=False)

        try:
            result = await self._call_ha_conversation(
                text, language=language or self._language, device_id=device_id
            )
            return self._parse_result(result)
        except Exception:
            logger.debug("fast_intent.error", exc_info=True)
            return FastIntentResult(matched=False)

    async def _call_ha_conversation(
        self,
        text: str,
        *,
        language: str,
        device_id: str | None,
    ) -> dict[str, Any]:
        """Call HA's conversation/process REST API with the built-in agent."""
        payload: dict[str, Any] = {
            "text": text,
            "language": language,
            "agent_id": HA_BUILTIN_AGENT,
        }
        if device_id:
            payload["device_id"] = device_id

        response = await self._ha._http.post(
            "/api/conversation/process",
            json=payload,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    @staticmethod
    def _parse_result(data: dict[str, Any]) -> FastIntentResult:
        """Parse HA's conversation/process response.

        Decision logic:
        - response_type == "action_done" → matched (command executed)
        - response_type == "query_answer" → matched (question answered)
        - response_type == "error" + code == "no_intent_match" → not matched
        - response_type == "error" + other code → matched but failed
        """
        response = data.get("response", {})
        response_type = response.get("response_type", "")
        speech_data = response.get("speech", {}).get("plain", {})
        speech = speech_data.get("speech", "")

        # Success: HA handled it
        if response_type in ("action_done", "query_answer"):
            logger.info(
                "fast_intent.matched",
                response_type=response_type,
                speech=speech[:80],
            )
            return FastIntentResult(
                matched=True,
                speech=speech or "Done.",
                response_type=response_type,
                data=response.get("data", {}),
            )

        # Error: check if it's "no match" (fall through) or a real error
        if response_type == "error":
            error_code = response.get("data", {}).get("code", "")

            if error_code == "no_intent_match":
                logger.debug("fast_intent.no_match", text=speech[:80])
                return FastIntentResult(matched=False)

            # Other errors (entity not found, execution failed) — still "matched"
            # but report the error speech to the user
            logger.info(
                "fast_intent.error_matched",
                code=error_code,
                speech=speech[:80],
            )
            return FastIntentResult(
                matched=True,
                speech=speech or "Sorry, I couldn't do that.",
                response_type=response_type,
                data=response.get("data", {}),
            )

        # Unknown response type — don't match, let brain handle
        return FastIntentResult(matched=False)
