from __future__ import annotations

import re
from dataclasses import dataclass

from app.config.settings import Settings
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService


@dataclass
class RetrievedChunk:
    chunk_text: str
    page_id: int
    title: str
    source_url: str
    score: float


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self._base_url = settings.bookstack_url.rstrip("/")

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = top_k or self.settings.rag_top_k
        query_embedding = self.embedding_service.embed_text(question)
        results = self.vector_store.query(query_embedding=query_embedding, n_results=k)

        chunks: list[RetrievedChunk] = []
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            score = round(1.0 - dist, 4)

            if score < self.settings.rag_min_score:
                continue

            page_id = int(meta["page_id"])
            chunks.append(
                RetrievedChunk(
                    chunk_text=_clean_text(doc),
                    page_id=page_id,
                    title=str(meta.get("title", "Untitled")),
                    source_url=self._build_page_url(page_id, meta),
                    score=score,
                )
            )

        return chunks

    def _build_page_url(self, page_id: int, meta: dict) -> str:
        stored_url = str(meta.get("source_url", ""))
        if stored_url and stored_url != self._base_url:
            return stored_url
        return f"{self._base_url}/link/{page_id}"


def _clean_text(text: str) -> str:
    """Remove HTML artifacts and normalize whitespace for clean display."""
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\u00a0", " ", text)
    return text.strip()
