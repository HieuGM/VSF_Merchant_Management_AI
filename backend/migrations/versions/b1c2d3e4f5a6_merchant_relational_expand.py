"""merchant_relational_expand — Stage B/C/D expand + backfill (core-first)

Additive relational refactor of the merchant data domain per
`docs/2026-07-23-merchant-relational-schema-design.md`. Scope for this pass is
core-first + expand-only:

- extend `merchants` with typed filterable columns (times, tags, flags, tz);
- extend `merchant_profiles` with the eight typed 0..1 score columns, tier and
  categorical price_level, and internal overall score;
- create `merchant_ratings` (external platform rating facts);
- extend `operational_metrics` with delivery/operation KPIs;
- backfill every new column/table from the legacy `dimensions_json`;
- add CHECK constraints (validating the backfill) and core indexes.

Legacy JSON (`merchant_profiles.dimensions_json` / `profile_json`,
`merchants.open_hours`, integer `is_demo_target`) is intentionally KEPT as a
runtime fallback. Deferred to a later cutover migration: dimension
calculations/evidence, complaints, market trending, boolean demo flag, dropping
legacy JSON. Backfill statements are idempotent (re-runnable).

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_ARRAY = postgresql.ARRAY(sa.Text())
_TZ = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. DDL — additive columns (all nullable / defaulted), keep legacy
    # ------------------------------------------------------------------
    # merchants: typed filterable fields
    op.add_column("merchants", sa.Column("category", sa.Text(), nullable=True))
    op.add_column("merchants", sa.Column("opens_at", sa.Time(), nullable=True))
    op.add_column("merchants", sa.Column("closes_at", sa.Time(), nullable=True))
    op.add_column("merchants", sa.Column(
        "timezone", sa.Text(), nullable=False,
        server_default=sa.text("'Asia/Ho_Chi_Minh'")))
    for col in ("taste_tags", "diet_tags", "ingredient_tags", "customer_segments"):
        op.add_column("merchants", sa.Column(
            col, _TEXT_ARRAY, nullable=False, server_default=sa.text("'{}'")))
    op.add_column("merchants", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("merchants", sa.Column(
        "updated_at", _TZ, nullable=False, server_default=sa.text("now()")))

    # merchant_profiles: eight typed scores + classification
    op.add_column("merchant_profiles", sa.Column("tier", sa.Text(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("price_level", sa.Text(), nullable=True))
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
        "overall_score_internal",
    ):
        op.add_column("merchant_profiles", sa.Column(col, sa.Numeric(4, 3), nullable=True))
    op.add_column("merchant_profiles", sa.Column("scoring_version", sa.Text(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("scored_at", _TZ, nullable=True))

    # merchant_ratings: external platform rating facts
    op.create_table(
        "merchant_ratings",
        sa.Column("merchant_id", sa.String(), nullable=False),
        sa.Column("shopeefood_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("shopeefood_review_count", sa.Integer(), nullable=True),
        sa.Column("foody_rating", sa.Numeric(4, 2), nullable=True),
        sa.Column("foody_review_count", sa.Integer(), nullable=True),
        sa.Column("updated_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("merchant_id"),
    )

    # operational_metrics: delivery + operation KPIs (avg_prep_time_min/peak_hours exist)
    op.add_column("operational_metrics", sa.Column("cancel_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("operational_metrics", sa.Column("acceptance_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("operational_metrics", sa.Column("estimated_daily_orders", sa.Integer(), nullable=True))
    op.add_column("operational_metrics", sa.Column("avg_delivery_time_min", sa.Numeric(6, 2), nullable=True))
    op.add_column("operational_metrics", sa.Column("on_time_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("operational_metrics", sa.Column("driver_rating", sa.Numeric(3, 2), nullable=True))
    op.add_column("operational_metrics", sa.Column("packaging_ok_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("operational_metrics", sa.Column("source_kind", sa.Text(), nullable=True))
    op.add_column("operational_metrics", sa.Column(
        "updated_at", _TZ, nullable=False, server_default=sa.text("now()")))

    # ------------------------------------------------------------------
    # 2. Backfill from legacy dimensions_json (idempotent)
    # ------------------------------------------------------------------
    # merchants: business hours from open_hours JSON
    op.execute("""
        UPDATE merchants m SET
            opens_at  = NULLIF(m.open_hours->>'open', '')::time,
            closes_at = NULLIF(m.open_hours->>'close', '')::time
        WHERE m.open_hours IS NOT NULL
    """)

    # merchants: customer_segments from profile attributes
    op.execute("""
        UPDATE merchants m SET customer_segments = COALESCE((
            SELECT array_agg(x)
            FROM jsonb_array_elements_text(
                p.dimensions_json->'attributes'->'customer_segments') x
        ), '{}')
        FROM merchant_profiles p
        WHERE p.merchant_id = m.merchant_id
          AND p.dimensions_json->'attributes' ? 'customer_segments'
    """)

    # merchants: taste/diet/ingredient tags aggregated from menu_items (canonical owner = merchants)
    for col, src in (
        ("taste_tags", "taste_tags"),
        ("diet_tags", "diet_tags"),
        ("ingredient_tags", "ingredient_tags"),
    ):
        op.execute(f"""
            UPDATE merchants m SET {col} = COALESCE(s.arr, '{{}}')
            FROM (
                SELECT mi.merchant_id, array_agg(DISTINCT x) AS arr
                FROM menu_items mi,
                     LATERAL jsonb_array_elements_text(mi.{src}) x
                GROUP BY mi.merchant_id
            ) s
            WHERE s.merchant_id = m.merchant_id
        """)

    # merchant_profiles: tier, categorical price_level, eight scores, overall
    # NOTE: dimension key `price_level` in JSON is the peer price COMPETITIVENESS
    # score; the top-level `price_level` is the categorical label.
    op.execute("""
        UPDATE merchant_profiles p SET
            tier        = p.dimensions_json->>'tier',
            price_level = p.dimensions_json->>'price_level',
            food_quality_score          = (p.dimensions_json->'dimensions'->'food_quality'->>'score')::numeric,
            image_quality_score         = (p.dimensions_json->'dimensions'->'image_quality'->>'score')::numeric,
            delivery_quality_score      = (p.dimensions_json->'dimensions'->'delivery_quality'->>'score')::numeric,
            packaging_score             = (p.dimensions_json->'dimensions'->'packaging'->>'score')::numeric,
            service_score               = (p.dimensions_json->'dimensions'->'service'->>'score')::numeric,
            waiting_time_score          = (p.dimensions_json->'dimensions'->'waiting_time'->>'score')::numeric,
            menu_diversity_score        = (p.dimensions_json->'dimensions'->'menu_diversity'->>'score')::numeric,
            price_competitiveness_score = (p.dimensions_json->'dimensions'->'price_level'->>'score')::numeric,
            overall_score_internal      = (p.dimensions_json->>'overall_score')::numeric,
            scoring_version = COALESCE(NULLIF(p.schema_version, ''), 'legacy'),
            scored_at       = COALESCE(p.updated_at, now())
    """)

    # merchant_ratings: external platform facts
    op.execute("""
        INSERT INTO merchant_ratings (
            merchant_id, shopeefood_rating, shopeefood_review_count,
            foody_rating, foody_review_count, updated_at)
        SELECT merchant_id,
            (dimensions_json->'ratings'->>'shopeefood_avg')::numeric,
            (dimensions_json->'ratings'->>'shopeefood_total_review')::int,
            (dimensions_json->'ratings'->>'foody_rating')::numeric,
            (dimensions_json->'ratings'->>'foody_review_count')::int,
            now()
        FROM merchant_profiles
        ON CONFLICT (merchant_id) DO UPDATE SET
            shopeefood_rating       = EXCLUDED.shopeefood_rating,
            shopeefood_review_count = EXCLUDED.shopeefood_review_count,
            foody_rating            = EXCLUDED.foody_rating,
            foody_review_count      = EXCLUDED.foody_review_count,
            updated_at              = EXCLUDED.updated_at
    """)

    # operational_metrics: operation + delivery KPIs
    op.execute("""
        UPDATE operational_metrics om SET
            cancel_rate            = (p.dimensions_json->'attributes'->'operation_kpis'->>'cancel_rate')::numeric,
            acceptance_rate        = (p.dimensions_json->'attributes'->'operation_kpis'->>'acceptance_rate')::numeric,
            estimated_daily_orders = (p.dimensions_json->'attributes'->'operation_kpis'->>'estimated_daily_orders')::int,
            avg_delivery_time_min  = (p.dimensions_json->'attributes'->'delivery_stats'->>'avg_delivery_minutes')::numeric,
            on_time_rate           = (p.dimensions_json->'attributes'->'delivery_stats'->>'on_time_rate')::numeric,
            driver_rating          = (p.dimensions_json->'attributes'->'delivery_stats'->>'driver_rating')::numeric,
            packaging_ok_rate      = (p.dimensions_json->'attributes'->'delivery_stats'->>'packaging_ok_rate')::numeric,
            source_kind            = 'synthetic',
            updated_at             = now()
        FROM merchant_profiles p
        WHERE p.merchant_id = om.merchant_id
    """)

    # ------------------------------------------------------------------
    # 3. CHECK constraints — validate the backfill (null passes)
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_merchant_profiles_tier", "merchant_profiles",
        "tier IS NULL OR tier IN ('hero', 'background')")
    op.create_check_constraint(
        "ck_merchant_profiles_price_level", "merchant_profiles",
        "price_level IS NULL OR price_level IN ('rẻ', 'trung bình', 'cao cấp')")
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
        "overall_score_internal",
    ):
        op.create_check_constraint(
            f"ck_merchant_profiles_{col}_range", "merchant_profiles",
            f"{col} IS NULL OR ({col} >= 0 AND {col} <= 1)")

    op.create_check_constraint(
        "ck_merchant_ratings_shopeefood", "merchant_ratings",
        "shopeefood_rating IS NULL OR (shopeefood_rating >= 0 AND shopeefood_rating <= 5)")
    op.create_check_constraint(
        "ck_merchant_ratings_foody", "merchant_ratings",
        "foody_rating IS NULL OR (foody_rating >= 0 AND foody_rating <= 10)")
    op.create_check_constraint(
        "ck_merchant_ratings_counts", "merchant_ratings",
        "(shopeefood_review_count IS NULL OR shopeefood_review_count >= 0) AND "
        "(foody_review_count IS NULL OR foody_review_count >= 0)")

    for col in ("cancel_rate", "acceptance_rate", "on_time_rate", "packaging_ok_rate"):
        op.create_check_constraint(
            f"ck_operational_metrics_{col}", "operational_metrics",
            f"{col} IS NULL OR ({col} >= 0 AND {col} <= 1)")
    op.create_check_constraint(
        "ck_operational_metrics_driver_rating", "operational_metrics",
        "driver_rating IS NULL OR (driver_rating >= 0 AND driver_rating <= 5)")
    op.create_check_constraint(
        "ck_operational_metrics_source_kind", "operational_metrics",
        "source_kind IS NULL OR source_kind IN "
        "('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')")

    # ------------------------------------------------------------------
    # 4. Core indexes
    # ------------------------------------------------------------------
    op.create_index("ix_merchants_cityslug_cuisine", "merchants", ["city_slug", "cuisine"])


def downgrade() -> None:
    op.drop_index("ix_merchants_cityslug_cuisine", table_name="merchants")

    for name in (
        "ck_operational_metrics_source_kind",
        "ck_operational_metrics_driver_rating",
        "ck_operational_metrics_cancel_rate",
        "ck_operational_metrics_acceptance_rate",
        "ck_operational_metrics_on_time_rate",
        "ck_operational_metrics_packaging_ok_rate",
    ):
        op.drop_constraint(name, "operational_metrics", type_="check")
    for name in (
        "ck_merchant_ratings_shopeefood",
        "ck_merchant_ratings_foody",
        "ck_merchant_ratings_counts",
    ):
        op.drop_constraint(name, "merchant_ratings", type_="check")
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
        "overall_score_internal",
    ):
        op.drop_constraint(f"ck_merchant_profiles_{col}_range", "merchant_profiles", type_="check")
    op.drop_constraint("ck_merchant_profiles_price_level", "merchant_profiles", type_="check")
    op.drop_constraint("ck_merchant_profiles_tier", "merchant_profiles", type_="check")

    for col in (
        "updated_at", "source_kind", "packaging_ok_rate", "driver_rating",
        "on_time_rate", "avg_delivery_time_min", "estimated_daily_orders",
        "acceptance_rate", "cancel_rate",
    ):
        op.drop_column("operational_metrics", col)

    op.drop_table("merchant_ratings")

    for col in (
        "scored_at", "scoring_version", "overall_score_internal",
        "price_competitiveness_score", "menu_diversity_score", "waiting_time_score",
        "service_score", "packaging_score", "delivery_quality_score",
        "image_quality_score", "food_quality_score", "price_level", "tier",
    ):
        op.drop_column("merchant_profiles", col)

    for col in (
        "updated_at", "is_active", "customer_segments", "ingredient_tags",
        "diet_tags", "taste_tags", "timezone", "closes_at", "opens_at", "category",
    ):
        op.drop_column("merchants", col)
