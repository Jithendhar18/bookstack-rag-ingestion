"""FastAPI utilities and helpers."""

import uuid
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing.

    Returns:
        A UUID4 string
    """
    return str(uuid.uuid4())


def get_request_id_from_context(context: dict[str, Any] | None = None) -> str:
    """Extract or generate request ID from context.

    Args:
        context: Optional context dict with potential request_id

    Returns:
        Request ID string
    """
    if context and isinstance(context.get("request_id"), str):
        return context["request_id"]
    return generate_request_id()


class APIException(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int = 500, details: dict[str, Any] | None = None):
        """Initialize API exception.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Additional error details
        """
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(APIException):
    """Validation error (400)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=400, details=details)


class NotFoundError(APIException):
    """Not found error (404)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=404, details=details)


class ServiceError(APIException):
    """Service error (503)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=503, details=details)
