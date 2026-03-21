"""SQLAlchemy repository implementations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.domain.entities import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    IngestionRun,
    PageSyncAudit,
    QueryCache,
)
from app.domain.exceptions import (
    ChatMessageNotFound,
    ChatSessionNotFound,
    ChunkNotFound,
    DocumentNotFound,
    IngestionRunNotFound,
)
from app.domain.repositories import (
    IChatMessageRepository,
    IChatSessionRepository,
    IDocumentChunkRepository,
    IDocumentRepository,
    IIngestionRunRepository,
    IPageSyncAuditRepository,
    IQueryCacheRepository,
)
from app.infrastructure.database.models import (
    ChatMessageORM,
    ChatSessionORM,
    DocumentChunkORM,
    DocumentORM,
    IngestionRunORM,
    PageSyncAuditORM,
    QueryCacheORM,
)


class DocumentRepository(IDocumentRepository):
    """SQLAlchemy implementation of document repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_page_id(self, page_id: int) -> Optional[Document]:
        """Get document by page ID."""
        orm = self.session.query(DocumentORM).filter_by(page_id=page_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_all(self, limit: int = 100, offset: int = 0) -> list[Document]:
        """Get all documents with pagination."""
        orms = self.session.query(DocumentORM).limit(limit).offset(offset).all()
        return [self._orm_to_domain(orm) for orm in orms]

    def create(self, document: Document) -> Document:
        """Create new document."""
        orm = DocumentORM(
            page_id=document.page_id,
            title=document.title,
            book_slug=document.book_slug,
            chapter_id=document.chapter_id,
            updated_at=document.updated_at,
            last_synced_at=document.last_synced_at,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def update(self, document: Document) -> Document:
        """Update existing document."""
        orm = self.session.query(DocumentORM).filter_by(page_id=document.page_id).first()
        if not orm:
            raise DocumentNotFound(document.page_id)

        orm.title = document.title
        orm.book_slug = document.book_slug
        orm.chapter_id = document.chapter_id
        orm.updated_at = document.updated_at
        orm.last_synced_at = document.last_synced_at

        self.session.flush()
        return self._orm_to_domain(orm)

    def delete(self, page_id: int) -> bool:
        """Delete document by page ID."""
        orm = self.session.query(DocumentORM).filter_by(page_id=page_id).first()
        if not orm:
            return False

        self.session.delete(orm)
        self.session.flush()
        return True

    def get_by_book_slug(self, book_slug: str) -> list[Document]:
        """Get all documents in a book."""
        orms = self.session.query(DocumentORM).filter_by(book_slug=book_slug).all()
        return [self._orm_to_domain(orm) for orm in orms]

    def check_exists(self, page_id: int) -> bool:
        """Check if document exists."""
        return self.session.query(DocumentORM).filter_by(page_id=page_id).exists().scalar() or False

    @staticmethod
    def _orm_to_domain(orm: DocumentORM) -> Document:
        """Convert ORM to domain entity."""
        return Document(
            page_id=orm.page_id,
            title=orm.title,
            book_slug=orm.book_slug,
            chapter_id=orm.chapter_id,
            updated_at=orm.updated_at,
            last_synced_at=orm.last_synced_at,
            chunks=[DocumentChunkRepository._orm_to_domain(c) for c in orm.chunks],
        )


class DocumentChunkRepository(IDocumentChunkRepository):
    """SQLAlchemy implementation of document chunk repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_chunk_id(self, chunk_id: int) -> Optional[DocumentChunk]:
        """Get chunk by chunk ID."""
        orm = self.session.query(DocumentChunkORM).filter_by(chunk_id=chunk_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_by_page_id(self, page_id: int) -> list[DocumentChunk]:
        """Get all chunks for a page."""
        orms = (
            self.session.query(DocumentChunkORM)
            .filter_by(page_id=page_id)
            .order_by(DocumentChunkORM.chunk_index)
            .all()
        )
        return [self._orm_to_domain(orm) for orm in orms]

    def get_by_vector_id(self, vector_id: str) -> Optional[DocumentChunk]:
        """Get chunk by vector ID."""
        orm = self.session.query(DocumentChunkORM).filter_by(vector_id=vector_id).first()
        return self._orm_to_domain(orm) if orm else None

    def create(self, chunk: DocumentChunk) -> DocumentChunk:
        """Create new chunk."""
        orm = DocumentChunkORM(
            page_id=chunk.page_id,
            chunk_index=chunk.chunk_index,
            chunk_text=chunk.chunk_text,
            vector_id=chunk.vector_id,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def create_batch(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Create multiple chunks efficiently."""
        orms = [
            DocumentChunkORM(
                page_id=chunk.page_id,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                vector_id=chunk.vector_id,
            )
            for chunk in chunks
        ]
        self.session.add_all(orms)
        self.session.flush()
        return [self._orm_to_domain(orm) for orm in orms]

    def delete_by_page_id(self, page_id: int) -> int:
        """Delete all chunks for a page. Returns count deleted."""
        count = self.session.query(DocumentChunkORM).filter_by(page_id=page_id).delete()
        self.session.flush()
        return count

    def delete_by_chunk_id(self, chunk_id: int) -> bool:
        """Delete chunk by chunk ID."""
        orm = self.session.query(DocumentChunkORM).filter_by(chunk_id=chunk_id).first()
        if not orm:
            return False

        self.session.delete(orm)
        self.session.flush()
        return True

    @staticmethod
    def _orm_to_domain(orm: DocumentChunkORM) -> DocumentChunk:
        """Convert ORM to domain entity."""
        return DocumentChunk(
            chunk_id=orm.chunk_id,
            page_id=orm.page_id,
            chunk_index=orm.chunk_index,
            chunk_text=orm.chunk_text,
            vector_id=orm.vector_id,
            created_at=orm.created_at,
        )


class IngestionRunRepository(IIngestionRunRepository):
    """SQLAlchemy implementation of ingestion run repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_run_id(self, run_id: int) -> Optional[IngestionRun]:
        """Get ingestion run by ID."""
        orm = self.session.query(IngestionRunORM).filter_by(run_id=run_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_all(self, limit: int = 50, offset: int = 0) -> list[IngestionRun]:
        """Get all ingestion runs with pagination."""
        orms = (
            self.session.query(IngestionRunORM)
            .order_by(IngestionRunORM.started_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [self._orm_to_domain(orm) for orm in orms]

    def create(self, run: IngestionRun) -> IngestionRun:
        """Create new ingestion run."""
        orm = IngestionRunORM(
            status=run.status,
            processed_pages=run.processed_pages,
            failed_pages=run.failed_pages,
            notes=run.notes,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def update(self, run: IngestionRun) -> IngestionRun:
        """Update existing ingestion run."""
        orm = self.session.query(IngestionRunORM).filter_by(run_id=run.run_id).first()
        if not orm:
            raise IngestionRunNotFound(run.run_id)

        orm.status = run.status
        orm.processed_pages = run.processed_pages
        orm.failed_pages = run.failed_pages
        orm.finished_at = run.finished_at
        orm.notes = run.notes

        self.session.flush()
        return self._orm_to_domain(orm)

    def get_latest_run(self) -> Optional[IngestionRun]:
        """Get most recent ingestion run."""
        orm = (
            self.session.query(IngestionRunORM).order_by(IngestionRunORM.started_at.desc()).first()
        )
        return self._orm_to_domain(orm) if orm else None

    def get_active_run(self) -> Optional[IngestionRun]:
        """Get currently running ingestion (if any)."""
        orm = self.session.query(IngestionRunORM).filter_by(status="started").first()
        return self._orm_to_domain(orm) if orm else None

    @staticmethod
    def _orm_to_domain(orm: IngestionRunORM) -> IngestionRun:
        """Convert ORM to domain entity."""
        return IngestionRun(
            run_id=orm.run_id,
            status=orm.status,
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            processed_pages=orm.processed_pages,
            failed_pages=orm.failed_pages,
            notes=orm.notes,
            page_audits=[PageSyncAuditRepository._orm_to_domain(a) for a in orm.page_audits],
        )


class PageSyncAuditRepository(IPageSyncAuditRepository):
    """SQLAlchemy implementation of page sync audit repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_audit_id(self, audit_id: int) -> Optional[PageSyncAudit]:
        """Get audit record by ID."""
        orm = self.session.query(PageSyncAuditORM).filter_by(audit_id=audit_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_by_run_id(self, run_id: int) -> list[PageSyncAudit]:
        """Get all audits for a run."""
        orms = self.session.query(PageSyncAuditORM).filter_by(run_id=run_id).all()
        return [self._orm_to_domain(orm) for orm in orms]

    def create(self, audit: PageSyncAudit) -> PageSyncAudit:
        """Create new audit record."""
        orm = PageSyncAuditORM(
            run_id=audit.run_id,
            page_id=audit.page_id,
            status=audit.status,
            reason=audit.reason,
            source_updated_at=audit.source_updated_at,
            local_updated_at=audit.local_updated_at,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def create_batch(self, audits: list[PageSyncAudit]) -> list[PageSyncAudit]:
        """Create multiple audit records efficiently."""
        orms = [
            PageSyncAuditORM(
                run_id=audit.run_id,
                page_id=audit.page_id,
                status=audit.status,
                reason=audit.reason,
                source_updated_at=audit.source_updated_at,
                local_updated_at=audit.local_updated_at,
            )
            for audit in audits
        ]
        self.session.add_all(orms)
        self.session.flush()
        return [self._orm_to_domain(orm) for orm in orms]

    @staticmethod
    def _orm_to_domain(orm: PageSyncAuditORM) -> PageSyncAudit:
        """Convert ORM to domain entity."""
        return PageSyncAudit(
            audit_id=orm.audit_id,
            run_id=orm.run_id,
            page_id=orm.page_id,
            status=orm.status,
            reason=orm.reason,
            source_updated_at=orm.source_updated_at,
            local_updated_at=orm.local_updated_at,
            created_at=orm.created_at,
        )


class ChatSessionRepository(IChatSessionRepository):
    """SQLAlchemy implementation of chat session repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_session_id(self, session_id: str) -> Optional[ChatSession]:
        """Get chat session by ID."""
        orm = self.session.query(ChatSessionORM).filter_by(session_id=session_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_by_user_id(self, user_id: str, limit: int = 50, offset: int = 0) -> list[ChatSession]:
        """Get all sessions for a user."""
        orms = (
            self.session.query(ChatSessionORM)
            .filter_by(user_id=user_id)
            .order_by(ChatSessionORM.updated_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [self._orm_to_domain(orm) for orm in orms]

    def create(self, session: ChatSession) -> ChatSession:
        """Create new chat session."""
        orm = ChatSessionORM(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            is_archived=session.is_archived,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def update(self, session: ChatSession) -> ChatSession:
        """Update existing chat session."""
        orm = self.session.query(ChatSessionORM).filter_by(session_id=session.session_id).first()
        if not orm:
            raise ChatSessionNotFound(session.session_id)

        orm.title = session.title
        orm.is_archived = session.is_archived
        orm.updated_at = session.updated_at

        self.session.flush()
        return self._orm_to_domain(orm)

    def delete(self, session_id: str) -> bool:
        """Delete chat session."""
        orm = self.session.query(ChatSessionORM).filter_by(session_id=session_id).first()
        if not orm:
            return False

        self.session.delete(orm)
        self.session.flush()
        return True

    @staticmethod
    def _orm_to_domain(orm: ChatSessionORM) -> ChatSession:
        """Convert ORM to domain entity."""
        return ChatSession(
            session_id=orm.session_id,
            user_id=orm.user_id,
            title=orm.title,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            is_archived=orm.is_archived,
            messages=[ChatMessageRepository._orm_to_domain(m) for m in orm.messages],
        )


class ChatMessageRepository(IChatMessageRepository):
    """SQLAlchemy implementation of chat message repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_message_id(self, message_id: str) -> Optional[ChatMessage]:
        """Get message by ID."""
        orm = self.session.query(ChatMessageORM).filter_by(message_id=message_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_by_session_id(
        self, session_id: str, limit: int = 100, offset: int = 0
    ) -> list[ChatMessage]:
        """Get messages for a session with pagination."""
        orms = (
            self.session.query(ChatMessageORM)
            .filter_by(session_id=session_id)
            .order_by(ChatMessageORM.created_at)
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [self._orm_to_domain(orm) for orm in orms]

    def create(self, message: ChatMessage) -> ChatMessage:
        """Create new message."""
        orm = ChatMessageORM(
            message_id=message.message_id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            tokens_used=message.tokens_used,
            extra_metadata=message.extra_metadata,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def create_batch(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Create multiple messages efficiently."""
        orms = [
            ChatMessageORM(
                message_id=message.message_id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                tokens_used=message.tokens_used,
                extra_metadata=message.extra_metadata,
            )
            for message in messages
        ]
        self.session.add_all(orms)
        self.session.flush()
        return [self._orm_to_domain(orm) for orm in orms]

    def delete_by_session_id(self, session_id: str) -> int:
        """Delete all messages in a session. Returns count deleted."""
        count = self.session.query(ChatMessageORM).filter_by(session_id=session_id).delete()
        self.session.flush()
        return count

    @staticmethod
    def _orm_to_domain(orm: ChatMessageORM) -> ChatMessage:
        """Convert ORM to domain entity."""
        return ChatMessage(
            message_id=orm.message_id,
            session_id=orm.session_id,
            role=orm.role,
            content=orm.content,
            tokens_used=orm.tokens_used,
            extra_metadata=orm.extra_metadata,
            created_at=orm.created_at,
        )


class QueryCacheRepository(IQueryCacheRepository):
    """SQLAlchemy implementation of query cache repository."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, cache_id: str) -> Optional[QueryCache]:
        """Get cached query by ID."""
        orm = self.session.query(QueryCacheORM).filter_by(cache_id=cache_id).first()
        return self._orm_to_domain(orm) if orm else None

    def get_by_hash(self, query_hash: str) -> Optional[QueryCache]:
        """Get cached query by query hash."""
        orm = self.session.query(QueryCacheORM).filter_by(query_hash=query_hash).first()
        return self._orm_to_domain(orm) if orm else None

    def set(self, cache: QueryCache) -> QueryCache:
        """Set/update cache entry."""
        existing = self.session.query(QueryCacheORM).filter_by(cache_id=cache.cache_id).first()
        if existing:
            existing.results = cache.results
            existing.expires_at = cache.expires_at
            self.session.flush()
            return self._orm_to_domain(existing)

        orm = QueryCacheORM(
            cache_id=cache.cache_id,
            query_hash=cache.query_hash,
            query_text=cache.query_text,
            filters=cache.filters,
            results=cache.results,
            ttl_seconds=cache.ttl_seconds,
            expires_at=cache.expires_at,
        )
        self.session.add(orm)
        self.session.flush()
        return self._orm_to_domain(orm)

    def delete(self, cache_id: str) -> bool:
        """Delete cache entry."""
        orm = self.session.query(QueryCacheORM).filter_by(cache_id=cache_id).first()
        if not orm:
            return False

        self.session.delete(orm)
        self.session.flush()
        return True

    def delete_expired(self) -> int:
        """Delete all expired entries. Returns count deleted."""
        from datetime import datetime, timezone

        count = (
            self.session.query(QueryCacheORM)
            .filter(QueryCacheORM.expires_at <= datetime.now(timezone.utc))
            .delete()
        )
        self.session.flush()
        return count

    @staticmethod
    def _orm_to_domain(orm: QueryCacheORM) -> QueryCache:
        """Convert ORM to domain entity."""
        return QueryCache(
            cache_id=orm.cache_id,
            query_hash=orm.query_hash,
            query_text=orm.query_text,
            filters=orm.filters,
            results=orm.results,
            ttl_seconds=orm.ttl_seconds,
            expires_at=orm.expires_at,
            created_at=orm.created_at,
        )
