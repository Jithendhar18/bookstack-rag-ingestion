"""V1 chat endpoints — sessions, messages, SSE streaming, archive."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.pagination import paginated_response
from app.api.response_formatters import format_chat_message, format_chat_session
from app.api.schemas.v1 import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSourceReference,
    CreateSessionRequest,
)
from app.api.utils import generate_request_id
from app.chat.chat_service import ChatService
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ── dependency ─────────────────────────────────────────────────────

def _get_chat_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    from app.api.dependencies import _get_embedding_service, _get_vector_store
    from app.llm.answer_generator import AnswerGenerator
    from app.retrieval.retriever import Retriever

    embedding_service = _get_embedding_service()
    vector_store = _get_vector_store()

    retriever = Retriever(
        embedding_service=embedding_service,
        vector_store=vector_store,
        settings=settings,
    )
    answer_generator = AnswerGenerator(settings=settings)
    return ChatService(
        session=db,
        retriever=retriever,
        answer_generator=answer_generator,
        settings=settings,
    )


# ── session management ─────────────────────────────────────────────

@router.post("/session", response_model=ChatSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    service: ChatService = Depends(_get_chat_service),
):
    """Create a new chat session."""
    session = service.create_session(user_id=request.user_id, title=request.title)
    return ChatSessionResponse(**format_chat_session(session))


@router.get("/session/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, le=500),
    service: ChatService = Depends(_get_chat_service),
):
    """Get full chat history for a session."""
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    history = service.get_session_history(session_id, limit=limit)
    messages = [ChatMessageResponse(**format_chat_message(m)) for m in history]
    return ChatHistoryResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        message_count=len(messages),
        messages=messages,
    )


@router.get("/sessions")
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    user_id: Optional[str] = Query(None),
    service: ChatService = Depends(_get_chat_service),
):
    """List chat sessions with page-based pagination."""
    offset = (page - 1) * limit
    sessions, total = service.list_sessions(user_id=user_id, limit=limit, offset=offset)
    items = [ChatSessionResponse(**format_chat_session(s)) for s in sessions]
    return paginated_response(items=items, total=total, page=page, limit=limit)


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    service: ChatService = Depends(_get_chat_service),
):
    """Delete a chat session and all its messages."""
    success = service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"message": f"Session {session_id} deleted"}


@router.post("/session/{session_id}/archive")
async def archive_session(
    session_id: str,
    service: ChatService = Depends(_get_chat_service),
):
    """Archive (soft-delete) a chat session."""
    success = service.archive_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"message": f"Session {session_id} archived"}


# ── messaging ──────────────────────────────────────────────────────

@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: ChatService = Depends(_get_chat_service),
):
    """Send a message and get a RAG-powered assistant response."""
    request_id = generate_request_id()
    logger.info("chat.message", request_id=request_id, session_id=request.session_id)

    try:
        response, history, sources = await service.chat(
            session_id=request.session_id,
            message=request.message,
            top_k=request.top_k,
            filters=request.filters,
            use_reranking=request.use_reranking,
            user_id=request.user_id,
        )

        source_refs = [
            ChatSourceReference(
                chunk_id=src["chunk_id"],
                page_id=src.get("page_id"),
                page_title=src.get("page_title"),
                score=src.get("score", 0.0),
            )
            for src in sources
        ]

        return ChatResponse(
            request_id=request_id,
            session_id=request.session_id,
            message_count=len(history),
            assistant_response=response,
            sources=source_refs,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("chat.error", request_id=request_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Chat failed")


# ── SSE streaming ──────────────────────────────────────────────────

@router.post("/message/stream")
async def stream_message(
    request: ChatRequest,
    service: ChatService = Depends(_get_chat_service),
):
    """Stream a chat response using Server-Sent Events (SSE).

    Emits ``data: {"token": "…"}`` lines followed by a final
    ``data: {"done": true, "sources": [...]}`` event.
    """
    request_id = generate_request_id()
    logger.info("chat.stream", request_id=request_id, session_id=request.session_id)

    async def _generate() -> AsyncGenerator[str, None]:
        try:
            # Validate session
            session = service.get_session(request.session_id)
            if not session:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                return
            if request.user_id and session.user_id and session.user_id != request.user_id:
                yield f"data: {json.dumps({'error': 'User mismatch'})}\n\n"
                return

            # Store user message
            await asyncio.to_thread(
                service.add_message, request.session_id, "user", request.message
            )

            # Build context (retrieval is blocking)
            history, chunks = await asyncio.to_thread(
                service.build_context,
                request.session_id,
                request.message,
                request.top_k,
                request.filters,
                request.use_reranking or False,
            )

            # Stream response from LLM
            full_response = ""
            if service.settings.enable_llm_generation:
                try:
                    stream = await asyncio.to_thread(
                        service.answer_generator.generate_stream,
                        request.message,
                        chunks,
                    )
                    for token in stream:
                        full_response += token
                        yield f"data: {json.dumps({'token': token})}\n\n"
                except AttributeError:
                    # Fallback: generator doesn't support streaming yet
                    response_text = await asyncio.to_thread(
                        service.answer_generator.generate,
                        request.message,
                        chunks,
                    )
                    full_response = response_text
                    yield f"data: {json.dumps({'token': response_text})}\n\n"
                except Exception as exc:
                    logger.error("chat.stream.llm_failed", error=str(exc))
                    full_response = f"Error generating response: {exc}"
                    yield f"data: {json.dumps({'token': full_response})}\n\n"
            else:
                full_response = service._summarize_chunks(chunks) if chunks else "No relevant information found."
                yield f"data: {json.dumps({'token': full_response})}\n\n"

            # Persist assistant message
            await asyncio.to_thread(
                service.add_message,
                request.session_id,
                "assistant",
                full_response,
                None,
                {"source_count": len(chunks)},
            )

            # Build source references
            source_refs = [
                {
                    "chunk_id": c.chunk_id,
                    "page_id": c.metadata.get("page_id"),
                    "page_title": c.metadata.get("page_title"),
                    "score": c.score,
                }
                for c in chunks
            ]

            yield f"data: {json.dumps({'done': True, 'sources': source_refs})}\n\n"

        except Exception as exc:
            logger.error("chat.stream.error", error=str(exc), exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Request-Id": request_id,
        },
    )


# ── WebSocket (preserved from v0) ─────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_chat(
    session_id: str,
    websocket: WebSocket,
    service: ChatService = Depends(_get_chat_service),
):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()
    logger.info("chat.ws_opened", session_id=session_id)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "").strip()
            if not message:
                await websocket.send_json({"error": "Empty message"})
                continue

            try:
                response, history, sources = await service.chat(
                    session_id=session_id,
                    message=message,
                    top_k=data.get("top_k"),
                    filters=data.get("filters"),
                    use_reranking=data.get("use_reranking", False),
                )
                await websocket.send_json(
                    {
                        "message_count": len(history),
                        "response": response,
                        "sources": sources,
                        "type": "response",
                    }
                )
            except ValueError as exc:
                await websocket.send_json({"error": str(exc), "type": "error"})
            except Exception as exc:
                logger.error("chat.ws_error", error=str(exc), exc_info=True)
                await websocket.send_json({"error": "Chat failed", "type": "error"})

    except WebSocketDisconnect:
        logger.info("chat.ws_closed", session_id=session_id)
    except Exception as exc:
        logger.error("chat.ws_exception", error=str(exc), exc_info=True)
        try:
            await websocket.close(code=1011, reason="Server error")
        except Exception:
            pass
