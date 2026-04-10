"""Tests for conversation session management."""

from __future__ import annotations

import time
from unittest.mock import patch

from clanker.brain.base import Role
from clanker.conversation.session import Session, SessionStore


def test_session_add_and_retrieve() -> None:
    session = Session(conversation_id="test-1")
    session.add(Role.USER, "Hello")
    session.add(Role.ASSISTANT, "Hi there!")
    assert len(session.messages) == 2
    assert session.messages[0].content == "Hello"
    assert session.messages[1].role == Role.ASSISTANT


def test_session_trim() -> None:
    session = Session(conversation_id="test-2")
    # Add a system message + 50 messages
    session.add(Role.SYSTEM, "System prompt")
    for i in range(50):
        session.add(Role.USER, f"msg {i}")
    session.trim(max_messages=10)
    # System message should be preserved + 9 most recent
    assert len(session.messages) == 10
    assert session.messages[0].role == Role.SYSTEM
    assert session.messages[-1].content == "msg 49"


def test_session_trim_no_op_when_small() -> None:
    session = Session(conversation_id="test-3")
    session.add(Role.USER, "Hello")
    session.trim(max_messages=40)
    assert len(session.messages) == 1


def test_store_get_or_create() -> None:
    store = SessionStore(ttl_seconds=60.0)
    s1 = store.get_or_create("conv-1")
    s2 = store.get_or_create("conv-1")
    assert s1 is s2  # same instance
    assert store.active_count == 1


def test_store_creates_new_for_different_ids() -> None:
    store = SessionStore(ttl_seconds=60.0)
    s1 = store.get_or_create("conv-1")
    s2 = store.get_or_create("conv-2")
    assert s1 is not s2
    assert store.active_count == 2


def test_store_evicts_stale_sessions() -> None:
    store = SessionStore(ttl_seconds=1.0)
    store.get_or_create("conv-old")

    # Simulate time passing
    with patch("clanker.conversation.session.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 10.0
        assert store.active_count == 0


def test_store_delete() -> None:
    store = SessionStore(ttl_seconds=60.0)
    store.get_or_create("conv-1")
    store.delete("conv-1")
    assert store.get("conv-1") is None


def test_store_get_nonexistent() -> None:
    store = SessionStore(ttl_seconds=60.0)
    assert store.get("nope") is None


def test_session_tool_call_id() -> None:
    session = Session(conversation_id="test-tc")
    session.add(Role.TOOL, '{"result": 42}', tool_call_id="call_123")
    assert session.messages[0].tool_call_id == "call_123"
