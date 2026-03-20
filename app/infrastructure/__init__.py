"""Infrastructure layer initialization - database, embeddings, vector store, external clients."""

from app.infrastructure.database.repositories import (
    ChatMessageRepository,
    ChatSessionRepository,
    DocumentChunkRepository,
    DocumentRepository,
    IngestionRunRepository,
    PageSyncAuditRepository,
    QueryCacheRepository,
)
from app.infrastructure.database.session import SessionManager, get_db, get_session_manager

__all__ = [
    "SessionManager",
    "get_db",
    "get_session_manager",
    "DocumentRepository",
    "DocumentChunkRepository",
    "IngestionRunRepository",
    "PageSyncAuditRepository",
    "ChatSessionRepository",
    "ChatMessageRepository",
    "QueryCacheRepository",
]
