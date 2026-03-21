"""API dependency injection setup."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
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

# Annotated shorthand for DB sessions injected via FastAPI DI
DbSession = Annotated[Session, Depends(get_db)]

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


def get_document_repository(db: DbSession) -> DocumentRepository:
    """Get document repository."""
    return DocumentRepository(db)


def get_document_chunk_repository(db: DbSession) -> DocumentChunkRepository:
    """Get document chunk repository."""
    return DocumentChunkRepository(db)


def get_ingestion_run_repository(db: DbSession) -> IngestionRunRepository:
    """Get ingestion run repository."""
    return IngestionRunRepository(db)


def get_page_sync_audit_repository(db: DbSession) -> PageSyncAuditRepository:
    """Get page sync audit repository."""
    return PageSyncAuditRepository(db)


def get_chat_session_repository(db: DbSession) -> ChatSessionRepository:
    """Get chat session repository."""
    return ChatSessionRepository(db)


def get_chat_message_repository(db: DbSession) -> ChatMessageRepository:
    """Get chat message repository."""
    return ChatMessageRepository(db)


def get_query_cache_repository(db: DbSession) -> QueryCacheRepository:
    """Get query cache repository."""
    return QueryCacheRepository(db)


# --------------------------------------------------------------------------- #
# Service dependencies (reuse cached singletons for expensive components)
# --------------------------------------------------------------------------- #


def get_document_service(db: DbSession) -> DocumentService:
    """Get document service."""
    doc_repo = DocumentRepository(db)
    chunk_repo = DocumentChunkRepository(db)
    vector_store = _get_vector_store()
    return DocumentService(doc_repo, chunk_repo, vector_store)


def get_query_service(db: DbSession) -> QueryService:
    """Get query service."""
    embedding_service = _get_embedding_service()
    vector_store = _get_vector_store()
    document_service = get_document_service(db)
    cache_repo = QueryCacheRepository(db)
    return QueryService(embedding_service, vector_store, document_service, cache_repo)


def get_chat_service(db: DbSession) -> ChatService:
    """Get chat service."""
    session_repo = ChatSessionRepository(db)
    message_repo = ChatMessageRepository(db)
    document_service = get_document_service(db)
    embedding_service = _get_embedding_service()
    return ChatService(session_repo, message_repo, document_service, embedding_service)


def get_ingestion_service(db: DbSession) -> IngestionService:
    """Get ingestion service."""
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
