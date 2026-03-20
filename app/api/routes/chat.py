"""Chat API routes for multi-turn RAG conversations."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.response_formatters import format_chat_message, format_chat_session
from app.api.utils import generate_request_id
from app.chat.chat_service import ChatService
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# Dependency: Get chat service (reuses cached singletons for expensive components)
def get_chat_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    """Get chat service instance with shared singleton services."""
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


# Request/Response Models
class CreateSessionRequest(BaseModel):
    """Request to create a chat session."""

    user_id: Optional[str] = Field(None, description="Optional user identifier", max_length=100)
    title: Optional[str] = Field(None, description="Optional session title", max_length=200)


class ChatSessionResponse(BaseModel):
    """Chat session details."""

    session_id: str
    user_id: Optional[str] = None
    title: Optional[str] = None
    created_at: str
    updated_at: str
    is_archived: bool

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """Chat message details."""

    message_id: str
    session_id: str
    role: str
    content: str
    tokens_used: Optional[int] = None
    created_at: str

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Request to send a chat message."""

    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., min_length=1, max_length=5000, description="Message text")
    top_k: Optional[int] = Field(None, description="Number of results to retrieve")
    filters: Optional[dict] = Field(None, description="Metadata filters")
    use_reranking: bool = Field(False, description="Apply cross-encoder reranking")
    user_id: Optional[str] = Field(None, description="User identifier for validation")


class SourceReference(BaseModel):
    """Reference to source chunk."""

    chunk_id: str
    page_id: Optional[int] = None
    page_title: Optional[str] = None
    score: float


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    request_id: str
    session_id: str
    message_count: int
    assistant_response: str
    sources: list[SourceReference] = Field(default_factory=list)
    tokens_used: Optional[int] = None

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """Full conversation history."""

    session_id: str
    user_id: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int
    messages: list[ChatMessageResponse]

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """List of chat sessions with pagination."""

    sessions: list[ChatSessionResponse]
    total: int
    limit: int
    offset: int


# Endpoints
@router.post("/session", response_model=ChatSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    service: ChatService = Depends(get_chat_service),
):
    """Create a new chat session.

    Args:
        request: Session creation parameters
        service: Chat service instance

    Returns:
        ChatSessionResponse with session_id
    """
    request_id = generate_request_id()
    logger.info("chat.create_session", request_id=request_id, user_id=request.user_id)

    try:
        session = service.create_session(user_id=request.user_id, title=request.title)
        return ChatSessionResponse(**format_chat_session(session))
    except Exception as e:
        logger.error(
            "chat.create_session_failed", request_id=request_id, error=str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    """Send a message in a chat session.

    Args:
        request: Message and parameters
        service: Chat service instance

    Returns:
        ChatResponse with assistant response and sources

    Raises:
        HTTPException: 404 if session not found, 400 for validation errors
    """
    request_id = generate_request_id()
    logger.info("chat.message", request_id=request_id, session_id=request.session_id)

    try:
        # Execute chat turn
        response, history, sources = await service.chat(
            session_id=request.session_id,
            message=request.message,
            top_k=request.top_k,
            filters=request.filters,
            use_reranking=request.use_reranking,
            user_id=request.user_id,
        )

        # Convert sources to response format
        source_refs = [
            SourceReference(
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

    except ValueError as e:
        logger.error("chat.validation_error", request_id=request_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("chat.error", request_id=request_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.get("/session/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, le=500),
    service: ChatService = Depends(get_chat_service),
):
    """Get full chat history for a session.

    Args:
        session_id: Session ID
        limit: Optional limit on number of messages
        service: Chat service instance

    Returns:
        ChatHistoryResponse with all messages

    Raises:
        HTTPException: 404 if session not found
    """
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    history = service.get_session_history(session_id, limit=limit)
    messages = [ChatMessageResponse(**format_chat_message(msg)) for msg in history]

    return ChatHistoryResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        message_count=len(history),
        messages=messages,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: ChatService = Depends(get_chat_service),
):
    """List chat sessions with pagination.

    Args:
        user_id: Optional user filter
        limit: Results per page
        offset: Page offset
        service: Chat service instance

    Returns:
        SessionListResponse with sessions and pagination info
    """
    sessions, total = service.list_sessions(user_id=user_id, limit=limit, offset=offset)
    session_items = [ChatSessionResponse(**format_chat_session(s)) for s in sessions]

    return SessionListResponse(
        sessions=session_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
):
    """Delete a chat session.

    Args:
        session_id: Session ID
        service: Chat service instance

    Returns:
        Success message or 404

    Raises:
        HTTPException: 404 if session not found
    """
    success = service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {"message": f"Session {session_id} deleted"}


@router.post("/session/{session_id}/archive")
async def archive_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
):
    """Archive a chat session (soft delete).

    Args:
        session_id: Session ID
        service: Chat service instance

    Returns:
        Success message or 404

    Raises:
        HTTPException: 404 if session not found
    """
    success = service.archive_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {"message": f"Session {session_id} archived"}


# WebSocket support for streaming responses (optional, bonus feature)
@router.websocket("/ws/{session_id}")
async def websocket_chat(
    session_id: str,
    websocket: WebSocket,
    service: ChatService = Depends(get_chat_service),
):
    """WebSocket endpoint for streaming chat responses.

    Allows real-time chat with streaming LLM responses.

    Args:
        session_id: Chat session ID
        websocket: WebSocket connection
        service: Chat service instance
    """
    await websocket.accept()
    logger.info("chat.ws_opened", session_id=session_id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            message = data.get("message", "").strip()
            if not message:
                await websocket.send_json({"error": "Empty message"})
                continue

            try:
                # Execute chat
                response, history, sources = await service.chat(
                    session_id=session_id,
                    message=message,
                    top_k=data.get("top_k"),
                    filters=data.get("filters"),
                    use_reranking=data.get("use_reranking", False),
                )

                # Send response
                await websocket.send_json(
                    {
                        "message_count": len(history),
                        "response": response,
                        "sources": sources,
                        "type": "response",
                    }
                )

            except ValueError as e:
                await websocket.send_json({"error": str(e), "type": "error"})
            except Exception as e:
                logger.error("chat.ws_error", error=str(e), exc_info=True)
                await websocket.send_json({"error": "Chat failed", "type": "error"})

    except WebSocketDisconnect:
        logger.info("chat.ws_closed", session_id=session_id)
    except Exception as e:
        logger.error("chat.ws_exception", error=str(e), exc_info=True)
        try:
            await websocket.close(code=1011, reason="Server error")
        except Exception:
            pass
