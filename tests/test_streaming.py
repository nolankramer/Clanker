"""Tests for sentence-buffered streaming TTS."""

from __future__ import annotations

from unittest.mock import AsyncMock

from clanker.brain.base import StreamDelta
from clanker.conversation.streaming import StreamingTTS, split_sentences

# ------------------------------------------------------------------
# Sentence splitting
# ------------------------------------------------------------------


def test_split_simple_sentences() -> None:
    sentences, remainder = split_sentences(
        "Hello world. How are you? I am fine."
    )
    assert sentences == ["Hello world.", "How are you?"]
    assert remainder == "I am fine."


def test_split_single_sentence_no_boundary() -> None:
    sentences, remainder = split_sentences("Hello world this is a test")
    assert sentences == []
    assert remainder == "Hello world this is a test"


def test_split_short_sentence_held() -> None:
    """Very short sentences are held and merged."""
    sentences, remainder = split_sentences("OK. Sure. Let me check that for you.")
    # "OK." and "Sure." are too short (<12 chars), so they get merged
    assert len(sentences) <= 2
    # Everything should still be accounted for
    all_text = " ".join(sentences) + " " + remainder if remainder else " ".join(sentences)
    assert "OK" in all_text
    assert "check" in all_text


def test_split_empty_string() -> None:
    sentences, remainder = split_sentences("")
    assert sentences == []
    assert remainder == ""


def test_split_exclamation() -> None:
    sentences, _remainder = split_sentences(
        "Fire detected! Evacuate now! Calling emergency services."
    )
    assert len(sentences) >= 2
    assert any("Fire" in s for s in sentences)


def test_split_preserves_all_text() -> None:
    """All input text should appear in sentences + remainder."""
    text = "First sentence here. Second one too. And a third."
    sentences, remainder = split_sentences(text)
    reconstructed = " ".join(sentences)
    if remainder:
        reconstructed += " " + remainder
    # All words should be present
    for word in ["First", "Second", "third"]:
        assert word in reconstructed


# ------------------------------------------------------------------
# StreamingTTS
# ------------------------------------------------------------------


async def test_stream_and_speak_basic() -> None:
    """Sentences should be sent to TTS as they complete."""
    services = AsyncMock()
    services.tts_speak = AsyncMock()

    streamer = StreamingTTS(
        services, speakers=["media_player.kitchen"]
    )

    # Mock brain that streams word by word
    brain = AsyncMock()

    async def fake_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        words = "The lights are now off. Have a good evening."
        for word in words.split():
            yield StreamDelta(content=word + " ")
        yield StreamDelta(finish_reason="stop")

    brain.stream = fake_stream

    result = await streamer.stream_and_speak(
        brain, [], system="test"
    )

    assert "lights" in result
    assert "evening" in result
    # TTS should have been called (at least once for the full text)
    assert services.tts_speak.await_count >= 1


async def test_stream_bails_on_tool_call() -> None:
    """If a tool call appears in the stream, return empty for chat() fallback."""
    services = AsyncMock()
    streamer = StreamingTTS(services, speakers=["media_player.kitchen"])

    brain = AsyncMock()
    from clanker.brain.base import ToolCall

    async def fake_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamDelta(content="Let me ")
        yield StreamDelta(
            tool_call=ToolCall(id="c1", name="ha_call_service", arguments={})
        )

    brain.stream = fake_stream

    result = await streamer.stream_and_speak(brain, [])
    assert result == ""  # empty = caller should use chat() instead


async def test_stream_no_speakers() -> None:
    """With no speakers, streaming still works (returns text)."""
    services = AsyncMock()
    streamer = StreamingTTS(services, speakers=[])

    brain = AsyncMock()

    async def fake_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamDelta(content="Hello there.")
        yield StreamDelta(finish_reason="stop")

    brain.stream = fake_stream

    result = await streamer.stream_and_speak(brain, [])
    assert "Hello" in result
    services.tts_speak.assert_not_awaited()


async def test_stream_handles_error_gracefully() -> None:
    """Errors during streaming should not crash."""
    services = AsyncMock()
    streamer = StreamingTTS(
        services, speakers=["media_player.kitchen"]
    )

    brain = AsyncMock()

    async def failing_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamDelta(content="Start of response. ")
        raise RuntimeError("Connection lost")

    brain.stream = failing_stream

    result = await streamer.stream_and_speak(brain, [])
    # Should return whatever was captured before the error
    assert "Start" in result
