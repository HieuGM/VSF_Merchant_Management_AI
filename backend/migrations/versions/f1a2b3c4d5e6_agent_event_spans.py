"""Add durable semantic span fields to the legacy agent event table.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-07-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("agent_events", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column("agent_events", sa.Column("span_id", sa.String(), nullable=True))
    op.add_column(
        "agent_events", sa.Column("parent_span_id", sa.String(), nullable=True)
    )
    op.add_column("agent_events", sa.Column("phase", sa.String(), nullable=True))
    op.add_column("agent_events", sa.Column("kind", sa.String(), nullable=True))
    op.add_column("agent_events", sa.Column("actor_type", sa.String(), nullable=True))
    op.add_column("agent_events", sa.Column("actor_name", sa.String(), nullable=True))
    op.add_column("agent_events", sa.Column("metrics_json", _JSONB, nullable=True))
    op.add_column(
        "agent_events", sa.Column("debug_payload_json", _JSONB, nullable=True)
    )
    # Legacy rows deliberately have NULL seq and are excluded.  The index
    # therefore guards exactly one semantic event for each run sequence.
    op.create_index(
        "uq_agent_events_trace_semantic_seq",
        "agent_events",
        ["trace_id", "seq"],
        unique=True,
        postgresql_where=sa.text("seq IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_events_trace_semantic_seq", table_name="agent_events")
    op.drop_column("agent_events", "debug_payload_json")
    op.drop_column("agent_events", "metrics_json")
    op.drop_column("agent_events", "actor_name")
    op.drop_column("agent_events", "actor_type")
    op.drop_column("agent_events", "kind")
    op.drop_column("agent_events", "phase")
    op.drop_column("agent_events", "parent_span_id")
    op.drop_column("agent_events", "span_id")
    op.drop_column("agent_events", "seq")
