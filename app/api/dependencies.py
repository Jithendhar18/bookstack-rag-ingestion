"""API dependency injection setup."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.infrastructure.database.repositories import (
    ChatMessageRepository,
    ChatSessionRepository,
    DocumentChunkRepository,
    DocumentRepository,
    IngestionRunRepository,
    PageSyncAuditRepository,
    QueryCacheRepository,
)
from app.infrastructure.database.session import get_db
from app.services import (
    ChatService,
    DocumentService,
    IngestionService,
    QueryService,
)

# --------------------------------------------------------------------------- #
# Cached singletons for expensive, stateless services
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def _get_embedding_service():
    from app.embeddings.embedding_service import EmbeddingService

    return EmbeddingService(get_settings())


@lru_cache(maxsize=1)
def _get_vector_store():
    from app.db.vector_store import VectorStore

    return VectorStore(get_settings())


@lru_cache(maxsize=1)
def _get_bookstack_client():
    from app.clients.bookstack_client import BookStackClient

    return BookStackClient(get_settings())


# --------------------------------------------------------------------------- #
# Repository dependencies (require a DB session)
# --------------------------------------------------------------------------- #


def get_document_repository(db: Session = None) -> DocumentRepository:
    """Get document repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return DocumentRepository(db)


def get_document_chunk_repository(db: Session = None) -> DocumentChunkRepository:
    """Get document chunk repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return DocumentChunkRepository(db)


def get_ingestion_run_repository(db: Session = None) -> IngestionRunRepository:
    """Get ingestion run repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return IngestionRunRepository(db)


def get_page_sync_audit_repository(db: Session = None) -> PageSyncAuditRepository:
    """Get page sync audit repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return PageSyncAuditRepository(db)


def get_chat_session_repository(db: Session = None) -> ChatSessionRepository:
    """Get chat session repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return ChatSessionRepository(db)


def get_chat_message_repository(db: Session = None) -> ChatMessageRepository:
    """Get chat message repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return ChatMessageRepository(db)


def get_query_cache_repository(db: Session = None) -> QueryCacheRepository:
    """Get query cache repository."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()
    return QueryCacheRepository(db)


# --------------------------------------------------------------------------- #
# Service dependencies (reuse cached singletons for expensive components)
# --------------------------------------------------------------------------- #


def get_document_service(db: Session = None) -> DocumentService:
    """Get document service."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()

    doc_repo = DocumentRepository(db)
    chunk_repo = DocumentChunkRepository(db)
    vector_store = _get_vector_store()

    return DocumentService(doc_repo, chunk_repo, vector_store)


def get_query_service(db: Session = None) -> QueryService:
    """Get query service."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()

    embedding_service = _get_embedding_service()
    vector_store = _get_vector_store()
    document_service = get_document_service(db)
    cache_repo = QueryCacheRepository(db)

    return QueryService(embedding_service, vector_store, document_service, cache_repo)


def get_chat_service(db: Session = None) -> ChatService:
    """Get chat service."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()

    session_repo = ChatSessionRepository(db)
    message_repo = ChatMessageRepository(db)
    document_service = get_document_service(db)
    embedding_service = _get_embedding_service()

    return ChatService(session_repo, message_repo, document_service, embedding_service)


def get_ingestion_service(db: Session = None) -> IngestionService:
    """Get ingestion service."""
    if db is None:
        from app.infrastructure.database.session import get_session_manager

        db = get_session_manager()._session_factory()

    settings = get_settings()
    bookstack_client = _get_bookstack_client()
    embedding_service = _get_embedding_service()
    vector_store = _get_vector_store()

    document_service = get_document_service(db)
    document_repo = DocumentRepository(db)
    ingestion_run_repo = IngestionRunRepository(db)
    audit_repo = PageSyncAuditRepository(db)

    return IngestionService(
        bookstack_client,
        document_service,
        embedding_service,
        vector_store,
        document_repo,
        ingestion_run_repo,
        audit_repo,
    )
