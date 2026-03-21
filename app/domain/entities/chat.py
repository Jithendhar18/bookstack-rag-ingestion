"""Chat domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ChatMessage:
    """Individual message in a chat session."""

    message_id: str
    session_id: str
    role: str  # "user", "assistant", "system"
    content: str
    created_at: datetime
    tokens_used: Optional[int] = None
    extra_metadata: Optional[str] = None  # JSON metadata with source refs, etc.

    def __hash__(self) -> int:
        """Make messages hashable by their ID."""
        return hash(self.message_id)

    def is_user_message(self) -> bool:
        """Check if message is from user."""
        return self.role == "user"

    def is_assistant_message(self) -> bool:
        """Check if message is from assistant."""
        return self.role == "assistant"


@dataclass
class ChatSession:
    """Multi-turn chat session for RAG conversations."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    title: Optional[str] = None
    user_id: Optional[str] = None
    is_archived: bool = False
    messages: list[ChatMessage] = field(default_factory=list)

    def __hash__(self) -> int:
        """Make sessions hashable by their ID."""
        return hash(self.session_id)

    def add_message(self, message: ChatMessage) -> None:
        """Add message to session."""
        if message.session_id != self.session_id:
            raise ValueError(
                f"Message session_id {message.session_id} does not match {self.session_id}"
            )
        self.messages.append(message)

    def get_messages_for_context(self, limit: int = 10) -> list[ChatMessage]:
        """Get recent messages for context, excluding most recent if user message."""
        context_messages = self.messages[-limit:]
        # Filter out incomplete conversations (ends with user message)
        if context_messages and context_messages[-1].role == "user":
            return context_messages[:-1]
        return context_messages

    def message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)

    def archive(self) -> None:
        """Archive the session."""
        self.is_archived = True
        self.updated_at = datetime.now(timezone.utc)
