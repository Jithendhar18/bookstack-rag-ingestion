"""Ingestion domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PageSyncAudit:
    """Audit trail for a page sync operation."""

    audit_id: int
    run_id: int
    status: str  # "success", "skip", "error", "update"
    reason: str
    created_at: datetime
    page_id: Optional[int] = None
    source_updated_at: Optional[datetime] = None
    local_updated_at: Optional[datetime] = None

    def __hash__(self) -> int:
        """Make audits hashable by their ID."""
        return hash(self.audit_id)


@dataclass
class IngestionRun:
    """Tracks a complete ingestion batch operation."""

    run_id: int
    status: str  # "started", "completed", "failed"
    started_at: datetime
    processed_pages: int = 0
    failed_pages: int = 0
    finished_at: Optional[datetime] = None
    notes: Optional[str] = None
    page_audits: list[PageSyncAudit] = field(default_factory=list)

    def __hash__(self) -> int:
        """Make runs hashable by their ID."""
        return hash(self.run_id)

    def is_complete(self) -> bool:
        """Check if ingestion run is complete."""
        return self.status in ("completed", "failed") and self.finished_at is not None

    def get_duration_seconds(self) -> Optional[float]:
        """Get duration of run in seconds."""
        if not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()
