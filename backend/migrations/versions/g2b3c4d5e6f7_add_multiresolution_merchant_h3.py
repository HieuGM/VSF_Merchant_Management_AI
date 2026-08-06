"""Add and backfill multi-resolution merchant H3 indexes.

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import h3
import sqlalchemy as sa
from alembic import op


revision: str = "g2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("h3_index_6", sa.String(length=32)))
    op.add_column("merchants", sa.Column("h3_index_9", sa.String(length=32)))
    op.create_index("ix_merchants_h3_index_6", "merchants", ["h3_index_6"])
    op.create_index("ix_merchants_h3_index_9", "merchants", ["h3_index_9"])

    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT merchant_id, lat, lng FROM merchants "
                "WHERE lat IS NOT NULL AND lng IS NOT NULL"
            )
        )
    )
    update = sa.text(
        "UPDATE merchants "
        "SET h3_index_6 = :h3_index_6, "
        "merchant_h3_cell = :merchant_h3_cell, "
        "h3_index_9 = :h3_index_9 "
        "WHERE merchant_id = :merchant_id"
    )
    for merchant_id, lat, lng in rows:
        latitude = float(lat)
        longitude = float(lng)
        bind.execute(
            update,
            {
                "merchant_id": merchant_id,
                "h3_index_6": h3.latlng_to_cell(latitude, longitude, 6),
                "merchant_h3_cell": h3.latlng_to_cell(latitude, longitude, 8),
                "h3_index_9": h3.latlng_to_cell(latitude, longitude, 9),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_merchants_h3_index_9", table_name="merchants")
    op.drop_index("ix_merchants_h3_index_6", table_name="merchants")
    op.drop_column("merchants", "h3_index_9")
    op.drop_column("merchants", "h3_index_6")
