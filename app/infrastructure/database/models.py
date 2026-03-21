"""SQLAlchemy ORM models for database persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class DocumentORM(Base):
    """SQLAlchemy ORM model for documents."""

    __tablename__ = "documents"

    page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    book_slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list[DocumentChunkORM]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunkORM(Base):
    """SQLAlchemy ORM model for document chunks."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("page_id", "chunk_index", name="uq_document_chunks_page_chunk_index"),
    )

    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.page_id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[DocumentORM] = relationship(back_populates="chunks")


class IngestionRunORM(Base):
    """SQLAlchemy ORM model for ingestion runs."""

    __tablename__ = "ingestion_runs"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    processed_pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    page_audits: Mapped[list[PageSyncAuditORM]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PageSyncAuditORM(Base):
    """SQLAlchemy ORM model for page sync audits."""

    __tablename__ = "page_sync_audit"

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    local_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[IngestionRunORM] = relationship(back_populates="page_audits")


class ChatSessionORM(Base):
    """SQLAlchemy ORM model for chat sessions."""

    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID as string
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    is_archived: Mapped[bool] = mapped_column(default=False, index=True)

    messages: Mapped[list[ChatMessageORM]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessageORM(Base):
    """SQLAlchemy ORM model for chat messages."""

    __tablename__ = "chat_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID as string
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "user", "assistant", "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_metadata: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[ChatSessionORM] = relationship(back_populates="messages")


class QueryCacheORM(Base):
    """SQLAlchemy ORM model for query cache."""

    __tablename__ = "query_cache"

    cache_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256 hash
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    results: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3600")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
