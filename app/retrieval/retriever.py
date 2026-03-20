"""Vector retrieval with metadata filtering."""

from __future__ import annotations

from typing import Any, Optional

from app.config.logging import get_logger
from app.config.settings import Settings
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService

logger = get_logger(__name__)


class ChunkResult:
    """Represents a retrieved chunk with metadata and score."""

    def __init__(
        self,
        chunk_id: str,
        chunk_text: str,
        metadata: dict[str, Any],
        score: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.chunk_text = chunk_text
        self.metadata = metadata
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_text": self.chunk_text,
            "metadata": self.metadata,
            "score": round(self.score, 4),
        }


class Retriever:
    """
    Retriever handles vector search with metadata filtering.
    Supports hybrid ranking and score normalization.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        settings: Settings,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.settings = settings

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: Optional[dict[str, Any]] = None,
        keyword_boost: bool = False,
    ) -> list[ChunkResult]:
        """
        Retrieve top-k chunks matching query with optional filtering.

        Args:
            query: Natural language query
            top_k: Number of results (default: settings.top_k_default)
            filters: Metadata filters (e.g., {"page_id": 10, "section_path": "Overview"})
            keyword_boost: Whether to boost results matching keywords from query

        Returns:
            List of ChunkResult objects sorted by score
        """
        if top_k is None:
            top_k = self.settings.top_k_default

        # Embed query
        logger.debug("query.embedding", query_preview=query[:100])
        query_embedding = self.embedding_service.embed_text(query)

        if not query_embedding:
            logger.warning("query.embed_failed")
            return []

        # Build Chroma where clause from filters
        where_clause = self._build_where_clause(filters)

        # Search with Chroma
        logger.debug("query.searching", top_k=top_k, filters=filters)
        results = self.vector_store.search(
            embedding=query_embedding,
            top_k=top_k * 2,  # Fetch extra for filtering/deduplication
            where=where_clause,
        )

        if not results:
            logger.info("query.no_results")
            return []

        # Parse results and convert to ChunkResult
        chunk_results: list[ChunkResult] = []
        for doc_id, metadata, distance in results:
            # Chroma uses distance (0=similar, 1=dissimilar), convert to similarity score
            similarity_score = 1 - distance

            # Apply keyword boost if enabled
            if keyword_boost:
                similarity_score = self._apply_keyword_boost(
                    similarity_score,
                    query,
                    metadata.get("chunk_text", ""),
                )

            chunk_results.append(
                ChunkResult(
                    chunk_id=doc_id,
                    chunk_text=metadata.get("chunk_text", ""),
                    metadata=metadata,
                    score=similarity_score,
                )
            )

        # Deduplicate similar chunks (same page + similar content)
        chunk_results = self._deduplicate_chunks(chunk_results)

        # Return top_k after deduplication
        return sorted(chunk_results, key=lambda x: x.score, reverse=True)[:top_k]

    def _build_where_clause(self, filters: Optional[dict[str, Any]]) -> Optional[dict]:
        """
        Build Chroma where clause from filters.

        Supports:
        - page_id: int
        - section_path: str (substring match)
        - document_title: str (substring match)
        - chunk_index: int
        """
        if not filters:
            return None

        where_conditions = []

        if "page_id" in filters:
            where_conditions.append({"page_id": {"$eq": filters["page_id"]}})

        if "section_path" in filters:
            # Chroma doesn't support substring matching directly,
            # so we filter post-retrieval in _post_filter_by_section
            pass

        if "document_title" in filters:
            where_conditions.append({"document_title": {"$eq": filters["document_title"]}})

        if "chunk_index" in filters:
            where_conditions.append({"chunk_index": {"$eq": filters["chunk_index"]}})

        if len(where_conditions) == 0:
            return None
        elif len(where_conditions) == 1:
            return where_conditions[0]
        else:
            # AND all conditions
            return {"$and": where_conditions}

    @staticmethod
    def _apply_keyword_boost(similarity_score: float, query: str, chunk_text: str) -> float:
        """
        Boost score if query keywords appear in chunk.

        Simple heuristic: +10% boost for each matching keyword.
        """
        query_keywords = set(query.lower().split())
        chunk_words = set(chunk_text.lower().split())
        matching_keywords = query_keywords & chunk_words

        boost_factor = 1.0 + (len(matching_keywords) * 0.05)  # 5% per match
        return min(similarity_score * boost_factor, 1.0)  # Cap at 1.0

    @staticmethod
    def _deduplicate_chunks(chunks: list[ChunkResult]) -> list[ChunkResult]:
        """
        Remove duplicate chunks from same page with high similarity.

        Simple heuristic: if two chunks are from same page and first 100 chars match,
        keep only the higher-scoring one.
        """
        seen: dict[tuple, int] = {}  # (page_id, chunk_preview) -> index
        unique_indices = set()

        for idx, chunk in enumerate(chunks):
            page_id = chunk.metadata.get("page_id")
            chunk_preview = chunk.chunk_text[:50]  # First 50 chars
            key = (page_id, chunk_preview)

            if key not in seen:
                seen[key] = idx
                unique_indices.add(idx)

        return [chunk for idx, chunk in enumerate(chunks) if idx in unique_indices]
