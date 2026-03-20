"""Embedding cache layer supporting in-memory and optional Redis storage."""

from __future__ import annotations

import hashlib
import json
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class EmbeddingCache(ABC):
    """Abstract base for embedding caches."""

    @abstractmethod
    def get(self, key: str) -> list[float] | None:
        """Get embedding from cache."""
        pass

    @abstractmethod
    def set(self, key: str, embedding: list[float]) -> None:
        """Store embedding in cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached embeddings."""
        pass

    @staticmethod
    def hash_text(text: str) -> str:
        """Generate deterministic hash key for text."""
        return hashlib.sha256(text.encode()).hexdigest()


class InMemoryEmbeddingCache(EmbeddingCache):
    """Thread-safe in-memory embedding cache with LRU eviction."""

    def __init__(self, max_size: int = 10000) -> None:
        self.max_size = max_size
        self.cache: OrderedDict[str, list[float]] = OrderedDict()
        self.hit_count = 0
        self.miss_count = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> list[float] | None:
        """Get embedding from cache (moves to end for LRU)."""
        with self._lock:
            if key in self.cache:
                self.hit_count += 1
                self.cache.move_to_end(key)
                return self.cache[key]
            self.miss_count += 1
            return None

    def set(self, key: str, embedding: list[float]) -> None:
        """Store embedding in cache, evicting LRU entry if needed."""
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = embedding
                return

            if len(self.cache) >= self.max_size:
                evicted_key, _ = self.cache.popitem(last=False)
                logger.debug("embedding_cache.evicted", key=evicted_key)

            self.cache[key] = embedding

    def clear(self) -> None:
        """Clear all cached embeddings."""
        with self._lock:
            self.cache.clear()
            self.hit_count = 0
            self.miss_count = 0
        logger.info("embedding_cache.cleared")

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self.hit_count + self.miss_count
            hit_rate = (self.hit_count / total * 100) if total > 0 else 0
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hit_count,
                "misses": self.miss_count,
                "hit_rate_percent": round(hit_rate, 2),
            }


class RedisEmbeddingCache(EmbeddingCache):
    """Redis-backed embedding cache (optional, requires redis-py)."""

    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_seconds: int = 86400) -> None:
        """
        Initialize Redis cache.

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Time-to-live for cached embeddings (default: 24h)
        """
        try:
            import redis

            self.redis_client = redis.from_url(redis_url, decode_responses=False)
            self.ttl_seconds = ttl_seconds
            self.hit_count = 0
            self.miss_count = 0
            logger.info("redis_cache.initialized", url=redis_url)
        except ImportError:
            raise ImportError(
                "redis-py is required for RedisEmbeddingCache. Install: pip install redis"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to Redis at {redis_url}: {exc}")

    def get(self, key: str) -> list[float] | None:
        """Get embedding from Redis cache."""
        try:
            value = self.redis_client.get(key)
            if value:
                self.hit_count += 1
                embedding = json.loads(value)
                return embedding
            self.miss_count += 1
            return None
        except Exception as exc:
            logger.warning("redis_cache.get_failed", error=str(exc))
            return None

    def set(self, key: str, embedding: list[float]) -> None:
        """Store embedding in Redis cache."""
        try:
            value = json.dumps(embedding)
            self.redis_client.setex(key, self.ttl_seconds, value)
        except Exception as exc:
            logger.warning("redis_cache.set_failed", error=str(exc))

    def clear(self) -> None:
        """Clear all cached embeddings in Redis."""
        try:
            self.redis_client.flushdb()
            self.hit_count = 0
            self.miss_count = 0
            logger.info("redis_cache.cleared")
        except Exception as exc:
            logger.warning("redis_cache.flush_failed", error=str(exc))

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        try:
            db_info = self.redis_client.info("keyspace")
            size = (
                db_info.get("db0", {}).get("keys", 0) if isinstance(db_info.get("db0"), dict) else 0
            )
        except Exception:
            size = 0

        return {
            "size": size,
            "hits": self.hit_count,
            "misses": self.miss_count,
            "hit_rate_percent": round(hit_rate, 2),
            "backend": "redis",
        }


class EmbeddingCacheFactory:
    """Factory for creating embedding caches."""

    @staticmethod
    def create(cache_type: str = "memory", **kwargs: Any) -> EmbeddingCache:
        """
        Create embedding cache instance.

        Args:
            cache_type: "memory" or "redis"
            **kwargs: Cache-specific arguments

        Returns:
            EmbeddingCache instance
        """
        if cache_type == "memory":
            max_size = kwargs.get("max_size", 10000)
            return InMemoryEmbeddingCache(max_size=max_size)
        elif cache_type == "redis":
            redis_url = kwargs.get("redis_url", "redis://localhost:6379")
            ttl_seconds = kwargs.get("ttl_seconds", 86400)
            return RedisEmbeddingCache(redis_url=redis_url, ttl_seconds=ttl_seconds)
        else:
            raise ValueError(f"Unknown cache type: {cache_type}. Use 'memory' or 'redis'.")
