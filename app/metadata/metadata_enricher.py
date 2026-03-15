from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.chunking.chunking_engine import TextChunk
from app.loaders.document_loader import LoadedDocument


class ChunkMetadata(BaseModel):
    page_id: int
    title: str
    book_slug: str | None = None
    chapter_id: int | None = None
    chunk_index: int
    source_url: str


class EnrichedChunk(BaseModel):
    chunk_id: str
    chunk_text: str
    metadata: ChunkMetadata


class MetadataEnricher:
    def enrich(self, document: LoadedDocument, chunks: list[TextChunk]) -> list[EnrichedChunk]:
        enriched: list[EnrichedChunk] = []

        for chunk in chunks:
            metadata = ChunkMetadata(
                page_id=document.page_id,
                title=document.title,
                book_slug=document.book_slug,
                chapter_id=document.chapter_id,
                chunk_index=chunk.chunk_index,
                source_url=document.source_url,
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
        return {
            "page_id": metadata.page_id,
            "title": metadata.title,
            "book_slug": metadata.book_slug or "",
            "chapter_id": metadata.chapter_id if metadata.chapter_id is not None else -1,
            "chunk_index": metadata.chunk_index,
            "source_url": metadata.source_url,
        }
