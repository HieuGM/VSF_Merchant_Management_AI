"""merchant_schema_complete — Stage D/E/F: full relational compliance

Completes the merchant relational schema per
`docs/2026-07-23-merchant-relational-schema-design.md`.

Changes on top of `b1c2d3e4f5a6` (expand + backfill):

1. Create 4 new tables: merchant_dimension_calculations,
   merchant_dimension_evidence, merchant_complaints, market_trending_dishes.
2. Alter merchants: is_demo_target INT→BOOL, created_at→TIMESTAMPTZ,
   drop open_hours, add coordinate CHECKs.
3. Alter merchant_profiles: enforce NOT NULL on scores/tier/price_level,
   replace overall_score_internal with GENERATED column, change
   updated_at→TIMESTAMPTZ, drop legacy JSON columns.
4. Alter operational_metrics: avg_prep_time_min FLOAT→NUMERIC(6,2),
   peak_hours JSONB→TEXT[], enforce NOT NULL on source_kind, add ≥0 CHECKs.
5. Alter reviews: rating FLOAT→NUMERIC(4,2), add source_kind, add 0..10
   CHECK, drop comments_json.
6. Alter delivery_feedbacks: add on_time, issue, source_kind.
7. Alter menu_items: add discount_price/total_like/has_photo/is_available,
   drop diet_tags/taste_tags/ingredient_tags.
8. Create remaining indexes from §9.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEXT_ARRAY = postgresql.ARRAY(sa.Text())
_TZ = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # ==================================================================
    # 1. CREATE NEW TABLES
    # ==================================================================

    # 1a. merchant_dimension_calculations (§6.5)
    op.create_table(
        "merchant_dimension_calculations",
        sa.Column("merchant_id", sa.String(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("scoring_version", sa.Text(), nullable=False),
        sa.Column("calculated_at", _TZ, nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("merchant_id", "dimension"),
        sa.CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', 'price_competitiveness')",
            name="ck_dim_calc_dimension",
        ),
        sa.CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_dim_calc_source_kind",
        ),
    )

    # 1b. merchant_dimension_evidence (§6.6)
    op.create_table(
        "merchant_dimension_evidence",
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("merchant_id", sa.String(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("value_numeric", sa.Numeric(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column("reference_ids", _TEXT_ARRAY, nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("observed_at", _TZ, nullable=True),
        sa.Column("created_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', 'price_competitiveness')",
            name="ck_dim_evidence_dimension",
        ),
        sa.CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_dim_evidence_source_kind",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_numeric, value_text, value_boolean) = 1",
            name="ck_dim_evidence_single_value",
        ),
    )

    # 1c. merchant_complaints (§6.7)
    op.create_table(
        "merchant_complaints",
        sa.Column("complaint_id", sa.String(), nullable=False),
        sa.Column("merchant_id", sa.String(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("review_id", sa.String(), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("created_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.review_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("complaint_id"),
        sa.CheckConstraint(
            "category IN ('giao_hàng_trễ', 'món_nguội', 'sai_hoặc_thiếu_món', "
            "'đóng_gói_kém', 'thái_độ_phục_vụ', 'giá_cao', 'vệ_sinh', 'chất_lượng_món')",
            name="ck_complaints_category",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_complaints_severity",
        ),
        sa.CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_complaints_source_kind",
        ),
    )

    # 1d. market_trending_dishes (§6.12)
    op.create_table(
        "market_trending_dishes",
        sa.Column("city_slug", sa.Text(), nullable=False),
        sa.Column("cuisine", sa.Text(), nullable=False),
        sa.Column("dish_name", sa.Text(), nullable=False),
        sa.Column("trend_score", sa.Numeric(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("updated_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("city_slug", "cuisine", "dish_name"),
        sa.CheckConstraint("rank > 0", name="ck_trending_rank_positive"),
    )

    # ==================================================================
    # 1e. BACKFILL new tables from legacy dimensions_json (before drop)
    # ==================================================================

    # Backfill merchant_dimension_calculations — 8 rows per merchant
    # JSON dimension key 'price_level' maps to relational dimension 'price_competitiveness'
    op.execute("""
        INSERT INTO merchant_dimension_calculations
            (merchant_id, dimension, basis, source_kind, scoring_version, calculated_at)
        SELECT
            p.merchant_id,
            CASE WHEN dim_key = 'price_level' THEN 'price_competitiveness' ELSE dim_key END,
            COALESCE(dim_val->>'basis', 'unknown'),
            COALESCE(p.source_kind, 'synthetic'),
            COALESCE(p.schema_version, 'legacy'),
            COALESCE(p.updated_at, now())
        FROM merchant_profiles p,
             LATERAL jsonb_each(p.dimensions_json->'dimensions') AS d(dim_key, dim_val)
        WHERE p.dimensions_json->'dimensions' IS NOT NULL
        ON CONFLICT (merchant_id, dimension) DO NOTHING
    """)

    # Backfill merchant_dimension_evidence — typed scalar facts from each dimension's evidence array
    # Evidence values can be numeric, text, or boolean. We route based on jsonb typeof.
    op.execute("""
        INSERT INTO merchant_dimension_evidence
            (evidence_id, merchant_id, dimension, evidence_type,
             value_numeric, value_text, value_boolean,
             source_kind, created_at)
        SELECT
            'ev:' || p.merchant_id || ':' ||
                CASE WHEN dim_key = 'price_level' THEN 'price_competitiveness' ELSE dim_key END
                || ':' || (ev->>'type'),
            p.merchant_id,
            CASE WHEN dim_key = 'price_level' THEN 'price_competitiveness' ELSE dim_key END,
            ev->>'type',
            CASE WHEN jsonb_typeof(ev->'value') IN ('number')
                 THEN (ev->>'value')::numeric ELSE NULL END,
            CASE WHEN jsonb_typeof(ev->'value') = 'string'
                 THEN ev->>'value' ELSE NULL END,
            CASE WHEN jsonb_typeof(ev->'value') = 'boolean'
                 THEN (ev->>'value')::boolean ELSE NULL END,
            COALESCE(p.source_kind, 'synthetic'),
            COALESCE(p.updated_at, now())
        FROM merchant_profiles p,
             LATERAL jsonb_each(p.dimensions_json->'dimensions') AS d(dim_key, dim_val),
             LATERAL jsonb_array_elements(dim_val->'evidence') AS ev
        WHERE p.dimensions_json->'dimensions' IS NOT NULL
          AND dim_val->'evidence' IS NOT NULL
          AND ev ? 'value'
          AND jsonb_typeof(ev->'value') IN ('number', 'string', 'boolean')
        ON CONFLICT (evidence_id) DO NOTHING
    """)

    # Backfill market_trending_dishes — current market aggregate per city/cuisine.
    # Source: dimensions_json.attributes.trending_dishes[].{dish,total_likes}.
    # Collapse duplicates (same dish sold across merchants) to the max likes, then
    # rank per (city_slug, cuisine). MUST run before dimensions_json is dropped.
    op.execute("""
        INSERT INTO market_trending_dishes
            (city_slug, cuisine, dish_name, trend_score, rank, updated_at)
        SELECT city_slug, cuisine, dish_name, trend_score,
               ROW_NUMBER() OVER (
                   PARTITION BY city_slug, cuisine
                   ORDER BY trend_score DESC, dish_name)::int,
               now()
        FROM (
            SELECT m.city_slug, m.cuisine,
                   td->>'dish' AS dish_name,
                   MAX((td->>'total_likes')::numeric) AS trend_score
            FROM merchant_profiles p
            JOIN merchants m ON m.merchant_id = p.merchant_id,
                 LATERAL jsonb_array_elements(
                     p.dimensions_json->'attributes'->'trending_dishes') AS td
            WHERE p.dimensions_json->'attributes'->'trending_dishes' IS NOT NULL
              AND td ? 'dish' AND td ? 'total_likes'
              AND NULLIF(td->>'dish', '') IS NOT NULL
            GROUP BY m.city_slug, m.cuisine, td->>'dish'
        ) agg
        ON CONFLICT (city_slug, cuisine, dish_name) DO NOTHING
    """)

    # Backfill merchant_complaints:
    # The legacy importer (scripts/db/build_import_rows.py) stored complaints
    # only at the profiles.jsonl level — they were NEVER inserted into
    # dimensions_json. Therefore no SQL backfill is possible from existing DB
    # data. The importer must be updated to populate merchant_complaints from
    # the 'complaints' array in profiles.jsonl.


    # ==================================================================
    # 2. ALTER merchants (§6.1)
    # ==================================================================

    # 2a. Convert is_demo_target INT → BOOL
    # Add temp column, copy data, drop old, rename
    op.add_column("merchants", sa.Column("is_demo_target_bool", sa.Boolean(), nullable=True))
    op.execute("UPDATE merchants SET is_demo_target_bool = (COALESCE(is_demo_target, 0) != 0)")
    op.drop_column("merchants", "is_demo_target")
    op.alter_column("merchants", "is_demo_target_bool", new_column_name="is_demo_target",
                     nullable=False, server_default=sa.text("false"))

    # 2b. Convert created_at TIMESTAMP → TIMESTAMPTZ NOT NULL
    op.alter_column("merchants", "created_at",
                     type_=_TZ,
                     existing_type=sa.TIMESTAMP(),
                     nullable=False,
                     server_default=sa.text("now()"),
                     postgresql_using="created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'")

    # 2c. Drop open_hours legacy column
    op.drop_column("merchants", "open_hours")

    # 2d. Coordinate CHECK constraints
    op.create_check_constraint(
        "ck_merchants_coord_pair", "merchants",
        "(lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)")
    op.create_check_constraint(
        "ck_merchants_lat_range", "merchants",
        "lat IS NULL OR (lat >= -90 AND lat <= 90)")
    op.create_check_constraint(
        "ck_merchants_lng_range", "merchants",
        "lng IS NULL OR (lng >= -180 AND lng <= 180)")

    # ==================================================================
    # 3. ALTER merchant_profiles (§6.3) — enforce NOT NULL, generated col, drop legacy
    # ==================================================================

    # 3a. Drop the old CHECK constraints from migration b1c2d3e4f5a6 that allow NULL
    #     (we will re-add them as table-level via the model, but since we make cols NOT NULL
    #      the IS NULL OR pattern is no longer needed. The model __table_args__ CHECKs
    #      use the stricter form.)
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
        "overall_score_internal",
    ):
        op.drop_constraint(f"ck_merchant_profiles_{col}_range", "merchant_profiles", type_="check")
    op.drop_constraint("ck_merchant_profiles_tier", "merchant_profiles", type_="check")
    op.drop_constraint("ck_merchant_profiles_price_level", "merchant_profiles", type_="check")

    # 3b. Ensure all required columns have values before NOT NULL
    op.execute("""
        UPDATE merchant_profiles SET
            tier = COALESCE(tier, 'background'),
            price_level = COALESCE(price_level, 'trung bình'),
            food_quality_score = COALESCE(food_quality_score, 0.5),
            image_quality_score = COALESCE(image_quality_score, 0.5),
            delivery_quality_score = COALESCE(delivery_quality_score, 0.5),
            packaging_score = COALESCE(packaging_score, 0.5),
            service_score = COALESCE(service_score, 0.5),
            waiting_time_score = COALESCE(waiting_time_score, 0.5),
            menu_diversity_score = COALESCE(menu_diversity_score, 0.5),
            price_competitiveness_score = COALESCE(price_competitiveness_score, 0.5),
            scoring_version = COALESCE(scoring_version, 'legacy'),
            scored_at = COALESCE(scored_at, now())
        WHERE tier IS NULL
           OR price_level IS NULL
           OR food_quality_score IS NULL
           OR scoring_version IS NULL
           OR scored_at IS NULL
    """)

    # 3c. Make columns NOT NULL
    for col in ("tier", "price_level",
                "food_quality_score", "image_quality_score", "delivery_quality_score",
                "packaging_score", "service_score", "waiting_time_score",
                "menu_diversity_score", "price_competitiveness_score",
                "scoring_version", "scored_at"):
        op.alter_column("merchant_profiles", col, nullable=False)

    # 3d. Drop old overall_score_internal, replace with GENERATED column
    op.drop_column("merchant_profiles", "overall_score_internal")
    op.execute("""
        ALTER TABLE merchant_profiles ADD COLUMN overall_score_internal NUMERIC(4,3)
        GENERATED ALWAYS AS (
            ROUND((
                food_quality_score + image_quality_score + delivery_quality_score +
                packaging_score + service_score + waiting_time_score +
                menu_diversity_score + price_competitiveness_score
            ) / 8, 3)
        ) STORED
    """)

    # 3e. Re-add score range CHECKs (now without IS NULL OR since cols are NOT NULL)
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
    ):
        op.create_check_constraint(
            f"ck_merchant_profiles_{col}_range", "merchant_profiles",
            f"{col} >= 0 AND {col} <= 1")

    # 3f. Convert updated_at to TIMESTAMPTZ
    op.alter_column("merchant_profiles", "updated_at",
                     type_=_TZ,
                     existing_type=sa.TIMESTAMP(),
                     nullable=False,
                     server_default=sa.text("now()"),
                     postgresql_using="updated_at AT TIME ZONE 'Asia/Ho_Chi_Minh'")

    # 3g. Drop legacy JSON columns
    op.drop_column("merchant_profiles", "dimensions_json")
    op.drop_column("merchant_profiles", "profile_json")
    op.drop_column("merchant_profiles", "schema_version")
    op.drop_column("merchant_profiles", "source_kind")

    # ==================================================================
    # 4. ALTER operational_metrics (§6.4)
    # ==================================================================

    # 4a. Convert avg_prep_time_min FLOAT → NUMERIC(6,2)
    op.alter_column("operational_metrics", "avg_prep_time_min",
                     type_=sa.Numeric(6, 2),
                     existing_type=sa.Float(),
                     postgresql_using="avg_prep_time_min::numeric(6,2)")

    # 4b. Convert peak_hours JSONB → TEXT[]
    op.add_column("operational_metrics", sa.Column("peak_hours_arr", _TEXT_ARRAY,
                                                    nullable=False, server_default=sa.text("'{}'::text[]")))
    op.execute("""
        UPDATE operational_metrics SET peak_hours_arr = COALESCE((
            SELECT array_agg(x)
            FROM jsonb_array_elements_text(peak_hours) x
        ), '{}'::text[])
        WHERE peak_hours IS NOT NULL
    """)
    op.drop_column("operational_metrics", "peak_hours")
    op.alter_column("operational_metrics", "peak_hours_arr", new_column_name="peak_hours")

    # 4c. Make source_kind NOT NULL (backfill nulls first)
    op.execute("UPDATE operational_metrics SET source_kind = 'synthetic' WHERE source_kind IS NULL")
    op.alter_column("operational_metrics", "source_kind", nullable=False,
                     server_default=sa.text("'synthetic'"))

    # 4d. Add ≥0 CHECK constraints
    op.create_check_constraint("ck_opmetrics_prep_time", "operational_metrics",
                               "avg_prep_time_min IS NULL OR avg_prep_time_min >= 0")
    op.create_check_constraint("ck_opmetrics_daily_orders", "operational_metrics",
                               "estimated_daily_orders IS NULL OR estimated_daily_orders >= 0")
    op.create_check_constraint("ck_opmetrics_delivery_time", "operational_metrics",
                               "avg_delivery_time_min IS NULL OR avg_delivery_time_min >= 0")

    # ==================================================================
    # 5. ALTER reviews (§6.9)
    # ==================================================================

    # 5a. Convert rating FLOAT → NUMERIC(4,2)
    op.alter_column("reviews", "rating",
                     type_=sa.Numeric(4, 2),
                     existing_type=sa.Float(),
                     postgresql_using="rating::numeric(4,2)")

    # 5b. Add source_kind
    op.add_column("reviews", sa.Column("source_kind", sa.Text(), nullable=True))
    op.execute("UPDATE reviews SET source_kind = 'real' WHERE source_kind IS NULL")
    op.alter_column("reviews", "source_kind", nullable=False, server_default=sa.text("'real'"))

    # 5c. Add CHECK constraints
    op.create_check_constraint("ck_reviews_rating_range", "reviews",
                               "rating IS NULL OR (rating >= 0 AND rating <= 10)")
    op.create_check_constraint("ck_reviews_source_kind", "reviews",
                               "source_kind IN ('real', 'synthetic')")

    # 5d. Drop comments_json
    op.drop_column("reviews", "comments_json")

    # ==================================================================
    # 6. ALTER delivery_feedbacks (§6.8)
    # ==================================================================
    op.add_column("delivery_feedbacks", sa.Column("on_time", sa.Boolean(), nullable=True))
    op.add_column("delivery_feedbacks", sa.Column("issue", sa.Text(), nullable=True))
    op.add_column("delivery_feedbacks", sa.Column("source_kind", sa.Text(), nullable=True))
    op.execute("UPDATE delivery_feedbacks SET source_kind = 'synthetic' WHERE source_kind IS NULL")
    op.alter_column("delivery_feedbacks", "source_kind", nullable=False,
                     server_default=sa.text("'synthetic'"))
    op.create_check_constraint("ck_delivery_feedbacks_source_kind", "delivery_feedbacks",
                               "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')")

    # ==================================================================
    # 7. ALTER menu_items (§6.10)
    # ==================================================================

    # 7a. Add new columns
    op.add_column("menu_items", sa.Column("discount_price", sa.Integer(), nullable=True))
    op.add_column("menu_items", sa.Column("total_like", sa.Integer(), nullable=False,
                                           server_default=sa.text("0")))
    op.add_column("menu_items", sa.Column("has_photo", sa.Boolean(), nullable=False,
                                           server_default=sa.text("false")))
    op.add_column("menu_items", sa.Column("is_available", sa.Boolean(), nullable=False,
                                           server_default=sa.text("true")))

    # 7b. Backfill has_photo from image_url presence
    op.execute("UPDATE menu_items SET has_photo = (image_url IS NOT NULL AND image_url != '')")

    # 7c. Add CHECK constraint
    op.create_check_constraint("ck_menu_items_discount_price", "menu_items",
                               "discount_price IS NULL OR discount_price >= 0")

    # 7d. Drop tag columns (canonical owner = merchants)
    op.drop_column("menu_items", "diet_tags")
    op.drop_column("menu_items", "taste_tags")
    op.drop_column("menu_items", "ingredient_tags")

    # ==================================================================
    # 8. CREATE REMAINING INDEXES (§9)
    # ==================================================================
    op.create_index("ix_food_images_merchant_item", "food_images", ["merchant_id", "item_id"])
    op.create_index("ix_dim_calc_merchant_dimension", "merchant_dimension_calculations",
                     ["merchant_id", "dimension"])
    op.create_index("ix_dim_evidence_merchant_dimension", "merchant_dimension_evidence",
                     ["merchant_id", "dimension"])
    op.create_index("ix_complaints_merchant_category_date", "merchant_complaints",
                     ["merchant_id", "category", "occurred_on"])
    op.create_index("ix_trending_city_cuisine_rank", "market_trending_dishes",
                     ["city_slug", "cuisine", "rank"])


def downgrade() -> None:
    # Drop new indexes
    op.drop_index("ix_trending_city_cuisine_rank", table_name="market_trending_dishes")
    op.drop_index("ix_complaints_merchant_category_date", table_name="merchant_complaints")
    op.drop_index("ix_dim_evidence_merchant_dimension", table_name="merchant_dimension_evidence")
    op.drop_index("ix_dim_calc_merchant_dimension", table_name="merchant_dimension_calculations")
    op.drop_index("ix_food_images_merchant_item", table_name="food_images")

    # --- menu_items: restore tag columns, drop new columns ---
    op.add_column("menu_items", sa.Column("ingredient_tags", postgresql.JSONB(), nullable=True))
    op.add_column("menu_items", sa.Column("taste_tags", postgresql.JSONB(), nullable=True))
    op.add_column("menu_items", sa.Column("diet_tags", postgresql.JSONB(), nullable=True))
    op.drop_constraint("ck_menu_items_discount_price", "menu_items", type_="check")
    op.drop_column("menu_items", "is_available")
    op.drop_column("menu_items", "has_photo")
    op.drop_column("menu_items", "total_like")
    op.drop_column("menu_items", "discount_price")

    # --- delivery_feedbacks: drop new columns ---
    op.drop_constraint("ck_delivery_feedbacks_source_kind", "delivery_feedbacks", type_="check")
    op.drop_column("delivery_feedbacks", "source_kind")
    op.drop_column("delivery_feedbacks", "issue")
    op.drop_column("delivery_feedbacks", "on_time")

    # --- reviews: restore comments_json, drop source_kind, restore rating type ---
    op.drop_constraint("ck_reviews_source_kind", "reviews", type_="check")
    op.drop_constraint("ck_reviews_rating_range", "reviews", type_="check")
    op.drop_column("reviews", "source_kind")
    op.add_column("reviews", sa.Column("comments_json", postgresql.JSONB(), nullable=True))
    op.alter_column("reviews", "rating",
                     type_=sa.Float(),
                     existing_type=sa.Numeric(4, 2),
                     postgresql_using="rating::double precision")

    # --- operational_metrics: restore types ---
    op.drop_constraint("ck_opmetrics_delivery_time", "operational_metrics", type_="check")
    op.drop_constraint("ck_opmetrics_daily_orders", "operational_metrics", type_="check")
    op.drop_constraint("ck_opmetrics_prep_time", "operational_metrics", type_="check")
    # peak_hours TEXT[] → JSONB
    op.add_column("operational_metrics", sa.Column("peak_hours_jsonb", postgresql.JSONB(), nullable=True))
    op.execute("""
        UPDATE operational_metrics SET peak_hours_jsonb = to_jsonb(peak_hours)
        WHERE peak_hours IS NOT NULL AND cardinality(peak_hours) > 0
    """)
    op.drop_column("operational_metrics", "peak_hours")
    op.alter_column("operational_metrics", "peak_hours_jsonb", new_column_name="peak_hours")
    op.alter_column("operational_metrics", "source_kind", nullable=True)
    op.alter_column("operational_metrics", "avg_prep_time_min",
                     type_=sa.Float(),
                     existing_type=sa.Numeric(6, 2),
                     postgresql_using="avg_prep_time_min::double precision")

    # --- merchant_profiles: restore legacy columns ---
    op.add_column("merchant_profiles", sa.Column("source_kind", sa.String(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("schema_version", sa.String(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("profile_json", postgresql.JSONB(), nullable=True))
    op.add_column("merchant_profiles", sa.Column("dimensions_json", postgresql.JSONB(), nullable=True))
    op.alter_column("merchant_profiles", "updated_at",
                     type_=sa.TIMESTAMP(),
                     existing_type=_TZ,
                     nullable=True,
                     server_default=sa.text("CURRENT_TIMESTAMP"),
                     postgresql_using="updated_at")
    # Drop generated column, replace with regular
    op.execute("ALTER TABLE merchant_profiles DROP COLUMN overall_score_internal")
    op.add_column("merchant_profiles", sa.Column("overall_score_internal", sa.Numeric(4, 3), nullable=True))
    for col in (
        "food_quality_score", "image_quality_score", "delivery_quality_score",
        "packaging_score", "service_score", "waiting_time_score",
        "menu_diversity_score", "price_competitiveness_score",
    ):
        op.drop_constraint(f"ck_merchant_profiles_{col}_range", "merchant_profiles", type_="check")
    for col in ("scored_at", "scoring_version",
                "price_competitiveness_score", "menu_diversity_score", "waiting_time_score",
                "service_score", "packaging_score", "delivery_quality_score",
                "image_quality_score", "food_quality_score", "price_level", "tier"):
        op.alter_column("merchant_profiles", col, nullable=True)
    # Restore old-style CHECK constraints (nullable-tolerant)
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

    # --- merchants: restore open_hours, is_demo_target as INT ---
    op.drop_constraint("ck_merchants_lng_range", "merchants", type_="check")
    op.drop_constraint("ck_merchants_lat_range", "merchants", type_="check")
    op.drop_constraint("ck_merchants_coord_pair", "merchants", type_="check")
    op.add_column("merchants", sa.Column("open_hours", postgresql.JSONB(), nullable=True))
    op.alter_column("merchants", "created_at",
                     type_=sa.TIMESTAMP(),
                     existing_type=_TZ,
                     nullable=True,
                     server_default=sa.text("CURRENT_TIMESTAMP"),
                     postgresql_using="created_at")
    # Convert is_demo_target BOOL → INT
    op.add_column("merchants", sa.Column("is_demo_target_int", sa.Integer(), nullable=True))
    op.execute("UPDATE merchants SET is_demo_target_int = CASE WHEN is_demo_target THEN 1 ELSE 0 END")
    op.drop_column("merchants", "is_demo_target")
    op.alter_column("merchants", "is_demo_target_int", new_column_name="is_demo_target")

    # Drop new tables
    op.drop_table("market_trending_dishes")
    op.drop_table("merchant_complaints")
    op.drop_table("merchant_dimension_evidence")
    op.drop_table("merchant_dimension_calculations")
