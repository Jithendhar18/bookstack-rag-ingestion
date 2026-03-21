from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    conversation_id: str | None = None


class Source(BaseModel):
    page_id: int
    title: str
    source_url: str
    relevance_score: float


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    model: str
    conversation_id: str
    usage: TokenUsage | None = None


class HealthResponse(BaseModel):
    status: str
    chunks_indexed: int
