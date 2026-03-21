"""V1 API request/response schemas — single source of truth for the /api/v1 contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────
# Shared / generic
# ────────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    """Envelope for paginated list endpoints."""

    items: list[Any]
    total: int
    page: int
    limit: int


class ErrorDetail(BaseModel):
    """Standardised error payload."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Top-level error wrapper — every error response follows this shape."""

    error: ErrorDetail


# ────────────────────────────────────────────────────────────────────
# Query
# ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """POST /api/v1/query"""

    query: str = Field(..., min_length=1, max_length=5000, description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")
    filters: Optional[dict[str, Any]] = Field(default=None, description="Metadata filters")
    use_llm: bool = Field(default=True, description="Generate answer using LLM")
    rerank: bool = Field(default=False, description="Apply cross-encoder reranking")
    include_sources: bool = Field(default=True, description="Include source references")


class SourceInfo(BaseModel):
    """A single source chunk returned alongside the answer."""

    chunk_id: str
    text: str
    score: float
    page_id: Optional[int] = None
    page_title: Optional[str] = None


class QueryResponse(BaseModel):
    """Response for POST /api/v1/query"""

    answer: Optional[str] = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[SourceInfo] = Field(default_factory=list)
    latency_ms: float = 0.0


# ────────────────────────────────────────────────────────────────────
# Ingestion
# ────────────────────────────────────────────────────────────────────

class StartIngestionRequest(BaseModel):
    """POST /api/v1/ingestion/run"""

    full_sync: bool = Field(default=False, description="Full sync instead of incremental")
    page_ids: Optional[list[int]] = Field(
        default=None,
        description="Specific page IDs to ingest (partial ingestion)",
    )
    force: bool = Field(default=False, description="Force re-ingestion even if unchanged")


class IngestionRunResponse(BaseModel):
    """Ingestion run status."""

    run_id: int
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    processed_pages: int = 0
    failed_pages: int = 0
    notes: Optional[str] = None


class IngestionRunStatusResponse(BaseModel):
    """GET /api/v1/ingestion/run/{run_id}/status"""

    run_id: int
    status: str
    processed_pages: int = 0
    failed_pages: int = 0


class IngestionStatsResponse(BaseModel):
    """GET /api/v1/ingestion/stats"""

    total_runs: int
    completed_runs: int
    failed_runs: int
    running_runs: int
    latest_run_id: Optional[int] = None
    latest_run_status: Optional[str] = None
    latest_run_at: Optional[str] = None


class PageAuditResponse(BaseModel):
    """Page sync audit record."""

    audit_id: int
    page_id: Optional[int] = None
    status: str
    reason: str
    source_updated_at: Optional[str] = None
    local_updated_at: Optional[str] = None
    created_at: str


# ────────────────────────────────────────────────────────────────────
# Chat
# ────────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """POST /api/v1/chat/session"""

    user_id: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, max_length=200)


class ChatSessionResponse(BaseModel):
    """Chat session info."""

    session_id: str
    user_id: Optional[str] = None
    title: Optional[str] = None
    created_at: str
    updated_at: str
    is_archived: bool


class ChatMessageResponse(BaseModel):
    """Single chat message."""

    message_id: str
    session_id: str
    role: str
    content: str
    tokens_used: Optional[int] = None
    created_at: str


class ChatRequest(BaseModel):
    """POST /api/v1/chat/message"""

    session_id: str
    message: str = Field(..., min_length=1, max_length=5000)
    top_k: Optional[int] = Field(None, ge=1, le=50)
    filters: Optional[dict[str, Any]] = None
    use_reranking: bool = False
    user_id: Optional[str] = None


class ChatSourceReference(BaseModel):
    """Source chunk referenced by a chat response."""

    chunk_id: str
    page_id: Optional[int] = None
    page_title: Optional[str] = None
    score: float


class ChatResponse(BaseModel):
    """Response from POST /api/v1/chat/message"""

    request_id: str
    session_id: str
    message_count: int
    assistant_response: str
    sources: list[ChatSourceReference] = Field(default_factory=list)
    tokens_used: Optional[int] = None


class ChatHistoryResponse(BaseModel):
    """Full conversation history for a session."""

    session_id: str
    user_id: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int
    messages: list[ChatMessageResponse]


# ────────────────────────────────────────────────────────────────────
# Metrics
# ────────────────────────────────────────────────────────────────────

class MetricSnapshot(BaseModel):
    """Single metric summary."""

    count: int = 0
    avg_time: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    total_time: float = 0.0
    errors: int = 0
    error_rate: float = 0.0


class MetricsResponse(BaseModel):
    """GET /api/v1/metrics"""

    metrics: dict[str, MetricSnapshot]
    collected_at: str


# ────────────────────────────────────────────────────────────────────
# Health
# ────────────────────────────────────────────────────────────────────

class HealthServiceStatus(BaseModel):
    """Individual service health."""

    status: str
    message: Optional[str] = None
    provider: Optional[str] = None


class HealthResponse(BaseModel):
    """GET /api/v1/health"""

    status: str
    timestamp: str
    services: dict[str, HealthServiceStatus]
