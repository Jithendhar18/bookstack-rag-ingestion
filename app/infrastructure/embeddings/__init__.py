"""Embedding service abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class IEmbeddingService(ABC):
    """Interface for embedding operations."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed single text to vector."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently."""

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Get dimension of embeddings (e.g., 1536 for OpenAI)."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if embedding service is healthy."""
