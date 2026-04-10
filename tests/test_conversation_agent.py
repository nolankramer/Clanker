"""Tests for the conversation agent."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from clanker.brain.base import LLMResponse, ToolCall
from clanker.conversation.agent import ConversationAgent


@pytest.fixture
def brain() -> AsyncMock:
    brain = AsyncMock()
    brain.chat = AsyncMock(
        return_value=LLMResponse(content="Done!", finish_reason="stop")
    )
    return brain


@pytest.fixture
def ha_client() -> AsyncMock:
    client = AsyncMock()
    client.call_service = AsyncMock(return_value={})
    client.get_state = AsyncMock(return_value={"state": "on"})
    client.find_entities = AsyncMock(return_value=[])
    return client


@pytest.fixture
def memory_tools() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def agent(brain: AsyncMock, ha_client: AsyncMock, memory_tools: AsyncMock) -> ConversationAgent:
    return ConversationAgent(
        brain=brain,
        ha_client=ha_client,
        memory_tools=memory_tools,
    )


async def test_simple_conversation(agent: ConversationAgent) -> None:
    result = await agent.process("Hello")
    assert result["speech"] == "Done!"
    assert "conversation_id" in result


async def test_preserves_conversation_id(agent: ConversationAgent) -> None:
    result = await agent.process("Hello", conversation_id="conv-123")
    assert result["conversation_id"] == "conv-123"


async def test_generates_conversation_id(agent: ConversationAgent) -> None:
    result = await agent.process("Hello")
    assert result["conversation_id"]  # non-empty UUID


async def test_tool_call_execution(
    agent: ConversationAgent, brain: AsyncMock, ha_client: AsyncMock
) -> None:
    # First call: brain returns a tool call
    tool_response = LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id="call_1", name="ha_call_service", arguments={
                "domain": "light", "service": "turn_off", "entity_id": "light.living_room"
            })
        ],
    )
    # Second call: brain returns text
    text_response = LLMResponse(content="Lights are off.", finish_reason="stop")
    brain.chat = AsyncMock(side_effect=[tool_response, text_response])

    result = await agent.process("Turn off the living room lights")

    assert result["speech"] == "Lights are off."
    ha_client.call_service.assert_awaited_once_with(
        "light", "turn_off", entity_id="light.living_room", data=None
    )


async def test_tool_get_state(
    agent: ConversationAgent, brain: AsyncMock, ha_client: AsyncMock
) -> None:
    tool_response = LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id="call_1", name="ha_get_state", arguments={"entity_id": "sensor.temp"})
        ],
    )
    text_response = LLMResponse(content="It's 72 degrees.", finish_reason="stop")
    brain.chat = AsyncMock(side_effect=[tool_response, text_response])

    result = await agent.process("What's the temperature?")
    assert result["speech"] == "It's 72 degrees."


async def test_tool_find_entities(
    agent: ConversationAgent, brain: AsyncMock, ha_client: AsyncMock
) -> None:
    ha_client.find_entities = AsyncMock(return_value=[
        {"entity_id": "light.kitchen", "state": "on",
         "attributes": {"friendly_name": "Kitchen Light"}},
    ])
    tool_response = LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id="call_1", name="ha_find_entities", arguments={"pattern": "kitchen"})
        ],
    )
    text_response = LLMResponse(content="Found the kitchen light.", finish_reason="stop")
    brain.chat = AsyncMock(side_effect=[tool_response, text_response])

    result = await agent.process("Find kitchen lights")
    assert "kitchen" in result["speech"].lower()


async def test_tool_error_handled(
    agent: ConversationAgent, brain: AsyncMock, ha_client: AsyncMock
) -> None:
    ha_client.call_service = AsyncMock(side_effect=RuntimeError("HA down"))
    tool_response = LLMResponse(
        content="",
        tool_calls=[ToolCall(id="call_1", name="ha_call_service", arguments={
            "domain": "light", "service": "turn_on"
        })],
    )
    text_response = LLMResponse(content="Had trouble, sorry.", finish_reason="stop")
    brain.chat = AsyncMock(side_effect=[tool_response, text_response])

    result = await agent.process("Turn on lights")
    assert result["speech"]  # should still return something


async def test_max_tool_rounds(
    agent: ConversationAgent, brain: AsyncMock
) -> None:
    # Brain always returns tool calls — should bail after MAX_TOOL_ROUNDS
    brain.chat = AsyncMock(
        return_value=LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_x", name="ha_find_entities", arguments={"pattern": "x"})],
        )
    )

    result = await agent.process("Loop forever")
    assert "trouble" in result["speech"].lower()


async def test_multi_turn_session(agent: ConversationAgent) -> None:
    await agent.process("Hello", conversation_id="multi-1")
    await agent.process("What did I say?", conversation_id="multi-1")
    # Same session should be reused
    session = agent.sessions.get("multi-1")
    assert session is not None
    # Should have messages from both turns
    assert len(session.messages) >= 4  # user+assistant + user+assistant
