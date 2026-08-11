"""user_liked_merchants — episodic memory (explicit merchant likes)

A durable junction table holding the CURRENT-STATE of a user's liked merchants (composite PK =
idempotent toggle). The append-only interaction_events log keeps the like/unlike history for
future time-decay; this table is the ranking/recall read-path.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_liked_merchants",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("merchant_id", sa.String(), nullable=False),
        sa.Column("liked_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "merchant_id"),
    )
    # Newest-first listing of a user's likes (composite PK already indexes user_id; this covers
    # the ordered "list my liked merchants" read used by the profile + FE).
    op.create_index(
        "ix_user_liked_merchants_user_liked_at",
        "user_liked_merchants",
        ["user_id", "liked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_liked_merchants_user_liked_at", table_name="user_liked_merchants")
    op.drop_table("user_liked_merchants")
