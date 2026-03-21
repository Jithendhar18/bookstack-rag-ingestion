from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.schemas import AskRequest, AskResponse, HealthResponse, Source, TokenUsage

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: Request, body: AskRequest) -> AskResponse:
    retrieval_service = request.app.state.retrieval_service
    llm_service = request.app.state.llm_service
    settings = request.app.state.settings

    chunks = retrieval_service.retrieve(question=body.question, top_k=body.top_k)

    if not chunks:
        conv_id = body.conversation_id or str(uuid.uuid4())
        return AskResponse(
            answer="I couldn't find any relevant information in the documentation to answer your question.",
            sources=[],
            model=settings.llm_model,
            conversation_id=conv_id,
        )

    result, conv_id = llm_service.generate_answer(
        question=body.question,
        chunks=chunks,
        conversation_id=body.conversation_id,
    )

    seen_pages: dict[int, Source] = {}
    for chunk in chunks:
        if chunk.page_id not in seen_pages:
            seen_pages[chunk.page_id] = Source(
                page_id=chunk.page_id,
                title=chunk.title,
                source_url=chunk.source_url,
                relevance_score=chunk.score,
            )

    return AskResponse(
        answer=result.answer,
        sources=list(seen_pages.values()),
        model=result.model,
        conversation_id=conv_id,
        usage=TokenUsage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.prompt_tokens + result.completion_tokens,
        ),
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    vector_store = request.app.state.vector_store
    count = vector_store.collection.count()
    return HealthResponse(status="ok", chunks_indexed=count)
