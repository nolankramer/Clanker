"""Semantic memory — markdown files indexed with local embeddings.

Memory entries are stored as markdown files in a configurable directory,
one file per topic/entity/day. Files are indexed into a ChromaDB collection
with embeddings from a local model (e.g. nomic-embed-text via Ollama).

Markdown format is chosen because it's greppable, diffable, human-editable,
and git-friendly — which matters when debugging what the system remembers.

TODO:
- Implement embedding generation via Ollama or sentence-transformers
- Implement ChromaDB collection management
- Add incremental re-indexing (only re-embed changed files)
- Add metadata extraction from markdown frontmatter
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from clanker.memory.base import MemoryStore

logger = structlog.get_logger(__name__)


class SemanticMemory(MemoryStore):
    """Markdown + embeddings memory store.

    Files are stored in ``markdown_dir`` and indexed into ChromaDB
    for semantic search. The embedding pipeline is currently stubbed.
    """

    def __init__(
        self,
        markdown_dir: str,
        chromadb_path: str,
        embedding_model: str = "nomic-embed-text",
        embedding_base_url: str = "http://localhost:11434",
    ) -> None:
        """Initialize semantic memory.

        Args:
            markdown_dir: Directory for markdown memory files.
            chromadb_path: Path to ChromaDB persistent storage.
            embedding_model: Name of the embedding model.
            embedding_base_url: URL of the embedding service (Ollama).
        """
        self._markdown_dir = Path(markdown_dir)
        self._chromadb_path = chromadb_path
        self._embedding_model = embedding_model
        self._embedding_base_url = embedding_base_url
        self._collection: Any = None  # TODO: chromadb.Collection

    async def initialize(self) -> None:
        """Create markdown directory and initialize ChromaDB collection."""
        self._markdown_dir.mkdir(parents=True, exist_ok=True)

        # TODO: Initialize ChromaDB client and collection
        # client = chromadb.PersistentClient(path=self._chromadb_path)
        # self._collection = client.get_or_create_collection(
        #     name="clanker_memory",
        #     embedding_function=OllamaEmbeddingFunction(...)
        # )

        logger.info(
            "semantic_memory.initialized",
            markdown_dir=str(self._markdown_dir),
            chromadb_path=self._chromadb_path,
        )

    async def store(self, key: str, value: Any, *, category: str = "general") -> None:
        """Store a memory entry as a markdown file.

        Args:
            key: Filename stem (sanitized for filesystem safety).
            value: Content to write.
            category: Subdirectory category.
        """
        category_dir = self._markdown_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize key for use as filename
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        file_path = category_dir / f"{safe_key}.md"

        content = str(value)
        now = datetime.now(tz=timezone.utc).isoformat()

        # Prepend metadata header
        header = f"---\nkey: {key}\ncategory: {category}\nupdated: {now}\n---\n\n"
        file_path.write_text(header + content, encoding="utf-8")

        # TODO: Embed and upsert into ChromaDB
        # self._collection.upsert(ids=[key], documents=[content], metadatas=[{...}])

        logger.debug("semantic_memory.stored", key=key, path=str(file_path))

    async def retrieve(self, key: str) -> Any | None:
        """Retrieve a memory entry by key (filename lookup).

        Args:
            key: Filename stem to look for.

        Returns:
            File content as string, or None if not found.
        """
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)

        # Search across all category subdirectories
        for md_file in self._markdown_dir.rglob(f"{safe_key}.md"):
            content = md_file.read_text(encoding="utf-8")
            # Strip YAML frontmatter if present
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].strip()
            return content
        return None

    async def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search memory entries semantically.

        Currently falls back to simple substring matching across files.
        Once embeddings are implemented, this will use ChromaDB similarity search.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching entries with filename, content snippet, and score.
        """
        # TODO: Use ChromaDB semantic search when embeddings are ready
        # results = self._collection.query(query_texts=[query], n_results=limit)

        # Fallback: simple substring search
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        for md_file in self._markdown_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            if query_lower in content.lower():
                results.append(
                    {
                        "key": md_file.stem,
                        "path": str(md_file.relative_to(self._markdown_dir)),
                        "content": content[:500],
                        "score": 1.0,  # Placeholder — real score from embeddings
                    }
                )
                if len(results) >= limit:
                    break

        return results

    async def delete(self, key: str) -> bool:
        """Delete a memory entry (file and ChromaDB record).

        Args:
            key: Filename stem to delete.

        Returns:
            True if the file existed and was deleted.
        """
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        deleted = False

        for md_file in self._markdown_dir.rglob(f"{safe_key}.md"):
            md_file.unlink()
            deleted = True
            logger.debug("semantic_memory.deleted", key=key, path=str(md_file))

        # TODO: Delete from ChromaDB
        # self._collection.delete(ids=[key])

        return deleted

    async def close(self) -> None:
        """Release resources."""
        # ChromaDB PersistentClient doesn't need explicit close
        logger.info("semantic_memory.closed")
