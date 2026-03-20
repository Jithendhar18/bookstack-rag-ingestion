"""External client abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class IBookStackClient(ABC):
    """Interface for BookStack API operations."""

    @abstractmethod
    def get_pages(self, limit: int = 500) -> list[dict[str, Any]]:
        """Get all pages from BookStack."""

    @abstractmethod
    def get_page_content(self, page_id: int) -> str:
        """Get full HTML content of a page."""

    @abstractmethod
    def get_books(self) -> list[dict[str, Any]]:
        """Get all books."""

    @abstractmethod
    def get_chapters(self, book_id: int) -> list[dict[str, Any]]:
        """Get all chapters in a book."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if BookStack API is accessible."""


class ILLMClient(ABC):
    """Interface for Large Language Model operations."""

    @abstractmethod
    def generate(self, prompt: str, context: Optional[str] = None, temperature: float = 0.7) -> str:
        """Generate response from LLM."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if LLM service is healthy."""


class IRerankerClient(ABC):
    """Interface for query reranking operations."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[str], top_k: int = 5) -> list[tuple[str, float]]:
        """Rerank candidates by relevance to query. Returns list of (text, score) tuples."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if reranker service is healthy."""
