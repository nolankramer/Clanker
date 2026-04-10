"""Sentence-buffered streaming for low-latency TTS.

Accumulates streamed LLM tokens into sentence-sized chunks and fires
TTS as soon as each sentence is complete.  This means the speaker starts
talking ~0.3s after the LLM begins generating instead of waiting for the
full response.

Usage::

    streamer = StreamingTTS(ha_services, speakers=["media_player.kitchen"])
    full_text = await streamer.stream_and_speak(brain, messages, system=prompt)
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.brain.base import LLMProvider, Message, ToolDefinition
    from clanker.ha.services import HAServices

logger = structlog.get_logger(__name__)

# Sentence boundary pattern — split on . ! ? followed by space or end
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?])$")

# Minimum characters before we consider flushing a sentence.
# Avoids sending tiny fragments like "OK." as separate TTS calls.
_MIN_SENTENCE_LEN = 12


def split_sentences(text: str) -> tuple[list[str], str]:
    """Split text into complete sentences and a remaining buffer.

    Returns:
        Tuple of (complete_sentences, remaining_buffer).
    """
    parts = _SENTENCE_RE.split(text)
    if not parts:
        return [], text

    complete: list[str] = []
    # All parts except the last are complete sentences
    for part in parts[:-1]:
        stripped = part.strip()
        if stripped:
            complete.append(stripped)

    # Last part is the remaining buffer (may be incomplete)
    remainder = parts[-1].strip() if parts[-1] else ""

    # Only return sentences that are long enough
    ready: list[str] = []
    held = ""
    for s in complete:
        held = f"{held} {s}".strip() if held else s
        if len(held) >= _MIN_SENTENCE_LEN:
            ready.append(held)
            held = ""

    # Put short held text back into remainder
    if held:
        remainder = f"{held} {remainder}".strip() if remainder else held

    return ready, remainder


class StreamingTTS:
    """Streams LLM output to TTS sentence-by-sentence.

    Instead of waiting for the full LLM response, this sends each
    complete sentence to TTS as soon as it's available. The first
    sentence starts playing ~0.3-0.5s after generation begins instead
    of 1-3s for the full response.
    """

    def __init__(
        self,
        ha_services: HAServices,
        *,
        speakers: list[str] | None = None,
        tts_service: str = "tts.speak",
    ) -> None:
        self._services = ha_services
        self._speakers = speakers or []
        self._tts_service = tts_service

    async def stream_and_speak(
        self,
        brain: LLMProvider,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> str:
        """Stream LLM response and speak sentences as they complete.

        Args:
            brain: LLM provider (must support streaming).
            messages: Conversation messages.
            system: System prompt.
            tools: Tool definitions (if tools are returned, streaming
                stops and the full response is returned for tool handling).

        Returns:
            The complete response text.
        """
        buffer = ""
        full_text = ""
        sentences_spoken = 0
        tts_tasks: list[asyncio.Task[Any]] = []

        try:
            async for delta in brain.stream(
                messages, system=system, tools=tools
            ):
                # If a tool call appears, bail out — caller handles tools
                if delta.tool_call:
                    logger.debug("streaming.tool_call_detected")
                    # Return what we have — agent will handle via chat()
                    return ""

                if delta.content:
                    buffer += delta.content
                    full_text += delta.content

                    # Try to extract complete sentences
                    sentences, buffer = split_sentences(buffer)
                    for sentence in sentences:
                        sentences_spoken += 1
                        logger.debug(
                            "streaming.sentence",
                            n=sentences_spoken,
                            text=sentence[:60],
                        )
                        # Fire TTS without waiting — speaks overlap with generation
                        task = asyncio.create_task(
                            self._speak(sentence)
                        )
                        tts_tasks.append(task)

                if delta.finish_reason:
                    break

        except Exception:
            logger.exception("streaming.error")
            # Fall through to flush buffer

        # Flush remaining buffer
        if buffer.strip():
            remaining = buffer.strip()
            if remaining:
                task = asyncio.create_task(self._speak(remaining))
                tts_tasks.append(task)

        # Wait for all TTS calls to complete
        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        logger.info(
            "streaming.complete",
            total_len=len(full_text),
            sentences=sentences_spoken + (1 if buffer.strip() else 0),
        )

        return full_text.strip()

    async def _speak(self, text: str) -> None:
        """Send a sentence to all configured speakers."""
        for speaker in self._speakers:
            try:
                await self._services.tts_speak(
                    speaker, text, service=self._tts_service
                )
            except Exception:
                logger.exception(
                    "streaming.tts_error", speaker=speaker
                )
