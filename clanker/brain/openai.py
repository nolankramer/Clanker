"""OpenAI LLM provider — stub implementation.

TODO:
- Implement chat() using openai.AsyncOpenAI
- Implement stream() with streaming support
- Implement tool use via function calling
- Support vision via GPT-4o image messages
- Handle rate limits and retries
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

import structlog

from clanker.brain.base import (
    LLMProvider,
    LLMResponse,
    Message,
    StreamDelta,
    ToolDefinition,
)

if TYPE_CHECKING:
    from clanker.config import OpenAIConfig

logger = structlog.get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI API.

    Currently a stub — chat and stream raise NotImplementedError.
    """

    def __init__(self, config: OpenAIConfig) -> None:
        """Initialize with OpenAI config."""
        self._config = config
        self._model = config.model
        self._max_tokens = config.max_tokens
        # TODO: initialize openai.AsyncOpenAI client

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        return "openai"

    @property
    def supports_vision(self) -> bool:
        """GPT-4o supports vision."""
        return True

    @property
    def supports_tools(self) -> bool:
        """OpenAI supports function calling."""
        return True

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request."""
        raise NotImplementedError("OpenAI provider not yet implemented")

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a chat completion."""
        raise NotImplementedError("OpenAI provider not yet implemented")
        yield  # type: ignore[misc]  # noqa: RUF028 — required for async generator

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        # TODO: close openai client
