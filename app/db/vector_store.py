from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from app.config.settings import Settings
from app.metadata.metadata_enricher import EnrichedChunk, MetadataEnricher


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if self.settings.chroma_use_http:
            self.client = chromadb.HttpClient(
                host=self.settings.chroma_host,
                port=self.settings.chroma_port,
            )
        else:
            self.client = chromadb.PersistentClient(path=self.settings.chroma_path)

        self.collection: Collection = self.client.get_or_create_collection(
            name=self.settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_page_chunks(self, page_id: int) -> None:
        self.collection.delete(where={"page_id": page_id})

    def delete_chunks_by_ids(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self.collection.delete(ids=chunk_ids)

    def upsert_chunks(self, chunks: list[EnrichedChunk], embeddings: list[list[float]]) -> list[str]:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        if not chunks:
            return []

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.chunk_text)
            metadatas.append(MetadataEnricher.to_chroma_metadata(chunk.metadata))

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        return ids
