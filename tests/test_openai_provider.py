"""Tests for the OpenAI LLM provider."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from clanker.brain.base import LLMResponse, Message, Role, StreamDelta, ToolDefinition
from clanker.brain.openai import OpenAIProvider, _build_messages, _build_tools
from clanker.config import OpenAIConfig


@pytest.fixture
def config() -> OpenAIConfig:
    return OpenAIConfig(api_key="test-key", model="gpt-4o", max_tokens=1024)


@pytest.fixture
def provider(config: OpenAIConfig) -> OpenAIProvider:
    with patch("openai.AsyncOpenAI"):
        return OpenAIProvider(config)


# ------------------------------------------------------------------
# Message conversion
# ------------------------------------------------------------------


def test_build_messages_with_system_override() -> None:
    msgs = [
        Message(role=Role.SYSTEM, content="old system"),
        Message(role=Role.USER, content="hello"),
    ]
    result = _build_messages(msgs, system="new system")
    assert result[0] == {"role": "system", "content": "new system"}
    assert result[1] == {"role": "user", "content": "hello"}
    assert len(result) == 2


def test_build_messages_extracts_system_from_messages() -> None:
    msgs = [
        Message(role=Role.SYSTEM, content="sys prompt"),
        Message(role=Role.USER, content="hi"),
    ]
    result = _build_messages(msgs, system=None)
    assert result[0] == {"role": "system", "content": "sys prompt"}
    assert result[1] == {"role": "user", "content": "hi"}


def test_build_messages_tool_result() -> None:
    msgs = [
        Message(role=Role.TOOL, content='{"result": 42}', tool_call_id="call_123"),
    ]
    result = _build_messages(msgs, system=None)
    assert result[0]["role"] == "tool"
    assert result[0]["tool_call_id"] == "call_123"


def test_build_tools() -> None:
    tools = [
        ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
    ]
    result = _build_tools(tools)
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "get_weather"


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------


async def test_chat_returns_response(provider: OpenAIProvider) -> None:
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hello!", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

    msgs = [Message(role=Role.USER, content="Hi")]
    result = await provider.chat(msgs)

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello!"
    assert result.finish_reason == "stop"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 5


async def test_chat_with_tool_calls(provider: OpenAIProvider) -> None:
    mock_tc = SimpleNamespace(
        id="call_abc",
        function=SimpleNamespace(
            name="get_weather",
            arguments='{"city": "Seattle"}',
        ),
    )
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[mock_tc]),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=15, completion_tokens=20),
    )
    provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

    tools = [
        ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
    ]
    result = await provider.chat([Message(role=Role.USER, content="Weather?")], tools=tools)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_weather"
    assert result.tool_calls[0].arguments == {"city": "Seattle"}


# ------------------------------------------------------------------
# Stream
# ------------------------------------------------------------------


async def test_stream_text(provider: OpenAIProvider) -> None:
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Hello", tool_calls=None),
                    finish_reason=None,
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=" world", tool_calls=None),
                    finish_reason=None,
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=None),
                    finish_reason="stop",
                )
            ]
        ),
    ]

    async def mock_stream(*args: Any, **kwargs: Any) -> Any:
        for chunk in chunks:
            yield chunk

    provider._client.chat.completions.create = AsyncMock(return_value=mock_stream())

    deltas: list[StreamDelta] = []
    async for delta in provider.stream([Message(role=Role.USER, content="Hi")]):
        deltas.append(delta)

    text = "".join(d.content for d in deltas if d.content)
    assert text == "Hello world"
    assert deltas[-1].finish_reason == "stop"


# ------------------------------------------------------------------
# Vision
# ------------------------------------------------------------------


async def test_vision(provider: OpenAIProvider) -> None:
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="A cat sitting on a mat"),
            )
        ],
    )
    provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await provider.vision("Describe this image", b"\xff\xd8\xff\xe0")

    assert result == "A cat sitting on a mat"
    call_kwargs = provider._client.chat.completions.create.call_args[1]
    msg_content = call_kwargs["messages"][0]["content"]
    assert msg_content[0]["type"] == "image_url"
    assert msg_content[1]["type"] == "text"


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------


def test_provider_properties(provider: OpenAIProvider) -> None:
    assert provider.name == "openai"
    assert provider.supports_vision is True
    assert provider.supports_tools is True


async def test_close(provider: OpenAIProvider) -> None:
    provider._client.close = AsyncMock()
    await provider.close()
    provider._client.close.assert_awaited_once()
