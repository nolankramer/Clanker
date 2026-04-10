"""Tests for structured (SQLite) memory CRUD operations."""

from __future__ import annotations

import pytest

from clanker.memory.structured import StructuredMemory


@pytest.fixture
async def memory(tmp_path):
    """Create a fresh in-memory-like structured memory for each test."""
    db_path = str(tmp_path / "test.db")
    mem = StructuredMemory(db_path)
    await mem.initialize()
    yield mem
    await mem.close()


async def test_preferences_crud(memory: StructuredMemory) -> None:
    """Store, retrieve, search, and delete a preference."""
    await memory.store("theme", "dark")
    assert await memory.retrieve("theme") == "dark"

    await memory.store("theme", "light")
    assert await memory.retrieve("theme") == "light"

    results = await memory.search("theme")
    assert len(results) == 1
    assert results[0]["key"] == "theme"

    deleted = await memory.delete("theme")
    assert deleted is True
    assert await memory.retrieve("theme") is None

    deleted_again = await memory.delete("theme")
    assert deleted_again is False


async def test_preferences_json_values(memory: StructuredMemory) -> None:
    """Non-string values are JSON-serialized and deserialized."""
    await memory.store("rooms", ["kitchen", "office", "bedroom"])
    result = await memory.retrieve("rooms")
    assert result == ["kitchen", "office", "bedroom"]

    await memory.store("count", 42)
    assert await memory.retrieve("count") == 42


async def test_add_and_get_face(memory: StructuredMemory) -> None:
    """Add a known face and retrieve it."""
    face_id = await memory.add_face(
        "Jim",
        embedding_id="emb_123",
        relationship="neighbor",
        notes="Lives at 1423, friendly",
    )
    assert face_id is not None

    face = await memory.get_face("Jim")
    assert face is not None
    assert face["name"] == "Jim"
    assert face["relationship"] == "neighbor"
    assert face["embedding_id"] == "emb_123"
    assert "1423" in face["notes"]


async def test_get_face_not_found(memory: StructuredMemory) -> None:
    """Looking up a nonexistent face returns None."""
    assert await memory.get_face("Nobody") is None


async def test_list_faces(memory: StructuredMemory) -> None:
    """List all known faces."""
    await memory.add_face("Alice", relationship="family")
    await memory.add_face("Bob", relationship="friend")

    faces = await memory.list_faces()
    names = [f["name"] for f in faces]
    assert "Alice" in names
    assert "Bob" in names


async def test_add_and_get_person(memory: StructuredMemory) -> None:
    """Add a person and retrieve them."""
    person_id = await memory.add_person(
        "Alice Smith",
        role="resident",
        is_adult=True,
        preferred_name="Alice",
        notes="Primary user",
    )
    assert person_id is not None

    person = await memory.get_person("Alice Smith")
    assert person is not None
    assert person["role"] == "resident"
    assert person["is_adult"] is True
    assert person["preferred_name"] == "Alice"


async def test_add_and_get_room(memory: StructuredMemory) -> None:
    """Add a room with speakers and retrieve it."""
    room_id = await memory.add_room(
        "kitchen",
        speaker_entity_ids=["media_player.kitchen_nest", "media_player.kitchen_sonos"],
    )
    assert room_id is not None

    room = await memory.get_room("kitchen")
    assert room is not None
    assert room["name"] == "kitchen"
    assert len(room["speaker_entity_ids"]) == 2


async def test_add_and_get_appliance(memory: StructuredMemory) -> None:
    """Add an appliance and retrieve it."""
    app_id = await memory.add_appliance(
        "sensor.washer_power",
        name="Washing Machine",
        owner="Alice",
        announcement_template="The laundry is done!",
    )
    assert app_id is not None

    appliance = await memory.get_appliance("sensor.washer_power")
    assert appliance is not None
    assert appliance["name"] == "Washing Machine"
    assert appliance["owner"] == "Alice"
    assert appliance["announcement_template"] == "The laundry is done!"


async def test_appliance_not_found(memory: StructuredMemory) -> None:
    """Looking up a nonexistent appliance returns None."""
    assert await memory.get_appliance("sensor.nonexistent") is None
