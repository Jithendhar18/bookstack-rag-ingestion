"""Pagination helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(default=20, ge=1, le=500, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def paginated_response(
    items: list[Any],
    total: int,
    page: int,
    limit: int,
) -> dict[str, Any]:
    """Build a standard paginated response envelope."""
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }
