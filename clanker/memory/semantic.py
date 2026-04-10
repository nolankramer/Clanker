"""Semantic memory — markdown files indexed with ChromaDB embeddings.

Memory entries are stored as markdown files (human-readable, git-friendly)
and indexed into a ChromaDB collection for vector similarity search.
Embeddings are generated via Ollama's embedding API (e.g. nomic-embed-text).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from clanker.memory.base import MemoryStore

logger = structlog.get_logger(__name__)


class _OllamaEmbedder:
    """Generate embeddings via Ollama's /api/embed endpoint."""

    def __init__(self, base_url: str, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model
        self._client = httpx.Client(timeout=30.0)
        self._dim: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        try:
            resp = self._client.post(
                self._url,
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                self._dim = len(embeddings[0])
            return embeddings  # type: ignore[no-any-return]
        except Exception:
            logger.warning("embedder.failed", model=self._model, exc_info=True)
            return []

    @property
    def available(self) -> bool:
        """Check if the embedding service is reachable."""
        try:
            resp = self._client.post(
                self._url,
                json={"model": self._model, "input": ["test"]},
            )
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self._client.close()


class SemanticMemory(MemoryStore):
    """Markdown + ChromaDB memory store.

    Files are stored in ``markdown_dir`` and indexed into ChromaDB
    for semantic search.  Falls back to substring matching if
    ChromaDB or embeddings are unavailable.
    """

    def __init__(
        self,
        markdown_dir: str,
        chromadb_path: str,
        embedding_model: str = "nomic-embed-text",
        embedding_base_url: str = "http://localhost:11434",
    ) -> None:
        self._markdown_dir = Path(markdown_dir)
        self._chromadb_path = chromadb_path
        self._embedding_model = embedding_model
        self._embedding_base_url = embedding_base_url
        self._collection: Any = None
        self._embedder: _OllamaEmbedder | None = None

    async def initialize(self) -> None:
        """Create markdown directory and initialize ChromaDB + embeddings."""
        self._markdown_dir.mkdir(parents=True, exist_ok=True)

        # Initialize embedder
        self._embedder = _OllamaEmbedder(
            self._embedding_base_url, self._embedding_model
        )

        # Initialize ChromaDB
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self._chromadb_path)
            self._collection = client.get_or_create_collection(
                name="clanker_memory",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "semantic_memory.chromadb_initialized",
                path=self._chromadb_path,
                count=self._collection.count(),
            )
        except Exception:
            logger.warning(
                "semantic_memory.chromadb_unavailable",
                exc_info=True,
            )

        # Index existing markdown files
        if self._collection is not None:
            await self._reindex()

        logger.info(
            "semantic_memory.initialized",
            markdown_dir=str(self._markdown_dir),
            chromadb=self._collection is not None,
            embeddings=self._embedder.available if self._embedder else False,
        )

    async def _reindex(self) -> None:
        """Index any unindexed markdown files into ChromaDB."""
        if not self._collection:
            return

        existing_ids = set(self._collection.get()["ids"])
        indexed = 0

        for md_file in self._markdown_dir.rglob("*.md"):
            doc_id = str(md_file.relative_to(self._markdown_dir))
            if doc_id in existing_ids:
                continue

            content = md_file.read_text(encoding="utf-8")
            body = self._strip_frontmatter(content)
            if not body.strip():
                continue

            self._upsert_doc(doc_id, body, {"path": str(md_file)})
            indexed += 1

        if indexed:
            logger.info("semantic_memory.reindexed", count=indexed)

    def _upsert_doc(
        self, doc_id: str, text: str, metadata: dict[str, str]
    ) -> None:
        """Insert or update a document in ChromaDB."""
        if not self._collection:
            return

        # Try embedding via Ollama
        if self._embedder:
            embeddings = self._embedder.embed([text])
            if embeddings:
                self._collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    embeddings=embeddings,
                    metadatas=[metadata],
                )
                return

        # Fallback: let ChromaDB use its default embedding
        self._collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata],
        )

    async def store(
        self, key: str, value: Any, *, category: str = "general"
    ) -> None:
        """Store a memory entry as a markdown file and index it."""
        category_dir = self._markdown_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        file_path = category_dir / f"{safe_key}.md"

        content = str(value)
        now = datetime.now(tz=UTC).isoformat()

        header = f"---\nkey: {key}\ncategory: {category}\nupdated: {now}\n---\n\n"
        file_path.write_text(header + content, encoding="utf-8")

        # Index in ChromaDB
        doc_id = f"{category}/{safe_key}.md"
        self._upsert_doc(doc_id, content, {"key": key, "category": category})

        logger.debug("semantic_memory.stored", key=key, path=str(file_path))

    async def retrieve(self, key: str) -> Any | None:
        """Retrieve a memory entry by key (filename lookup)."""
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)

        for md_file in self._markdown_dir.rglob(f"{safe_key}.md"):
            content = md_file.read_text(encoding="utf-8")
            return self._strip_frontmatter(content)
        return None

    async def search(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Search memory entries semantically via ChromaDB.

        Falls back to substring matching if ChromaDB is unavailable.
        """
        # Try ChromaDB semantic search
        if self._collection and self._collection.count() > 0:
            try:
                query_params: dict[str, Any] = {
                    "query_texts": [query],
                    "n_results": min(limit, self._collection.count()),
                }

                # Use Ollama embeddings if available
                if self._embedder:
                    embeddings = self._embedder.embed([query])
                    if embeddings:
                        query_params = {
                            "query_embeddings": embeddings,
                            "n_results": min(limit, self._collection.count()),
                        }

                results = self._collection.query(**query_params)

                entries: list[dict[str, Any]] = []
                ids = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for i, doc_id in enumerate(ids):
                    entries.append({
                        "key": doc_id,
                        "content": docs[i][:500] if i < len(docs) else "",
                        "score": 1.0 - (distances[i] if i < len(distances) else 0.0),
                        "path": doc_id,
                    })
                return entries
            except Exception:
                logger.warning("semantic_memory.search_failed", exc_info=True)

        # Fallback: substring search
        return self._substring_search(query, limit)

    def _substring_search(
        self, query: str, limit: int
    ) -> list[dict[str, Any]]:
        """Simple substring search across markdown files."""
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        for md_file in self._markdown_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            if query_lower in content.lower():
                results.append({
                    "key": md_file.stem,
                    "path": str(md_file.relative_to(self._markdown_dir)),
                    "content": content[:500],
                    "score": 0.5,
                })
                if len(results) >= limit:
                    break

        return results

    async def delete(self, key: str) -> bool:
        """Delete a memory entry (file and ChromaDB record)."""
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        deleted = False

        for md_file in self._markdown_dir.rglob(f"{safe_key}.md"):
            doc_id = str(md_file.relative_to(self._markdown_dir))
            md_file.unlink()
            deleted = True

            if self._collection:
                import contextlib

                with contextlib.suppress(Exception):
                    self._collection.delete(ids=[doc_id])

            logger.debug("semantic_memory.deleted", key=key)

        return deleted

    async def close(self) -> None:
        """Release resources."""
        if self._embedder:
            self._embedder.close()
        logger.info("semantic_memory.closed")

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content
