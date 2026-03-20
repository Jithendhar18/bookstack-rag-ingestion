"""Document domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DocumentChunk:
    """Represents a text chunk extracted from a document."""

    chunk_id: int
    page_id: int
    chunk_index: int
    chunk_text: str
    vector_id: str
    created_at: datetime

    def __hash__(self) -> int:
        """Make chunks hashable by their ID."""
        return hash(self.chunk_id)


@dataclass
class Document:
    """Represents a BookStack page/document."""

    page_id: int
    title: str
    updated_at: datetime
    last_synced_at: datetime
    book_slug: Optional[str] = None
    chapter_id: Optional[int] = None
    chunks: list[DocumentChunk] = field(default_factory=list)

    def __hash__(self) -> int:
        """Make documents hashable by their ID."""
        return hash(self.page_id)

    def needs_update(self, source_updated_at: datetime) -> bool:
        """Check if document needs updating based on source timestamp."""
        return source_updated_at > self.updated_at
