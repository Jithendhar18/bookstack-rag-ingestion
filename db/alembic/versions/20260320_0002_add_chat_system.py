"""Create chat and query cache tables.

Revision ID: 20260320_0002_add_chat_system
Revises: 20260315_0001_init_schema
Create Date: 2026-03-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "20260320_0002_add_chat_system"
down_revision = "20260315_0001_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create chat and query cache tables."""

    # Create chat_sessions table
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("session_id"),
        sa.Index("ix_chat_sessions_user_id", "user_id"),
        sa.Index("ix_chat_sessions_is_archived", "is_archived"),
    )

    # Create chat_messages table
    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.session_id"], ondelete="CASCADE"),
        sa.Index("ix_chat_messages_session_id", "session_id"),
    )

    # Create query_cache table
    op.create_table(
        "query_cache",
        sa.Column("cache_id", sa.String(64), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("filters", sa.Text(), nullable=True),
        sa.Column("results", sa.Text(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_id"),
        sa.Index("ix_query_cache_query_hash", "query_hash"),
        sa.Index("ix_query_cache_expires_at", "expires_at"),
    )


def downgrade() -> None:
    """Drop chat and query cache tables."""
    op.drop_table("query_cache")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
