"""Tests for the Ollama LLM provider."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clanker.brain.base import LLMResponse, Message, Role, StreamDelta, ToolDefinition
from clanker.brain.ollama import OllamaProvider, _build_messages, _build_tools, _parse_tool_calls
from clanker.config import OllamaConfig


@pytest.fixture
def config() -> OllamaConfig:
    return OllamaConfig(base_url="http://localhost:11434", model="llama3.2", max_tokens=512)


@pytest.fixture
def provider(config: OllamaConfig) -> OllamaProvider:
    return OllamaProvider(config)


# ------------------------------------------------------------------
# Message conversion helpers
# ------------------------------------------------------------------


def test_build_messages_with_system_override() -> None:
    msgs = [
        Message(role=Role.SYSTEM, content="old"),
        Message(role=Role.USER, content="hi"),
    ]
    result = _build_messages(msgs, system="new system")
    assert result[0] == {"role": "system", "content": "new system"}
    assert result[1] == {"role": "user", "content": "hi"}
    assert len(result) == 2


def test_build_messages_system_from_messages() -> None:
    msgs = [
        Message(role=Role.SYSTEM, content="sys"),
        Message(role=Role.USER, content="hey"),
    ]
    result = _build_messages(msgs, system=None)
    assert result[0]["content"] == "sys"


def test_build_tools() -> None:
    tools = [
        ToolDefinition(name="fn", description="desc", parameters={"type": "object"}),
    ]
    result = _build_tools(tools)
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "fn"


def test_parse_tool_calls() -> None:
    msg = {
        "tool_calls": [
            {"function": {"name": "fn1", "arguments": {"x": 1}}},
            {"function": {"name": "fn2", "arguments": {"y": 2}}},
        ]
    }
    calls = _parse_tool_calls(msg)
    assert len(calls) == 2
    assert calls[0].name == "fn1"
    assert calls[0].arguments == {"x": 1}
    assert calls[1].id == "call_1"


def test_parse_tool_calls_empty() -> None:
    assert _parse_tool_calls({}) == []


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------


async def test_chat_basic(provider: OllamaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "message": {"role": "assistant", "content": "Hello there!"},
        "done": True,
        "prompt_eval_count": 12,
        "eval_count": 8,
    }
    provider._client.post = AsyncMock(return_value=mock_resp)

    msgs = [Message(role=Role.USER, content="Hi")]
    result = await provider.chat(msgs)

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello there!"
    assert result.finish_reason == "stop"
    assert result.usage["input_tokens"] == 12
    assert result.usage["output_tokens"] == 8

    # Verify request payload
    call_args = provider._client.post.call_args
    payload = call_args[1]["json"]
    assert payload["model"] == "llama3.2"
    assert payload["stream"] is False


async def test_chat_with_tools(provider: OllamaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "get_time", "arguments": {"tz": "UTC"}}}
            ],
        },
        "done": True,
    }
    provider._client.post = AsyncMock(return_value=mock_resp)

    tools = [ToolDefinition(name="get_time", description="Get time", parameters={})]
    result = await provider.chat(
        [Message(role=Role.USER, content="time?")], tools=tools
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_time"


# ------------------------------------------------------------------
# Stream
# ------------------------------------------------------------------


async def test_stream_text(provider: OllamaProvider) -> None:
    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    class MockStreamResp:
        def raise_for_status(self) -> None:
            pass

        async def aiter_lines(self) -> Any:
            for line in lines:
                yield line

        async def __aenter__(self) -> MockStreamResp:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    provider._client.stream = MagicMock(return_value=MockStreamResp())

    deltas: list[StreamDelta] = []
    async for delta in provider.stream([Message(role=Role.USER, content="Hi")]):
        deltas.append(delta)

    text = "".join(d.content for d in deltas if d.content)
    assert text == "Hello world"
    assert deltas[-1].finish_reason == "stop"


# ------------------------------------------------------------------
# Vision
# ------------------------------------------------------------------


async def test_vision(provider: OllamaProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": "A dog playing fetch"},
        "done": True,
    }
    provider._client.post = AsyncMock(return_value=mock_resp)

    result = await provider.vision("Describe this", b"\xff\xd8")

    assert result == "A dog playing fetch"
    payload = provider._client.post.call_args[1]["json"]
    assert "images" in payload["messages"][0]
    assert payload["stream"] is False


# ------------------------------------------------------------------
# Properties and lifecycle
# ------------------------------------------------------------------


def test_properties(provider: OllamaProvider) -> None:
    assert provider.name == "ollama"
    assert provider.supports_vision is True
    assert provider.supports_tools is True


async def test_close(provider: OllamaProvider) -> None:
    provider._client.aclose = AsyncMock()
    await provider.close()
    provider._client.aclose.assert_awaited_once()
