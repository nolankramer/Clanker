"""Tests for semantic memory (markdown + ChromaDB)."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime by pytest

import pytest

from clanker.memory.semantic import SemanticMemory


@pytest.fixture
async def memory(tmp_path: Path) -> SemanticMemory:
    """Create a semantic memory instance with a temp directory."""
    mem = SemanticMemory(
        markdown_dir=str(tmp_path / "memory"),
        chromadb_path=str(tmp_path / "chroma"),
        embedding_model="nomic-embed-text",
        embedding_base_url="http://localhost:11434",
    )
    await mem.initialize()
    return mem


async def test_store_and_retrieve(memory: SemanticMemory) -> None:
    await memory.store("greeting", "Hello world", category="general")
    result = await memory.retrieve("greeting")
    assert result is not None
    assert "Hello world" in result


async def test_retrieve_not_found(memory: SemanticMemory) -> None:
    result = await memory.retrieve("nonexistent")
    assert result is None


async def test_store_creates_category_dir(
    memory: SemanticMemory, tmp_path: Path
) -> None:
    await memory.store("note", "test", category="daily")
    assert (tmp_path / "memory" / "daily" / "note.md").exists()


async def test_store_writes_frontmatter(
    memory: SemanticMemory, tmp_path: Path
) -> None:
    await memory.store("mykey", "content here", category="general")
    content = (tmp_path / "memory" / "general" / "mykey.md").read_text()
    assert "---" in content
    assert "key: mykey" in content
    assert "category: general" in content


async def test_substring_search(memory: SemanticMemory) -> None:
    await memory.store("recipe", "Chocolate chip cookies with butter")
    await memory.store("todo", "Buy groceries")

    results = await memory.search("chocolate")
    assert len(results) >= 1
    assert any("chocolate" in r["content"].lower() for r in results)


async def test_search_returns_results_for_stored_content(
    memory: SemanticMemory,
) -> None:
    await memory.store("note", "Hello world")
    results = await memory.search("Hello")
    assert len(results) >= 1


async def test_search_limit(memory: SemanticMemory) -> None:
    for i in range(10):
        await memory.store(f"item_{i}", f"Match this keyword item {i}")

    results = await memory.search("keyword", limit=3)
    assert len(results) <= 3


async def test_delete(memory: SemanticMemory) -> None:
    await memory.store("to_delete", "temp data")
    assert await memory.retrieve("to_delete") is not None

    deleted = await memory.delete("to_delete")
    assert deleted is True
    assert await memory.retrieve("to_delete") is None


async def test_delete_not_found(memory: SemanticMemory) -> None:
    deleted = await memory.delete("never_existed")
    assert deleted is False


async def test_close(memory: SemanticMemory) -> None:
    await memory.close()  # should not raise
