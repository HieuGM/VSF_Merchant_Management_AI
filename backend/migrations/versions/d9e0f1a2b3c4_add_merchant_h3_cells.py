"""Add indexed H3 cells to merchant coordinates.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-29
"""
from __future__ import annotations

from typing import Sequence, Union

import h3
import sqlalchemy as sa
from alembic import op


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESOLUTION = 8


def upgrade() -> None:
    op.add_column("merchants", sa.Column("merchant_h3_cell", sa.String(length=32)))
    op.create_index("ix_merchants_merchant_h3_cell", "merchants", ["merchant_h3_cell"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT merchant_id, lat, lng FROM merchants "
            "WHERE lat IS NOT NULL AND lng IS NOT NULL"
        )
    )
    for merchant_id, lat, lng in rows:
        bind.execute(
            sa.text(
                "UPDATE merchants SET merchant_h3_cell = :h3_cell "
                "WHERE merchant_id = :merchant_id"
            ),
            {
                "merchant_id": merchant_id,
                "h3_cell": h3.latlng_to_cell(float(lat), float(lng), _RESOLUTION),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_merchants_merchant_h3_cell", table_name="merchants")
    op.drop_column("merchants", "merchant_h3_cell")
