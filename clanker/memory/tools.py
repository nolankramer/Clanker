"""MCP tool wrappers for memory operations.

These functions are registered as MCP tools in the server, giving the
brain access to read/write/search memory.

TODO:
- Wire these into the MCP server tool registration
- Add more granular tools (face lookup, room lookup, etc.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clanker.memory.semantic import SemanticMemory
    from clanker.memory.structured import StructuredMemory

logger = structlog.get_logger(__name__)


class MemoryTools:
    """Tool wrappers that the MCP server registers for brain access."""

    def __init__(
        self,
        structured: StructuredMemory,
        semantic: SemanticMemory,
    ) -> None:
        """Initialize with both memory backends.

        Args:
            structured: SQLite-backed structured memory.
            semantic: Markdown + embeddings semantic memory.
        """
        self._structured = structured
        self._semantic = semantic

    async def memory_read(self, key: str) -> dict[str, Any]:
        """Read a memory entry, checking structured then semantic.

        Args:
            key: The memory key to look up.

        Returns:
            Dict with source and value.
        """
        # Try structured first
        value = await self._structured.retrieve(key)
        if value is not None:
            return {"source": "structured", "key": key, "value": value}

        # Fall back to semantic
        value = await self._semantic.retrieve(key)
        if value is not None:
            return {"source": "semantic", "key": key, "value": value}

        return {"source": "none", "key": key, "value": None}

    async def memory_write(
        self,
        key: str,
        value: str,
        *,
        store: str = "semantic",
    ) -> dict[str, str]:
        """Write a memory entry.

        Args:
            key: Memory key.
            value: Content to store.
            store: Which store to write to ("structured" or "semantic").

        Returns:
            Confirmation dict.
        """
        if store == "structured":
            await self._structured.store(key, value)
        else:
            await self._semantic.store(key, value)
        return {"status": "ok", "key": key, "store": store}

    async def memory_search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search across both memory stores.

        Args:
            query: Search query.
            limit: Maximum results per store.

        Returns:
            Combined results from both stores.
        """
        structured_results = await self._structured.search(query, limit=limit)
        semantic_results = await self._semantic.search(query, limit=limit)

        for r in structured_results:
            r["source"] = "structured"
        for r in semantic_results:
            r["source"] = "semantic"

        return structured_results + semantic_results
