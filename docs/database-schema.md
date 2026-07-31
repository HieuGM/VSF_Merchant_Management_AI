# Merchant platform database schema

Current production schema for the merchant domain. PostgreSQL remains the
database; no PostGIS extension is required. The source of truth is
`backend/database/models.py` plus the Alembic revisions:

- `b7c8d9e0f1a2`: additive relational expansion and backfill-ready columns.
- `c8d9e0f1a2b3`: validated cutover and removal of legacy profile JSON.

The migration was applied to `merchant_platform` on 2026-07-23 after a
custom-format backup at `/tmp/merchant_platform-before-relational-20260723.dump`.

## Design rules

- Merchant profile facts are typed columns or normalized child rows.
- `merchant_profiles` contains no `JSON`/`JSONB` columns.
- Filterable attributes are columns: cuisine, category, city, coordinates,
  open/close times, tags, active/demo flags, price level and ratings.
- Scores use one normalized scale, `0..1`; all eight score columns are
  constrained to that range.
- `overall_score_internal` is a generated database value for internal QA only;
  API and agent payloads never expose it.
- Competitors and `distance_km` are not persisted. Nearby queries calculate
  Haversine distance at query time.
- JSONB is still allowed in runtime/user tables where it represents evolving
  session state, but not in merchant profile facts.

## Merchant domain

```
merchants (1)
  ├── merchant_profiles (1)
  ├── merchant_ratings (1)
  ├── operational_metrics (1)
  ├── merchant_dimension_calculations (8)
  ├── merchant_dimension_evidence (N)
  ├── merchant_complaints (N)
  ├── reviews (N)
  ├── delivery_feedbacks (N)
  ├── menu_items (N) ─── food_images (N)
  └── market_trending_dishes (cluster-level, no merchant FK)
```

All merchant child FKs cascade on merchant deletion. `food_images.item_id`
uses `ON DELETE SET NULL`.

### `merchants`

| Column | Type | Notes |
|---|---|---|
| `merchant_id` | `text` PK | Source merchant ID |
| `name`, `cuisine`, `city`, `city_slug` | `text` NOT NULL | Filterable identity |
| `category` | `text` | Merchant category |
| `address` | `text` | |
| `lat`, `lng` | `double precision` | Pair must be both null or both present; range checks |
| `opens_at`, `closes_at` | `time` | Local business hours |
| `timezone` | `text` NOT NULL | Defaults to `Asia/Ho_Chi_Minh` |
| `taste_tags`, `diet_tags`, `ingredient_tags`, `customer_segments` | `text[]` NOT NULL | Typed multi-value filters |
| `source`, `source_url` | `text` | Provenance |
| `is_active`, `is_demo_target` | `boolean` NOT NULL | Current availability/demo cohort |
| `created_at`, `updated_at` | `timestamptz` | |

### `merchant_profiles`

One current row per merchant. `tier` is `hero` or `background`; `price_level`
is a categorical label (`rẻ`, `trung bình`, `cao cấp`).

| Column | Type | Notes |
|---|---|---|
| `merchant_id` | `text` PK/FK | |
| `tier`, `price_level` | `text` NOT NULL | |
| `food_quality_score`, `image_quality_score`, `delivery_quality_score` | `numeric(4,3)` | `0..1` |
| `packaging_score`, `service_score`, `waiting_time_score` | `numeric(4,3)` | `0..1` |
| `menu_diversity_score`, `price_competitiveness_score` | `numeric(4,3)` | `0..1` |
| `overall_score_internal` | generated `numeric(4,3)` | Mean of eight scores; internal only |
| `scoring_version`, `scored_at`, `updated_at` | `text`/`timestamptz` | Calculation provenance |

### `merchant_ratings`

One row per merchant: `shopeefood_rating` (`0..5`), `shopeefood_review_count`,
`foody_rating` (`0..10`), `foody_review_count`, and `updated_at`.

### `operational_metrics`

One row per merchant. Typed operational and delivery facts:
`avg_prep_time_min`, `cancel_rate`, `acceptance_rate`,
`estimated_daily_orders`, `peak_hours text[]`, `avg_delivery_time_min`,
`on_time_rate`, `driver_rating`, `packaging_ok_rate`, `source_kind`,
`updated_at`. Rates are constrained to `0..1`; driver rating is `0..5`.

### `merchant_dimension_calculations`

Exactly eight rows per complete merchant profile. Composite PK is
`(merchant_id, dimension)`. `dimension` is constrained to:
`food_quality`, `image_quality`, `delivery_quality`, `packaging`, `service`,
`waiting_time`, `menu_diversity`, `price_competitiveness`.

Columns: `basis`, `source_kind`, `scoring_version`, `calculated_at`.
The score itself lives in the typed `merchant_profiles` column, avoiding
duplicate score values.

### `merchant_dimension_evidence`

Evidence rows reference a dimension and hold exactly one typed scalar:
`value_numeric`, `value_text`, or `value_boolean`. Other columns are
`evidence_id`, `merchant_id`, `dimension`, `evidence_type`, `unit`,
`reference_type`, `reference_ids text[]`, `source_kind`, `observed_at`,
`created_at`.

### `merchant_complaints`

Typed complaint facts: `complaint_id`, `merchant_id`, `category`,
`severity`, `text`, `occurred_on`, optional `review_id`, `source_kind`,
`created_at`. Category/severity/source values are constrained by the migration.

### `reviews` and `delivery_feedbacks`

Reviews retain source rating (`0..10`), text, sentiment, source page,
source kind and timestamp. Delivery feedback retains `on_time`, `issue`,
driver/rating/comment, source kind and timestamp. Neither table stores JSON
profile blobs.

### `menu_items` and `food_images`

Menu items contain typed price/discount, likes, photo/availability flags,
description/category and image URL. Merchant-level tags are stored on
`merchants`; they are not repeated as JSON on every menu item.

## Runtime tables

`user_profiles`, `chat_sessions`, `chat_messages`, agent runs and token usage
remain runtime/application tables. Their JSONB context snapshots are outside
the merchant profile domain and are intentionally unchanged by this migration.

## Validation queries

```sql
-- no legacy merchant-profile JSON remains
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'merchant_profiles'
  AND column_name IN ('dimensions_json', 'profile_json');

-- every current profile has eight calculations
SELECT merchant_id
FROM merchant_profiles
WHERE (SELECT count(*) FROM merchant_dimension_calculations c
       WHERE c.merchant_id = merchant_profiles.merchant_id) <> 8;

-- dynamic nearby distance (illustrative; application uses the same expression)
SELECT merchant_id
FROM merchants
WHERE lat IS NOT NULL AND lng IS NOT NULL;
```
