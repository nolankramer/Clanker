"""Tests for the HA intent fast-path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from clanker.conversation.fast_intent import FastIntentMatcher


def _make_ha_client(response_data: dict) -> AsyncMock:
    """Create a mock HA client with a pre-configured HTTP response."""
    client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = response_data
    client._http = AsyncMock()
    client._http.post = AsyncMock(return_value=mock_resp)
    return client


def _ha_response(
    response_type: str,
    speech: str = "",
    error_code: str = "",
) -> dict:
    """Build a mock HA conversation/process response."""
    data: dict = {}
    if error_code:
        data["code"] = error_code
    return {
        "response": {
            "response_type": response_type,
            "speech": {"plain": {"speech": speech}},
            "data": data,
        },
        "conversation_id": "test-123",
    }


# ------------------------------------------------------------------
# Matching
# ------------------------------------------------------------------


async def test_action_done_matches() -> None:
    """action_done response = intent matched and executed."""
    ha = _make_ha_client(
        _ha_response("action_done", "Turned off the kitchen lights")
    )
    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("turn off the kitchen lights")

    assert result.matched is True
    assert "kitchen" in result.speech.lower()
    assert result.response_type == "action_done"


async def test_query_answer_matches() -> None:
    """query_answer response = question answered."""
    ha = _make_ha_client(
        _ha_response("query_answer", "It's 72 degrees")
    )
    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("what's the temperature?")

    assert result.matched is True
    assert "72" in result.speech


async def test_no_intent_match_falls_through() -> None:
    """no_intent_match error = not handled, brain should take over."""
    ha = _make_ha_client(
        _ha_response("error", "Sorry, I didn't understand", "no_intent_match")
    )
    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("tell me a joke about smart homes")

    assert result.matched is False


async def test_entity_not_found_still_matches() -> None:
    """no_valid_targets = intent matched but entity missing — still 'matched'."""
    ha = _make_ha_client(
        _ha_response("error", "I couldn't find that entity", "no_valid_targets")
    )
    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("turn on the nonexistent light")

    assert result.matched is True
    assert "couldn't find" in result.speech.lower()


async def test_disabled_never_matches() -> None:
    """Disabled matcher always returns not matched."""
    ha = _make_ha_client(
        _ha_response("action_done", "Done")
    )
    matcher = FastIntentMatcher(ha, enabled=False)
    result = await matcher.try_match("turn off the lights")

    assert result.matched is False
    ha._http.post.assert_not_awaited()


async def test_network_error_falls_through() -> None:
    """Network errors should fall through gracefully."""
    ha = AsyncMock()
    ha._http = AsyncMock()
    ha._http.post = AsyncMock(side_effect=ConnectionError("HA down"))

    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("turn off the lights")

    assert result.matched is False


async def test_passes_agent_id() -> None:
    """Should use HA's built-in agent, not Clanker."""
    ha = _make_ha_client(
        _ha_response("action_done", "Done")
    )
    matcher = FastIntentMatcher(ha)
    await matcher.try_match("turn off the lights")

    call_args = ha._http.post.call_args[1]["json"]
    assert call_args["agent_id"] == "conversation.home_assistant"


async def test_passes_device_id() -> None:
    """Device ID should be forwarded for area context."""
    ha = _make_ha_client(
        _ha_response("action_done", "Done")
    )
    matcher = FastIntentMatcher(ha)
    await matcher.try_match(
        "turn off the lights", device_id="abc123"
    )

    call_args = ha._http.post.call_args[1]["json"]
    assert call_args["device_id"] == "abc123"


async def test_empty_speech_defaults_to_done() -> None:
    """If HA returns empty speech, default to 'Done.'."""
    ha = _make_ha_client(
        _ha_response("action_done", "")
    )
    matcher = FastIntentMatcher(ha)
    result = await matcher.try_match("turn off the lights")

    assert result.matched is True
    assert result.speech == "Done."
