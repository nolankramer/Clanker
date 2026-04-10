"""Anthropic (Claude) LLM provider — fully implemented with streaming and tool use."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

import structlog

from clanker.brain.base import (
    LLMProvider,
    LLMResponse,
    Message,
    Role,
    StreamDelta,
    ToolCall,
    ToolDefinition,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anthropic import AsyncAnthropic

    from clanker.config import AnthropicConfig

logger = structlog.get_logger(__name__)


def _build_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert internal Message list to Anthropic API format.

    System messages are stripped here — the caller passes them via
    the ``system`` parameter instead.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == Role.SYSTEM:
            continue
        entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
        if msg.role == Role.TOOL and msg.tool_call_id:
            entry = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ],
            }
        result.append(entry)
    return result


def _build_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert internal ToolDefinition list to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def _extract_system(messages: list[Message], override: str | None) -> str | None:
    """Extract system prompt from messages or use the override."""
    if override:
        return override
    for msg in messages:
        if msg.role == Role.SYSTEM:
            return msg.content
    return None


def _parse_tool_calls(content_blocks: list[Any]) -> list[ToolCall]:
    """Extract tool calls from Anthropic response content blocks."""
    calls: list[ToolCall] = []
    for block in content_blocks:
        if hasattr(block, "type") and block.type == "tool_use":
            calls.append(
                ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                )
            )
    return calls


def _extract_text(content_blocks: list[Any]) -> str:
    """Extract text content from Anthropic response content blocks."""
    parts: list[str] = []
    for block in content_blocks:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic (Claude) API.

    Supports chat completion, streaming, vision, and tool use.
    """

    def __init__(self, config: AnthropicConfig) -> None:
        """Initialize with Anthropic config.

        Args:
            config: Anthropic provider configuration containing API key and model.
        """
        # Lazy import to avoid hard dependency at module level
        from anthropic import AsyncAnthropic

        self._config = config
        self._client: AsyncAnthropic = AsyncAnthropic(api_key=config.api_key)
        self._model = config.model
        self._max_tokens = config.max_tokens

    @property
    def name(self) -> str:
        """Human-readable provider name."""
        return "anthropic"

    @property
    def supports_vision(self) -> bool:
        """Anthropic Claude supports vision."""
        return True

    @property
    def supports_tools(self) -> bool:
        """Anthropic Claude supports tool use."""
        return True

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion to Claude and return the full response."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages),
            "max_tokens": max_tokens or self._max_tokens,
        }

        system_prompt = _extract_system(messages, system)
        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = _build_tools(tools)

        logger.debug("anthropic.chat", model=self._model, message_count=len(messages))
        response = await self._client.messages.create(**kwargs)

        return LLMResponse(
            content=_extract_text(response.content),
            tool_calls=_parse_tool_calls(response.content),
            finish_reason=response.stop_reason or "",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a chat completion from Claude, yielding deltas."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages),
            "max_tokens": max_tokens or self._max_tokens,
        }

        system_prompt = _extract_system(messages, system)
        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = _build_tools(tools)

        logger.debug("anthropic.stream", model=self._model, message_count=len(messages))

        # Track tool use blocks being built across stream events
        current_tool_id: str = ""
        current_tool_name: str = ""
        tool_input_json: str = ""

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if hasattr(block, "type") and block.type == "tool_use":
                        current_tool_id = block.id
                        current_tool_name = block.name
                        tool_input_json = ""
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "type"):
                        if delta.type == "text_delta":
                            yield StreamDelta(content=delta.text)
                        elif delta.type == "input_json_delta":
                            tool_input_json += delta.partial_json
                elif event.type == "content_block_stop":
                    if current_tool_id:
                        try:
                            args = json.loads(tool_input_json) if tool_input_json else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamDelta(
                            tool_call=ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments=args,
                            )
                        )
                        current_tool_id = ""
                        current_tool_name = ""
                        tool_input_json = ""
                elif event.type == "message_stop":
                    yield StreamDelta(finish_reason="end_turn")

    async def vision(
        self,
        prompt: str,
        image_data: bytes,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int | None = None,
    ) -> str:
        """Describe an image using Claude's vision capability."""
        b64 = base64.b64encode(image_data).decode("utf-8")

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        return _extract_text(response.content)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
