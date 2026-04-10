"""Tests for face recognition integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from clanker.vision.faces import FaceMatch, FaceRecognizer


@pytest.fixture
def ha_client() -> AsyncMock:
    client = AsyncMock()
    client.subscribe_events = AsyncMock(return_value=1)
    return client


@pytest.fixture
def memory() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def vlm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def recognizer(ha_client: AsyncMock, memory: AsyncMock, vlm: AsyncMock) -> FaceRecognizer:
    return FaceRecognizer(ha_client=ha_client, memory=memory, vlm=vlm)


# ------------------------------------------------------------------
# identify() — known faces
# ------------------------------------------------------------------


async def test_identify_known_face_with_person(recognizer: FaceRecognizer) -> None:
    recognizer.memory.get_face = AsyncMock(
        return_value={"name": "Jim", "person_id": 1}
    )
    recognizer.memory.get_person = AsyncMock(
        return_value={"name": "Jim Thompson", "role": "neighbor"}
    )

    result = await recognizer.identify("Jim", confidence=0.95, camera="front_door")

    assert isinstance(result, FaceMatch)
    assert result.person_name == "Jim Thompson"
    assert result.confidence == 0.95
    assert result.camera == "front_door"


async def test_identify_known_face_no_person_record(recognizer: FaceRecognizer) -> None:
    recognizer.memory.get_face = AsyncMock(
        return_value={"name": "Alice", "person_id": None}
    )

    result = await recognizer.identify("Alice", confidence=0.8, camera="back_yard")

    assert result.person_name == "Alice"


async def test_identify_known_face_not_in_memory(recognizer: FaceRecognizer) -> None:
    recognizer.memory.get_face = AsyncMock(return_value=None)

    result = await recognizer.identify("Bob", confidence=0.7, camera="garage")

    assert result.person_name == "Bob"


# ------------------------------------------------------------------
# identify() — unknown faces
# ------------------------------------------------------------------


async def test_identify_unknown_with_vlm(recognizer: FaceRecognizer) -> None:
    recognizer.vlm.describe = AsyncMock(return_value="Male, 30s, wearing a blue jacket")

    result = await recognizer.identify(
        None, confidence=0.0, camera="front_door", snapshot=b"\xff\xd8"
    )

    assert result.person_name is None
    assert result.description == "Male, 30s, wearing a blue jacket"
    recognizer.vlm.describe.assert_awaited_once()


async def test_identify_unknown_no_snapshot(recognizer: FaceRecognizer) -> None:
    result = await recognizer.identify(None, confidence=0.0, camera="front_door")

    assert result.person_name is None
    assert result.description is None


async def test_identify_unknown_vlm_error(recognizer: FaceRecognizer) -> None:
    recognizer.vlm.describe = AsyncMock(side_effect=RuntimeError("VLM down"))

    result = await recognizer.identify(
        None, confidence=0.0, camera="front_door", snapshot=b"\xff\xd8"
    )

    assert result.person_name is None
    assert result.description is None  # graceful fallback


async def test_identify_unknown_no_vlm(
    ha_client: AsyncMock, memory: AsyncMock
) -> None:
    recognizer = FaceRecognizer(ha_client=ha_client, memory=memory, vlm=None)

    result = await recognizer.identify(
        None, confidence=0.0, camera="front_door", snapshot=b"\xff\xd8"
    )

    assert result.person_name is None
    assert result.description is None


# ------------------------------------------------------------------
# Event subscription
# ------------------------------------------------------------------


async def test_start_subscribes(recognizer: FaceRecognizer) -> None:
    await recognizer.start()
    recognizer.ha_client.subscribe_events.assert_awaited_once_with(
        recognizer._on_event, event_type="doubletake"
    )
