"""Ollama LLM provider — uses Ollama's native REST API via httpx.

Supports chat, streaming, vision (for multimodal models like LLaVA),
and tool use (for models that support function calling).
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

import httpx
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

    from clanker.config import OllamaConfig

logger = structlog.get_logger(__name__)


def _build_messages(
    messages: list[Message], system: str | None
) -> list[dict[str, Any]]:
    """Convert internal messages to Ollama ``/api/chat`` format."""
    result: list[dict[str, Any]] = []

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
        result.append({"role": msg.role.value, "content": msg.content})

    return result


def _build_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert internal ToolDefinition list to Ollama tool format."""
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


def _parse_tool_calls(msg: dict[str, Any]) -> list[ToolCall]:
    """Extract tool calls from an Ollama response message."""
    calls: list[ToolCall] = []
    for i, tc in enumerate(msg.get("tool_calls", [])):
        fn = tc.get("function", {})
        calls.append(
            ToolCall(
                id=f"call_{i}",
                name=fn.get("name", ""),
                arguments=fn.get("arguments", {}),
            )
        )
    return calls


class OllamaProvider(LLMProvider):
    """LLM provider using a local Ollama instance via its native REST API.

    Uses ``/api/chat`` for both streaming and non-streaming completions.
    Vision is supported for multimodal models (LLaVA, Qwen2-VL, etc.)
    via the ``images`` field. Tool calling works for compatible models.
    """

    def __init__(self, config: OllamaConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    @property
    def name(self) -> str:
        return "ollama"

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
        """Send a non-streaming chat completion to Ollama."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages, system),
            "stream": False,
            "options": {"num_predict": max_tokens or self._max_tokens},
        }
        if tools:
            payload["tools"] = _build_tools(tools)

        logger.debug("ollama.chat", model=self._model, message_count=len(messages))
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})

        usage: dict[str, int] = {}
        if "prompt_eval_count" in data:
            usage["input_tokens"] = data["prompt_eval_count"]
        if "eval_count" in data:
            usage["output_tokens"] = data["eval_count"]

        return LLMResponse(
            content=msg.get("content", ""),
            tool_calls=_parse_tool_calls(msg),
            finish_reason="stop" if data.get("done") else "",
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
        """Stream a chat completion from Ollama, yielding deltas."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _build_messages(messages, system),
            "stream": True,
            "options": {"num_predict": max_tokens or self._max_tokens},
        }
        if tools:
            payload["tools"] = _build_tools(tools)

        logger.debug("ollama.stream", model=self._model, message_count=len(messages))

        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = data.get("message", {})
                content = msg.get("content", "")

                if content:
                    yield StreamDelta(content=content)

                # Tool calls arrive in the final message
                for tc in _parse_tool_calls(msg):
                    yield StreamDelta(tool_call=tc)

                if data.get("done"):
                    yield StreamDelta(finish_reason="stop")

    async def vision(
        self,
        prompt: str,
        image_data: bytes,
        *,
        media_type: str = "image/jpeg",
        max_tokens: int | None = None,
    ) -> str:
        """Describe an image using a multimodal Ollama model."""
        b64 = base64.b64encode(image_data).decode("utf-8")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }
            ],
            "stream": False,
            "options": {"num_predict": max_tokens or self._max_tokens},
        }

        logger.debug("ollama.vision", model=self._model)
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
