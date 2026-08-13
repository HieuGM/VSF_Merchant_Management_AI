"""user_profiles.allergens — durable allergy/avoid facts (no FIFO cap)

A dedicated JSONB list for permanent allergy/avoid declarations, DISTINCT from
context_memory.notes (which is FIFO-capped at 8). Allergies are safety-critical and must NOT be
evicted under durable-fact pressure (memory_test.json 6.1). Mirrors the liked_cuisines/dietary
JSONB-list columns (nullable, no server_default, no MutableDict — the repo layer coerces NULL→[]
and reassigns on write).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("allergens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "allergens")
