"""runtime_agent_schema — §6.2 runtime records for agent integration (Phase 0 FROZEN)

Adds preference_events, interaction_events, agent_runs, agent_events; extends
merchant_profiles / chat_sessions / chat_messages; creates all §6.2 minimum indexes.

Single migration owned by the migration-chain owner (plan.md §[C2]). Do NOT create a
parallel Alembic head in Phase 1/2 — route schema changes through this chain.

Revision ID: a1b2c3d4e5f6
Revises: 026b4a8e16d0
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "026b4a8e16d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # --- merchant_profiles extension (§6.2) ---
    op.add_column("merchant_profiles", sa.Column("profile_json", _JSONB, nullable=True))
    op.add_column("merchant_profiles", sa.Column("schema_version", sa.String(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("source_kind", sa.String(), nullable=True))

    # --- chat_sessions extension (§6.2) ---
    op.add_column("chat_sessions", sa.Column("context_snapshot_json", _JSONB, nullable=True))
    op.add_column("chat_sessions", sa.Column("last_trace_id", sa.String(), nullable=True))

    # --- chat_messages extension (§6.2) ---
    op.add_column("chat_messages", sa.Column("trace_id", sa.String(), nullable=True))
    op.add_column("chat_messages", sa.Column("structured_payload_json", _JSONB, nullable=True))

    # --- preference_events (§6.6) ---
    op.create_table(
        "preference_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("value_json", _JSONB, nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("evidence_refs_json", _JSONB, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # --- interaction_events (§11.7) ---
    op.create_table(
        "interaction_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("merchant_id", sa.String(), nullable=True),
        sa.Column("menu_item_id", sa.String(), nullable=True),
        sa.Column("metadata_json", _JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # --- agent_runs (§6.2) ---
    op.create_table(
        "agent_runs",
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("crew_name", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("token_usage_json", _JSONB, nullable=True),
        sa.PrimaryKeyConstraint("trace_id"),
    )

    # --- agent_events (§6.2) ---
    op.create_table(
        "agent_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("parent_event_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("input_hash", sa.String(), nullable=True),
        sa.Column("output_summary_json", _JSONB, nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["trace_id"], ["agent_runs.trace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # --- §6.2 minimum indexes ---
    op.create_index("ix_merchants_city_cuisine", "merchants", ["city", "cuisine"])
    op.create_index("ix_merchants_lat_lng", "merchants", ["lat", "lng"])
    op.create_index("ix_menu_items_merchant_price", "menu_items", ["merchant_id", "price"])
    op.create_index("ix_reviews_merchant_created", "reviews", ["merchant_id", "created_at"])
    op.create_index("ix_pref_events_user_status_created", "preference_events", ["user_id", "status", "created_at"])
    op.create_index("ix_interaction_events_user_session_created", "interaction_events", ["user_id", "session_id", "created_at"])
    op.create_index("ix_agent_events_trace_created", "agent_events", ["trace_id", "created_at"])
    op.create_index("ix_chat_messages_session_timestamp", "chat_messages", ["session_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_timestamp", table_name="chat_messages")
    op.drop_index("ix_agent_events_trace_created", table_name="agent_events")
    op.drop_index("ix_interaction_events_user_session_created", table_name="interaction_events")
    op.drop_index("ix_pref_events_user_status_created", table_name="preference_events")
    op.drop_index("ix_reviews_merchant_created", table_name="reviews")
    op.drop_index("ix_menu_items_merchant_price", table_name="menu_items")
    op.drop_index("ix_merchants_lat_lng", table_name="merchants")
    op.drop_index("ix_merchants_city_cuisine", table_name="merchants")

    op.drop_table("agent_events")
    op.drop_table("agent_runs")
    op.drop_table("interaction_events")
    op.drop_table("preference_events")

    op.drop_column("chat_messages", "structured_payload_json")
    op.drop_column("chat_messages", "trace_id")
    op.drop_column("chat_sessions", "last_trace_id")
    op.drop_column("chat_sessions", "context_snapshot_json")
    op.drop_column("merchant_profiles", "source_kind")
    op.drop_column("merchant_profiles", "schema_version")
    op.drop_column("merchant_profiles", "profile_json")
