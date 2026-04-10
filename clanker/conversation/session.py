"""Per-conversation session state with TTL-based expiry.

Tracks message history per ``conversation_id`` across voice, push, and
chat surfaces.  Old sessions are evicted after a configurable TTL so
memory stays bounded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from clanker.brain.base import Message, Role


@dataclass
class Session:
    """A single conversation session."""

    conversation_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, role: Role, content: str, *, tool_call_id: str | None = None) -> None:
        """Append a message and refresh the activity timestamp."""
        self.messages.append(
            Message(role=role, content=content, tool_call_id=tool_call_id)
        )
        self.last_active = time.monotonic()

    def trim(self, max_messages: int = 40) -> None:
        """Keep the most recent messages, always preserving any system message."""
        if len(self.messages) <= max_messages:
            return
        # Keep system messages + tail
        system = [m for m in self.messages if m.role == Role.SYSTEM]
        rest = [m for m in self.messages if m.role != Role.SYSTEM]
        self.messages = system + rest[-(max_messages - len(system)) :]


class SessionStore:
    """In-memory session store with automatic TTL eviction.

    Args:
        ttl_seconds: Seconds of inactivity before a session is evicted.
        max_messages: Maximum messages per session before trimming.
    """

    def __init__(self, ttl_seconds: float = 600.0, max_messages: int = 40) -> None:
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_seconds
        self._max_messages = max_messages

    def get_or_create(self, conversation_id: str) -> Session:
        """Return an existing session or create a new one."""
        self._evict_stale()
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = Session(conversation_id=conversation_id)
        session = self._sessions[conversation_id]
        session.last_active = time.monotonic()
        return session

    def get(self, conversation_id: str) -> Session | None:
        """Return a session if it exists and is still alive."""
        self._evict_stale()
        return self._sessions.get(conversation_id)

    def delete(self, conversation_id: str) -> None:
        """Remove a session."""
        self._sessions.pop(conversation_id, None)

    @property
    def active_count(self) -> int:
        """Number of live sessions."""
        self._evict_stale()
        return len(self._sessions)

    def _evict_stale(self) -> None:
        """Remove sessions that have exceeded the TTL."""
        now = time.monotonic()
        stale = [
            cid
            for cid, s in self._sessions.items()
            if now - s.last_active > self._ttl
        ]
        for cid in stale:
            del self._sessions[cid]
