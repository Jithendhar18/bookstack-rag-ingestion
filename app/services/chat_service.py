"""Chat service - multi-turn conversation management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.config.logging import get_logger
from app.domain.entities import ChatMessage, ChatSession
from app.domain.exceptions import ChatSessionNotFound, InvalidSessionState
from app.domain.repositories import IChatMessageRepository, IChatSessionRepository
from app.infrastructure.embeddings import IEmbeddingService
from app.infrastructure.external import ILLMClient
from app.services.document_service import DocumentService

logger = get_logger(__name__)


class ChatService:
    """
    Chat service for multi-turn RAG conversations.

    Responsibilities:
    - Manage chat sessions (create, retrieve, archive)
    - Store and retrieve messages
    - Coordinate with retriever and LLM for responses
    """

    def __init__(
        self,
        session_repo: IChatSessionRepository,
        message_repo: IChatMessageRepository,
        document_service: DocumentService,
        embedding_service: IEmbeddingService,
        llm_client: Optional[ILLMClient] = None,
    ):
        """Initialize chat service.

        Args:
            session_repo: Chat session repository
            message_repo: Chat message repository
            document_service: Document service for retrieval
            embedding_service: Embedding service for query vectors
            llm_client: Optional LLM for generating responses
        """
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.document_service = document_service
        self.embedding_service = embedding_service
        self.llm_client = llm_client

    def create_session(
        self,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> ChatSession:
        """Create a new chat session.

        Args:
            user_id: Optional user identifier
            title: Optional session title

        Returns:
            New ChatSession entity

        Raises:
            None - always succeeds
        """
        session_id = str(uuid4())
        now = datetime.now(timezone.utc)

        session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=title or f"Chat {now.strftime('%Y-%m-%d %H:%M')}",
            created_at=now,
            updated_at=now,
        )

        logger.info("chat.session_creating", session_id=session_id, user_id=user_id)
        return self.session_repo.create(session)

    def get_session(self, session_id: str) -> ChatSession:
        """Retrieve a chat session.

        Args:
            session_id: Session ID to retrieve

        Returns:
            ChatSession entity

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        session = self.session_repo.get_by_session_id(session_id)
        if not session:
            raise ChatSessionNotFound(session_id)
        return session

    def add_user_message(
        self,
        session_id: str,
        content: str,
        tokens_used: Optional[int] = None,
    ) -> ChatMessage:
        """Add user message to session.

        Args:
            session_id: Session ID
            content: Message content
            tokens_used: Optional token count

        Returns:
            New ChatMessage entity

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        # Verify session exists
        self.get_session(session_id)

        message_id = str(uuid4())
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            role="user",
            content=content,
            tokens_used=tokens_used,
            created_at=datetime.now(timezone.utc),
        )

        logger.debug("chat.user_message_added", session_id=session_id)
        return self.message_repo.create(message)

    def add_assistant_message(
        self,
        session_id: str,
        content: str,
        tokens_used: Optional[int] = None,
        sources: Optional[list[dict]] = None,
    ) -> ChatMessage:
        """Add assistant message to session (with optional source metadata).

        Args:
            session_id: Session ID
            content: Message content
            tokens_used: Optional token count
            sources: Optional list of source dicts (for RAG attribution)

        Returns:
            New ChatMessage entity

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        # Verify session exists
        self.get_session(session_id)

        message_id = str(uuid4())
        metadata = None
        if sources:
            metadata = json.dumps({"sources": sources})

        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            role="assistant",
            content=content,
            tokens_used=tokens_used,
            extra_metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )

        logger.debug("chat.assistant_message_added", session_id=session_id)
        return self.message_repo.create(message)

    def get_session_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[ChatMessage]:
        """Get messages from a session.

        Args:
            session_id: Session ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of ChatMessage entities

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        # Verify session exists
        self.get_session(session_id)

        return self.message_repo.get_by_session_id(session_id, limit=limit)

    def get_session_context(
        self,
        session_id: str,
        max_messages: int = 10,
    ) -> list[ChatMessage]:
        """Get recent messages for context building.

        Args:
            session_id: Session ID
            max_messages: Maximum messages to include

        Returns:
            List of recent ChatMessage entities

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        messages = self.get_session_messages(session_id, limit=max_messages)

        # If last message is from user (incomplete turn), exclude it
        if messages and messages[-1].role == "user":
            messages = messages[:-1]

        return messages

    def archive_session(self, session_id: str) -> ChatSession:
        """Archive a chat session.

        Args:
            session_id: Session ID to archive

        Returns:
            Updated ChatSession entity

        Raises:
            ChatSessionNotFound: If session does not exist
        """
        session = self.get_session(session_id)

        if session.is_archived:
            raise InvalidSessionState(session_id, "Session is already archived")

        session.archive()
        logger.info("chat.session_archived", session_id=session_id)
        return self.session_repo.update(session)

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and all messages.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted, False if not found
        """
        if not self.session_repo.get_by_session_id(session_id):
            return False

        # Delete messages first (cascade)
        self.message_repo.delete_by_session_id(session_id)

        # Delete session
        result = self.session_repo.delete(session_id)
        logger.info("chat.session_deleted", session_id=session_id)
        return result

    def get_user_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[ChatSession]:
        """Get all sessions for a user.

        Args:
            user_id: User ID
            limit: Maximum sessions to retrieve

        Returns:
            List of ChatSession entities
        """
        return self.session_repo.get_by_user_id(user_id, limit=limit)
