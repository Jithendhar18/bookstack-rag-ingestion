"""Ingestion service - document processing pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.config.logging import get_logger
from app.domain.entities import Document, DocumentChunk, IngestionRun, PageSyncAudit
from app.domain.repositories import (
    IDocumentRepository,
    IIngestionRunRepository,
    IPageSyncAuditRepository,
)
from app.infrastructure.embeddings import IEmbeddingService
from app.infrastructure.external import IBookStackClient
from app.infrastructure.vector_store import IVectorStore
from app.services.document_service import DocumentService

logger = get_logger(__name__)


class IngestionService:
    """
    Ingestion service for document processing pipeline.

    Responsibilities:
    - Orchestrate full ingestion workflow
    - Manage ingestion runs and audit trail
    - Coordinate document fetching, processing, chunking, embedding, and storage
    """

    def __init__(
        self,
        bookstack_client: IBookStackClient,
        document_service: DocumentService,
        embedding_service: IEmbeddingService,
        vector_store: IVectorStore,
        document_repo: IDocumentRepository,
        ingestion_run_repo: IIngestionRunRepository,
        audit_repo: IPageSyncAuditRepository,
    ):
        """Initialize ingestion service.

        Args:
            bookstack_client: BookStack API client
            document_service: Document service for storage
            embedding_service: Embedding service for vectorization
            vector_store: Vector store for persistence
            document_repo: Document repository
            ingestion_run_repo: Ingestion run repository
            audit_repo: Audit repository
        """
        self.bookstack_client = bookstack_client
        self.document_service = document_service
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.document_repo = document_repo
        self.ingestion_run_repo = ingestion_run_repo
        self.audit_repo = audit_repo

    def start_ingestion_run(self) -> IngestionRun:
        """Create and start a new ingestion run.

        Returns:
            New IngestionRun entity with status "started"

        Raises:
            IngestionAlreadyRunning: If another ingestion is in progress
        """
        # Check for active run
        active = self.ingestion_run_repo.get_active_run()
        if active:
            from app.domain.exceptions import IngestionAlreadyRunning

            raise IngestionAlreadyRunning(active.run_id)

        run = IngestionRun(
            run_id=0,  # Will be auto-generated
            status="started",
            started_at=datetime.now(timezone.utc),
        )

        logger.info("ingestion.starting_run")
        return self.ingestion_run_repo.create(run)

    def finish_ingestion_run(
        self,
        run_id: int,
        status: str = "completed",
        notes: Optional[str] = None,
    ) -> IngestionRun:
        """Complete an ingestion run.

        Args:
            run_id: Run ID to complete
            status: Final status ("completed" or "failed")
            notes: Optional notes about the run

        Returns:
            Updated IngestionRun entity

        Raises:
            IngestionRunNotFound: If run does not exist
        """
        from app.domain.exceptions import IngestionRunNotFound

        run = self.ingestion_run_repo.get_by_run_id(run_id)
        if not run:
            raise IngestionRunNotFound(run_id)

        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.notes = notes

        logger.info("ingestion.finishing_run", run_id=run_id, status=status)
        return self.ingestion_run_repo.update(run)

    def record_page_sync(
        self,
        run_id: int,
        page_id: Optional[int],
        status: str,
        reason: str,
        source_updated_at: Optional[datetime] = None,
        local_updated_at: Optional[datetime] = None,
    ) -> PageSyncAudit:
        """Record a page sync audit entry.

        Args:
            run_id: Ingestion run ID
            page_id: BookStack page ID (optional for non-page records)
            status: Sync status ("success", "skip", "error", "update")
            reason: Human-readable reason
            source_updated_at: Update time from source
            local_updated_at: Update time in local DB

        Returns:
            Created PageSyncAudit entity
        """
        audit = PageSyncAudit(
            audit_id=0,  # Will be auto-generated
            run_id=run_id,
            page_id=page_id,
            status=status,
            reason=reason,
            source_updated_at=source_updated_at,
            local_updated_at=local_updated_at,
            created_at=datetime.now(timezone.utc),
        )

        return self.audit_repo.create(audit)

    def should_process_page(self, page_id: int, updated_at: datetime) -> bool:
        """Determine if a page needs processing (new or updated).

        Args:
            page_id: BookStack page ID
            updated_at: Update timestamp from BookStack

        Returns:
            True if page should be processed, False if unchanged
        """
        existing = self.document_repo.get_by_page_id(page_id)
        if not existing:
            return True  # New page

        return updated_at > existing.updated_at  # Updated page

    def process_pages_batch(
        self,
        run_id: int,
        pages: list[dict],
        processor_func,  # Function to process pages: (pages) -> list[Document]
    ) -> tuple[int, int]:
        """Process a batch of pages.

        Args:
            run_id: Ingestion run ID
            pages: List of page dicts from BookStack
            processor_func: Function to process pages and return documents

        Returns:
            Tuple of (processed_count, failed_count)
        """
        processed = 0
        failed = 0

        try:
            documents = processor_func(pages)

            for doc in documents:
                try:
                    # Store document
                    stored_doc = self.document_service.store_document(doc)

                    # Store chunks and embeddings
                    if doc.chunks:
                        stored_chunks = self.document_service.store_chunks(doc.chunks)

                        # Get embeddings for chunks
                        embeddings = self.embedding_service.embed_batch(
                            [c.chunk_text for c in stored_chunks]
                        )

                        # Store in vector store
                        self.vector_store.upsert_chunks(stored_chunks, embeddings)

                    # Record success
                    self.record_page_sync(
                        run_id=run_id,
                        page_id=doc.page_id,
                        status="success",
                        reason="Processed successfully",
                        local_updated_at=doc.updated_at,
                    )

                    processed += 1
                    logger.debug("page.processed", page_id=doc.page_id)

                except Exception as e:
                    failed += 1
                    logger.error("page.process_failed", error=str(e))
                    self.record_page_sync(
                        run_id=run_id,
                        page_id=doc.page_id,
                        status="error",
                        reason=f"Processing failed: {str(e)}",
                    )

        except Exception as e:
            logger.error("ingestion.batch_failed", error=str(e))
            failed = len(pages)

        return processed, failed

    def get_ingestion_statistics(self) -> dict:
        """Get overall ingestion statistics.

        Returns:
            Dict with stats (total_documents, total_chunks, etc.)
        """
        from app.infrastructure.database.models import DocumentChunkORM, DocumentORM

        # This would be called with an actual repository method
        return {
            "total_documents": 0,
            "total_chunks": 0,
            "last_ingestion": None,
        }

    def get_run_details(self, run_id: int) -> Optional[IngestionRun]:
        """Get details of a specific ingestion run.

        Args:
            run_id: Run ID

        Returns:
            IngestionRun entity or None
        """
        return self.ingestion_run_repo.get_by_run_id(run_id)

    def get_run_audits(self, run_id: int) -> list[PageSyncAudit]:
        """Get all audit entries for a run.

        Args:
            run_id: Run ID

        Returns:
            List of PageSyncAudit entities
        """
        return self.audit_repo.get_by_run_id(run_id)
