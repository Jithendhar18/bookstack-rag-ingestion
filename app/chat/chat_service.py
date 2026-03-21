"""Chat service for multi-turn RAG conversations."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.config.settings import Settings
from app.db.models import ChatMessage, ChatSession
from app.llm.answer_generator import AnswerGenerator
from app.retrieval.retriever import ChunkResult, Retriever

logger = get_logger(__name__)


class ChatService:
    """Manages multi-turn chat sessions with memory and context."""

    def __init__(
        self,
        session: Session,
        retriever: Retriever,
        answer_generator: AnswerGenerator,
        settings: Settings,
    ):
        """Initialize chat service.

        Args:
            session: SQLAlchemy database session
            retriever: Retriever for fetching relevant chunks
            answer_generator: LLM for generating answers
            settings: Application settings
        """
        self.session = session
        self.retriever = retriever
        self.answer_generator = answer_generator
        self.settings = settings

    def create_session(
        self, user_id: Optional[str] = None, title: Optional[str] = None
    ) -> ChatSession:
        """Create a new chat session.

        Args:
            user_id: Optional user identifier
            title: Optional session title

        Returns:
            New ChatSession
        """
        session_id = str(uuid4())
        chat_session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=title or f"Chat {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        )
        self.session.add(chat_session)
        self.session.commit()
        logger.info("chat.session_created", session_id=session_id, user_id=user_id)
        return chat_session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieve a chat session.

        Args:
            session_id: Session ID

        Returns:
            ChatSession or None if not found
        """
        return self.session.query(ChatSession).filter_by(session_id=session_id).first()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens_used: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> ChatMessage:
        """Add a message to a session.

        Args:
            session_id: Session ID
            role: Message role ("user", "assistant", "system")
            content: Message content
            tokens_used: Optional token count
            metadata: Optional metadata dict (source refs, etc.)

        Returns:
            New ChatMessage
        """
        message_id = str(uuid4())
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            tokens_used=tokens_used,
            extra_metadata=json.dumps(metadata) if metadata else None,
        )
        self.session.add(message)
        self.session.commit()
        logger.info("chat.message_added", role=role, session_id=session_id)
        return message

    def get_session_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[ChatMessage]:
        """Get chat history for a session.

        Args:
            session_id: Session ID
            limit: Optional limit on number of messages to return (default from settings)

        Returns:
            List of ChatMessage ordered by creation time
        """
        limit = limit or self.settings.chat_history_limit
        query = (
            self.session.query(ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def build_context(
        self,
        session_id: str,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
        use_reranking: bool = False,
    ) -> tuple[list[ChatMessage], list[ChunkResult]]:
        """Build context from history and retrieval.

        Args:
            session_id: Session ID
            query: User query
            top_k: Number of results to retrieve
            filters: Optional metadata filters
            use_reranking: Whether to apply reranking

        Returns:
            Tuple of (chat history, retrieved chunks)
        """
        # Get chat history
        history = self.get_session_history(session_id)

        # Retrieve relevant context
        try:
            chunks = self.retriever.retrieve(
                query=query,
                top_k=top_k or self.settings.top_k_default,
                filters=filters,
                use_reranking=use_reranking,
            )
        except Exception as e:
            logger.error("chat.retrieval_failed", error=str(e))
            chunks = []

        return history, chunks

    async def chat(
        self,
        session_id: str,
        message: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
        use_reranking: bool = False,
        user_id: Optional[str] = None,
    ) -> tuple[str, list[ChatMessage], list[dict]]:
        """Execute a chat turn.

        Args:
            session_id: Session ID
            message: User message
            top_k: Number of results to retrieve
            filters: Optional metadata filters
            use_reranking: Whether to apply reranking
            user_id: Optional user identifier for validation

        Returns:
            Tuple of (assistant response, updated history, source references)

        Raises:
            ValueError: If session not found or user_id mismatch
        """
        # Validate session exists and user matches
        chat_session = self.get_session(session_id)
        if not chat_session:
            raise ValueError(f"Session {session_id} not found")
        if user_id and chat_session.user_id and chat_session.user_id != user_id:
            raise ValueError(f"User mismatch for session {session_id}")

        # Add user message (blocking DB call wrapped for async safety)
        await asyncio.to_thread(self.add_message, session_id, "user", message)

        # Build context
        history, chunks = self.build_context(
            session_id=session_id,
            query=message,
            top_k=top_k,
            filters=filters,
            use_reranking=use_reranking,
        )

        # Build conversation context
        history_text = self._format_history(history)
        context_text = self._format_chunks(chunks)

        # Generate response
        if not self.settings.enable_llm_generation:
            # Fallback: return summary of retrieved chunks
            response = (
                self._summarize_chunks(chunks) if chunks else "No relevant information found."
            )
            source_refs = []
        else:
            try:
                response = await self.answer_generator.generate(
                    query=message,
                    chunks=chunks,
                    conversation_context=history_text,
                )
                source_refs = [
                    {
                        "chunk_id": chunk.chunk_id,
                        "page_id": chunk.metadata.get("page_id"),
                        "page_title": chunk.metadata.get("page_title"),
                        "score": chunk.score,
                    }
                    for chunk in chunks
                ]
            except Exception as e:
                logger.error("chat.llm_generation_failed", error=str(e))
                response = f"Error generating response: {str(e)}"
                source_refs = []

        # Add assistant response (blocking DB call wrapped for async safety)
        assistant_msg = await asyncio.to_thread(
            self.add_message,
            session_id,
            "assistant",
            response,
            None,
            {"source_count": len(chunks)},
        )

        # Update session timestamp
        chat_session.updated_at = datetime.now(timezone.utc)
        await asyncio.to_thread(self.session.commit)

        # Reuse the history we already fetched + the two new messages
        # instead of making a redundant DB query
        from app.db.models import ChatMessage as _CM

        user_msg_placeholder = _CM(
            message_id=str(uuid4()),
            session_id=session_id,
            role="user",
            content=message,
        )
        updated_history = list(history) + [user_msg_placeholder, assistant_msg]

        logger.info("chat.turn_completed", session_id=session_id)
        return response, updated_history, source_refs

    def _format_history(self, messages: list[ChatMessage], limit_tokens: int = 1000) -> str:
        """Format chat history for context.

        Args:
            messages: List of messages
            limit_tokens: Maximum tokens to include (rough estimate)

        Returns:
            Formatted history string
        """
        formatted = []
        token_count = 0

        for msg in reversed(messages):  # Start from most recent
            role_name = msg.role.capitalize()
            line = f"{role_name}: {msg.content}"
            tokens = len(msg.content.split()) + 2  # Rough estimate

            if token_count + tokens > limit_tokens:
                break

            formatted.insert(0, line)
            token_count += tokens

        return "\n".join(formatted) if formatted else "(No prior conversation)"

    def _format_chunks(self, chunks: list[ChunkResult]) -> str:
        """Format retrieved chunks for context.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Formatted context string
        """
        if not chunks:
            return "(No relevant information retrieved)"

        lines = ["Retrieved context:"]
        for i, chunk in enumerate(chunks, 1):
            page_title = chunk.metadata.get("page_title", "Unknown")
            section = chunk.metadata.get("section_path", "")
            preview = chunk.chunk_text[:200].replace("\n", " ")
            lines.append(f"\n[{i}] {page_title}")
            if section:
                lines.append(f"    Section: {section}")
            lines.append(f"    {preview}...")

        return "\n".join(lines)

    def _summarize_chunks(self, chunks: list[ChunkResult]) -> str:
        """Generate a simple summary of retrieved chunks.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Summary text
        """
        if not chunks:
            return "No relevant information found."

        lines = ["Based on the documentation:\n"]
        for chunk in chunks[:3]:  # Limit to top 3
            preview = chunk.chunk_text[:150].replace("\n", " ")
            lines.append(f"• {preview}...")
        return "\n".join(lines)

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        self.session.delete(session)
        self.session.commit()
        logger.info("chat.session_deleted", session_id=session_id)
        return True

    def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ChatSession], int]:
        """List chat sessions with pagination.

        Args:
            user_id: Optional user filter
            limit: Number of sessions per page
            offset: Page offset

        Returns:
            Tuple of (sessions list, total count)
        """
        query = self.session.query(ChatSession).filter_by(is_archived=False)
        if user_id:
            query = query.filter_by(user_id=user_id)

        total = query.count()
        sessions = query.order_by(ChatSession.updated_at.desc()).offset(offset).limit(limit).all()

        return sessions, total

    def archive_session(self, session_id: str) -> bool:
        """Archive a chat session.

        Args:
            session_id: Session ID

        Returns:
            True if archived, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        session.is_archived = True
        self.session.commit()
        logger.info("chat.session_archived", session_id=session_id)
        return True
