"""Application constants and enums."""

from enum import Enum


class IngestionStatus(str, Enum):
    """Ingestion run status constants."""

    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PageSyncStatus(str, Enum):
    """Page sync status constants."""

    SUCCESS = "SUCCESS"
    SKIP = "SKIP"
    ERROR = "ERROR"
    UPDATE = "UPDATE"


class ChatRole(str, Enum):
    """Chat message role constants."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Pagination defaults (not environment-specific)
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 500

# Token estimation (structural constant, not config)
EMBEDDING_CONTEXT_TOKEN_LIMIT = 1000
