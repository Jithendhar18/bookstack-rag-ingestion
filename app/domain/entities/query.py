"""Query cache domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class QueryCache:
    """Cache for query results to improve performance."""

    cache_id: str  # SHA256 hash
    query_hash: str
    query_text: str
    results: str  # JSON
    expires_at: datetime
    created_at: datetime
    ttl_seconds: int
    filters: str | None = None  # JSON

    def __hash__(self) -> int:
        """Make cache entries hashable by their ID."""
        return hash(self.cache_id)

    def is_expired(self, current_time: datetime) -> bool:
        """Check if cache entry has expired."""
        return current_time >= self.expires_at
