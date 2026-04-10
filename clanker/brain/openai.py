"""OpenAI LLM provider — full implementation with streaming, vision, and tool use.

Also serves as the backend for OpenAI-compatible endpoints (vLLM, llama.cpp, etc.)
when configured with a custom ``base_url``.
"""

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

    from openai import AsyncOpenAI

    from clanker.config import OpenAIConfig

logger = structlog.get_logger(__name__)


def _build_messages(
    messages: list[Message], system: str | None
) -> list[dict[str, Any]]:
    """Convert internal Message list to OpenAI API format."""
    result: list[dict[str, Any]] = []

    # System prompt: explicit override > first system message
    sys_prompt = system
    if not sys_prompt:
        for msg in messages:
            if msg.role == Role.SYSTEM:
                sys_prompt = msg.content
                break

    if sys_prompt:
        result.append({"role": "system", "content": sys_prompt})

    for msg in messages:
        if msg.role == Role.SYSTEM:
            continue
        if msg.role == Role.TOOL and msg.tool_call_id:
            result.append(
                {
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                }
            )
        else:
            result.append({"role": msg.role.value, "content": msg.content})

    return result


def _build_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert internal ToolDefinition list to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI API.

    Supports chat, streaming, vision, and tool use. When ``base_url`` is set
    in the config, the same class serves as a generic OpenAI-compatible client.
    """

    def __init__(self, config: OpenAIConfig) -> None:
        from openai import AsyncOpenAI

        self._config = config
        self._model = config.model
        self._max_tokens = config.max_tokens

        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url

        self._client: AsyncOpenAI = AsyncOpenAI(**kwargs)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion and return the full response."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages, system),
            "max_tokens": max_tokens or self._max_tokens,
        }
        if tools:
            kwargs["tools"] = _build_tools(tools)

        logger.debug("openai.chat", model=self._model, message_count=len(messages))
        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        usage: dict[str, int] = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "",
            usage=usage,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a chat completion, yielding deltas."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages, system),
            "max_tokens": max_tokens or self._max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _build_tools(tools)

        logger.debug("openai.stream", model=self._model, message_count=len(messages))

        # Accumulate tool-call fragments across chunks
        tool_call_buffers: dict[int, dict[str, str]] = {}

        response_stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in response_stream:  # type: ignore[union-attr]
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish = chunk.choices[0].finish_reason

            if delta.content:
                yield StreamDelta(content=delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                    buf = tool_call_buffers[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["arguments"] += tc_delta.function.arguments

            if finish:
                # Emit any accumulated tool calls
                if tool_call_buffers:
                    for _idx in sorted(tool_call_buffers):
                        buf = tool_call_buffers[_idx]
                        try:
                            args = json.loads(buf["arguments"]) if buf["arguments"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamDelta(
                            tool_call=ToolCall(
                                id=buf["id"], name=buf["name"], arguments=args
                            )
                        )
                    tool_call_buffers.clear()
                yield StreamDelta(finish_reason=finish)

    async def vision(
        self,
        prompt: str,
        image_data: bytes,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int | None = None,
    ) -> str:
        """Describe an image using GPT-4o vision."""
        b64 = base64.b64encode(image_data).decode("utf-8")

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
