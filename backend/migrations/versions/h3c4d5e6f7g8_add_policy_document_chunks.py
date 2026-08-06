"""Add normalized policy documents and structure-aware chunks.

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "h3c4d5e6f7g8"
down_revision: Union[str, Sequence[str], None] = "g2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("policy_updated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint("source_url"),
    )
    op.create_index("ix_policy_documents_category", "policy_documents", ["category"])
    op.create_table(
        "policy_document_chunks",
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "section_path",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["policy_documents.document_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index(
        "ix_policy_document_chunks_document_id",
        "policy_document_chunks",
        ["document_id"],
    )
    op.create_index(
        "uq_policy_document_chunks_document_index",
        "policy_document_chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_policy_document_chunks_document_index",
        table_name="policy_document_chunks",
    )
    op.drop_index(
        "ix_policy_document_chunks_document_id",
        table_name="policy_document_chunks",
    )
    op.drop_table("policy_document_chunks")
    op.drop_index("ix_policy_documents_category", table_name="policy_documents")
    op.drop_table("policy_documents")
