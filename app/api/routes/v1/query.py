"""V1 query endpoints — clean route layer that delegates to QueryService."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.observability import get_metrics
from app.api.schemas.v1 import QueryRequest, QueryResponse, SourceInfo
from app.api.utils import generate_request_id
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.services import QueryService

logger = get_logger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


def _get_query_service(
    db=Depends(),
) -> QueryService:
    """Thin wrapper — actual wiring lives in dependencies.py."""
    from app.api.dependencies import get_query_service

    # get_query_service already receives db via Depends(get_db)
    raise NotImplementedError  # overridden below


# Re-use the real dependency directly
from app.api.dependencies import get_query_service as _dep_query_service


@router.post("", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    query_service: QueryService = Depends(_dep_query_service),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    """Execute a RAG query and return answer + sources."""
    request_id = generate_request_id()
    start = time.monotonic()

    logger.info(
        "query.request",
        request_id=request_id,
        query_preview=request.query[:100],
        top_k=request.top_k,
        use_llm=request.use_llm,
        rerank=request.rerank,
    )

    try:
        result = query_service.query(
            query=request.query,
            top_k=request.top_k,
            enable_reranking=request.rerank and settings.enable_reranking,
            enable_generation=request.use_llm and settings.enable_llm_generation,
        )

        sources: list[SourceInfo] = []
        if request.include_sources and result.sources:
            sources = [
                SourceInfo(
                    chunk_id=str(s.get("chunk_id", "")),
                    text=s.get("text", ""),
                    score=s.get("score", 0.0),
                    page_id=s.get("page_id"),
                    page_title=s.get("page_title"),
                )
                for s in result.sources
            ]

        latency_ms = (time.monotonic() - start) * 1000
        get_metrics().record("query", latency_ms, success=True)

        logger.info(
            "query.complete",
            request_id=request_id,
            results=len(sources),
            latency_ms=round(latency_ms, 2),
        )

        return QueryResponse(
            answer=result.answer,
            results=[],  # raw chunk dicts omitted in v1 — use sources
            sources=sources,
            latency_ms=round(latency_ms, 2),
        )

    except ValueError as exc:
        logger.warning("query.invalid_request", request_id=request_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        get_metrics().record("query", latency_ms, success=False)
        logger.error("query.failed", request_id=request_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed")
