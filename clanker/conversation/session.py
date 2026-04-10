"""Per-conversation session state with persistence and compaction.

Sessions track message history per ``conversation_id``. Features:

- **Token-aware compaction**: when context nears the model limit,
  older messages are summarized via the LLM and replaced with a
  compact summary message.
- **SQLite persistence**: sessions survive restarts.
- **TTL eviction**: stale sessions are cleaned up automatically.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from clanker.brain.base import Message, Role

logger = structlog.get_logger(__name__)

# Rough token estimate: ~4 chars per token for English text
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count estimate from character length."""
    return len(text) // _CHARS_PER_TOKEN + 1


def estimate_session_tokens(messages: list[Message]) -> int:
    """Estimate total tokens across all messages in a session."""
    return sum(estimate_tokens(m.content) for m in messages)


@dataclass
class Session:
    """A single conversation session."""

    conversation_id: str
    messages: list[Message] = field(default_factory=list)
    summary: str = ""  # compacted summary of older messages
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(
        self, role: Role, content: str, *, tool_call_id: str | None = None
    ) -> None:
        """Append a message and refresh the activity timestamp."""
        self.messages.append(
            Message(role=role, content=content, tool_call_id=tool_call_id)
        )
        self.last_active = time.monotonic()

    @property
    def token_estimate(self) -> int:
        """Rough token count for the full session."""
        total = estimate_session_tokens(self.messages)
        if self.summary:
            total += estimate_tokens(self.summary)
        return total

    def needs_compaction(self, max_tokens: int = 6000) -> bool:
        """Whether this session exceeds the token budget."""
        return self.token_estimate > max_tokens

    def get_messages_for_brain(self) -> list[Message]:
        """Get the message list to send to the brain.

        If a compacted summary exists, it's prepended as a system-level
        context note so the brain has continuity.
        """
        if self.summary:
            summary_msg = Message(
                role=Role.SYSTEM,
                content=f"[Previous conversation summary: {self.summary}]",
            )
            return [summary_msg, *self.messages]
        return list(self.messages)

    def compact(self, summary: str, keep_recent: int = 6) -> None:
        """Replace older messages with a summary.

        Args:
            summary: LLM-generated summary of the compacted messages.
            keep_recent: Number of recent messages to keep verbatim.
        """
        self.summary = summary
        # Keep only the most recent messages
        if len(self.messages) > keep_recent:
            self.messages = self.messages[-keep_recent:]
        logger.info(
            "session.compacted",
            conversation_id=self.conversation_id,
            summary_len=len(summary),
            remaining_messages=len(self.messages),
        )

    def trim(self, max_messages: int = 40) -> None:
        """Hard trim — fallback if compaction isn't available."""
        if len(self.messages) <= max_messages:
            return
        system = [m for m in self.messages if m.role == Role.SYSTEM]
        rest = [m for m in self.messages if m.role != Role.SYSTEM]
        self.messages = system + rest[-(max_messages - len(system)):]


class SessionStore:
    """Session store with SQLite persistence and TTL eviction.

    Args:
        db_path: Path to SQLite database (None for in-memory only).
        ttl_seconds: Seconds of inactivity before a session is evicted.
        max_context_tokens: Token budget per session before compaction.
    """

    def __init__(
        self,
        *,
        db_path: str | None = None,
        ttl_seconds: float = 600.0,
        max_context_tokens: int = 6000,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._db_path = db_path
        self._ttl = ttl_seconds
        self._max_tokens = max_context_tokens
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the sessions table and load persisted sessions."""
        if not self._db_path:
            return

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                conversation_id TEXT PRIMARY KEY,
                messages TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                last_active REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)
        await self._db.commit()

        # Load recent sessions
        await self._load_sessions()
        logger.info(
            "session_store.initialized",
            db_path=self._db_path,
            loaded=len(self._sessions),
        )

    async def _load_sessions(self) -> None:
        """Load non-stale sessions from SQLite."""
        if not self._db:
            return

        cutoff = time.time() - self._ttl
        async with self._db.execute(
            "SELECT * FROM sessions WHERE last_active > ?", (cutoff,)
        ) as cursor:
            async for row in cursor:
                cid, msgs_json, summary, created, active, meta_json = row
                try:
                    msgs_data = json.loads(msgs_json)
                    messages = [
                        Message(
                            role=Role(m["role"]),
                            content=m["content"],
                            tool_call_id=m.get("tool_call_id"),
                        )
                        for m in msgs_data
                    ]
                    session = Session(
                        conversation_id=cid,
                        messages=messages,
                        summary=summary,
                        created_at=created,
                        last_active=active,
                        metadata=json.loads(meta_json),
                    )
                    self._sessions[cid] = session
                except Exception:
                    logger.warning("session_store.load_error", cid=cid)

    async def _persist_session(self, session: Session) -> None:
        """Save a session to SQLite."""
        if not self._db:
            return

        msgs_json = json.dumps([
            {
                "role": m.role.value,
                "content": m.content,
                "tool_call_id": m.tool_call_id,
            }
            for m in session.messages
        ])

        await self._db.execute(
            """INSERT OR REPLACE INTO sessions
               (conversation_id, messages, summary, created_at, last_active, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session.conversation_id,
                msgs_json,
                session.summary,
                session.created_at,
                session.last_active,
                json.dumps(session.metadata),
            ),
        )
        await self._db.commit()

    def get_or_create(self, conversation_id: str) -> Session:
        """Return an existing session or create a new one."""
        self._evict_stale()
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = Session(
                conversation_id=conversation_id
            )
        session = self._sessions[conversation_id]
        session.last_active = time.monotonic()
        return session

    def get(self, conversation_id: str) -> Session | None:
        """Return a session if it exists and is still alive."""
        self._evict_stale()
        return self._sessions.get(conversation_id)

    async def save(self, session: Session) -> None:
        """Persist a session after modification."""
        await self._persist_session(session)

    def delete(self, conversation_id: str) -> None:
        """Remove a session from memory."""
        self._sessions.pop(conversation_id, None)

    @property
    def active_count(self) -> int:
        """Number of live sessions."""
        self._evict_stale()
        return len(self._sessions)

    @property
    def max_context_tokens(self) -> int:
        """Token budget per session."""
        return self._max_tokens

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()

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
