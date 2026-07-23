"""Expand merchant domain to a typed current-state relational schema.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_CHECK = (
    "source_kind IN "
    "('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')"
)
_DIMENSION_CHECK = (
    "dimension IN "
    "('food_quality', 'image_quality', 'delivery_quality', 'packaging', "
    "'service', 'waiting_time', 'menu_diversity', 'price_competitiveness')"
)


def upgrade() -> None:
    # Merchant identity and filterable attributes. Legacy open_hours remains
    # available until the validated cleanup migration.
    op.add_column("merchants", sa.Column("category", sa.Text(), nullable=True))
    op.add_column("merchants", sa.Column("opens_at", sa.Time(), nullable=True))
    op.add_column("merchants", sa.Column("closes_at", sa.Time(), nullable=True))
    op.add_column(
        "merchants",
        sa.Column(
            "timezone",
            sa.String(),
            nullable=False,
            server_default="Asia/Ho_Chi_Minh",
        ),
    )
    for name in (
        "taste_tags",
        "diet_tags",
        "ingredient_tags",
        "customer_segments",
    ):
        op.add_column(
            "merchants",
            sa.Column(
                name,
                postgresql.ARRAY(sa.Text()),
                nullable=False,
                server_default=sa.text("ARRAY[]::text[]"),
            ),
        )
    op.add_column(
        "merchants",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "merchants",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.alter_column(
        "merchants",
        "is_demo_target",
        existing_type=sa.Integer(),
        type_=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
        postgresql_using="is_demo_target <> 0",
    )
    op.create_check_constraint(
        "ck_merchants_coordinate_pair",
        "merchants",
        "(lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_merchants_lat", "merchants", "lat IS NULL OR lat BETWEEN -90 AND 90"
    )
    op.create_check_constraint(
        "ck_merchants_lng", "merchants", "lng IS NULL OR lng BETWEEN -180 AND 180"
    )

    # Current profile typed columns. They remain nullable during backfill.
    op.add_column("merchant_profiles", sa.Column("tier", sa.String(), nullable=True))
    op.add_column(
        "merchant_profiles", sa.Column("price_level", sa.String(), nullable=True)
    )
    score_columns = (
        "food_quality_score",
        "image_quality_score",
        "delivery_quality_score",
        "packaging_score",
        "service_score",
        "waiting_time_score",
        "menu_diversity_score",
        "price_competitiveness_score",
    )
    for name in score_columns:
        op.add_column(
            "merchant_profiles", sa.Column(name, sa.Numeric(4, 3), nullable=True)
        )
        op.create_check_constraint(
            f"ck_merchant_profiles_{name}",
            "merchant_profiles",
            f"{name} IS NULL OR {name} BETWEEN 0 AND 1",
        )
    op.add_column(
        "merchant_profiles",
        sa.Column(
            "overall_score_internal",
            sa.Numeric(4, 3),
            sa.Computed(
                "("
                "food_quality_score + image_quality_score + "
                "delivery_quality_score + packaging_score + service_score + "
                "waiting_time_score + menu_diversity_score + "
                "price_competitiveness_score"
                ") / 8.0",
                persisted=True,
            ),
        ),
    )
    op.add_column(
        "merchant_profiles",
        sa.Column("scoring_version", sa.String(), nullable=True),
    )
    op.add_column(
        "merchant_profiles",
        sa.Column("scored_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_merchant_profiles_tier",
        "merchant_profiles",
        "tier IS NULL OR tier IN ('hero', 'background')",
    )
    op.create_check_constraint(
        "ck_merchant_profiles_price_level",
        "merchant_profiles",
        "price_level IS NULL OR price_level IN ('rẻ', 'trung bình', 'cao cấp')",
    )

    # Current operational facts. Keep legacy JSON peak_hours until cleanup.
    op.add_column(
        "operational_metrics", sa.Column("cancel_rate", sa.Numeric(5, 4))
    )
    op.add_column(
        "operational_metrics", sa.Column("acceptance_rate", sa.Numeric(5, 4))
    )
    op.add_column(
        "operational_metrics", sa.Column("estimated_daily_orders", sa.Integer())
    )
    op.add_column(
        "operational_metrics",
        sa.Column(
            "peak_hours_text",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
    )
    op.add_column(
        "operational_metrics",
        sa.Column("avg_delivery_time_min", sa.Numeric(6, 2)),
    )
    op.add_column(
        "operational_metrics", sa.Column("on_time_rate", sa.Numeric(5, 4))
    )
    op.add_column(
        "operational_metrics", sa.Column("driver_rating", sa.Numeric(3, 2))
    )
    op.add_column(
        "operational_metrics", sa.Column("packaging_ok_rate", sa.Numeric(5, 4))
    )
    op.add_column(
        "operational_metrics", sa.Column("source_kind", sa.String(), nullable=True)
    )
    op.add_column(
        "operational_metrics",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    for name in ("cancel_rate", "acceptance_rate", "on_time_rate", "packaging_ok_rate"):
        op.create_check_constraint(
            f"ck_operational_metrics_{name}",
            "operational_metrics",
            f"{name} IS NULL OR {name} BETWEEN 0 AND 1",
        )
    op.create_check_constraint(
        "ck_operational_metrics_daily_orders",
        "operational_metrics",
        "estimated_daily_orders IS NULL OR estimated_daily_orders >= 0",
    )
    op.create_check_constraint(
        "ck_operational_metrics_delivery_time",
        "operational_metrics",
        "avg_delivery_time_min IS NULL OR avg_delivery_time_min >= 0",
    )
    op.create_check_constraint(
        "ck_operational_metrics_driver_rating",
        "operational_metrics",
        "driver_rating IS NULL OR driver_rating BETWEEN 0 AND 5",
    )

    # Rating facts.
    op.create_table(
        "merchant_ratings",
        sa.Column(
            "merchant_id",
            sa.String(),
            sa.ForeignKey("merchants.merchant_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("shopeefood_rating", sa.Numeric(3, 2)),
        sa.Column("shopeefood_review_count", sa.Integer()),
        sa.Column("foody_rating", sa.Numeric(4, 2)),
        sa.Column("foody_review_count", sa.Integer()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "shopeefood_rating IS NULL OR shopeefood_rating BETWEEN 0 AND 5",
            name="ck_merchant_ratings_shopeefood",
        ),
        sa.CheckConstraint(
            "foody_rating IS NULL OR foody_rating BETWEEN 0 AND 10",
            name="ck_merchant_ratings_foody",
        ),
        sa.CheckConstraint(
            "shopeefood_review_count IS NULL OR shopeefood_review_count >= 0",
            name="ck_merchant_ratings_shopeefood_count",
        ),
        sa.CheckConstraint(
            "foody_review_count IS NULL OR foody_review_count >= 0",
            name="ck_merchant_ratings_foody_count",
        ),
    )

    op.create_table(
        "merchant_dimension_calculations",
        sa.Column(
            "merchant_id",
            sa.String(),
            sa.ForeignKey("merchants.merchant_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dimension", sa.String(), primary_key=True),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("scoring_version", sa.String(), nullable=False),
        sa.Column("calculated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(_DIMENSION_CHECK, name="ck_dimension_calculations_dimension"),
        sa.CheckConstraint(_SOURCE_CHECK, name="ck_dimension_calculations_source"),
    )

    op.create_table(
        "merchant_dimension_evidence",
        sa.Column("evidence_id", sa.String(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.String(),
            sa.ForeignKey("merchants.merchant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(), nullable=False),
        sa.Column("evidence_type", sa.String(), nullable=False),
        sa.Column("value_numeric", sa.Numeric()),
        sa.Column("value_text", sa.Text()),
        sa.Column("value_boolean", sa.Boolean()),
        sa.Column("unit", sa.String()),
        sa.Column("reference_type", sa.String()),
        sa.Column(
            "reference_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(_DIMENSION_CHECK, name="ck_dimension_evidence_dimension"),
        sa.CheckConstraint(_SOURCE_CHECK, name="ck_dimension_evidence_source"),
        sa.CheckConstraint(
            "num_nonnulls(value_numeric, value_text, value_boolean) = 1",
            name="ck_dimension_evidence_one_value",
        ),
    )
    op.create_index(
        "ix_dimension_evidence_merchant_dimension",
        "merchant_dimension_evidence",
        ["merchant_id", "dimension"],
    )

    op.create_table(
        "merchant_complaints",
        sa.Column("complaint_id", sa.String(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.String(),
            sa.ForeignKey("merchants.merchant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date()),
        sa.Column(
            "review_id",
            sa.String(),
            sa.ForeignKey("reviews.review_id", ondelete="SET NULL"),
        ),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "category IN "
            "('giao_hàng_trễ', 'món_nguội', 'sai_hoặc_thiếu_món', "
            "'đóng_gói_kém', 'thái_độ_phục_vụ', 'giá_cao', 'vệ_sinh', "
            "'chất_lượng_món')",
            name="ck_merchant_complaints_category",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_merchant_complaints_severity",
        ),
        sa.CheckConstraint(_SOURCE_CHECK, name="ck_merchant_complaints_source"),
    )
    op.create_index(
        "ix_merchant_complaints_merchant_category_date",
        "merchant_complaints",
        ["merchant_id", "category", "occurred_on"],
    )

    op.create_table(
        "market_trending_dishes",
        sa.Column("city_slug", sa.String(), primary_key=True),
        sa.Column("cuisine", sa.String(), primary_key=True),
        sa.Column("dish_name", sa.Text(), primary_key=True),
        sa.Column("trend_score", sa.Numeric(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("rank > 0", name="ck_market_trending_dishes_rank"),
    )

    # Preserve source facts currently discarded by the importer.
    op.add_column("reviews", sa.Column("source_kind", sa.String(), nullable=True))
    op.add_column(
        "delivery_feedbacks", sa.Column("on_time", sa.Boolean(), nullable=True)
    )
    op.add_column("delivery_feedbacks", sa.Column("issue", sa.Text(), nullable=True))
    op.add_column(
        "delivery_feedbacks", sa.Column("source_kind", sa.String(), nullable=True)
    )
    op.add_column("menu_items", sa.Column("discount_price", sa.Integer()))
    op.add_column(
        "menu_items",
        sa.Column("total_like", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "menu_items",
        sa.Column("has_photo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "menu_items",
        sa.Column(
            "is_available", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    for name in ("is_available", "has_photo", "total_like", "discount_price"):
        op.drop_column("menu_items", name)
    for name in ("source_kind", "issue", "on_time"):
        op.drop_column("delivery_feedbacks", name)
    op.drop_column("reviews", "source_kind")

    op.drop_table("market_trending_dishes")
    op.drop_index(
        "ix_merchant_complaints_merchant_category_date",
        table_name="merchant_complaints",
    )
    op.drop_table("merchant_complaints")
    op.drop_index(
        "ix_dimension_evidence_merchant_dimension",
        table_name="merchant_dimension_evidence",
    )
    op.drop_table("merchant_dimension_evidence")
    op.drop_table("merchant_dimension_calculations")
    op.drop_table("merchant_ratings")

    for name in (
        "updated_at",
        "source_kind",
        "packaging_ok_rate",
        "driver_rating",
        "on_time_rate",
        "avg_delivery_time_min",
        "peak_hours_text",
        "estimated_daily_orders",
        "acceptance_rate",
        "cancel_rate",
    ):
        op.drop_column("operational_metrics", name)

    op.drop_constraint(
        "ck_merchant_profiles_price_level", "merchant_profiles", type_="check"
    )
    op.drop_constraint("ck_merchant_profiles_tier", "merchant_profiles", type_="check")
    op.drop_column("merchant_profiles", "scored_at")
    op.drop_column("merchant_profiles", "scoring_version")
    op.drop_column("merchant_profiles", "overall_score_internal")
    for name in (
        "price_competitiveness_score",
        "menu_diversity_score",
        "waiting_time_score",
        "service_score",
        "packaging_score",
        "delivery_quality_score",
        "image_quality_score",
        "food_quality_score",
    ):
        op.drop_constraint(
            f"ck_merchant_profiles_{name}", "merchant_profiles", type_="check"
        )
        op.drop_column("merchant_profiles", name)
    op.drop_column("merchant_profiles", "price_level")
    op.drop_column("merchant_profiles", "tier")

    op.drop_constraint("ck_merchants_lng", "merchants", type_="check")
    op.drop_constraint("ck_merchants_lat", "merchants", type_="check")
    op.drop_constraint("ck_merchants_coordinate_pair", "merchants", type_="check")
    op.alter_column(
        "merchants",
        "is_demo_target",
        existing_type=sa.Boolean(),
        type_=sa.Integer(),
        nullable=True,
        server_default="0",
        postgresql_using="CASE WHEN is_demo_target THEN 1 ELSE 0 END",
    )
    for name in (
        "updated_at",
        "is_active",
        "customer_segments",
        "ingredient_tags",
        "diet_tags",
        "taste_tags",
        "timezone",
        "closes_at",
        "opens_at",
        "category",
    ):
        op.drop_column("merchants", name)
