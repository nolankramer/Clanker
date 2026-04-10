"""Structured memory — SQLite-backed storage for facts with schema.

Stores: known faces, people/users, room-to-speaker mappings, appliance
ownership, and arbitrary key-value preferences. All data is queryable
by exact match or SQL pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from clanker.memory.base import MemoryStore

logger = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    embedding_id TEXT,
    relationship TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    role TEXT DEFAULT 'resident',
    is_adult BOOLEAN DEFAULT 1,
    preferred_name TEXT,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    speaker_entity_ids TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appliances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    announcement_template TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_faces_name ON faces(name);
CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);
CREATE INDEX IF NOT EXISTS idx_appliances_entity ON appliances(entity_id);
"""


class StructuredMemory(MemoryStore):
    """SQLite-backed structured memory.

    Each table has typed columns for its domain. The generic
    ``store``/``retrieve`` interface uses the ``preferences`` table.
    Direct table access is available via dedicated methods.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize structured memory.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and tables if they don't exist."""
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("structured_memory.initialized", db_path=self._db_path)

    @property
    def db(self) -> aiosqlite.Connection:
        """Get the active database connection.

        Raises:
            RuntimeError: If the store has not been initialized.
        """
        if self._db is None:
            msg = "StructuredMemory not initialized — call initialize() first"
            raise RuntimeError(msg)
        return self._db

    # ------------------------------------------------------------------
    # Generic key-value (preferences table)
    # ------------------------------------------------------------------

    async def store(self, key: str, value: Any, *, category: str = "general") -> None:
        """Store a preference key-value pair."""
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await self.db.execute(
            "INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (key, serialized),
        )
        await self.db.commit()

    async def retrieve(self, key: str) -> Any | None:
        """Retrieve a preference by key."""
        cursor = await self.db.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is None:
            return None
        val = row[0]
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search preferences by key pattern (LIKE match)."""
        cursor = await self.db.execute(
            "SELECT key, value FROM preferences WHERE key LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [{"key": row[0], "value": row[1]} for row in rows]

    async def delete(self, key: str) -> bool:
        """Delete a preference by key."""
        cursor = await self.db.execute("DELETE FROM preferences WHERE key = ?", (key,))
        await self.db.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Faces
    # ------------------------------------------------------------------

    async def add_face(
        self,
        name: str,
        *,
        embedding_id: str | None = None,
        relationship: str = "",
        notes: str = "",
    ) -> int:
        """Add a known face.

        Args:
            name: Person's name.
            embedding_id: Reference to face embedding in the recognition system.
            relationship: Relationship description (neighbor, family, etc.).
            notes: Free-text notes.

        Returns:
            Row ID of the inserted face.
        """
        cursor = await self.db.execute(
            "INSERT INTO faces (name, embedding_id, relationship, notes) VALUES (?, ?, ?, ?)",
            (name, embedding_id, relationship, notes),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_face(self, name: str) -> dict[str, Any] | None:
        """Look up a face by name.

        Args:
            name: Person's name to search for.

        Returns:
            Face record as a dict, or None.
        """
        cursor = await self.db.execute(
            "SELECT id, name, embedding_id, relationship, notes FROM faces WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "embedding_id": row[2],
            "relationship": row[3],
            "notes": row[4],
        }

    async def list_faces(self) -> list[dict[str, Any]]:
        """List all known faces."""
        cursor = await self.db.execute(
            "SELECT id, name, embedding_id, relationship, notes FROM faces ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "embedding_id": row[2],
                "relationship": row[3],
                "notes": row[4],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    async def add_person(
        self,
        name: str,
        *,
        role: str = "resident",
        is_adult: bool = True,
        preferred_name: str | None = None,
        notes: str = "",
    ) -> int:
        """Add a person/user.

        Args:
            name: Full name.
            role: Role in the household (resident, guest, etc.).
            is_adult: Whether this person is an adult.
            preferred_name: What Clanker should call them.
            notes: Free-text notes.

        Returns:
            Row ID of the inserted person.
        """
        cursor = await self.db.execute(
            "INSERT INTO people (name, role, is_adult, preferred_name, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, role, is_adult, preferred_name, notes),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_person(self, name: str) -> dict[str, Any] | None:
        """Look up a person by name.

        Args:
            name: Person's name.

        Returns:
            Person record as a dict, or None.
        """
        cursor = await self.db.execute(
            "SELECT id, name, role, is_adult, preferred_name, notes FROM people WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "role": row[2],
            "is_adult": bool(row[3]),
            "preferred_name": row[4],
            "notes": row[5],
        }

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    async def add_room(
        self,
        name: str,
        *,
        speaker_entity_ids: list[str] | None = None,
        notes: str = "",
    ) -> int:
        """Add a room with its speaker mapping.

        Args:
            name: Room name.
            speaker_entity_ids: List of media_player entity IDs in this room.
            notes: Free-text notes.

        Returns:
            Row ID of the inserted room.
        """
        speakers_json = json.dumps(speaker_entity_ids or [])
        cursor = await self.db.execute(
            "INSERT INTO rooms (name, speaker_entity_ids, notes) VALUES (?, ?, ?)",
            (name, speakers_json, notes),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_room(self, name: str) -> dict[str, Any] | None:
        """Look up a room by name.

        Args:
            name: Room name.

        Returns:
            Room record as a dict, or None.
        """
        cursor = await self.db.execute(
            "SELECT id, name, speaker_entity_ids, notes FROM rooms WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "speaker_entity_ids": json.loads(row[2]),
            "notes": row[3],
        }

    # ------------------------------------------------------------------
    # Appliances
    # ------------------------------------------------------------------

    async def add_appliance(
        self,
        entity_id: str,
        *,
        name: str = "",
        owner: str = "",
        announcement_template: str = "",
        notes: str = "",
    ) -> int:
        """Add an appliance for monitoring/announcements.

        Args:
            entity_id: HA entity ID for the appliance.
            name: Human-readable name.
            owner: Who owns/uses this appliance.
            announcement_template: Template for done announcements.
            notes: Free-text notes.

        Returns:
            Row ID of the inserted appliance.
        """
        cursor = await self.db.execute(
            "INSERT INTO appliances (entity_id, name, owner, announcement_template, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (entity_id, name, owner, announcement_template, notes),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_appliance(self, entity_id: str) -> dict[str, Any] | None:
        """Look up an appliance by entity ID.

        Args:
            entity_id: HA entity ID.

        Returns:
            Appliance record as a dict, or None.
        """
        cursor = await self.db.execute(
            "SELECT id, entity_id, name, owner, announcement_template, notes "
            "FROM appliances WHERE entity_id = ?",
            (entity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "entity_id": row[1],
            "name": row[2],
            "owner": row[3],
            "announcement_template": row[4],
            "notes": row[5],
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("structured_memory.closed")
