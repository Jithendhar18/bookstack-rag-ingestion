"""Domain exceptions - business logic errors."""

from __future__ import annotations


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class DocumentNotFound(DomainException):
    """Document does not exist."""

    def __init__(self, page_id: int):
        super().__init__(f"Document with page_id {page_id} not found", "DOCUMENT_NOT_FOUND")
        self.page_id = page_id


class ChunkNotFound(DomainException):
    """Document chunk does not exist."""

    def __init__(self, chunk_id: int):
        super().__init__(f"Chunk with chunk_id {chunk_id} not found", "CHUNK_NOT_FOUND")
        self.chunk_id = chunk_id


class IngestionRunNotFound(DomainException):
    """Ingestion run does not exist."""

    def __init__(self, run_id: int):
        super().__init__(f"Ingestion run with run_id {run_id} not found", "INGESTION_RUN_NOT_FOUND")
        self.run_id = run_id


class IngestionAlreadyRunning(DomainException):
    """Another ingestion is already in progress."""

    def __init__(self, current_run_id: int):
        super().__init__(
            f"Ingestion already in progress (run_id: {current_run_id})",
            "INGESTION_ALREADY_RUNNING",
        )
        self.current_run_id = current_run_id


class ChatSessionNotFound(DomainException):
    """Chat session does not exist."""

    def __init__(self, session_id: str):
        super().__init__(f"Chat session {session_id} not found", "CHAT_SESSION_NOT_FOUND")
        self.session_id = session_id


class ChatMessageNotFound(DomainException):
    """Chat message does not exist."""

    def __init__(self, message_id: str):
        super().__init__(f"Chat message {message_id} not found", "CHAT_MESSAGE_NOT_FOUND")
        self.message_id = message_id


class InvalidSessionState(DomainException):
    """Session is in invalid state for operation."""

    def __init__(self, session_id: str, reason: str):
        super().__init__(
            f"Chat session {session_id} in invalid state: {reason}",
            "INVALID_SESSION_STATE",
        )
        self.session_id = session_id
        self.reason = reason


class RepositoryException(DomainException):
    """Base exception for repository operations."""

    pass


class QueryBuilderException(DomainException):
    """Exception building database query."""

    pass


class TransactionException(DomainException):
    """Transaction failed."""

    pass


class ValidationException(DomainException):
    """Business logic validation failed."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message, "VALIDATION_ERROR")
        self.field = field


class InvalidChunkVector(ValidationException):
    """Chunk vector is missing or invalid."""

    def __init__(self, chunk_id: int, reason: str = ""):
        msg = f"Chunk {chunk_id} has invalid vector"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, "CHUNK_ID")


class InvalidDocument(ValidationException):
    """Document is invalid."""

    def __init__(self, page_id: int, reason: str = ""):
        msg = f"Document {page_id} is invalid"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, "PAGE_ID")
