"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# === Query Schemas ===
class QueryRequest(BaseModel):
    """Query endpoint request."""

    query: str = Field(..., min_length=1, description="User query")
    top_k: int = Field(default=5, ge=1, le=100, description="Number of results")
    enable_reranking: bool = Field(default=False, description="Enable reranking")
    enable_generation: bool = Field(default=False, description="Generate answer with LLM")


class SourceInfo(BaseModel):
    """Source information in query result."""

    chunk_id: int
    text: str
    score: float


class QueryResponse(BaseModel):
    """Query endpoint response."""

    query: str
    answer: Optional[str] = None
    sources: list[SourceInfo] = []
    retrieval_time_ms: float
    total_time_ms: float
    cache_hit: bool = False


# === Chat Schemas ===
class CreateChatSessionRequest(BaseModel):
    """Create chat session request."""

    user_id: Optional[str] = None
    title: Optional[str] = None


class ChatSessionResponse(BaseModel):
    """Chat session response."""

    session_id: str
    user_id: Optional[str]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    message_count: int = 0


class AddMessageRequest(BaseModel):
    """Add message request."""

    content: str = Field(..., min_length=1, description="Message content")
    role: str = Field(default="user", description="Message role")


class ChatMessageResponse(BaseModel):
    """Chat message response."""

    message_id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    tokens_used: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


# === Ingestion Schemas ===
class StartIngestionRequest(BaseModel):
    """Start ingestion request."""

    mode: str = Field(default="full", description="Ingestion mode: 'full' or 'incremental'")
    dry_run: bool = Field(default=False, description="Validate without storing")


class IngestionRunResponse(BaseModel):
    """Ingestion run response."""

    run_id: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    processed_pages: int = 0
    failed_pages: int = 0
    notes: Optional[str] = None


class IngestionStatsResponse(BaseModel):
    """Ingestion statistics response."""

    total_documents: int = 0
    total_chunks: int = 0
    last_ingestion: Optional[datetime] = None


# === Health Schemas ===
class ComponentHealth(BaseModel):
    """Individual component health."""

    status: str  # "healthy", "degraded", "unhealthy"
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    components: dict[str, ComponentHealth]


# === Error Schemas ===
class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    message: str
    code: Optional[str] = None
    timestamp: datetime


class ValidationErrorResponse(ErrorResponse):
    """Validation error response."""

    field: Optional[str] = None
