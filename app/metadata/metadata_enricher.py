from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.chunking.chunking_engine import TextChunk
from app.loaders.document_loader import LoadedDocument


class ChunkMetadata(BaseModel):
    """Metadata attached to each enriched text chunk."""

    page_id: int
    title: str
    book_slug: str | None = None
    chapter_id: int | None = None
    chunk_index: int
    source_url: str
    section_path: str = ""  # Hierarchical section path (e.g., "Overview > PreAlert")
    section_level: int = 1  # Heading level of the section
    document_title: str = ""  # Full document title for context
    tokens_count: int = 0  # Token count for this chunk


class EnrichedChunk(BaseModel):
    """A text chunk enriched with full metadata and a unique ID."""

    chunk_id: str
    chunk_text: str
    metadata: ChunkMetadata


class MetadataEnricher:
    """Enriches text chunks with document and section metadata."""

    def __init__(self) -> None:
        pass

    def enrich(
        self,
        document: LoadedDocument,
        chunks: list[TextChunk],
        section_path: str = "",
        section_level: int = 1,
    ) -> list[EnrichedChunk]:
        """
        Enrich chunks with comprehensive metadata.

        Args:
            document: Loaded document
            chunks: Text chunks
            section_path: Hierarchical section path (e.g., "Overview > PreAlert")
            section_level: Heading level (1-6)

        Returns:
            List of enriched chunks
        """
        enriched: list[EnrichedChunk] = []

        for chunk in chunks:
            metadata = ChunkMetadata(
                page_id=document.page_id,
                title=document.title,
                book_slug=document.book_slug,
                chapter_id=document.chapter_id,
                chunk_index=chunk.chunk_index,
                source_url=document.source_url,
                section_path=section_path,
                section_level=section_level,
                document_title=document.title,
                tokens_count=chunk.end_token - chunk.start_token,
            )

            chunk_id = f"{document.page_id}:{chunk.chunk_index}"
            enriched.append(
                EnrichedChunk(
                    chunk_id=chunk_id,
                    chunk_text=chunk.text,
                    metadata=metadata,
                )
            )

        return enriched

    @staticmethod
    def to_chroma_metadata(metadata: ChunkMetadata) -> dict[str, Any]:
        """
        Convert metadata to Chroma-compatible format.

        Args:
            metadata: Chunk metadata

        Returns:
            Dictionary compatible with Chroma metadata filtering
        """
        return {
            "page_id": metadata.page_id,
            "title": metadata.title,
            "book_slug": metadata.book_slug or "",
            "chapter_id": metadata.chapter_id if metadata.chapter_id is not None else -1,
            "chunk_index": metadata.chunk_index,
            "source_url": metadata.source_url,
            "section_path": metadata.section_path,
            "section_level": metadata.section_level,
            "document_title": metadata.document_title,
            "tokens_count": metadata.tokens_count,
        }
