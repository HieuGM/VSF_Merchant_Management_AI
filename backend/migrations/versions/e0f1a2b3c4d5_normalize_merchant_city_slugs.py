"""Normalize persisted merchant city slugs to the canonical snake-case form.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE merchants SET city_slug = replace(city_slug, '-', '_') "
            "WHERE city_slug LIKE '%-%'"
        )
    )


def downgrade() -> None:
    # A generic string replacement cannot distinguish legacy hyphenated rows
    # from rows that were already canonical. Preserve canonical data instead.
    pass
