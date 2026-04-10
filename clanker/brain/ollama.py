"""Ollama LLM provider — stub implementation.

Ollama exposes an OpenAI-compatible API, so this provider uses httpx
to talk to the Ollama REST endpoint directly.

TODO:
- Implement chat() via POST /api/chat
- Implement stream() with streaming support
- Add tool use support (Ollama supports it for some models)
- Add vision support for multimodal models (LLaVA, Qwen2-VL)
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
    from clanker.config import OllamaConfig

logger = structlog.get_logger(__name__)


class OllamaProvider(LLMProvider):
    """LLM provider using a local Ollama instance.

    Currently a stub — chat and stream raise NotImplementedError.
    """

    def __init__(self, config: OllamaConfig) -> None:
        """Initialize with Ollama config."""
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model
        self._max_tokens = config.max_tokens
        # TODO: initialize httpx.AsyncClient

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        return "ollama"

    @property
    def supports_vision(self) -> bool:
        """Some Ollama models support vision (LLaVA, Qwen2-VL)."""
        return False  # TODO: detect from model capabilities

    @property
    def supports_tools(self) -> bool:
        """Some Ollama models support tool use."""
        return False  # TODO: detect from model capabilities

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request to Ollama."""
        raise NotImplementedError("Ollama provider not yet implemented")

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a chat completion from Ollama."""
        raise NotImplementedError("Ollama provider not yet implemented")
        yield  # type: ignore[misc]  # noqa: RUF028 — required for async generator

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        # TODO: close httpx client
