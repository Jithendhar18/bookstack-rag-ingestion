"""Document service - manages document lifecycle and retrieval."""

from __future__ import annotations

from typing import Optional

from app.config.logging import get_logger
from app.domain.entities import Document, DocumentChunk
from app.domain.repositories import IDocumentChunkRepository, IDocumentRepository
from app.infrastructure.vector_store import IVectorStore

logger = get_logger(__name__)


class DocumentService:
    """
    Service for document operations.

    Responsibilities:
    - Retrieve documents and chunks
    - Manage document metadata
    - Coordinate with vector store for chunk retrieval
    """

    def __init__(
        self,
        document_repo: IDocumentRepository,
        chunk_repo: IDocumentChunkRepository,
        vector_store: IVectorStore,
    ):
        """Initialize document service.

        Args:
            document_repo: Document repository for data access
            chunk_repo: Chunk repository for data access
            vector_store: Vector store for similarity search
        """
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.vector_store = vector_store

    def get_document(self, page_id: int) -> Optional[Document]:
        """Get document by page ID.

        Args:
            page_id: BookStack page ID

        Returns:
            Document or None if not found
        """
        return self.document_repo.get_by_page_id(page_id)

    def get_chunks_for_document(self, page_id: int) -> list[DocumentChunk]:
        """Get all chunks for a document.

        Args:
            page_id: BookStack page ID

        Returns:
            List of DocumentChunk entities
        """
        return self.chunk_repo.get_by_page_id(page_id)

    def store_document(self, document: Document) -> Document:
        """Store a new document.

        Args:
            document: Document entity to create

        Returns:
            Persisted Document with IDs populated
        """
        logger.info("document.storing", page_id=document.page_id, title=document.title)
        return self.document_repo.create(document)

    def store_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Store multiple chunks for a document (batch operation).

        Args:
            chunks: List of DocumentChunk entities to create

        Returns:
            List of persisted chunks with IDs populated
        """
        if not chunks:
            return []

        logger.info("chunks.storing", count=len(chunks), page_id=chunks[0].page_id)
        return self.chunk_repo.create_batch(chunks)

    def delete_document_chunks(self, page_id: int) -> int:
        """Delete all chunks for a document (during re-ingestion).

        Args:
            page_id: BookStack page ID

        Returns:
            Number of chunks deleted
        """
        logger.info("chunks.deleting", page_id=page_id)
        count = self.chunk_repo.delete_by_page_id(page_id)
        if count > 0:
            self.vector_store.delete_page_chunks(page_id)
        return count

    def search_similar_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        page_id: Optional[int] = None,
    ) -> list[tuple[DocumentChunk, float]]:
        """Search for chunks similar to query embedding.

        Args:
            query_embedding: Query vector from embedding service
            top_k: Number of results to return
            page_id: Optional filter to specific page

        Returns:
            List of (DocumentChunk, similarity_score) tuples
        """
        filters = {"page_id": page_id} if page_id else None
        return self.vector_store.search(query_embedding, top_k=top_k, filters=filters)

    def document_exists(self, page_id: int) -> bool:
        """Check if document exists in database.

        Args:
            page_id: BookStack page ID

        Returns:
            True if document exists, False otherwise
        """
        return self.document_repo.check_exists(page_id)

    def list_documents_in_book(self, book_slug: str) -> list[Document]:
        """Get all documents in a book.

        Args:
            book_slug: BookStack book slug

        Returns:
            List of Document entities in book
        """
        return self.document_repo.get_by_book_slug(book_slug)
