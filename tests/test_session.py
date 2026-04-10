"""Tests for conversation session management, compaction, and persistence."""

from __future__ import annotations

import time
from pathlib import Path  # noqa: TC003 — used at runtime by pytest
from unittest.mock import patch

from clanker.brain.base import Role
from clanker.conversation.session import (
    Session,
    SessionStore,
    estimate_session_tokens,
    estimate_tokens,
)

# ------------------------------------------------------------------
# Token estimation
# ------------------------------------------------------------------


def test_estimate_tokens() -> None:
    assert estimate_tokens("hello") > 0
    assert estimate_tokens("a" * 400) == 101  # 400/4 + 1


def test_estimate_session_tokens() -> None:
    from clanker.brain.base import Message

    msgs = [
        Message(role=Role.USER, content="hello world"),
        Message(role=Role.ASSISTANT, content="hi there"),
    ]
    tokens = estimate_session_tokens(msgs)
    assert tokens > 0


# ------------------------------------------------------------------
# Session basics
# ------------------------------------------------------------------


def test_session_add_and_retrieve() -> None:
    session = Session(conversation_id="test-1")
    session.add(Role.USER, "Hello")
    session.add(Role.ASSISTANT, "Hi there!")
    assert len(session.messages) == 2
    assert session.messages[0].content == "Hello"


def test_session_token_estimate() -> None:
    session = Session(conversation_id="test-tok")
    session.add(Role.USER, "a" * 400)
    assert session.token_estimate > 0


def test_session_needs_compaction() -> None:
    session = Session(conversation_id="test-compact")
    # Add enough content to exceed 100 tokens
    for _ in range(50):
        session.add(Role.USER, "a" * 100)
    assert session.needs_compaction(max_tokens=100)
    assert not session.needs_compaction(max_tokens=999999)


# ------------------------------------------------------------------
# Compaction
# ------------------------------------------------------------------


def test_compact_replaces_old_messages() -> None:
    session = Session(conversation_id="test-c")
    for i in range(20):
        session.add(Role.USER, f"msg {i}")
    assert len(session.messages) == 20

    session.compact("User asked about lights and weather.", keep_recent=6)
    assert len(session.messages) == 6
    assert session.summary == "User asked about lights and weather."
    assert session.messages[-1].content == "msg 19"


def test_compact_merges_with_existing_summary() -> None:
    session = Session(conversation_id="test-merge")
    session.summary = "Earlier: discussed lights."
    for i in range(10):
        session.add(Role.USER, f"msg {i}")

    session.compact("Then discussed weather.", keep_recent=4)
    # Summary should not lose old context — agent.py handles merge
    assert session.summary == "Then discussed weather."


def test_get_messages_for_brain_with_summary() -> None:
    session = Session(conversation_id="test-brain")
    session.summary = "User turned off kitchen lights."
    session.add(Role.USER, "What about the bedroom?")

    msgs = session.get_messages_for_brain()
    assert len(msgs) == 2
    assert msgs[0].role == Role.SYSTEM
    assert "kitchen lights" in msgs[0].content
    assert msgs[1].content == "What about the bedroom?"


def test_get_messages_for_brain_without_summary() -> None:
    session = Session(conversation_id="test-no-sum")
    session.add(Role.USER, "Hello")

    msgs = session.get_messages_for_brain()
    assert len(msgs) == 1
    assert msgs[0].content == "Hello"


def test_trim_fallback() -> None:
    session = Session(conversation_id="test-trim")
    session.add(Role.SYSTEM, "System prompt")
    for i in range(50):
        session.add(Role.USER, f"msg {i}")
    session.trim(max_messages=10)
    assert len(session.messages) == 10
    assert session.messages[0].role == Role.SYSTEM


# ------------------------------------------------------------------
# SessionStore
# ------------------------------------------------------------------


def test_store_get_or_create() -> None:
    store = SessionStore()
    s1 = store.get_or_create("conv-1")
    s2 = store.get_or_create("conv-1")
    assert s1 is s2
    assert store.active_count == 1


def test_store_different_ids() -> None:
    store = SessionStore()
    s1 = store.get_or_create("conv-1")
    s2 = store.get_or_create("conv-2")
    assert s1 is not s2
    assert store.active_count == 2


def test_store_evicts_stale() -> None:
    store = SessionStore(ttl_seconds=1.0)
    store.get_or_create("conv-old")

    with patch("clanker.conversation.session.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 10.0
        assert store.active_count == 0


def test_store_delete() -> None:
    store = SessionStore()
    store.get_or_create("conv-1")
    store.delete("conv-1")
    assert store.get("conv-1") is None


def test_store_get_nonexistent() -> None:
    store = SessionStore()
    assert store.get("nope") is None


def test_session_tool_call_id() -> None:
    session = Session(conversation_id="test-tc")
    session.add(Role.TOOL, '{"result": 42}', tool_call_id="call_123")
    assert session.messages[0].tool_call_id == "call_123"


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


async def test_persistence_save_and_load(tmp_path: Path) -> None:
    db = str(tmp_path / "sessions.db")

    # Save a session
    store1 = SessionStore(db_path=db, ttl_seconds=600.0)
    await store1.initialize()
    session = store1.get_or_create("persist-1")
    session.add(Role.USER, "Turn off the lights")
    session.add(Role.ASSISTANT, "Done!")
    session.summary = "User turned off lights."
    session.last_active = time.time()  # use wall clock for persistence
    await store1.save(session)
    await store1.close()

    # Load in a new store
    store2 = SessionStore(db_path=db, ttl_seconds=600.0)
    await store2.initialize()
    loaded = store2.get("persist-1")
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0].content == "Turn off the lights"
    assert loaded.summary == "User turned off lights."
    await store2.close()


async def test_persistence_no_db() -> None:
    store = SessionStore(db_path=None)
    await store.initialize()  # should not raise
    store.get_or_create("test")
    await store.save(store.get("test"))  # type: ignore[arg-type]
    await store.close()
