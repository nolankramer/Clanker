"""LLMProvider abstract base class.

Every LLM backend (Anthropic, OpenAI, Ollama, generic OpenAI-compatible)
implements this interface so the rest of Clanker can call the brain without
knowing which model is behind it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class Role(str, Enum):
    """Chat message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message."""

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Schema for a tool the LLM can call."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class LLMResponse:
    """Response from an LLM completion call."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StreamDelta:
    """A single chunk from a streaming response."""

    content: str = ""
    tool_call: ToolCall | None = None
    finish_reason: str = ""


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations must support at minimum ``chat`` and ``stream``.
    Vision and tool-use are opt-in capabilities gated by the
    ``supports_vision`` and ``supports_tools`` properties.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @property
    def supports_vision(self) -> bool:
        """Whether this provider can process image inputs."""
        return False

    @property
    def supports_tools(self) -> bool:
        """Whether this provider supports tool/function calling."""
        return False

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request and return the full response.

        Args:
            messages: Conversation history.
            tools: Available tools the model may call.
            system: System prompt override.
            max_tokens: Maximum tokens to generate.

        Returns:
            Complete LLM response with content and optional tool calls.
        """

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a chat completion, yielding deltas as they arrive.

        Args:
            messages: Conversation history.
            tools: Available tools the model may call.
            system: System prompt override.
            max_tokens: Maximum tokens to generate.

        Yields:
            StreamDelta chunks.
        """
        # AsyncIterator requires this to be an async generator
        yield StreamDelta()  # pragma: no cover

    async def vision(
        self,
        prompt: str,
        image_data: bytes,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int | None = None,
    ) -> str:
        """Describe an image using the model's vision capability.

        Args:
            prompt: Text prompt to accompany the image.
            image_data: Raw image bytes.
            media_type: MIME type of the image.
            max_tokens: Maximum tokens to generate.

        Returns:
            Natural-language description of the image.

        Raises:
            NotImplementedError: If the provider does not support vision.
        """
        raise NotImplementedError(f"{self.name} does not support vision")

    async def close(self) -> None:
        """Release any resources held by the provider."""
