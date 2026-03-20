"""init schema

Revision ID: 20260315_0001
Revises: None
Create Date: 2026-03-15 03:00:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260315_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("page_id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("book_slug", sa.Text(), nullable=True),
        sa.Column("chapter_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "page_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.page_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("vector_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("page_id", "chunk_index", name="uq_document_chunks_page_chunk_index"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "page_sync_audit",
        sa.Column("audit_id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("ingestion_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index("idx_documents_updated_at", "documents", ["updated_at"], unique=False)
    op.create_index(
        "idx_document_chunks_page_chunk",
        "document_chunks",
        ["page_id", "chunk_index"],
        unique=False,
    )
    op.create_index("idx_document_chunks_vector_id", "document_chunks", ["vector_id"], unique=False)
    op.create_index("idx_page_sync_audit_run_id", "page_sync_audit", ["run_id"], unique=False)
    op.create_index("idx_page_sync_audit_page_id", "page_sync_audit", ["page_id"], unique=False)
    op.create_index("idx_page_sync_audit_status", "page_sync_audit", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_page_sync_audit_status", table_name="page_sync_audit")
    op.drop_index("idx_page_sync_audit_page_id", table_name="page_sync_audit")
    op.drop_index("idx_page_sync_audit_run_id", table_name="page_sync_audit")
    op.drop_index("idx_document_chunks_vector_id", table_name="document_chunks")
    op.drop_index("idx_document_chunks_page_chunk", table_name="document_chunks")
    op.drop_index("idx_documents_updated_at", table_name="documents")

    op.drop_table("page_sync_audit")
    op.drop_table("ingestion_runs")
    op.drop_table("document_chunks")
    op.drop_table("documents")
