# Merchant Relational Current-State Schema Design

**Date:** 2026-07-23  
**Database:** PostgreSQL database `merchant_platform` in the existing Docker setup  
**Scope:** Merchant data domain only  
**Status:** Approved design; implementation not started

## 1. Purpose

Refactor the merchant data domain so that PostgreSQL, rather than nested profile
JSON, is the runtime source of truth.

The existing `merchant_profiles.dimensions_json` and
`merchant_profiles.profile_json` contain ratings, operational metrics, scored
dimensions, descriptive attributes, evidence, and precomputed competitors in
one nested document. This has caused schema drift, incorrect field access,
oversized agent tool results, inconsistent score interpretation, and filters
that cannot rely on typed database columns.

The replacement schema is a current-state relational model:

- one current profile per merchant;
- typed columns for every value used by filtering, sorting, comparison, scoring,
  or validation;
- separate raw metrics, ratings, computed scores, evidence, and complaints;
- no persisted merchant-to-merchant distance or competitor list;
- no JSONB in the merchant profile domain;
- PostgreSQL `TEXT[]` columns for the approved multi-value filter fields;
- score constraints use the canonical `0..1` scale.

Schema correctness and data consistency are acceptance requirements. Query
performance is a later optimization and is not an acceptance gate for this
refactor.

## 2. Decisions and Non-Goals

### 2.1 Approved decisions

1. The model is **current-only**. Historical profile snapshots and metric
   time-series are out of scope.
2. The existing PostgreSQL Docker image remains unchanged. PostGIS is not
   introduced.
3. Geographic distance is calculated at query time from `lat` and `lng`.
4. `TEXT[]` is used for `taste_tags`, `diet_tags`, `ingredient_tags`,
   `customer_segments`, and `peak_hours`.
5. The refactor covers the merchant data domain only. User profiles,
   preferences, chat sessions, messages, agent runs, and agent events retain
   their current schemas.
6. `overall_score` remains an internal derived value and must never appear in a
   public API response, agent tool output, or merchant-facing answer.

### 2.2 Non-goals

- Profile or operational history.
- PostGIS or a change to the PostgreSQL Docker image.
- Refactoring session, user, preference, or observability tables.
- Persisting query-relative values such as `distance_km`.
- Preserving the existing nested profile JSON as a long-term compatibility
  format.
- Performance targets or broad index tuning before correct query contracts
  exist.

## 3. Source-of-Truth Rules

After cutover:

- PostgreSQL relational tables are the runtime source of truth.
- `data/profiles.jsonl` remains an import artifact, not an application read
  model.
- The scoring pipeline may still build a structured Python object, but the
  importer must decompose it into typed relational rows and columns.
- The application reconstructs API and agent DTOs at its boundary. It does not
  store those DTOs as JSON.
- A metric is stored once in its owning table. Computed dimensions reference
  that metric through evidence; they do not duplicate it in an attributes
  object.

## 4. Target Entity Model

```text
merchants
├── merchant_ratings                 1:0..1
├── merchant_profiles                1:1
├── operational_metrics              1:1
├── merchant_dimension_calculations  1:8
├── merchant_dimension_evidence      1:N
├── merchant_complaints              1:N
├── reviews                          1:N
├── delivery_feedbacks               1:N
├── menu_items                       1:N
│   └── food_images                  1:N
└── no persisted competitor relation

market_trending_dishes
└── one current ranked set per city/cuisine market
```

The `merchant_profiles` table is deliberately wide for the eight fixed scores.
This makes every dimension a typed filterable field while preserving separate
tables for the facts and evidence from which the scores were calculated.

## 5. Canonical Values and Shared Constraints

Application models and database constraints must share these definitions:

```text
dimensions:
  food_quality
  image_quality
  delivery_quality
  packaging
  service
  waiting_time
  menu_diversity
  price_competitiveness

tier:
  hero
  background

price_level:
  rẻ
  trung bình
  cao cấp

source_kind:
  real
  synthetic
  heuristic
  mixed
  development_fixture

complaint category:
  giao_hàng_trễ
  món_nguội
  sai_hoặc_thiếu_món
  đóng_gói_kém
  thái_độ_phục_vụ
  giá_cao
  vệ_sinh
  chất_lượng_món

complaint severity:
  low
  medium
  high
```

PostgreSQL `CHECK` constraints are preferred over database enum types so the
allowed values can be migrated without replacing an enum type.

All new timestamps use `TIMESTAMPTZ`. Existing naive timestamps are migrated by
interpreting them according to the application’s documented timezone behavior.

## 6. Table Designs

### 6.1 `merchants`

This table owns merchant identity, physical location, operating state, and
merchant-level filter tags.

| Column | Type | Rules |
|---|---|---|
| `merchant_id` | `VARCHAR` | Primary key |
| `name` | `TEXT` | Not null |
| `cuisine` | `TEXT` | Not null |
| `category` | `TEXT` | Nullable |
| `address` | `TEXT` | Nullable |
| `city` | `TEXT` | Not null |
| `city_slug` | `TEXT` | Not null |
| `lat` | `DOUBLE PRECISION` | Nullable; `-90 <= lat <= 90` |
| `lng` | `DOUBLE PRECISION` | Nullable; `-180 <= lng <= 180` |
| `opens_at` | `TIME` | Nullable |
| `closes_at` | `TIME` | Nullable |
| `timezone` | `TEXT` | Not null; default `Asia/Ho_Chi_Minh` |
| `taste_tags` | `TEXT[]` | Not null; default empty array |
| `diet_tags` | `TEXT[]` | Not null; default empty array |
| `ingredient_tags` | `TEXT[]` | Not null; default empty array |
| `customer_segments` | `TEXT[]` | Not null; default empty array |
| `source` | `TEXT` | Nullable |
| `source_url` | `TEXT` | Nullable |
| `is_active` | `BOOLEAN` | Not null; default true |
| `is_demo_target` | `BOOLEAN` | Not null; default false |
| `created_at` | `TIMESTAMPTZ` | Not null |
| `updated_at` | `TIMESTAMPTZ` | Not null |

Coordinate integrity requires both coordinates to be absent or both present:

```text
(lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)
```

`opens_at` and `closes_at` replace the current `{open, close}` JSON shape. The
source currently uses one schedule for the merchant rather than weekday-specific
schedules. A weekday schedule table is intentionally deferred until such source
data exists.

The current integer `is_demo_target` is migrated to a boolean.

### 6.2 `merchant_ratings`

This table owns current rating summaries from external platforms. These values
are facts, not computed profile dimensions.

| Column | Type | Rules |
|---|---|---|
| `merchant_id` | `VARCHAR` | PK and FK to `merchants` |
| `shopeefood_rating` | `NUMERIC(3,2)` | Nullable; `0..5` |
| `shopeefood_review_count` | `INTEGER` | Nullable; `>= 0` |
| `foody_rating` | `NUMERIC(4,2)` | Nullable; `0..10` |
| `foody_review_count` | `INTEGER` | Nullable; `>= 0` |
| `updated_at` | `TIMESTAMPTZ` | Not null |

Merchant-level rating filters must use this table. They must not filter against
an arbitrary individual row in `reviews`.

### 6.3 `merchant_profiles`

This table owns the current eight computed dimensions and profile
classification. It keeps the current primary-key relationship: one profile per
merchant.

| Column | Type | Rules |
|---|---|---|
| `merchant_id` | `VARCHAR` | PK and FK to `merchants` |
| `tier` | `TEXT` | Not null; approved tier check |
| `price_level` | `TEXT` | Not null; approved price-level check |
| `food_quality_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `image_quality_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `delivery_quality_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `packaging_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `service_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `waiting_time_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `menu_diversity_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `price_competitiveness_score` | `NUMERIC(4,3)` | Not null; `0..1` |
| `overall_score_internal` | `NUMERIC(4,3)` | Generated from the eight scores |
| `scoring_version` | `TEXT` | Not null |
| `scored_at` | `TIMESTAMPTZ` | Not null |
| `updated_at` | `TIMESTAMPTZ` | Not null |

The categorical `price_level` and scored price competitiveness are intentionally
named differently. The existing profile calls both concepts `price_level`,
which makes tool and filter contracts ambiguous.

`overall_score_internal` is a database-generated column. No repository method
that builds a public or tool-facing DTO may select or serialize this field.

The legacy columns below are removed only after application cutover:

```text
dimensions_json
profile_json
schema_version
source_kind
```

Profile-level `source_kind` is removed because one profile can combine real,
synthetic, and heuristic evidence. Provenance belongs to calculations and
evidence rows.

### 6.4 `operational_metrics`

This table owns current operational and delivery facts.

| Column | Type | Rules |
|---|---|---|
| `merchant_id` | `VARCHAR` | PK and FK to `merchants` |
| `avg_prep_time_min` | `NUMERIC(6,2)` | Nullable; `>= 0` |
| `cancel_rate` | `NUMERIC(5,4)` | Nullable; `0..1` |
| `acceptance_rate` | `NUMERIC(5,4)` | Nullable; `0..1` |
| `estimated_daily_orders` | `INTEGER` | Nullable; `>= 0` |
| `peak_hours` | `TEXT[]` | Not null; default empty array |
| `avg_delivery_time_min` | `NUMERIC(6,2)` | Nullable; `>= 0` |
| `on_time_rate` | `NUMERIC(5,4)` | Nullable; `0..1` |
| `driver_rating` | `NUMERIC(3,2)` | Nullable; `0..5` |
| `packaging_ok_rate` | `NUMERIC(5,4)` | Nullable; `0..1` |
| `source_kind` | `TEXT` | Not null; approved source check |
| `updated_at` | `TIMESTAMPTZ` | Not null |

The JSON paths `attributes.operation_kpis` and
`attributes.delivery_stats` cease to exist after cutover.

`waiting_time` is preparation time only. A late-delivery complaint may affect
`delivery_quality`, but it must not affect `waiting_time`.

### 6.5 `merchant_dimension_calculations`

This table records how each current dimension was calculated without moving its
filterable score out of `merchant_profiles`.

| Column | Type | Rules |
|---|---|---|
| `merchant_id` | `VARCHAR` | FK to `merchants` |
| `dimension` | `TEXT` | Approved dimension check |
| `basis` | `TEXT` | Not null |
| `source_kind` | `TEXT` | Not null; approved source check |
| `scoring_version` | `TEXT` | Not null |
| `calculated_at` | `TIMESTAMPTZ` | Not null |

Primary key:

```text
(merchant_id, dimension)
```

Every complete merchant profile has exactly eight rows in this table.

### 6.6 `merchant_dimension_evidence`

Evidence is stored as typed scalar facts. It is not stored as arbitrary JSON.

| Column | Type | Rules |
|---|---|---|
| `evidence_id` | `VARCHAR` | Primary key |
| `merchant_id` | `VARCHAR` | FK to `merchants` |
| `dimension` | `TEXT` | Approved dimension check |
| `evidence_type` | `TEXT` | Not null |
| `value_numeric` | `NUMERIC` | Nullable |
| `value_text` | `TEXT` | Nullable |
| `value_boolean` | `BOOLEAN` | Nullable |
| `unit` | `TEXT` | Nullable |
| `reference_type` | `TEXT` | Nullable |
| `reference_ids` | `TEXT[]` | Not null; default empty array |
| `source_kind` | `TEXT` | Not null; approved source check |
| `observed_at` | `TIMESTAMPTZ` | Nullable |
| `created_at` | `TIMESTAMPTZ` | Not null |

Exactly one typed value must be present:

```text
num_nonnulls(value_numeric, value_text, value_boolean) = 1
```

Evidence IDs generated during import are deterministic:

```text
ev:{merchant_id}:{dimension}:{evidence_type}
```

If more than one evidence of the same type can exist for a dimension, the ID
also contains a stable source reference or ordinal.

`reference_ids` may contain review, menu-item, feedback, complaint, image, or
metric identifiers. References missing from the source must remain explicitly
empty; the importer must not invent resolvable references.

### 6.7 `merchant_complaints`

Complaints currently trapped in profile source data become first-class rows.

| Column | Type | Rules |
|---|---|---|
| `complaint_id` | `VARCHAR` | Primary key |
| `merchant_id` | `VARCHAR` | FK to `merchants` |
| `category` | `TEXT` | Not null; approved category check |
| `severity` | `TEXT` | Not null; low/medium/high |
| `text` | `TEXT` | Not null |
| `occurred_on` | `DATE` | Nullable |
| `review_id` | `VARCHAR` | Nullable FK to `reviews` |
| `source_kind` | `TEXT` | Not null |
| `created_at` | `TIMESTAMPTZ` | Not null |

The table does not persist a dimension column. Complaint category-to-dimension
mapping is a versioned scoring rule. This prevents the same complaint from
being assigned to conflicting dimensions by stored data.

### 6.8 `delivery_feedbacks`

The existing table remains, with these additions:

| Column | Type | Rules |
|---|---|---|
| `on_time` | `BOOLEAN` | Nullable |
| `issue` | `TEXT` | Nullable |
| `source_kind` | `TEXT` | Not null |

The importer must preserve `on_time` rather than only converting it to a
synthetic rating. Existing identity, merchant, driver, comment, rating, and
timestamp columns remain.

### 6.9 `reviews`

The existing relational table remains with the following contract:

- `text` is `TEXT NOT NULL`.
- `rating` is `NUMERIC(4,2)` with a `0..10` check.
- `source_kind` distinguishes `real` and `synthetic`.
- `source_page` remains source metadata.
- `comments_json` is removed.
- Columns that are always null and have no importer source are removed rather
  than retained as speculative schema. Each candidate column is dropped only
  after a null/source audit; a source-linkage field with real data is retained.

If nested review comments acquire a real source later, they get a dedicated
`review_comments` table.

### 6.10 `menu_items`

The table continues to own item-level facts. It adds source fields already
available in crawled data:

| Column | Type | Rules |
|---|---|---|
| `discount_price` | `INTEGER` | Nullable; `>= 0` |
| `total_like` | `INTEGER` | Not null; default 0 |
| `has_photo` | `BOOLEAN` | Not null; default false |
| `is_available` | `BOOLEAN` | Not null; default true |

Merchant-level `diet_tags`, `taste_tags`, and `ingredient_tags` are removed from
menu items. The current importer copies all three from the merchant catalog, so
their canonical owner is `merchants`.

### 6.11 `food_images`

The existing relational table remains. Its quality fields retain the `0..1`
checks:

```text
dish_image_quality
logo_quality
blur_score
```

Vision output is imported into this table. It must no longer exist only inside
profile evidence JSON.

### 6.12 `market_trending_dishes`

Trending dishes are a current market aggregate rather than a merchant-relative
or user-relative relation.

| Column | Type | Rules |
|---|---|---|
| `city_slug` | `TEXT` | PK component |
| `cuisine` | `TEXT` | PK component |
| `dish_name` | `TEXT` | PK component |
| `trend_score` | `NUMERIC` | Not null |
| `rank` | `INTEGER` | Not null; `> 0` |
| `updated_at` | `TIMESTAMPTZ` | Not null |

Primary key:

```text
(city_slug, cuisine, dish_name)
```

The table is rebuilt as a current snapshot. Unlike distance, this value does not
depend on a target merchant, user location, or requested radius.

## 7. Dynamic Competitor Query Contract

There is no `merchant_competitors` table and no `distance_km` column.

The repository receives:

```text
target_merchant_id
radius_km
optional cuisine rule
limit
```

The query:

1. Loads the target merchant’s coordinates and cuisine.
2. Rejects a missing or invalid coordinate pair with a typed
   `insufficient_location_data` result.
3. Calculates a latitude/longitude bounding box from the requested radius.
4. Selects other merchants in the bounding box and required cuisine segment.
5. Calculates Haversine distance in SQL.
6. Keeps rows whose calculated distance is within the requested radius.
7. Joins ratings, profile scores, and operational metrics for the selected
   candidates.
8. Orders by calculated distance and applies the requested limit.

Bounding-box deltas:

```text
lat_delta = radius_km / 111.045
lng_delta = radius_km / (111.045 * cos(radians(target_lat)))
```

The Haversine calculation is authoritative. The bounding box only reduces
candidates and must not determine whether a merchant is inside the radius.

Distance belongs only to the query result DTO. It is never written back to any
table.

## 8. Search Semantics

A non-materialized `merchant_search_current` SQL view may flatten:

```text
merchants
JOIN merchant_profiles
LEFT JOIN merchant_ratings
LEFT JOIN operational_metrics
```

The view is a read contract, not stored state.

Filter definitions:

- merchant rating filters use `merchant_ratings`;
- score filters use the eight profile score columns;
- price-segment filters use `merchant_profiles.price_level`;
- “has an item in price range” uses `EXISTS` against `menu_items`;
- cuisine, city, category, tags, segments, and coordinates use `merchants`;
- operational filters use `operational_metrics`;
- radius uses the dynamic competitor/location query.

This replaces the current behavior that joins individual menu items and reviews
and then applies `DISTINCT`, which gives ambiguous merchant-level semantics.

## 9. Minimal Index Policy

Indexes required for primary keys and uniqueness are part of the schema.
Foreign-key lookup indexes are added where needed for referential operations.

Initial domain indexes:

```text
merchants(city_slug, cuisine)
merchant_dimension_calculations(merchant_id, dimension)
merchant_dimension_evidence(merchant_id, dimension)
merchant_complaints(merchant_id, category, occurred_on)
reviews(merchant_id, created_at)
menu_items(merchant_id, price)
food_images(merchant_id, item_id)
market_trending_dishes(city_slug, cuisine, rank)
```

The initial migration does not add GIN or score-specific indexes because query
performance is not an acceptance requirement. Those indexes require a separate
query-driven change after real access patterns are known.

## 10. Import and Update Semantics

The new importer validates an input profile and decomposes it:

```text
profiles.jsonl
→ merchants
→ merchant_ratings
→ operational_metrics
→ merchant_profiles
→ merchant_dimension_calculations
→ merchant_dimension_evidence
→ merchant_complaints
→ reviews / delivery_feedbacks / menu_items / food_images
→ market_trending_dishes
```

An update for one merchant is atomic:

1. upsert merchant identity and current facts;
2. upsert rating, operational, and profile rows;
3. replace that merchant’s current calculation/evidence/complaint rows;
4. commit only after all validation succeeds.

The importer ignores the legacy `attributes.competitors` input field.

The runtime import path no longer uses `TRUNCATE ... CASCADE`. A full reset
remains a separate, explicit development operation.

## 11. Migration Plan

### Stage A — Backup and preflight

1. Create a `pg_dump` backup of `merchant_platform`.
2. Record row counts and constraint violations for all merchant-domain tables.
3. Record canonical samples, including merchant `94` and the five demo
   scenarios.
4. Confirm the Alembic head and prohibit parallel migration heads.

### Stage B — Expand schema

1. Add relational columns to `merchants`, `merchant_profiles`, and
   `operational_metrics` as nullable.
2. Create `merchant_ratings`, `merchant_dimension_calculations`,
   `merchant_dimension_evidence`, `merchant_complaints`, and
   `market_trending_dishes`.
3. Add the approved columns to delivery feedbacks, reviews, menu items, and food
   images.
4. Keep all legacy JSON columns during backfill.

### Stage C — Backfill

1. Read `dimensions_json` as the legacy source. Do not use the currently nested
   `profile_json`.
2. Validate the legacy object before mapping it.
3. Map all eight scores to the canonical `0..1` columns.
4. Map ratings and operational facts to their owner tables.
5. Map merchant tags and segments to `TEXT[]`.
6. Create exactly eight calculation rows per complete profile.
7. Generate deterministic evidence and complaint IDs.
8. Keep missing evidence references empty instead of inventing references.
9. Convert integer demo flags to booleans.
10. Do not migrate precomputed competitor IDs or distances.

### Stage D — Validate backfill

The migration cannot proceed to cutover until:

- merchant and profile counts match the expected source counts;
- all complete profiles have eight scores;
- all scores are in `0..1`;
- all rates and ratings satisfy their own scales;
- all complete profiles have eight calculation rows;
- coordinate pairs are valid;
- no orphan foreign keys exist;
- merchant `94` retains `waiting_time_score = 0.8`;
- merchant `94` retains `avg_prep_time_min = 13`;
- late-delivery complaints are not waiting-time evidence;
- profile reconstruction from relational tables matches the canonical source
  except for intentionally removed fields;
- no migrated row contains persisted competitor distance.

### Stage E — Application cutover

1. Update SQLAlchemy models and Pydantic contracts.
2. Switch repositories and domain services to relational reads.
3. Switch tools to compact typed DTOs.
4. Switch competitor lookup to query-time distance.
5. Switch the importer to relational writes.
6. Run contract, repository, service, route, and agent-tool integration tests.

A short-lived legacy read fallback is permitted during cutover, but all new
writes must target the relational schema.

### Stage F — Enforce and clean up

After cutover validation:

1. make required relational columns `NOT NULL`;
2. add final `CHECK`, FK, and unique constraints;
3. remove the legacy read fallback;
4. drop `dimensions_json` and `profile_json`;
5. drop obsolete profile `schema_version` and profile-level `source_kind`;
6. drop `merchants.open_hours`;
7. remove duplicated merchant tags from menu items;
8. remove obsolete JSON parsing code;
9. update `docs/database-schema.md` and the data dictionary.

### Stage G — Rollback boundary

Before Stage F, rollback means returning application reads to legacy columns and
dropping the newly populated structures if necessary. After the legacy columns
are dropped, rollback requires restoring the pre-migration `pg_dump`. Therefore
the destructive cleanup is a separate migration and is not combined with
expand/backfill.

## 12. Repository and Tool Contracts

### 12.1 `get_merchant_profile`

Reads `merchant_profiles`, `merchant_ratings`, and `operational_metrics`.
Reconstructs the eight named dimensions without returning
`overall_score_internal`.

### 12.2 `get_profile_evidence`

Requires a valid dimension. Reads one score, its calculation row, and only the
matching evidence rows. An unknown dimension returns a typed validation error;
it must not fall back to returning the full profile.

### 12.3 `compare_competitors`

Requires `merchant_id` and the request radius. It computes current distance in
SQL and returns only the columns needed for comparison.

### 12.4 Evidence verification

Structural verification resolves every non-empty reference against its owning
table and compares cited values against typed database columns. Invalid or
unresolvable claims fail closed.

## 13. Correctness Test Plan

### 13.1 Schema tests

- Database constraints reject scores, rates, ratings, and coordinates outside
  their canonical ranges.
- Coordinate pair integrity is enforced.
- Required array columns are non-null.
- Every complete profile has eight calculations.
- Typed evidence contains exactly one value.
- Public models cannot serialize `overall_score_internal`.
- Merchant profile domain tables contain no JSONB after cleanup.

### 13.2 Migration tests

- Backfill count reconciliation for every target table.
- Field-by-field comparison for representative hero and background merchants.
- Explicit checks for merchant `94` and the five weak demo scenarios.
- No precomputed competitor distance survives.
- Re-running the data backfill is idempotent.
- Failed validation rolls back the affected transaction.
- Cleanup is not executed while any application path still reads legacy JSON.

### 13.3 Query contract tests

- Merchant-level rating filters use summary ratings.
- Menu price filters use `EXISTS` semantics.
- All eight score filters use typed score columns.
- Tag/segment array filters have deterministic containment semantics.
- Dynamic radius results change when radius changes.
- Haversine results respect the radius boundary.
- Missing coordinates return a typed insufficient-data result.

### 13.4 Agent and tool tests

- A one-dimension evidence request cannot return the full profile.
- Waiting-time evidence contains preparation facts only.
- Competitor results use the caller-provided radius.
- Tool output schemas contain no internal aggregate score.
- Evidence references resolve to real relational rows when references are
  present.

## 14. Documentation and Ownership

Implementation must update:

- `docs/database-schema.md`;
- `docs/data-pipeline-and-dictionary.md`;
- scoring documentation for the `0..1` contract and waiting-time rule;
- SQLAlchemy models;
- Pydantic merchant profile and evidence contracts;
- importer mappings;
- repository and tool contract tests.

No session, user, chat, preference, agent-run, or agent-event schema is changed
by this work.

## 15. Completion Criteria

The refactor is complete when:

1. the application reads and writes only the relational merchant schema;
2. all filterable merchant facts are typed columns or approved `TEXT[]` fields;
3. eight profile scores use one documented `0..1` scale;
4. ratings, operations, calculations, evidence, and complaints have unambiguous
   ownership;
5. the merchant profile domain no longer contains JSONB;
6. distance is calculated from coordinates at query time and never persisted;
7. the old JSON columns and parsing paths are removed;
8. the migration and correctness test suites pass;
9. the updated schema and data dictionary describe the database as built.
