"""Finalize the typed merchant schema and remove legacy JSON columns.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_CHECK = (
    "source_kind IN "
    "('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')"
)


def _to_timestamptz(table: str, column: str) -> None:
    op.alter_column(
        table,
        column,
        type_=sa.TIMESTAMP(timezone=True),
        existing_type=sa.TIMESTAMP(timezone=False),
        postgresql_using=f"{column} AT TIME ZONE 'UTC'",
    )


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE merchant_dimension_calculations "
            "SET basis = 'avg_prep_time_min only' "
            "WHERE dimension = 'waiting_time'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE merchant_profiles AS profile "
            "SET waiting_time_score = LEAST(1, GREATEST(0, "
            "1 - (ops.avg_prep_time_min - 5) / 40)) "
            "FROM operational_metrics AS ops "
            "WHERE ops.merchant_id = profile.merchant_id "
            "AND ops.avg_prep_time_min IS NOT NULL"
        )
    )
    # Refuse destructive cleanup when the relational backfill is incomplete.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM merchant_profiles
                WHERE tier IS NULL
                   OR price_level IS NULL
                   OR food_quality_score IS NULL
                   OR image_quality_score IS NULL
                   OR delivery_quality_score IS NULL
                   OR packaging_score IS NULL
                   OR service_score IS NULL
                   OR waiting_time_score IS NULL
                   OR menu_diversity_score IS NULL
                   OR price_competitiveness_score IS NULL
              ) THEN
                RAISE EXCEPTION 'merchant relational backfill has incomplete profiles';
              END IF;
              IF EXISTS (
                SELECT m.merchant_id
                FROM merchant_profiles m
                LEFT JOIN merchant_dimension_calculations c
                  ON c.merchant_id = m.merchant_id
                GROUP BY m.merchant_id
                HAVING count(c.dimension) <> 8
              ) THEN
                RAISE EXCEPTION 'merchant relational backfill does not have eight calculations per profile';
              END IF;
            END $$;
            """
        )
    )

    # Finalize NOT NULL and source/range constraints on current-state data.
    for column in (
        "tier",
        "price_level",
        "food_quality_score",
        "image_quality_score",
        "delivery_quality_score",
        "packaging_score",
        "service_score",
        "waiting_time_score",
        "menu_diversity_score",
        "price_competitiveness_score",
        "scoring_version",
        "scored_at",
    ):
        op.alter_column("merchant_profiles", column, nullable=False)

    op.alter_column("operational_metrics", "source_kind", nullable=False)
    op.create_check_constraint(
        "ck_operational_metrics_source",
        "operational_metrics",
        _SOURCE_CHECK,
    )
    op.create_check_constraint(
        "ck_operational_metrics_prep",
        "operational_metrics",
        "avg_prep_time_min IS NULL OR avg_prep_time_min >= 0",
    )

    # Replace the temporary array column with the final peak_hours column.
    op.drop_column("operational_metrics", "peak_hours")
    op.alter_column(
        "operational_metrics",
        "peak_hours_text",
        new_column_name="peak_hours",
        existing_type=postgresql.ARRAY(sa.Text()),
        nullable=False,
    )
    op.alter_column(
        "operational_metrics",
        "avg_prep_time_min",
        type_=sa.Numeric(6, 2),
        existing_type=sa.Float(),
        postgresql_using="avg_prep_time_min::numeric(6,2)",
    )
    _to_timestamptz("operational_metrics", "updated_at")
    _to_timestamptz("merchant_profiles", "updated_at")

    # Convert existing timestamp columns to the explicit UTC-aware contract.
    for table, column in (
        ("merchants", "created_at"),
        ("menu_items", "created_at"),
        ("food_images", "created_at"),
    ):
        _to_timestamptz(table, column)

    # Legacy source JSON is no longer needed after the validated backfill.
    op.drop_column("merchant_profiles", "dimensions_json")
    op.drop_column("merchant_profiles", "profile_json")
    op.drop_column("merchant_profiles", "schema_version")
    op.drop_column("merchant_profiles", "source_kind")
    op.drop_column("merchants", "open_hours")

    # Reviews retain typed source/rating fields only.
    op.alter_column(
        "reviews",
        "rating",
        type_=sa.Numeric(4, 2),
        existing_type=sa.Float(),
        postgresql_using="rating::numeric(4,2)",
    )
    op.alter_column(
        "reviews",
        "text",
        type_=sa.Text(),
        existing_type=sa.String(),
    )
    op.alter_column("reviews", "source_kind", nullable=False)
    op.create_check_constraint(
        "ck_reviews_rating",
        "reviews",
        "rating IS NULL OR rating BETWEEN 0 AND 10",
    )
    op.create_check_constraint("ck_reviews_source_kind", "reviews", _SOURCE_CHECK)
    _to_timestamptz("reviews", "created_at")
    for column in (
        "foody_restaurant_id",
        "author_id",
        "author_name",
        "total_comment",
        "total_pictures",
        "review_url",
        "comments_json",
    ):
        op.drop_column("reviews", column)

    # Delivery feedback retains original event facts and typed provenance.
    op.alter_column(
        "delivery_feedbacks",
        "comment",
        type_=sa.Text(),
        existing_type=sa.String(),
    )
    op.alter_column("delivery_feedbacks", "source_kind", nullable=False)
    op.create_check_constraint(
        "ck_delivery_feedbacks_source_kind",
        "delivery_feedbacks",
        _SOURCE_CHECK,
    )
    _to_timestamptz("delivery_feedbacks", "created_at")

    # Item tags were copied merchant-level attributes and are now owned by
    # merchants. Item-level typed source fields remain.
    for column in ("diet_tags", "ingredient_tags", "taste_tags"):
        op.drop_column("menu_items", column)
    op.create_check_constraint(
        "ck_menu_items_price", "menu_items", "price >= 0"
    )
    op.create_check_constraint(
        "ck_menu_items_discount_price",
        "menu_items",
        "discount_price IS NULL OR discount_price >= 0",
    )
    op.create_check_constraint(
        "ck_menu_items_total_like", "menu_items", "total_like >= 0"
    )


def downgrade() -> None:
    raise RuntimeError(
        "merchant relational cleanup is destructive; restore "
        "/tmp/merchant_platform-before-relational-20260723.dump instead"
    )
