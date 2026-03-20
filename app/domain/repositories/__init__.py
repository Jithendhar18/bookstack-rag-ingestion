"""Repository interfaces - data access contracts."""

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    IngestionRun,
    PageSyncAudit,
    QueryCache,
)


class IDocumentRepository(ABC):
    """Interface for document data access."""

    @abstractmethod
    def get_by_page_id(self, page_id: int) -> Optional[Document]:
        """Get document by page ID."""

    @abstractmethod
    def get_all(self, limit: int = 100, offset: int = 0) -> list[Document]:
        """Get all documents with pagination."""

    @abstractmethod
    def create(self, document: Document) -> Document:
        """Create new document."""

    @abstractmethod
    def update(self, document: Document) -> Document:
        """Update existing document."""

    @abstractmethod
    def delete(self, page_id: int) -> bool:
        """Delete document by page ID."""

    @abstractmethod
    def get_by_book_slug(self, book_slug: str) -> list[Document]:
        """Get all documents in a book."""

    @abstractmethod
    def check_exists(self, page_id: int) -> bool:
        """Check if document exists."""


class IDocumentChunkRepository(ABC):
    """Interface for document chunk data access."""

    @abstractmethod
    def get_by_chunk_id(self, chunk_id: int) -> Optional[DocumentChunk]:
        """Get chunk by chunk ID."""

    @abstractmethod
    def get_by_page_id(self, page_id: int) -> list[DocumentChunk]:
        """Get all chunks for a page."""

    @abstractmethod
    def get_by_vector_id(self, vector_id: str) -> Optional[DocumentChunk]:
        """Get chunk by vector ID."""

    @abstractmethod
    def create(self, chunk: DocumentChunk) -> DocumentChunk:
        """Create new chunk."""

    @abstractmethod
    def create_batch(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Create multiple chunks efficiently."""

    @abstractmethod
    def delete_by_page_id(self, page_id: int) -> int:
        """Delete all chunks for a page. Returns count deleted."""

    @abstractmethod
    def delete_by_chunk_id(self, chunk_id: int) -> bool:
        """Delete chunk by chunk ID."""


class IIngestionRunRepository(ABC):
    """Interface for ingestion run data access."""

    @abstractmethod
    def get_by_run_id(self, run_id: int) -> Optional[IngestionRun]:
        """Get ingestion run by ID."""

    @abstractmethod
    def get_all(self, limit: int = 50, offset: int = 0) -> list[IngestionRun]:
        """Get all ingestion runs with pagination."""

    @abstractmethod
    def create(self, run: IngestionRun) -> IngestionRun:
        """Create new ingestion run."""

    @abstractmethod
    def update(self, run: IngestionRun) -> IngestionRun:
        """Update existing ingestion run."""

    @abstractmethod
    def get_latest_run(self) -> Optional[IngestionRun]:
        """Get most recent ingestion run."""

    @abstractmethod
    def get_active_run(self) -> Optional[IngestionRun]:
        """Get currently running ingestion (if any)."""


class IPageSyncAuditRepository(ABC):
    """Interface for page sync audit data access."""

    @abstractmethod
    def get_by_audit_id(self, audit_id: int) -> Optional[PageSyncAudit]:
        """Get audit record by ID."""

    @abstractmethod
    def get_by_run_id(self, run_id: int) -> list[PageSyncAudit]:
        """Get all audits for a run."""

    @abstractmethod
    def create(self, audit: PageSyncAudit) -> PageSyncAudit:
        """Create new audit record."""

    @abstractmethod
    def create_batch(self, audits: list[PageSyncAudit]) -> list[PageSyncAudit]:
        """Create multiple audit records efficiently."""


class IChatSessionRepository(ABC):
    """Interface for chat session data access."""

    @abstractmethod
    def get_by_session_id(self, session_id: str) -> Optional[ChatSession]:
        """Get chat session by ID."""

    @abstractmethod
    def get_by_user_id(self, user_id: str, limit: int = 50, offset: int = 0) -> list[ChatSession]:
        """Get all sessions for a user."""

    @abstractmethod
    def create(self, session: ChatSession) -> ChatSession:
        """Create new chat session."""

    @abstractmethod
    def update(self, session: ChatSession) -> ChatSession:
        """Update existing chat session."""

    @abstractmethod
    def delete(self, session_id: str) -> bool:
        """Delete chat session."""


class IChatMessageRepository(ABC):
    """Interface for chat message data access."""

    @abstractmethod
    def get_by_message_id(self, message_id: str) -> Optional[ChatMessage]:
        """Get message by ID."""

    @abstractmethod
    def get_by_session_id(
        self, session_id: str, limit: int = 100, offset: int = 0
    ) -> list[ChatMessage]:
        """Get messages for a session with pagination."""

    @abstractmethod
    def create(self, message: ChatMessage) -> ChatMessage:
        """Create new message."""

    @abstractmethod
    def create_batch(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Create multiple messages efficiently."""

    @abstractmethod
    def delete_by_session_id(self, session_id: str) -> int:
        """Delete all messages in a session. Returns count deleted."""


class IQueryCacheRepository(ABC):
    """Interface for query cache data access."""

    @abstractmethod
    def get(self, cache_id: str) -> Optional[QueryCache]:
        """Get cached query by ID."""

    @abstractmethod
    def get_by_hash(self, query_hash: str) -> Optional[QueryCache]:
        """Get cached query by query hash."""

    @abstractmethod
    def set(self, cache: QueryCache) -> QueryCache:
        """Set/update cache entry."""

    @abstractmethod
    def delete(self, cache_id: str) -> bool:
        """Delete cache entry."""

    @abstractmethod
    def delete_expired(self) -> int:
        """Delete all expired entries. Returns count deleted."""
