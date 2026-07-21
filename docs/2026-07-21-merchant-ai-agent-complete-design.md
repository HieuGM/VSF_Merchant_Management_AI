# Merchant AI Agent Platform - Complete System Design

> Version: 1.1
> Date: 2026-07-21
> Status: Design for team review
> Scope: Development/demo phase, local deployment, mocked and crawled data accepted

## 1. Purpose

This document is the implementation reference for the Merchant Management AI project.
It consolidates the requirements, data schema, backend architecture, CrewAI agent
design, cache and memory rules, API contracts, tool registry, UI preference tracking,
feature roadmap, and acceptance criteria.

The team should use this document as the contract between frontend, backend, data,
and AI agent work. A contract change must be reviewed before related code is changed.

Development fixtures may be small and synthetic as long as they follow the schemas
and evidence contracts below.

> **[C1]** Tài liệu này là **contract chuẩn duy nhất** cho Agent Layer (Native CrewAI,
> multi-agent). Mọi thiết kế agent trước đó (bản 2-agent OpenAI function-calling) không
> còn hiệu lực; không tạo doc agent song song để tránh xung đột nguồn implement.

## 2. Verified Decisions

| Area | Decision |
|---|---|
| Backend | Python FastAPI |
| Database | PostgreSQL 15 in Docker |
| ORM/migrations | SQLAlchemy and Alembic |
| Agent framework | Native CrewAI |
| LangChain | No LangChain services, tools, or orchestration |
| LLM provider | OpenAI-compatible API selected by environment variables |
| Agent tracing | CrewAI events, local logs, internal events, optional CrewAI AMP |
| Cache | Redis for volatile cache; PostgreSQL remains source of truth |
| Frontend | React/Vite and TailwindCSS, mobile-first |
| Location permission | Browser Geolocation API |
| Weather | Open-Meteo |
| Nearby distance | PostgreSQL Haversine over the internal catalog |
| Map | Leafmap using backend-generated GeoJSON |
| Road distance/ETA | Optional OSRM, not required for initial search |
| Reverse geocoding | Nominatim adapter with cache and rate limit |
| Data scale | Small development/demo data is accepted |
| Delivery model | Build the complete target system through feature-based tasks |

> **[TBD — R3]** Xác nhận version CrewAI dùng bản standalone (không kéo LangChain) trước
> Feature F/G/H. Nếu bản chọn còn phụ thuộc LangChain, điều khoản "No LangChain in
> dependency graph" phải review lại.

Google Places is not the primary nearby merchant source. The product searches its
own merchant catalog, so PostgreSQL is authoritative. An external place provider is
outside the approved scope and requires a separate review.

## 3. Product Use Cases

### 3.1 Actors

| Actor | Primary goal |
|---|---|
| Merchant Owner | Understand weaknesses, evidence, and improvement actions |
| Customer | Find food by preference, budget, distance, and context |
| Demo Reviewer | Inspect the flow, evidence, and trace |

### 3.2 Merchant use cases

#### UC-01 - Merchant Diagnosis

Example: "Tại sao quán tôi ít đơn?"

The system loads the merchant profile, selects weak dimensions, retrieves supporting
evidence, ranks up to five likely causes, and attaches evidence references. It must
return insufficient_data instead of inventing a cause.

#### UC-02 - Merchant Recommendation

Example: "Tôi nên cải thiện điều gì trước?"

The system converts weak dimensions into prioritized actions. Expected impact is an
estimate, not a guaranteed business result. Every recommendation must link to at
least one dimension and one evidence reference.

#### UC-03 - Competitor Analysis

Example: "Đối thủ gần đây làm tốt hơn tôi ở điểm nào?"

The system finds comparable merchants by location and cuisine, compares public or
profile dimensions, and returns relative strengths and weaknesses. Private business
KPI claims about competitors are forbidden.

### 3.3 Customer use cases

#### UC-04 - Restaurant Search

Example: "Tìm quán bún bò dưới 70 nghìn, cách đây 3 km."

The system extracts constraints, calls structured search tools, and returns a small
result set with distance and reasons. It cannot claim a merchant is open or available
unless the source contains that field.

#### UC-05 - Preference and Context Reasoning

Example: "Trời mưa thì hôm nay tôi nên ăn gì?"

The system reads confirmed preferences, session constraints, permitted location, and
weather context. It searches and ranks merchants, then explains the result using
visible preference signals.

## 4. System Architecture

### 4.1 High-level flow

~~~mermaid
flowchart TD
    UI[React UI / Chat / Preference Center] --> API[FastAPI Routes]
    API --> APP[Application Services]
    APP --> FLOW[CrewAI Flow Boundary]
    FLOW --> CREW[Customer or Merchant Crew]
    CREW --> AGENTS[CrewAI Agents]
    AGENTS --> REG[Tool Registry]
    REG --> TOOLS[Native CrewAI BaseTool wrappers]
    TOOLS --> DOMAIN[Domain Services]
    DOMAIN --> REPO[Repositories]
    REPO --> PG[(PostgreSQL)]
    DOMAIN --> REDIS[(Redis Cache)]
    TOOLS --> EXT[Open-Meteo / Nominatim / OSRM optional]
    FLOW --> OBS[Event Listener + Trace Context]
    OBS --> LOGS[Structured Logs / Agent Events / AMP optional]
    TOOLS --> GEO[GeoJSON]
    GEO --> MAP[Leafmap development map]
~~~

### 4.2 Runtime request flow

~~~text
HTTP request
  -> route validation
  -> application service
  -> canonical query and trace context
  -> load session/user context
  -> load or create Redis context snapshot
  -> kickoff CrewAI Flow
  -> run Crew and agent task
  -> agent selects registered tools
  -> tool calls domain service
  -> domain service reads Redis or repository
  -> structured tool result
  -> CrewAI structured final output
  -> profile suggestions and evidence validation
  -> append events and persist chat
  -> persist confirmed deltas only
  -> invalidate relevant cache keys
  -> API response or SSE stream
~~~

### 4.3 Dependency direction

~~~text
routes
  -> application services
    -> flows/crews
      -> agents
        -> native CrewAI tools
          -> domain services
            -> repositories
              -> PostgreSQL
~~~

Rules:

- Routes only validate requests and serialize responses.
- Application services coordinate a use case and transaction boundary.
- Flows coordinate deterministic steps around a Crew.
- Agents decide how to complete a task using allowed tools.
- Tools are thin wrappers and contain no ORM query.
- Domain services own deterministic business rules.
- Repositories own database access.
- Agents never receive a SQLAlchemy session.
- No route imports a repository directly.
- No agent imports database models.
- No LangChain object is allowed in the backend dependency graph.

## 5. CrewAI Design

### 5.1 CrewAI responsibilities

CrewAI is the orchestration layer, not the business layer. It builds runtime prompts
from agent role, goal, backstory, task description, expected output, tool schemas,
structured context, and prior task output.

Agent and task configurations are versioned in agents.yaml and tasks.yaml or focused
configuration modules. Routes must not contain long prompts.

| CrewAI concept | Project responsibility |
|---|---|
| Agent | Role with explicit tools and output responsibility |
| Task | Bounded work such as search or diagnosis |
| Crew | Agents completing one domain use case |
| Flow | Deterministic application boundary around a Crew |
| BaseTool | Typed adapter to a domain service |
| Event listener | Maps execution events to trace/log records |
| Pydantic output | API-safe structured result |
| Delegation | Manager assigns bounded work to specialists |

### 5.2 Customer Discovery Crew

#### Customer Coordinator Agent

Responsibilities:

- interpret intent
- choose search, refinement, profile lookup, or explanation
- delegate bounded work to specialists
- merge specialist output

Delegation is limited to one coordinator-to-specialist hop.

#### Restaurant Search Agent

Converts normalized constraints to MerchantSearchInput, calls search tools, and
returns merchant candidates. Delegation is disabled.

#### Preference Reasoning Agent

Reads confirmed preferences and session context, combines explicit constraints with
weather/location, and proposes profile deltas. It never persists them. Delegation is
disabled.

#### Customer Explanation Agent

Explains why results match and references visible profile signals and merchant data.
Delegation is disabled.

### 5.3 Merchant Advisor Crew

#### Merchant Coordinator Agent

Routes requests to profile analysis, diagnosis, recommendation, or competitor
analysis. It is the only merchant agent allowed to delegate.

#### Merchant Profile Analyst Agent

Reads a structured profile through tools, identifies weak dimensions, and summarizes
evidence without inventing facts.

#### Diagnosis Agent

Produces ranked causes connected to dimensions and evidence.

#### Recommendation Agent

Converts weak dimensions into practical actions, retrieves trends when relevant,
and assigns priority and estimated impact.

#### Competitor Agent

Retrieves comparable merchants, compares public/profile dimensions, and reports
relative differences.

#### Evidence Verifier Agent (semantic grounding — Layer 2 only)

Evidence verification runs in two layers:

- **Layer 1 — Structural check (deterministic Flow guardrail, runs first, non-negotiable):**
  pure code, no LLM. Asserts the Pydantic schema is valid, every claim has at least one
  `evidence_ref`, each ref resolves to a real record via the evidence repository, and
  every cited number matches the stored record. A claim that fails is dropped; if no
  claim survives, the response is `insufficient_data`.
- **Layer 2 — Semantic grounding check (this agent, LLM):** runs only on claims that
  passed Layer 1. Judges whether the evidence actually supports the claim's meaning and
  causal link — catching misattribution (e.g. "delivery kém do tài xế" backed by a
  packaging complaint), overstatement, or a wrong dimension link. Output is `pass` or
  `flag for regeneration` with a reason. Tool: `get_profile_evidence`; delegation
  disabled.

Delegation rules:

- only coordinators may delegate
- specialists have allow_delegation disabled
- managers cannot delegate to themselves
- specialists receive minimum required context
- evidence verification is mandatory before a merchant response is returned

### 5.4 Agent-tool ownership

The registry enforces this allow-list at runtime. A prompt cannot grant a tool that
is absent from the registry assignment.

| Agent | Direct tools |
|---|---|
| Customer Coordinator | get_user_profile, get_session_candidates |
| Restaurant Search | merchant_search, nearby_merchant_search |
| Preference Reasoning | get_user_profile, get_session_candidates, get_weather_context, propose_profile_delta |
| Customer Explanation | get_merchant_profile |
| Merchant Coordinator | get_merchant_profile |
| Merchant Profile Analyst | get_merchant_profile, get_profile_evidence |
| Diagnosis | get_merchant_profile, get_profile_evidence, diagnose_merchant |
| Recommendation | get_merchant_profile, get_profile_evidence, get_trending_dishes, recommend_improvements |
| Competitor | nearby_merchant_search, compare_competitors |
| Evidence Verifier | get_profile_evidence |

Coordinators may perform lightweight routing and context loading, then delegate one
bounded task. They do not execute specialist diagnosis, recommendation, or search
logic themselves.

The Layer 1 structural evidence check is a deterministic guardrail owned by
`merchant_flow.py`, not an agent tool. The Evidence Verifier agent owns only the
Layer 2 semantic grounding check.

### 5.5 Prompt and output policy

Every agent defines:

- role
- goal
- backstory
- allowed tools
- maximum iterations
- retry limit
- timeout
- delegation policy
- output schema

Every task returns a Pydantic-compatible object. Free text is only the final answer.
Search results, evidence, deltas, confidence, and trace identifiers stay structured.

## 6. Data Architecture

### 6.1 Runtime source of truth

There are two explicit source-of-truth boundaries:

- `data/profiles.jsonl` is the source of truth for the generated dataset.
- PostgreSQL is the source of truth for the running API and agents after import.

Agents never open JSONL or JSON files directly. Import jobs validate and project the
dataset into runtime tables.

The current schema contains:

~~~text
merchants
menu_items
reviews
delivery_feedbacks
food_images
operational_metrics
merchant_profiles
user_profiles
chat_sessions
chat_messages
~~~

The current database is sufficient for Customer Search. Current profile rows use an
older score shape, so Merchant Agent development requires a profile projection.

### 6.2 Required runtime schema changes

Existing tables remain the base catalog. Alembic migrations add the following
runtime records before agent integration:

| Table/change | Required fields | Ownership and retention |
|---|---|---|
| merchant_profiles extension | merchant_id, profile_json, schema_version, source_kind, updated_at | Latest imported profile; durable |
| preference_events | event_id, user_id, session_id, field, operation, value_json, scope, source, confidence, status, evidence_refs_json, expires_at, created_at, resolved_at | Append-only preference audit |
| interaction_events | event_id, user_id, session_id, event_type, merchant_id, menu_item_id, metadata_json, created_at | Append-only UI/chat signal |
| agent_runs | trace_id, session_id, user_id, crew_name, intent, status, started_at, finished_at, error_code, token_usage_json | One record per Flow run |
| agent_events | event_id, trace_id, parent_event_id, event_type, agent_name, task_name, tool_name, input_hash, output_summary_json, duration_ms, status, error_code, created_at | Task/tool/delegation trace |
| chat_messages extension | trace_id, structured_payload_json | Connect visible messages to results and traces |
| chat_sessions extension | context_snapshot_json, last_trace_id | Durable recovery snapshot; Redis remains hot copy |

`preference_events` never replaces `user_profiles`. The profile
table stores current confirmed state; events explain how that state changed.
`interaction_events` are evidence only and cannot directly mutate
`user_profiles`.

`profile_json` follows the contract below. During migration,
`dimensions_json` may be read as a legacy fallback but no new agent code
writes the legacy shape.

Minimum indexes:

~~~text
merchants(city, cuisine)
merchants(lat, lng)
menu_items(merchant_id, price)
reviews(merchant_id, created_at)
preference_events(user_id, status, created_at)
interaction_events(user_id, session_id, created_at)
agent_events(trace_id, created_at)
chat_messages(session_id, timestamp)
~~~

### 6.3 Development profile projection

Before Merchant Agent integration:

1. Select the demo merchant set. **[M5 — TBD]** As-built has 18 hero merchants; confirm
   whether the fixture uses all 18 or a 5-10 subset.
2. Build the target Merchant Profile shape.
3. Use deterministic heuristic/mock values where data is absent.
4. Reference real review/menu/feedback records when available.
5. Mark mocked values as synthetic or heuristic.
6. Seed one weak merchant, one strong merchant, and one competitor cluster.

This fixture demonstrates the contract and is not a real performance claim.

### 6.4 Merchant Profile contract

~~~json
{
  "merchant_id": "68814",
  "tier": "hero",
  "overall_score": 0.64,
  "metadata": {
    "name": "Dì Bảy",
    "cuisine": "Món Việt",
    "category": "Món Việt",
    "location": {
      "address": "string",
      "city": "TP. HCM",
      "lat": 10.79,
      "lng": 106.66
    },
    "open_hours": {"open": "09:00", "close": "22:00"},
    "image_url": "string",
    "source_url": "string",
    "phones": [],
    "taste_tags": ["đậm đà"],
    "diet_tags": []
  },
  "price_level": "trung bình",
  "dimensions": {
    "food_quality": {
      "score": 0.55,
      "evidence": [
        {
          "evidence_id": "ev_001",
          "type": "negative_review_count",
          "value": 4,
          "ref_type": "review",
          "ref_ids": ["68814_rv_1"],
          "source_kind": "real"
        }
      ],
      "basis": "reviews+complaints"
    },
    "image_quality": {
      "score": 0.71,
      "evidence": [{"evidence_id": "ev_002", "type": "dishes_with_hd_photo", "value": 0.75, "ref_type": "food_image", "ref_ids": ["img_001"], "source_kind": "heuristic"}],
      "basis": "vision_or_image_coverage"
    },
    "delivery_quality": {
      "score": 0.68,
      "evidence": [{"evidence_id": "ev_003", "type": "on_time_rate", "value": 0.82, "ref_type": "operational_metric", "ref_ids": ["68814"], "source_kind": "synthetic"}],
      "basis": "delivery_stats+complaints"
    },
    "packaging": {
      "score": 0.61,
      "evidence": [{"evidence_id": "ev_004", "type": "packaging_ok_rate", "value": 0.78, "ref_type": "delivery_feedback", "ref_ids": ["fb_001"], "source_kind": "synthetic"}],
      "basis": "delivery_stats+packaging_complaints"
    },
    "service": {
      "score": 0.63,
      "evidence": [{"evidence_id": "ev_005", "type": "service_complaint_count", "value": 2, "ref_type": "complaint", "ref_ids": ["cp_001"], "source_kind": "synthetic"}],
      "basis": "rating+service_complaints"
    },
    "waiting_time": {
      "score": 0.52,
      "evidence": [{"evidence_id": "ev_006", "type": "avg_prep_minutes", "value": 18, "ref_type": "operational_metric", "ref_ids": ["68814"], "source_kind": "synthetic"}],
      "basis": "preparation_time"
    },
    "menu_diversity": {
      "score": 0.76,
      "evidence": [{"evidence_id": "ev_007", "type": "dish_count", "value": 24, "ref_type": "menu_item", "ref_ids": [], "source_kind": "real"}],
      "basis": "dish_count+dish_type_count"
    },
    "price_level": {
      "score": 0.66,
      "evidence": [{"evidence_id": "ev_008", "type": "price_ratio", "value": 0.91, "ref_type": "menu_item", "ref_ids": ["68814::item_01"], "source_kind": "real"}],
      "basis": "merchant_median_vs_city_cuisine_median"
    }
  },
  "attributes": {
    "customer_segments": ["sinh viên"],
    "peak_time": ["11:00-13:00"],
    "competitors": [
      {"merchant_id": "3752", "name": "Bánh Mì Chim Chạy", "distance_km": 2.1}
    ],
    "trending_dishes": ["bún bò Huế"],
    "operation_kpis": {"avg_prep_minutes": 18, "cancel_rate": 0.04},
    "delivery_stats": {
      "on_time_rate": 0.82,
      "driver_rating": 4.1,
      "packaging_ok_rate": 0.78
    }
  },
  "ratings": {
    "shopeefood_avg": 4.4,
    "shopeefood_total_review": 1000,
    "foody_rating": 8.1,
    "foody_review_count": 10
  },
  "menu": [
    {"name": "Bún bò Huế", "type": "Món chính", "price": 65000, "discount_price": null, "total_like": 20, "has_photo": true}
  ],
  "reviews": [
    {"review_id": "68814_rv_1", "text": "Nước dùng ngon.", "score": 8.0}
  ],
  "synthetic_reviews": [],
  "complaints": [
    {"complaint_id": "cp_001", "category": "service", "text": "Phục vụ chậm.", "severity": "medium", "date": "2026-07-01"}
  ],
  "delivery_feedback": [
    {"feedback_id": "fb_001", "rating": 4, "comment": "Đóng gói ổn.", "created_at": "2026-07-02T00:00:00Z"}
  ],
  "data_sources": {
    "profile": "development_fixture",
    "reviews": "real_or_mocked",
    "operations": "synthetic",
    "vision": "heuristic_or_vision"
  },
  "updated_at": "2026-07-21T00:00:00Z"
}
~~~

The eight scored dimensions are:

~~~text
food_quality
image_quality
delivery_quality
packaging
service
waiting_time
menu_diversity
price_level
~~~

The five descriptive attributes are:

~~~text
customer_segments
peak_time
competitors
trending_dishes
operation_kpis
~~~

`delivery_stats` is the operational support object grouped with
`operation_kpis`; it is not a sixth scored or descriptive dimension.
Arrays may be empty, but all top-level keys and all eight dimensions are required.

> **[C2] `overall_score` is internal-only.** It is kept in the stored shape for
> sort/filter/QA, but must be **stripped from every external surface** — the profile API
> response, tool outputs, and agent answers. Never show a single aggregate score to a
> merchant or customer. See the hard rule in `docs/scoring-methodology.md`; always return
> per-dimension score + evidence instead.

> **[M1] `waiting_time` = preparation time only.** Per decision 2026-07-21 the
> `giao_hàng_trễ` (late-delivery) penalty is removed from `waiting_time` and kept only in
> `delivery_quality` (avoids double-count). Implementation pending in
> `scripts/profile/dimension_scoring.py` (week 2).

### 6.5 User Profile contract

~~~json
{
  "user_id": "user_demo_01",
  "liked_cuisines": ["Món Việt"],
  "disliked_cuisines": ["Món Nhật"],
  "spice_tolerance": "medium",
  "dietary": ["healthy"],
  "budget_level": "standard",
  "distance_preference_km": 5.0,
  "current_lat": 10.7912,
  "current_lng": 106.667,
  "context_memory": {"last_weather_mode": "rainy"},
  "updated_at": "2026-07-21T00:00:00Z"
}
~~~

Location is session-scoped by default. It is persisted only after user consent.

### 6.6 Preference Event contract

~~~json
{
  "event_id": "pref_evt_001",
  "user_id": "user_demo_01",
  "session_id": "sess_001",
  "field": "liked_cuisines",
  "operation": "add",
  "value": "Món Việt",
  "scope": "candidate_global",
  "source": "chat_explicit",
  "confidence": 0.95,
  "status": "candidate",
  "evidence_refs": ["msg_004"],
  "created_at": "2026-07-21T00:00:00Z",
  "expires_at": null
}
~~~

## 7. Preference and Memory Rules

### 7.1 Profile Delta scopes

| Scope | Example | Persistence rule |
|---|---|---|
| session | "Hôm nay tôi muốn ăn cay" | Apply to current session |
| candidate_global | Repeated interest in Món Việt | Show confirmation |
| confirmed_global | User presses Ghi nhớ | Persist to PostgreSQL |

LLM output never directly changes confirmed profile.

Signals:

- explicit chat statement
- explicit UI preference action
- result feedback
- menu or merchant click
- repeated search
- imported review history

Rules:

- explicit statements produce high-confidence candidates
- click and search history only produce observations
- review history produces evidence, not automatic persistence
- allergy, dietary, and health-related fields always require confirmation
- a weak signal cannot overwrite a confirmed preference

Candidate statuses are candidate, confirmed, rejected, and expired.

### 7.2 Preference Center UI

The Customer App contains a Preference Center that shows:

- confirmed preferences
- current session constraints
- pending suggestions
- source of each preference
- edit and delete controls

When a global candidate appears, the UI shows:

~~~text
Bạn muốn hệ thống ghi nhớ rằng bạn thích Món Việt?

[Ghi nhớ] [Chỉ dùng phiên này] [Bỏ qua]
~~~

The UI tracks:

~~~text
MENU_VIEWED
MENU_CLICKED
MERCHANT_VIEWED
SEARCH_SUBMITTED
FILTER_SELECTED
RESULT_LIKED
RESULT_DISLIKED
PREFERENCE_CANDIDATE_CREATED
PREFERENCE_CONFIRMED
PREFERENCE_REJECTED
PREFERENCE_DELETED
REVIEW_IMPORTED
~~~

Result cards include "Vì sao gợi ý?" and reference the preference signals used.

## 8. Cache Architecture

### 8.1 Permanent versus volatile state

| State | Storage | Rule |
|---|---|---|
| Confirmed preference | PostgreSQL | Durable and auditable |
| Preference event history | PostgreSQL | Append-only |
| Chat messages | PostgreSQL | Durable |
| Current session context | Redis plus PostgreSQL snapshot | Redis is hot copy |
| Search candidates | Redis | TTL |
| Weather | Redis | TTL |
| Geocode | Redis | TTL |
| CrewAI trace | Logs/event records/AMP | Not business state |

### 8.2 Redis keys

| Key | TTL |
|---|---:|
| agent:session:{id}:context:v1 | 30 minutes |
| agent:session:{id}:candidates:{hash} | 5 minutes |
| agent:user:{id}:profile_snapshot:v1 | 15 minutes |
| agent:weather:{lat}:{lng} | 10 minutes |
| agent:geocode:{query_hash} | 24 hours |
| agent:run:{trace_id} | 24 hours |

Profile confirmation, rejection, editing, or deletion invalidates the user profile
snapshot. Search constraint, location, or weather changes invalidate candidates.

Tests use an in-memory cache adapter. Local development uses Redis in Docker.

## 9. Tool Registry

### 9.1 Registry metadata

Every registered tool defines:

~~~text
name
version
description
input_schema
output_schema
allowed_agents
timeout_seconds
retry_policy
cache_policy
has_side_effect
source_kind
~~~

### 9.2 Tool catalog

| Tool | Implementation | Main consumer |
|---|---|---|
| merchant_search | SQLAlchemy repository and search service | Customer |
| nearby_merchant_search | PostgreSQL Haversine | Customer, Competitor |
| get_merchant_profile | Profile repository | Merchant |
| get_profile_evidence | Evidence repository | Merchant, Verifier |
| get_trending_dishes | Profile cache/table | Customer, Merchant |
| compare_competitors | Location/cuisine/profile service | Merchant |
| diagnose_merchant | Deterministic profile/evidence service | Merchant |
| recommend_improvements | Recommendation and trend services | Merchant |
| get_user_profile | User profile repository | Customer |
| propose_profile_delta | Preference service | Customer |
| get_session_candidates | Redis cache | Customer |
| get_weather_context | Open-Meteo adapter | Customer |
| reverse_geocode | Nominatim adapter | Customer |

Current browser location is supplied by the frontend, not discovered silently by
the backend.

Tool rules:

- return structured JSON-friendly output
- return no hidden chain-of-thought
- never mutate confirmed profile
- validate input before provider/repository calls
- use typed errors: validation_error, not_found, provider_error, timeout,
  and internal_error
- keep external providers behind replaceable interfaces

## 10. Location, Distance, Weather, and Map

The browser requests location permission and sends latitude, longitude, and
accuracy. The user may alternatively select a city, enter an address, drop a map
pin, or use demo coordinates.

PostgreSQL Haversine performs radius filtering and straight-line distance display.
OSRM is optional for road route and ETA.

The backend returns GeoJSON. Leafmap is a Python library, so the backend map service
passes this GeoJSON to a Leafmap renderer and exposes an embeddable HTML view.
React embeds that view in a controlled iframe and uses the GeoJSON endpoint for
result cards, distance labels, and selected-merchant state. The initial integration
does not introduce a second frontend map library.

Leafmap renders:

- user location
- merchant markers
- selected merchant
- radius circle
- optional competitor group
- optional OSRM route geometry

Open-Meteo supplies:

~~~text
temperature_2m
apparent_temperature
precipitation
rain
weather_code
wind_speed_10m
~~~

Weather is session context and never becomes a global preference.

## 11. API Contract

Business endpoints use /api/v1; the health endpoint remains /health.
Requests and responses use JSON with UTC timestamps. Every agent response contains
trace_id, and the server also returns X-Request-ID.

### 11.1 Health

~~~http
GET /health
~~~

~~~json
{
  "status": "ok",
  "database": "ok",
  "redis": "ok",
  "llm_configured": true
}
~~~

### 11.2 Merchant search

~~~http
GET /api/v1/merchants/search
~~~

Parameters:

~~~text
q
cuisine
city
min_price
max_price
min_rating
lat
lng
radius_km
limit
~~~

Response:

~~~json
{
  "items": [
    {
      "merchant_id": "68814",
      "name": "Dì Bảy",
      "cuisine": "Món Việt",
      "city": "TP. HCM",
      "price_level": "trung bình",
      "rating": 4.4,
      "distance_km": 1.42,
      "lat": 10.79,
      "lng": 106.66,
      "source": "internal_catalog"
    }
  ],
  "total": 1,
  "query_id": "q_001"
}
~~~

### 11.3 Merchant profile and evidence

~~~http
GET /api/v1/merchants/{merchant_id}/profile
GET /api/v1/merchants/{merchant_id}/evidence/{evidence_type}/{evidence_id}
~~~

### 11.4 Customer chat

~~~http
POST /api/v1/agent/customer/chat
~~~

Request:

~~~json
{
  "user_id": "user_demo_01",
  "session_id": "sess_001",
  "message": "Trời mưa, tìm món Việt dưới 70 nghìn gần tôi",
  "location": {"lat": 10.7912, "lng": 106.667, "accuracy_m": 30},
  "weather_override": null
}
~~~

Response:

~~~json
{
  "trace_id": "trace_001",
  "session_id": "sess_001",
  "intent": "restaurant_search",
  "answer": "Tôi tìm được ...",
  "results": [],
  "preference_suggestions": [],
  "evidence": [],
  "warnings": []
}
~~~

preference_suggestions contains candidates only. Confirmed profile changes are
returned by the explicit delta confirmation endpoint, never by the chat endpoint.

When the client sends Accept: text/event-stream, the endpoint emits:

~~~text
run_started
agent_started
tool_started
tool_finished
preference_suggestion
answer_delta
run_finished
error
~~~

### 11.5 Merchant agent

~~~http
POST /api/v1/agent/merchant/chat
~~~

Request:

~~~json
{
  "user_id": "merchant_owner_01",
  "session_id": "merchant_sess_001",
  "merchant_id": "68814",
  "message": "Tại sao quán tôi ít đơn và nên cải thiện gì trước?",
  "intent": null,
  "competitor_radius_km": 8
}
~~~

Response:

~~~json
{
  "trace_id": "trace_merchant_001",
  "intent": "diagnosis_and_recommendation",
  "answer": "Ba vấn đề ưu tiên là ...",
  "diagnosis": [
    {
      "cause": "Thời gian chuẩn bị cao",
      "dimension": "waiting_time",
      "score": 0.52,
      "confidence": 0.82,
      "evidence_refs": ["ev_006"]
    }
  ],
  "recommendations": [
    {
      "action": "Chuẩn bị trước nguyên liệu cho giờ cao điểm",
      "priority": "high",
      "estimated_impact": "Giảm thời gian chờ",
      "dimension": "waiting_time",
      "evidence_refs": ["ev_006"]
    }
  ],
  "competitor_comparison": [],
  "warnings": []
}
~~~

The caller may set `intent` to `diagnosis`,
`recommendation`, `competitor_analysis`, or leave it null for
coordinator routing. Merchant ownership authentication is required before
production; the development demo uses seeded owner-to-merchant mappings.

### 11.6 User profile and deltas

~~~http
GET /api/v1/users/{user_id}/profile
POST /api/v1/users/{user_id}/profile/deltas/{delta_id}/confirm
POST /api/v1/users/{user_id}/profile/deltas/{delta_id}/reject
DELETE /api/v1/users/{user_id}/preferences/{field}
~~~

The frontend cannot directly update user_profiles with arbitrary JSON.

### 11.7 Interaction events

~~~http
POST /api/v1/users/{user_id}/events
~~~

~~~json
{
  "session_id": "sess_001",
  "event_type": "MENU_CLICKED",
  "merchant_id": "68814",
  "menu_item_id": "68814::item_01",
  "metadata": {"position": 1, "source": "search_results"}
}
~~~

### 11.8 Map GeoJSON

~~~http
GET /api/v1/maps/merchants.geojson
~~~

Parameters are `lat`, `lng`, `radius_km`,
`cuisine`, and `selected_merchant_id`. The response is a GeoJSON
`FeatureCollection`; marker properties contain only display-safe merchant
fields and the distance calculated by the search service.

### 11.9 Session and trace inspection

~~~http
GET /api/v1/users/{user_id}/sessions
GET /api/v1/sessions/{session_id}
GET /api/v1/agent/runs/{trace_id}
~~~

The trace endpoint is development/admin-only. It returns run status, agent/task/tool
events, durations, error codes, and output summaries. It never returns prompts,
secrets, raw provider credentials, or hidden chain-of-thought.

### 11.10 Error envelope

~~~json
{
  "error": {
    "code": "insufficient_data",
    "message": "Không đủ bằng chứng để kết luận.",
    "details": {},
    "trace_id": "trace_001"
  }
}
~~~

Stable error codes are validation_error, unauthorized, forbidden, not_found,
insufficient_data, provider_error, timeout, conflict, and internal_error. HTTP
status and error code are both part of the contract.

## 12. Backend Module Layout

~~~text
backend/
  app/
    main.py
  core/
    settings.py
    errors.py
    logging.py
    tracing.py
    cache.py
    dependencies.py
  models/
    api.py
    agent.py
    profile.py
    preference.py
    events.py
  database/
    connection.py
    models.py
    migrations/
  providers/
    cache/
      redis_adapter.py
      memory_adapter.py
    weather/
      open_meteo.py
    geocode/
      nominatim.py
    routing/
      osrm.py
  repositories/
    merchant_repository.py
    merchant_profile_repository.py
    evidence_repository.py
    user_profile_repository.py
    session_repository.py
    preference_event_repository.py
    interaction_event_repository.py
  services/
    merchant_search_service.py
    merchant_profile_service.py
    evidence_service.py
    customer_context_service.py
    preference_service.py
    session_service.py
    recommendation_service.py
    competitor_service.py
    weather_service.py
    geocode_service.py
    map_service.py
    agent_run_service.py
  tools/
    registry.py
    merchant_search_tool.py
    nearby_merchant_tool.py
    merchant_profile_tool.py
    evidence_tool.py
    competitor_tool.py
    trend_tool.py
    user_profile_tool.py
    profile_delta_tool.py
    weather_tool.py
    geocode_tool.py
  agents/
    config/
      agents.yaml
      tasks.yaml
    customer/
      coordinator.py
      search_agent.py
      preference_agent.py
      explanation_agent.py
      crew.py
    merchant/
      coordinator.py
      profile_analyst.py
      diagnosis_agent.py
      recommendation_agent.py
      competitor_agent.py
      evidence_verifier.py
      crew.py
    listeners/
      crewai_listener.py
  flows/
    customer_flow.py
    merchant_flow.py
  routes/
    health.py
    merchant_routes.py
    customer_agent_routes.py
    merchant_agent_routes.py
    user_routes.py
    event_routes.py
    map_routes.py
    trace_routes.py
  tests/
    unit/
    contract/
    integration/
    fixtures/
~~~

## 13. Feature-Based Implementation Roadmap

This roadmap builds the complete target agent. It is organized by finished features,
not experimental agent levels.

### 13.1 Task matrix

Tasks run in dependency order. Tasks within the same feature may run in parallel only
after their shared contracts are approved.

| Task | Feature | Work | Concrete output | Depends on |
|---|---|---|---|---|
| A-01 | Foundation | Bootstrap FastAPI package | App factory, health route | Design approval |
| A-02 | Foundation | Centralize settings/errors/logging | Core modules and request IDs | A-01 |
| A-03 | Foundation | Wire PostgreSQL and Redis ports | Dependency providers, Docker config | A-01 |
| A-04 | Foundation | Add test harness | Unit test command, fake cache | A-02, A-03 |
| B-01 | Contracts | Define API/domain schemas | Pydantic contracts | A-02 |
| B-02 | Contracts | Add runtime migrations | Tables and indexes from section 6.2 | B-01 |
| B-03 | Contracts | Build target profile fixtures | 5-10 validated profiles | B-01 |
| B-04 | Contracts | Add schema validators/import projection | Repeatable fixture import | B-02, B-03 |
| C-01 | Data/domain | Implement catalog repositories | Merchant/menu/review access | B-02 |
| C-02 | Data/domain | Implement profile/evidence repositories | Profile and evidence lookup | B-02 |
| C-03 | Data/domain | Implement user/session/event repositories | Durable memory and audit access | B-02 |
| C-04 | Data/domain | Implement search/ranking service | Structured ranked candidates | C-01 |
| C-05 | Data/domain | Implement diagnosis/recommendation services | Deterministic candidate causes/actions | C-02 |
| D-01 | Cache/context | Define CachePort and key builder | Stable cache interface | A-03, B-01 |
| D-02 | Cache/context | Implement Redis and memory adapters | Local and test adapters | D-01 |
| D-03 | Cache/context | Build session context service | Snapshot load/save/restore | C-03, D-02 |
| D-04 | Cache/context | Add TTL/invalidation rules | Tested invalidation service | D-03 |
| E-01 | Preferences | Ingest interaction events | Event API and validation | C-03 |
| E-02 | Preferences | Generate profile delta candidates | Rule-based candidate service | D-03, E-01 |
| E-03 | Preferences | Confirm/reject/delete deltas | Audited profile mutations | E-02 |
| E-04 | Preferences | Build Preference Center | Confirmed/session/pending UI | E-03 |
| F-01 | Tools/providers | Implement tool registry | Metadata and per-agent allow-list | B-01 |
| F-02 | Tools/providers | Wrap domain tools with CrewAI BaseTool | Typed internal tool set | C-04, C-05, F-01 |
| F-03 | Tools/providers | Add Open-Meteo/Nominatim adapters | Cached context providers | D-02, F-01 |
| F-04 | Tools/providers | Add Haversine and GeoJSON services | Nearby results and map payload | C-04 |
| F-05 | Tools/providers | Add optional OSRM adapter | Labeled road route/ETA fallback | F-04 |
| G-01 | Customer Agent | Configure customer agents/tasks | Versioned YAML/config | F-02, F-03 |
| G-02 | Customer Agent | Build Customer Discovery Crew | Search/preference/explanation flow | G-01 |
| G-03 | Customer Agent | Expose chat and SSE API | Customer response contract | G-02 |
| G-04 | Customer Agent | Add customer scenario tests | UC-04 and UC-05 coverage | G-03 |
| H-01 | Merchant Agent | Configure merchant agents/tasks | Versioned YAML/config | F-02, B-03 |
| H-02 | Merchant Agent | Build diagnosis/recommendation tasks | Evidence-backed structured output | H-01 |
| H-03 | Merchant Agent | Build competitor task + 2-layer evidence check (structural guardrail + semantic verifier) | Comparison and claim validation | H-01 |
| H-04 | Merchant Agent | Expose merchant chat API | UC-01 to UC-03 contract | H-02, H-03 |
| H-05 | Merchant Agent | Add merchant scenario tests | UC-01 to UC-03 coverage | H-04 |
| I-01 | Coordination | Implement coordinator delegation | One-hop bounded delegation | G-02, H-03 |
| I-02 | Coordination | Add timeouts and partial-result policy | Resilient Crew behavior | I-01 |
| I-03 | Coordination | Validate tool and delegation allow-lists | Security/contract tests | I-01 |
| J-01 | Observability | Implement CrewAI event listener | Normalized run/task/tool events | A-02 |
| J-02 | Observability | Persist run and event traces | agent_runs and agent_events writes | B-02, J-01 |
| J-03 | Observability | Add trace inspection API/log view | Debuggable end-to-end run | J-02 |
| J-04 | Observability | Add optional CrewAI AMP config | Environment-gated external trace | J-01 |
| K-01 | Map/UI | Render backend GeoJSON with Leafmap | User/merchant/radius layers | F-04 |
| K-02 | Map/UI | Connect result cards and selection | Synchronized map/list state | K-01, G-03 |
| K-03 | Map/UI | Add weather and preference controls | Context and memory UI | E-04, F-03 |
| L-01 | Evaluation | Define fixed evaluation cases | Versioned customer/merchant dataset | G-04, H-05 |
| L-02 | Evaluation | Measure tool/evidence correctness | Evaluation report | L-01, J-03 |
| L-03 | Evaluation | Add resettable demo seed | Repeatable local demo | B-04 |
| L-04 | Evaluation | Run end-to-end acceptance | Signed review checklist | K-03, L-02, L-03 |

### 13.2 Week 1 closure mapping

| Original task | Covered by this document | Review outcome |
|---|---|---|
| W1-01 Requirements and use cases | Sections 3 and 18 | Previously marked complete |
| W1-02 System architecture | Sections 4, 5, 8, 9, 10, and 12 | Ready for reviewer approval |
| W1-03 Database and profile schema | Sections 6 and 7 | Ready for reviewer approval |
| W1-04 Mock data | Section 6.3 and task B-03 | Existing data accepted; target fixtures pending implementation |
| W1-05 Project setup | Feature A and task group F | Planned; no code started |

After this document is approved, the first implementation plan covers Feature A only.
The implementation roadmap remains the full target system; this review boundary is
for manageable code review, not a simplified agent stage.

### 13.3 Feature acceptance details

#### Feature A - Backend foundation

Deliverables:

- FastAPI entrypoint
- environment settings
- PostgreSQL and Redis dependencies
- in-memory cache for tests
- common errors
- request and trace IDs
- base Pydantic contracts

Acceptance:

- health reports database and Redis status
- settings load without importing agent modules
- unit tests run without Docker

#### Feature B - Runtime contracts and fixtures

Deliverables:

- Merchant Profile contract
- User Profile contract
- Preference Event and Evidence contracts
- target profiles for 5-10 merchants
- weak merchant and competitor cluster

Acceptance:

- every scored dimension has score, evidence, and basis
- synthetic values declare source_kind
- current merchant database remains usable for search

#### Feature C - Repositories and domain services

Deliverables:

- merchant, profile, evidence, user, session, preference, and event repositories
- deterministic search, ranking, diagnosis, and recommendation services

Acceptance:

- only repositories query ORM models
- services are testable with fakes
- outputs match domain contracts

#### Feature D - Cache and context memory

Deliverables:

- CachePort
- Redis and in-memory adapters
- session snapshot
- candidate, weather, and geocode caches
- invalidation service

Acceptance:

- cache hits avoid repeated calls
- confirmed changes invalidate snapshots
- TTL and invalidation tests pass

#### Feature E - Preference Center and Profile Delta

Deliverables:

- interaction event taxonomy
- candidate generation
- confirm, reject, edit, and delete flow
- session/global scopes
- source/evidence display

Acceptance:

- clicks never directly update global profile
- confirmation persists a delta
- sensitive preferences require confirmation
- user can inspect and delete remembered fields

#### Feature F - Tool Registry and providers

Deliverables:

- registry metadata
- per-agent tool allow-list
- native CrewAI BaseTool wrappers
- Open-Meteo, Nominatim, optional OSRM adapters
- GeoJSON map service

Acceptance:

- adding a tool does not modify a route
- invalid input fails before provider calls
- external providers are replaceable

#### Feature G - Customer Discovery Agent

Deliverables:

- coordinator, search, preference, and explanation agents
- Customer Discovery Crew
- customer chat API and optional SSE

Acceptance:

- prompts come from agent/task/context configuration
- agent calls typed search tools
- answers contain result reasons
- suggestions remain unconfirmed
- weather/location can be overridden

#### Feature H - Merchant Advisor Agent

Deliverables:

- profile analysis
- evidence retrieval
- diagnosis, recommendation, and competitor tasks
- Evidence Verifier
- Merchant Advisor Crew

Acceptance:

- diagnosis has at most five causes
- every cause has evidence
- recommendations link to weak dimensions
- competitor output uses permitted data
- missing evidence is explicit

#### Feature I - Multi-agent coordination

Deliverables:

- customer and merchant coordinator delegation
- specialist allow-list
- delegation depth/timeout policy
- hierarchical or sequential CrewAI process
- structured handoff

Acceptance:

- only approved specialists receive delegated work
- specialists cannot delegate further
- optional specialist failure yields a valid partial response
- delegation is visible in traces

#### Feature J - Observability

Deliverables:

- CrewAI event listener
- local JSON logs
- run and tool call events
- task timing and error fields
- optional AMP configuration

Acceptance:

- a run is traceable from HTTP request to response
- tool calls record input hash, duration, status, and summary
- secrets never appear in logs

#### Feature K - Map and context UI

Deliverables:

- Leafmap development view
- GeoJSON endpoint
- user and merchant markers
- radius and selected merchant
- weather indicator
- Preference Center and feedback controls

Acceptance:

- map renders merchant points
- card and map distances match the API
- UI distinguishes session and remembered preferences

#### Feature L - Evaluation and demo hardening

Deliverables:

- fixed customer and merchant query sets
- tool and evidence metrics
- latency/token logs
- resettable demo seed
- end-to-end tests

Acceptance:

- all five use cases run with small fixtures
- no flow requires the full crawled dataset
- every agent response has trace ID
- demo scenarios can be reset and rerun

## 14. Progress and Review Workflow

Before coding each feature, create a feature plan and obtain reviewer approval.
During implementation, update:

~~~text
docs/superpowers/progress/FEATURE-<letter>.md
~~~

The progress record contains:

~~~text
feature
task
status
files changed
tests run
known limitation
review decision
~~~

Workflow:

1. Prepare one feature plan with task IDs, files, tests, and contract changes.
2. Reviewer approves or requests changes.
3. Implement only approved tasks.
4. Update the progress file after each task.
5. Run tests and record results.
6. Reviewer accepts the feature before dependent feature work begins.

Any API, database, profile, tool, or agent output contract change returns to design
review before implementation.

## 15. Testing Strategy

Unit tests cover Haversine distance, profile validation, delta rules, conflict
resolution, cache behavior, provider normalization, and tool validation.

Contract tests cover route schemas, tool schemas, CrewAI outputs, evidence shape,
and SSE events.

Integration tests cover PostgreSQL repositories, Redis hit/miss/invalidation,
provider adapters with mocked HTTP, and Crews with deterministic fake tools.

End-to-end scenarios:

1. Customer searches by cuisine, price, and radius.
2. Customer grants location and receives weather-aware results.
3. Customer clicks a dish and receives a preference suggestion.
4. Customer confirms and inspects a remembered preference.
5. Customer rejects a suggestion.
6. Merchant views eight dimensions.
7. Merchant receives evidence-backed diagnosis.
8. Merchant receives prioritized recommendations.
9. Merchant compares a competitor cluster.
10. Reviewer follows route, Crew, task, tool, and response traces.

## 16. Error and Fallback Policy

| Failure | Behavior |
|---|---|
| Redis unavailable | In-memory degraded mode for local request |
| Weather unavailable | Manual override or no-weather recommendation |
| Geocoding unavailable | Keep coordinates and omit address label |
| OSRM unavailable | Use labeled straight-line distance |
| LLM unavailable | Typed provider error; no fabricated answer |
| Profile missing | profile_not_found or development fallback |
| Evidence missing | insufficient_data |
| Tool validation error | No retry; return input correction |
| Tool timeout | Retry once if idempotent, then partial response |
| Specialist failure | Coordinator returns partial result with warning |

## 17. Security and Privacy

- API keys remain in environment variables.
- Exact location is session-scoped unless confirmed.
- Preference events contain minimum personal data.
- Logs use IDs/hashes instead of sensitive payloads.
- Business revenue/profit KPI is outside scope.
- External providers receive minimum required data.
- Nominatim uses an identifying User-Agent and server-side cache.

## 18. Definition of Done

The development demo is done when:

- backend starts with PostgreSQL and Redis
- customer search works with the small current dataset
- weather and location can be supplied or overridden
- profile suggestions require confirmation
- confirmed preferences are visible, editable, and auditable
- Leafmap renders merchant GeoJSON
- merchant fixtures follow the full profile contract
- diagnosis, recommendation, and comparison return evidence
- CrewAI delegation runs through explicit coordinators
- trace IDs and tool/task events are inspectable
- all five use cases pass end-to-end
- no feature requires the full crawled dataset

## 19. References

Project:

- docs/prd-merchant-management-ai-v2.md
- docs/data-pipeline-and-dictionary.md
- AGENT_IMPLEMENT_ROADMAP.md
- backend/database/models.py
- scripts/db/import_dataset.py

CrewAI:

- [CrewAI Introduction](https://docs.crewai.com/en/introduction)
- [CrewAI Agents](https://docs.crewai.com/en/concepts/agents)
- [CrewAI Collaboration](https://docs.crewai.com/en/concepts/collaboration)
- [CrewAI Event Listeners](https://docs.crewai.com/en/concepts/event-listener)
- [CrewAI Custom Tools](https://docs.crewai.com/en/learn/create-custom-tools)
- [CrewAI Traces](https://docs.crewai.com/en/enterprise/features/traces)

Infrastructure:

- [Redis data types](https://redis.io/docs/latest/develop/data-types/)
- [Leafmap usage](https://leafmap.org/usage/)
- [PostgreSQL earthdistance](https://www.postgresql.org/docs/15/earthdistance.html)
- [OSRM API](https://project-osrm.org/docs/v26.4.0/)
- [Browser Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition)
- [Open-Meteo documentation](https://open-meteo.com/en/docs)
- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
