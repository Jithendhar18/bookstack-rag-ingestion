"""Query service - retrieval and answer generation."""

from __future__ import annotations

from typing import Any, Optional

from app.config.logging import get_logger
from app.domain.repositories import IQueryCacheRepository
from app.infrastructure.embeddings import IEmbeddingService
from app.infrastructure.external import ILLMClient, IRerankerClient
from app.infrastructure.vector_store import IVectorStore
from app.services.document_service import DocumentService

logger = get_logger(__name__)


class QueryResult:
    """Represents final query result with answer and sources."""

    def __init__(
        self,
        query: str,
        answer: Optional[str] = None,
        sources: Optional[list[dict[str, Any]]] = None,
        retrieval_time_ms: float = 0.0,
        total_time_ms: float = 0.0,
        cache_hit: bool = False,
    ):
        self.query = query
        self.answer = answer
        self.sources = sources or []
        self.retrieval_time_ms = retrieval_time_ms
        self.total_time_ms = total_time_ms
        self.cache_hit = cache_hit

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response dict."""
        return {
            "query": self.query,
            "answer": self.answer,
            "sources": self.sources,
            "retrieval_time_ms": round(self.retrieval_time_ms, 2),
            "total_time_ms": round(self.total_time_ms, 2),
            "cache_hit": self.cache_hit,
        }


class QueryService:
    """
    Query orchestration service.

    Responsibilities:
    - Handle RAG query pipeline: retrieve → rerank → generate
    - Manage query caching
    - Coordinate with embedding, retrieval, and LLM services
    """

    def __init__(
        self,
        embedding_service: IEmbeddingService,
        vector_store: IVectorStore,
        document_service: DocumentService,
        cache_repo: IQueryCacheRepository,
        llm_client: Optional[ILLMClient] = None,
        reranker_client: Optional[IRerankerClient] = None,
    ):
        """Initialize query service.

        Args:
            embedding_service: Service for query embeddings
            vector_store: Vector store for similarity search
            document_service: Document service for metadata
            cache_repo: Query cache repository
            llm_client: Optional LLM for answer generation
            reranker_client: Optional reranker for result ranking
        """
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.document_service = document_service
        self.cache_repo = cache_repo
        self.llm_client = llm_client
        self.reranker_client = reranker_client

    def query(
        self,
        query: str,
        top_k: int = 5,
        enable_reranking: bool = False,
        enable_generation: bool = False,
        use_cache: bool = True,
    ) -> QueryResult:
        """
        Execute full RAG query: retrieve, optionally rerank and generate.

        Args:
            query: Natural language query
            top_k: Number of results to retrieve
            enable_reranking: Whether to apply reranking
            enable_generation: Whether to generate answer with LLM
            use_cache: Whether to use cached results

        Returns:
            QueryResult with answer and sources
        """
        import time

        start_time = time.time()

        # Check cache first
        if use_cache:
            cached = self._get_cached_result(query)
            if cached:
                return QueryResult(
                    query=query,
                    answer=cached.get("answer"),
                    sources=cached.get("sources"),
                    cache_hit=True,
                    total_time_ms=(time.time() - start_time) * 1000,
                )

        # Step 1: Embed query
        logger.info("query.executing", query_preview=query[:100])
        query_embedding = self.embedding_service.embed_text(query)
        if not query_embedding:
            logger.error("query.embed_failed")
            return QueryResult(query=query)

        # Step 2: Retrieve chunks
        retrieval_start = time.time()
        chunks_with_scores = self.vector_store.search(query_embedding, top_k=top_k * 2)
        retrieval_time = (time.time() - retrieval_start) * 1000

        if not chunks_with_scores:
            logger.info("query.no_results")
            return QueryResult(query=query, retrieval_time_ms=retrieval_time)

        # Step 3: Optional reranking
        if enable_reranking and self.reranker_client:
            chunks_with_scores = self._rerank_results(query, chunks_with_scores, top_k)

        # Limit to top_k
        chunks_with_scores = chunks_with_scores[:top_k]

        # Extract sources
        sources = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.chunk_text,
                "score": round(score, 4),
            }
            for chunk, score in chunks_with_scores
        ]

        # Step 4: Optional answer generation
        answer = None
        if enable_generation and self.llm_client:
            context = "\n\n".join([chunk.chunk_text for chunk, _ in chunks_with_scores])
            answer = self.llm_client.generate(query, context=context)

        result = QueryResult(
            query=query,
            answer=answer,
            sources=sources,
            retrieval_time_ms=retrieval_time,
            total_time_ms=(time.time() - start_time) * 1000,
        )

        # Cache result
        if use_cache:
            self._cache_result(query, result)

        return result

    def _rerank_results(
        self,
        query: str,
        chunks: list[tuple[Any, float]],
        top_k: int,
    ) -> list[tuple[Any, float]]:
        """Apply reranking to retrieved chunks.

        Args:
            query: Original query
            chunks: List of (chunk, score) from retrieval
            top_k: Number of results after reranking

        Returns:
            Reranked list of (chunk, score)
        """
        if not self.reranker_client or not chunks:
            return chunks

        texts = [chunk.chunk_text for chunk, _ in chunks]
        reranked = self.reranker_client.rerank(query, texts, top_k=top_k)

        # Map back to chunk objects
        result = []
        for text, score in reranked:
            for chunk, _ in chunks:
                if chunk.chunk_text == text:
                    result.append((chunk, score))
                    break

        return result

    def _get_cached_result(self, query: str) -> Optional[dict[str, Any]]:
        """Retrieve cached query result.

        Args:
            query: Query to look up

        Returns:
            Cached result dict or None
        """
        import hashlib
        import json

        query_hash = hashlib.sha256(query.encode()).hexdigest()
        cached = self.cache_repo.get_by_hash(query_hash)

        if not cached:
            return None

        # Check expiration
        from datetime import datetime, timezone

        if cached.is_expired(datetime.now(timezone.utc)):
            self.cache_repo.delete(cached.cache_id)
            return None

        return json.loads(cached.results)

    def _cache_result(self, query: str, result: QueryResult) -> None:
        """Cache query result.

        Args:
            query: Query string
            result: QueryResult to cache
        """
        import hashlib
        import json
        from datetime import datetime, timedelta, timezone

        query_hash = hashlib.sha256(query.encode()).hexdigest()
        cache_id = hashlib.sha256(f"{query_hash}:{datetime.now(timezone.utc)}".encode()).hexdigest()

        from app.domain.entities import QueryCache

        cache_ttl = 3600  # 1 hour
        cache = QueryCache(
            cache_id=cache_id,
            query_hash=query_hash,
            query_text=query,
            results=json.dumps(result.to_dict()),
            ttl_seconds=cache_ttl,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=cache_ttl),
            created_at=datetime.now(timezone.utc),
        )

        try:
            self.cache_repo.set(cache)
        except Exception as e:
            logger.warning("query.cache_failed", error=str(e))
