"""Query endpoints for RAG retrieval and generation."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_query_service
from app.api.utils import generate_request_id
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.services import QueryService

logger = get_logger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    """Request model for query endpoint."""

    query: str = Field(..., description="Natural language query", min_length=1, max_length=5000)
    top_k: Optional[int] = Field(
        default=None,
        description="Number of results to return",
        ge=1,
        le=50,
    )
    filters: Optional[dict[str, Any]] = Field(
        default=None,
        description="Metadata filters (e.g., page_id, section_path)",
    )
    use_llm: bool = Field(
        default=False,
        description="Generate answer using LLM",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include metadata in results",
    )
    keyword_boost: bool = Field(
        default=False,
        description="Boost results matching keywords",
    )


class QueryResultMetadata(BaseModel):
    """Metadata for a chunk result."""

    page_id: int
    document_title: str
    section_path: Optional[str] = None
    section_level: Optional[int] = None
    chunk_index: int


class QueryResult(BaseModel):
    """Single result from query."""

    chunk_id: str
    chunk_text: str
    score: float
    metadata: Optional[QueryResultMetadata] = None


class QueryResponse(BaseModel):
    """Response model for query endpoint."""

    request_id: str
    query: str
    num_results: int
    results: list[QueryResult]
    answer: Optional[str] = None
    metrics: dict[str, Any]


def _format_chunk_results(chunks: list, include_metadata: bool) -> list[QueryResult]:
    """Format retrieval chunks into API response models."""
    results = []
    for chunk in chunks:
        metadata = None
        if include_metadata and chunk.metadata:
            metadata = QueryResultMetadata(
                page_id=chunk.metadata.get("page_id", 0),
                document_title=chunk.metadata.get("document_title", "Unknown"),
                section_path=chunk.metadata.get("section_path"),
                section_level=chunk.metadata.get("section_level"),
                chunk_index=chunk.metadata.get("chunk_index", 0),
            )
        results.append(
            QueryResult(
                chunk_id=chunk.chunk_id,
                chunk_text=chunk.chunk_text,
                score=chunk.score,
                metadata=metadata,
            )
        )
    return results


@router.post("/")
async def query(
    request: QueryRequest,
    query_service: QueryService = Depends(get_query_service),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    """
    Query documents using natural language.

    Returns relevant chunks from vector database, optionally reranked
    and with LLM-generated answers.

    Example:
        ```json
        {
            "query": "What is IVA Digital in Chile?",
            "top_k": 5,
            "filters": {"page_id": 10},
            "use_llm": true,
            "include_metadata": true
        }
        ```
    """
    request_id = generate_request_id()

    try:
        # Validate request
        if not request.query or len(request.query) < 2:
            raise ValueError("Query must be at least 2 characters")

        logger.info(
            "query.request",
            request_id=request_id,
            query_preview=request.query[:100],
            top_k=request.top_k,
            use_llm=request.use_llm,
        )

        # Execute query
        use_llm = request.use_llm and settings.enable_llm_generation
        response = query_service.query(
            query_text=request.query,
            top_k=request.top_k,
            filters=request.filters,
            use_llm=use_llm,
            keyword_boost=request.keyword_boost,
        )

        # Format results
        formatted_results = _format_chunk_results(response.results, request.include_metadata)

        # Build response
        query_response = QueryResponse(
            request_id=request_id,
            query=request.query,
            num_results=len(formatted_results),
            results=formatted_results,
            answer=response.answer,
            metrics=response.metrics,
        )

        logger.info(
            "query.complete",
            request_id=request_id,
            results=len(formatted_results),
            total_ms=response.metrics.get("total_time_ms", 0),
        )

        return query_response

    except ValueError as exc:
        logger.warning("query.invalid_request", request_id=request_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("query.failed", request_id=request_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {str(exc)}",
        )


@router.post("/batch")
async def batch_query(
    requests: list[QueryRequest],
    query_service: QueryService = Depends(get_query_service),
    settings: Settings = Depends(get_settings),
) -> list[QueryResponse]:
    """
    Batch query endpoint for multiple queries at once.

    Useful for comparing results or processing multiple questions.
    Maximum 20 queries per batch.
    """
    if len(requests) > 20:
        raise HTTPException(status_code=400, detail="Batch size cannot exceed 20 queries")
    if not requests:
        raise HTTPException(status_code=400, detail="Batch must contain at least 1 query")

    batch_id = generate_request_id()
    logger.info("query.batch", batch_id=batch_id, count=len(requests))

    responses = []
    for idx, query_request in enumerate(requests):
        try:
            request_id = f"{batch_id}-{idx}"
            logger.debug(
                "query.batch_item", request_id=request_id, index=idx + 1, total=len(requests)
            )

            use_llm = query_request.use_llm and settings.enable_llm_generation
            response = query_service.query(
                query_text=query_request.query,
                top_k=query_request.top_k,
                filters=query_request.filters,
                use_llm=use_llm,
                keyword_boost=query_request.keyword_boost,
            )

            formatted_results = _format_chunk_results(
                response.results, query_request.include_metadata
            )

            responses.append(
                QueryResponse(
                    request_id=request_id,
                    query=query_request.query,
                    num_results=len(formatted_results),
                    results=formatted_results,
                    answer=response.answer,
                    metrics=response.metrics,
                )
            )

        except Exception as exc:
            logger.error("query.batch_item_failed", request_id=request_id, error=str(exc))
            responses.append(
                QueryResponse(
                    request_id=f"{batch_id}-{idx}",
                    query=query_request.query,
                    num_results=0,
                    results=[],
                    answer=None,
                    metrics={"error": str(exc)},
                )
            )

    logger.info("query.batch_complete", batch_id=batch_id, count=len(responses))
    return responses
