"""Optional reranking for search results using cross-encoders."""

from __future__ import annotations

import threading
from typing import Any, Optional

from app.config.logging import get_logger

logger = get_logger(__name__)


class Reranker:
    """
    Reranker uses a cross-encoder to reorder search results.
    Optional feature for improving result relevance.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large") -> None:
        """
        Initialize reranker.

        Args:
            model_name: HuggingFace cross-encoder model name
        """
        self.model_name = model_name
        self._model = None
        self._model_lock = threading.Lock()

    def rerank(
        self,
        query: str,
        chunks_with_texts: list[tuple[Any, str]],
        top_k: int | None = None,
    ) -> list[tuple[Any, float]]:
        """
        Rerank chunks based on relevance to query.

        Args:
            query: User query
            chunks_with_texts: List of (chunk_object, text) tuples
            top_k: Return top_k reranked results

        Returns:
            List of (chunk_object, reranker_score) sorted by score
        """
        if not chunks_with_texts:
            return []

        try:
            model = self._get_model()
        except ImportError:
            logger.warning(
                "sentence-transformers not available. Skipping reranking. "
                "Install: pip install sentence-transformers"
            )
            # Fallback: return original order with dummy scores
            return [(chunk, 1.0) for chunk, _ in chunks_with_texts]

        # Prepare pairs for reranker
        pairs = [[query, text] for _, text in chunks_with_texts]

        # Score pairs
        logger.debug("reranker.scoring", count=len(pairs), model=self.model_name)
        scores = model.predict(pairs)

        # Combine chunks with scores and sort by score descending
        reranked = [
            (chunks_with_texts[i][0], float(scores[i])) for i in range(len(chunks_with_texts))
        ]
        reranked.sort(key=lambda x: x[1], reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked

    def _get_model(self):
        """Lazy load cross-encoder model (thread-safe)."""
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    logger.info("reranker.loading_model", model=self.model_name)
                    self._model = CrossEncoder(self.model_name)

        return self._model
