"""MemoryStore abstract base class.

Defines the interface that both structured (SQLite) and semantic
(markdown + embeddings) memory implementations must satisfy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoryStore(ABC):
    """Abstract base for memory backends.

    Every memory implementation supports basic CRUD operations.
    Semantic memory adds ``search`` with relevance ranking.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Set up the backing store (create tables, load indexes, etc.)."""

    @abstractmethod
    async def store(self, key: str, value: Any, *, category: str = "general") -> None:
        """Store a fact or memory entry.

        Args:
            key: Unique identifier for this memory.
            value: The data to store.
            category: Grouping category.
        """

    @abstractmethod
    async def retrieve(self, key: str) -> Any | None:
        """Retrieve a memory entry by key.

        Args:
            key: The identifier to look up.

        Returns:
            The stored value, or None if not found.
        """

    @abstractmethod
    async def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search for memory entries matching a query.

        Args:
            query: Search string (exact match for structured, semantic for embeddings).
            limit: Maximum results to return.

        Returns:
            List of matching entries as dicts.
        """

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a memory entry.

        Args:
            key: The identifier to delete.

        Returns:
            True if the entry existed and was deleted.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the store."""
