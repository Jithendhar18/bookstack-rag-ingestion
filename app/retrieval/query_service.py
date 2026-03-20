"""Query orchestration service for retrieval + generation."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from app.config.logging import get_logger
from app.config.settings import Settings
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import ChunkResult, Retriever

logger = get_logger(__name__)


class QueryResponse:
    """Response from a query."""

    def __init__(
        self,
        query: str,
        results: list[ChunkResult],
        answer: Optional[str] = None,
        metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        self.query = query
        self.results = results
        self.answer = answer
        self.metrics = metrics or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "num_results": len(self.results),
            "results": [r.to_dict() for r in self.results],
            "answer": self.answer,
            "metrics": self.metrics,
        }


class QueryCache:
    """In-memory query result cache with LRU eviction and bounded size."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.cache: dict[str, tuple[QueryResponse, float]] = {}

    def get(self, key: str) -> Optional[QueryResponse]:
        """Get cached response if exists and not expired."""
        if key not in self.cache:
            return None

        response, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            del self.cache[key]
            return None

        return response

    def set(self, key: str, response: QueryResponse) -> None:
        """Cache response with current timestamp, evicting oldest if at capacity."""
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Evict the oldest entry
            oldest_key = min(self.cache, key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]

        self.cache[key] = (response, time.time())

    def clear(self) -> None:
        """Clear all cached responses."""
        self.cache.clear()

    def evict_expired(self) -> int:
        """Actively remove all expired entries. Returns count of evicted entries."""
        now = time.time()
        expired_keys = [k for k, (_, ts) in self.cache.items() if now - ts > self.ttl_seconds]
        for k in expired_keys:
            del self.cache[k]
        return len(expired_keys)

    @staticmethod
    def compute_key(query: str, top_k: int, filters: Optional[dict] = None) -> str:
        """Compute cache key from query parameters."""
        key_data = {
            "query": query,
            "top_k": top_k,
            "filters": filters,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()


class QueryService:
    """
    Orchestrates retrieval, reranking, and LLM generation.
    Provides high-level query interface.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self.embedding_service = embedding_service
        self.vector_store = vector_store

        # Initialize retriever
        self.retriever = Retriever(embedding_service, vector_store, settings)

        # Initialize optional reranker
        self.reranker: Optional[Reranker] = None
        if settings.enable_reranking:
            self.reranker = Reranker(settings.reranker_model)

        # Initialize optional LLM
        self.llm_generator = None
        if settings.enable_llm_generation:
            from app.llm.answer_generator import AnswerGenerator

            self.llm_generator = AnswerGenerator(settings)

        # Initialize query cache
        self.query_cache: Optional[QueryCache] = None
        if settings.enable_query_cache:
            self.query_cache = QueryCache(settings.query_result_cache_ttl)

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
        use_llm: bool = False,
        use_cache: bool = True,
        keyword_boost: bool = False,
    ) -> QueryResponse:
        """
        Execute query with retrieval, optional reranking, and optional LLM.

        Args:
            query_text: Natural language query
            top_k: Number of results
            filters: Metadata filters
            use_llm: Generate answer with LLM
            use_cache: Use query cache
            keyword_boost: Boost results matching keywords

        Returns:
            QueryResponse with results and optional answer
        """
        query_start = time.time()
        metrics = {}

        # Check cache
        cache_key: Optional[str] = None
        if use_cache and self.query_cache:
            cache_key = QueryCache.compute_key(
                query_text, top_k or self.settings.top_k_default, filters
            )
            cached = self.query_cache.get(cache_key)
            if cached:
                logger.debug("query.cache_hit", query_preview=query_text[:50])
                metrics["cache_hit"] = True
                return cached

        # Retrieve
        retrieval_start = time.time()
        chunks = self.retriever.retrieve(
            query_text,
            top_k=top_k,
            filters=filters,
            keyword_boost=keyword_boost,
        )
        retrieval_time = time.time() - retrieval_start
        metrics["retrieval_time_ms"] = round(retrieval_time * 1000, 2)

        # Rerank if enabled
        if self.reranker and chunks:
            rerank_start = time.time()
            chunk_tuples = [(c, c.chunk_text) for c in chunks]
            reranked_tuples = self.reranker.rerank(
                query_text,
                chunk_tuples,
                top_k=len(chunks),
            )
            chunks = [
                ChunkResult(
                    chunk_id=original.chunk_id,
                    chunk_text=original.chunk_text,
                    metadata=original.metadata,
                    score=new_score,
                )
                for original, new_score in reranked_tuples
            ]
            rerank_time = time.time() - rerank_start
            metrics["reranking_time_ms"] = round(rerank_time * 1000, 2)

        # Generate answer if LLM enabled
        answer = None
        if use_llm and self.llm_generator and chunks:
            llm_start = time.time()
            answer = self.llm_generator.generate(query_text, chunks)
            llm_time = time.time() - llm_start
            metrics["llm_time_ms"] = round(llm_time * 1000, 2)

        # Compile response
        total_time = time.time() - query_start
        metrics["total_time_ms"] = round(total_time * 1000, 2)
        metrics["num_results"] = len(chunks)

        response = QueryResponse(
            query=query_text,
            results=chunks,
            answer=answer,
            metrics=metrics,
        )

        # Cache response
        if use_cache and self.query_cache and cache_key:
            self.query_cache.set(cache_key, response)

        logger.info(
            "query.complete",
            results=len(chunks),
            total_ms=metrics["total_time_ms"],
            retrieval_ms=metrics["retrieval_time_ms"],
            llm_ms=metrics.get("llm_time_ms", 0),
        )

        return response

    def clear_cache(self) -> None:
        """Clear query result cache."""
        if self.query_cache:
            self.query_cache.clear()
            logger.info("query_cache.cleared")

    def get_cache_stats(self) -> Optional[dict[str, int]]:
        """Get query cache statistics."""
        if self.query_cache:
            return {
                "size": len(self.query_cache.cache),
                "ttl_seconds": self.query_cache.ttl_seconds,
            }
        return None
