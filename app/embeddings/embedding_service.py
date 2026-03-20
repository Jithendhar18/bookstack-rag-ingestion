from __future__ import annotations

import threading
import time
from typing import Optional

from openai import OpenAI

from app.config.logging import get_logger
from app.config.settings import Settings
from app.utils.embedding_cache import EmbeddingCache, EmbeddingCacheFactory

logger = get_logger(__name__)


class EmbeddingService:
    """Generates text embeddings via OpenAI API or a local model, with optional caching."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = self.settings.embedding_provider.strip().lower()
        self._quota_exhausted = False
        self._local_model = None
        self._local_model_lock = threading.Lock()

        if self.provider == "openai":
            self.client = OpenAI(api_key=self.settings.openai_api_key, timeout=30.0)
        elif self.provider == "local":
            self.client = None
        else:
            raise ValueError("Unsupported embedding provider. Use 'openai' or 'local'.")

        # Initialize embedding cache
        self.cache: Optional[EmbeddingCache] = None
        if self.settings.enable_embedding_cache:
            try:
                self.cache = EmbeddingCacheFactory.create(
                    cache_type=self.settings.embedding_cache_type,
                    max_size=self.settings.embedding_cache_max_size,
                    redis_url=self.settings.embedding_cache_redis_url,
                    ttl_seconds=self.settings.embedding_cache_ttl_seconds,
                )
                logger.info(
                    "embedding_cache.enabled",
                    cache_type=self.settings.embedding_cache_type,
                    max_size=self.settings.embedding_cache_max_size,
                )
            except Exception as exc:
                logger.warning("embedding_cache.init_failed", error=str(exc))
                self.cache = None

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string and return its vector."""
        vectors = self.embed_batch([text])
        return vectors[0] if vectors else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, using cache when available."""
        if not texts:
            return []

        # Try cache for each text
        cached_results: dict[int, list[float]] = {}
        texts_to_embed: list[tuple[int, str]] = []

        if self.cache:
            for idx, text in enumerate(texts):
                cache_key = EmbeddingCache.hash_text(text)
                cached_embedding = self.cache.get(cache_key)
                if cached_embedding:
                    cached_results[idx] = cached_embedding
                    logger.debug("embedding_cache.hit", chunk_idx=idx)
                else:
                    texts_to_embed.append((idx, text))
        else:
            texts_to_embed = list(enumerate(texts))

        # Embed uncached texts
        if texts_to_embed:
            uncached_indices, uncached_texts = zip(*texts_to_embed)
            if self.provider == "local":
                embeddings = self._embed_batch_local(list(uncached_texts))
            else:
                embeddings = self._embed_batch_openai(list(uncached_texts))

            # Cache new embeddings
            if self.cache:
                for idx, text, embedding in zip(uncached_indices, uncached_texts, embeddings):
                    cache_key = EmbeddingCache.hash_text(text)
                    self.cache.set(cache_key, embedding)
                    cached_results[idx] = embedding
            else:
                for idx, embedding in zip(uncached_indices, embeddings):
                    cached_results[idx] = embedding

        # Reconstruct results in original order
        results = [cached_results[i] for i in range(len(texts))]
        return results

    def _embed_batch_openai(self, texts: list[str]) -> list[list[float]]:
        if self._quota_exhausted and self.settings.embedding_fail_fast_on_quota:
            raise RuntimeError(
                "OpenAI quota exhausted in this run; failing fast for remaining pages."
            )

        last_error: Exception | None = None
        for attempt in range(1, self.settings.embedding_max_retries + 1):
            try:
                response = self.client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=texts,
                )
                logger.info("embedding.openai_batch_complete", count=len(texts))
                return [item.embedding for item in response.data]
            except Exception as exc:  # noqa: BLE001 - intentionally retries provider errors
                if self._is_quota_error(exc):
                    self._quota_exhausted = True
                    if self.settings.embedding_fail_fast_on_quota:
                        raise RuntimeError(
                            "OpenAI quota exceeded. Update billing/key or switch EMBEDDING_PROVIDER=local."
                        ) from exc

                last_error = exc
                if attempt >= self.settings.embedding_max_retries:
                    break
                sleep_seconds = self.settings.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "embedding.openai_retry",
                    attempt=attempt,
                    sleep_seconds=sleep_seconds,
                    error=str(exc),
                )
                time.sleep(sleep_seconds)

        if last_error is not None:
            raise last_error

        return []

    def _embed_batch_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            with self._local_model_lock:
                if self._local_model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(
                        "embedding.loading_local_model", model=self.settings.local_embedding_model
                    )
                    self._local_model = SentenceTransformer(self.settings.local_embedding_model)

        vectors = self._local_model.encode(texts, normalize_embeddings=True)
        logger.info("embedding.local_batch_complete", count=len(texts))
        return [vector.tolist() for vector in vectors]

    def get_cache_stats(self) -> Optional[dict]:
        """Get embedding cache statistics."""
        if self.cache:
            return self.cache.stats()
        return None

    def clear_cache(self) -> None:
        """Clear embedding cache."""
        if self.cache:
            self.cache.clear()
            logger.info("embedding_cache.cleared")

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "insufficient_quota" in message or "quota" in message
