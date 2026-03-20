from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, text

from app.config.settings import Settings
from app.db.models import Document, DocumentChunk, IngestionRun, PageSyncAudit
from app.db.session import SessionManager
from app.loaders.document_loader import LoadedDocument


class MetadataStore:
    """PostgreSQL-backed store for document metadata and ingestion audit records."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_manager = SessionManager(settings=settings)

    def acquire_page_lock(self, page_id: int):
        """Acquire a per-page advisory lock to avoid duplicate ingestion across workers."""
        from contextlib import contextmanager

        @contextmanager
        def _lock_context():
            with self.session_manager.session_scope() as session:
                acquired = bool(
                    session.execute(
                        text("SELECT pg_try_advisory_lock(:page_id)"),
                        {"page_id": int(page_id)},
                    ).scalar_one()
                )

                try:
                    yield acquired
                finally:
                    if acquired:
                        session.execute(
                            text("SELECT pg_advisory_unlock(:page_id)"),
                            {"page_id": int(page_id)},
                        )

        return _lock_context()

    def get_document(self, page_id: int) -> dict[str, Any] | None:
        """Retrieve a document's metadata by page ID, or None if not found."""
        with self.session_manager.session_scope() as session:
            document = session.get(Document, page_id)

        if document is None:
            return None

        return {
            "page_id": document.page_id,
            "title": document.title,
            "book_slug": document.book_slug,
            "chapter_id": document.chapter_id,
            "updated_at": document.updated_at,
            "last_synced_at": document.last_synced_at,
        }

    def start_ingestion_run(self, notes: str | None = None) -> int:
        """Create a new ingestion run record and return its ID."""
        with self.session_manager.session_scope() as session:
            run = IngestionRun(status="RUNNING", notes=notes)
            session.add(run)
            session.flush()
            return int(run.run_id)

    def finish_ingestion_run(
        self,
        run_id: int,
        status: str,
        processed_pages: int,
        failed_pages: int,
        notes: str | None = None,
    ) -> None:
        """Update an ingestion run with final status and page counts."""
        with self.session_manager.session_scope() as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                return

            run.status = status
            run.processed_pages = processed_pages
            run.failed_pages = failed_pages
            run.notes = notes
            run.finished_at = datetime.now(timezone.utc)

    def record_page_audit(
        self,
        run_id: int,
        page_id: int | None,
        status: str,
        reason: str,
        source_updated_at: datetime | None = None,
        local_updated_at: datetime | None = None,
    ) -> None:
        """Record an audit entry for a page within an ingestion run."""
        with self.session_manager.session_scope() as session:
            session.add(
                PageSyncAudit(
                    run_id=run_id,
                    page_id=page_id,
                    status=status,
                    reason=reason,
                    source_updated_at=source_updated_at,
                    local_updated_at=local_updated_at,
                )
            )

    def list_document_page_ids(self) -> set[int]:
        """Return the set of all stored document page IDs."""
        with self.session_manager.session_scope() as session:
            rows = session.execute(select(Document.page_id)).all()
        return {int(row[0]) for row in rows}

    def delete_document(self, page_id: int) -> None:
        """Delete a document record by page ID."""
        with self.session_manager.session_scope() as session:
            session.execute(delete(Document).where(Document.page_id == page_id))

    def is_page_stale(self, page_id: int, updated_at_raw: str) -> bool:
        """Check whether a page has been updated since last sync."""
        existing = self.get_document(page_id)
        if not existing:
            return True

        remote_updated_at = self._parse_timestamp(updated_at_raw)
        local_updated_at = existing["updated_at"]

        if not isinstance(local_updated_at, datetime):
            return True

        return remote_updated_at > local_updated_at

    def upsert_document(self, document: LoadedDocument) -> None:
        """Insert or update a document record from a LoadedDocument."""
        with self.session_manager.session_scope() as session:
            existing = session.get(Document, document.page_id)
            parsed_updated_at = self._parse_timestamp(document.updated_at)

            if existing is None:
                existing = Document(
                    page_id=document.page_id,
                    title=document.title,
                    book_slug=document.book_slug,
                    chapter_id=document.chapter_id,
                    updated_at=parsed_updated_at,
                    last_synced_at=datetime.now(timezone.utc),
                )
                session.add(existing)
            else:
                existing.title = document.title
                existing.book_slug = document.book_slug
                existing.chapter_id = document.chapter_id
                existing.updated_at = parsed_updated_at
                existing.last_synced_at = datetime.now(timezone.utc)

    def get_document_chunks(self, page_id: int) -> dict[str, dict[str, Any]]:
        """Return existing chunks for a page as a dict keyed by vector_id."""
        with self.session_manager.session_scope() as session:
            rows = session.execute(
                select(
                    DocumentChunk.chunk_index, DocumentChunk.chunk_text, DocumentChunk.vector_id
                ).where(DocumentChunk.page_id == page_id)
            ).all()

        chunk_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            vector_id = str(row.vector_id)
            chunk_map[vector_id] = {
                "chunk_index": row.chunk_index,
                "chunk_text": row.chunk_text,
                "vector_id": row.vector_id,
            }

        return chunk_map

    def delete_document_chunks_by_vector_ids(self, page_id: int, vector_ids: list[str]) -> None:
        """Delete document chunks matching the given vector IDs."""
        if not vector_ids:
            return

        with self.session_manager.session_scope() as session:
            session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.page_id == page_id,
                    DocumentChunk.vector_id.in_(vector_ids),
                )
            )

    def upsert_document_chunks(self, page_id: int, rows: list[tuple[int, str, str]]) -> None:
        """Insert or update document chunks for a page."""
        if not rows:
            return

        with self.session_manager.session_scope() as session:
            by_index = {
                chunk.chunk_index: chunk
                for chunk in session.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.page_id == page_id,
                        DocumentChunk.chunk_index.in_([item[0] for item in rows]),
                    )
                ).scalars()
            }

            for chunk_index, chunk_text, vector_id in rows:
                existing = by_index.get(chunk_index)
                if existing is None:
                    session.add(
                        DocumentChunk(
                            page_id=page_id,
                            chunk_index=chunk_index,
                            chunk_text=chunk_text,
                            vector_id=vector_id,
                        )
                    )
                    continue

                existing.chunk_text = chunk_text
                existing.vector_id = vector_id
                existing.created_at = datetime.now(timezone.utc)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        normalized = value.strip()
        if not normalized:
            return datetime.now(timezone.utc)

        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
