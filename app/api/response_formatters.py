"""Response formatting utilities for consistent ORM→Pydantic conversion."""

from datetime import datetime
from typing import Any, Optional

from app.db.models import ChatMessage, ChatSession, IngestionRun, PageSyncAudit


def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO string or None."""
    return dt.isoformat() if dt else None


def format_ingestion_run(run: IngestionRun) -> dict[str, Any]:
    """Convert IngestionRun ORM to response dict."""
    return {
        "run_id": run.run_id,
        "status": run.status,
        "started_at": format_datetime(run.started_at),
        "finished_at": format_datetime(run.finished_at),
        "processed_pages": run.processed_pages,
        "failed_pages": run.failed_pages,
        "notes": run.notes,
    }


def format_page_audit(audit: PageSyncAudit) -> dict[str, Any]:
    """Convert PageSyncAudit ORM to response dict."""
    return {
        "audit_id": audit.audit_id,
        "page_id": audit.page_id,
        "status": audit.status,
        "reason": audit.reason,
        "source_updated_at": format_datetime(audit.source_updated_at),
        "local_updated_at": format_datetime(audit.local_updated_at),
        "created_at": format_datetime(audit.created_at),
    }


def format_chat_session(session: ChatSession) -> dict[str, Any]:
    """Convert ChatSession ORM to response dict."""
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "title": session.title,
        "created_at": format_datetime(session.created_at),
        "updated_at": format_datetime(session.updated_at),
        "is_archived": session.is_archived,
    }


def format_chat_message(message: ChatMessage) -> dict[str, Any]:
    """Convert ChatMessage ORM to response dict."""
    return {
        "message_id": message.message_id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "tokens_used": message.tokens_used,
        "created_at": format_datetime(message.created_at),
    }
