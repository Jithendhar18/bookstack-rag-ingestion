from __future__ import annotations

import time
from typing import Any, Optional

import chromadb
from chromadb.api.models.Collection import Collection

from app.config.logging import get_logger
from app.config.settings import Settings
from app.metadata.metadata_enricher import EnrichedChunk, MetadataEnricher

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0


class VectorStore:
    """ChromaDB-backed vector store for document chunk embeddings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if self.settings.chroma_use_http:
            self.client = chromadb.HttpClient(
                host=self.settings.chroma_host,
                port=self.settings.chroma_port,
                settings=chromadb.Settings(
                    chroma_client_auth_provider=None,
                    anonymized_telemetry=False,
                ),
            )
        else:
            self.client = chromadb.PersistentClient(path=self.settings.chroma_path)

        self.collection: Collection = self.client.get_or_create_collection(
            name=self.settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def search(
        self,
        embedding: list[float],
        top_k: int = 10,
        where: Optional[dict[str, Any]] = None,
    ) -> list[tuple[str, dict[str, Any], float]]:
        """Search for similar chunks by embedding vector.

        Args:
            embedding: Query embedding vector.
            top_k: Maximum number of results to return.
            where: Optional ChromaDB where clause for metadata filtering.

        Returns:
            List of (doc_id, metadata, distance) tuples sorted by distance ascending.
        """
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k,
        }
        if where:
            query_kwargs["where"] = where

        try:
            results = self._query_with_retry(**query_kwargs)
        except Exception as exc:
            logger.error("vector_store.search_failed", error=str(exc))
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)

        return list(zip(ids, metadatas, distances))

    def delete_page_chunks(self, page_id: int) -> None:
        """Delete all chunks for a given page from the vector store."""
        self.collection.delete(where={"page_id": page_id})

    def delete_chunks_by_ids(self, chunk_ids: list[str]) -> None:
        """Delete specific chunks by their IDs."""
        if not chunk_ids:
            return
        self.collection.delete(ids=chunk_ids)

    def upsert_chunks(
        self, chunks: list[EnrichedChunk], embeddings: list[list[float]]
    ) -> list[str]:
        """Insert or update chunks with their embeddings in the vector store."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        if not chunks:
            return []

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.chunk_text)
            metadatas.append(MetadataEnricher.to_chroma_metadata(chunk.metadata))

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                return ids
            except Exception as exc:
                last_error = exc
                if attempt >= _MAX_RETRIES:
                    break
                logger.warning(
                    "vector_store.upsert_retry",
                    attempt=attempt,
                    error=str(exc),
                )
                time.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))

        logger.error("vector_store.upsert_failed", error=str(last_error))
        raise last_error

    def _query_with_retry(self, **kwargs) -> dict:
        """Execute a ChromaDB query with retry for transient errors."""
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self.collection.query(**kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= _MAX_RETRIES:
                    break
                logger.warning(
                    "vector_store.query_retry",
                    attempt=attempt,
                    error=str(exc),
                )
                time.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
        raise last_error
