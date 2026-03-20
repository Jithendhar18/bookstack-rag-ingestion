"""Vector store abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.domain.entities import DocumentChunk


class IVectorStore(ABC):
    """Interface for vector store operations."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[tuple[DocumentChunk, float]]:
        """Search for similar vectors. Returns list of (chunk, score) tuples."""

    @abstractmethod
    def upsert_chunks(
        self, chunks: list[DocumentChunk], embeddings: list[list[float]]
    ) -> list[str]:
        """Upsert chunks with embeddings. Returns list of vector IDs."""

    @abstractmethod
    def delete_page_chunks(self, page_id: int) -> int:
        """Delete all chunks for a page. Returns count deleted."""

    @abstractmethod
    def delete_chunk(self, vector_id: str) -> bool:
        """Delete specific chunk by vector ID."""

    @abstractmethod
    def get_collection_size(self) -> int:
        """Get total number of vectors in collection."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if vector store is healthy."""
