# System Architecture

End-to-end architecture of the VSF AI Restaurant platform. Currently focused on the **customer** vertical (CrewAI agent + unified preference/memory store, phases 1–4 of plan A). Merchant-vertical + deployment topology sections to be added.

> Source of truth for the unified-memory work: `plans/260805-1005-unify-preference-memory-store/` (plan + phase files). Cross-link at the bottom.

---

## High-Level Components

```
React (frontend/customer) ──HTTP──> FastAPI (backend) ──> CrewAI customer_flow
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                       search tools    get_user_profile   LLM (FPT Cloud AI)
                                       (merchant_       tool reads           │
                                        search,         user_profiles        │
                                        nearby_         + context_memory     │
                                        search)                              ▼
                                              │                          explanation
                                              ▼
                                     MerchantSearchService
                                     (+ profile_ranking additive)
                                              │
                                              ▼
                                     PostgreSQL (merchant_platform)
```

Domains: **customer** (CrewAI agent, search/recommend/explain, preference + memory) and **merchant** (relational schema, advisor agent — see `docs/2026-07-23-merchant-relational-schema-design.md`). Customer domain is wired end-to-end; merchant domain is relational-only at head `c2d3e4f5a6b7`.

---

## Customer Preference & Memory — 3-Layer Model

The "remember user preferences" promise is backed by **one canonical taste store** (`user_profiles`) plus two complementary memory layers. Each layer has a distinct scope, lifetime, and write path.

| Layer | Store | Scope | Lifetime | Written by | Read by |
|---|---|---|---|---|---|
| **1. Structured profile** | `user_profiles` (taste cols: `liked_cuisines`, `disliked_cuisines`, `spice_tolerance`, `dietary`, `budget_level`, `distance_preference_km`) | Canonical taste facts (typed, enumerable) | Cross-session, durable | PATCH (explicit edit) **or** confirm-delta (chat suggestion) | `get_user_profile` tool + `customer_flow._load_profile` (server-side) |
| **2. context_memory** | `user_profiles.context_memory["notes"]` (JSONB `list[str]`) | Long-term free-text facts NOT expressible in the structured schema (e.g. "dị ứng đậu phộng", persistent diet, specific medical) | Cross-session, durable | `context_memory_service.maybe_persist` at flow entry (heuristic extract → PII-redact → dedupe → FIFO cap 8) | `get_user_profile` tool (same row) |
| **3. prior_context** | `chat_messages` (per `session_id`) | Short-term in-session anaphora / recent turns | Within session (TTL 24h) | `chat_message_repository` on every turn | `customer_flow._format_prior_context` → crew prompt |

**Boundary rule (phase-03):** context_memory MUST NOT duplicate structured fields — extractor skips cuisine/budget keywords already enumerable in the schema. It only captures free-text facts. PII redacted via `core/pii.py` before persist; F3-safe (swallow + log on DB failure — never breaks the chat flow).

### Active-Constraints Enforcement (unified layer)

The 3 layers STORE facts; this layer ENFORCES them on every output. It replaced a scattered set of per-restriction filters (`_detect_dietary_conflict`, `_declared_persistent_preference`, `_recalled_dietary_filter`, `_EXCLUDED_FOODS`) that each read one layer for one restriction and fired only REACTIVELY (when the query matched the restriction) — so "không ăn được hải sản" → "xin chào" still suggested sushi. Now enforcement is PROACTIVE (keyed off the constraint set, not the query) and DATA-DRIVEN (a new restriction type = one row in the catalog, not a new filter).

- **Catalog:** `core/constraint_catalog.py` — `ConstraintDef(scope, terms, kind avoid|want)`. Currently seafood (allergy) + chay (diet). Extensible.
- **Loader:** `services/active_constraints_loader.py` — `build_active_constraints(profile, prior_turns, query) → ActiveConstraints`. ONE pass over all 3 layers + the current message → `{hard, soft}` constraints with provenance (origin/persistence). Contradiction (diet-break in current query) suppresses diet constraints.
- **Enforcer:** `services/active_constraints_enforcer.py` — `apply_constraints` (post-search hard-filter, L1 cuisine/name + dish-level L2 partial-overlap: keep a mixed merchant with ≥1 safe dish), `hard_filter_l1` (DB-result level, no dishes loaded), `query_requests_restriction` (confirm-gate when the user explicitly requests an allergen).
- **Propagation:** `constraints_scope` ContextVar in `core/profile_context.py` (mirrors `profile_scope`) — `should_hard_filter` reads it at the merchant loop so allergies filter even with `ranking_enabled=False` (safety > taste).
- **Defense-in-depth:** L1 DB pre-filter (`should_hard_filter`) → L2 post-search filter (`apply_constraints`) → L3 prompt block (`active_constraints_block` in `_build_explanation_messages`).
- **Hard vs soft:** allergies + durable/session diet = `hard_filter` (safety, always-on, every turn incl. "xin chào"); disliked cuisines = `soft_penalty` (ranking). The propose-only invariant is preserved — enforcement is a READ projection of existing data, never a new write.

### Write Paths to `user_profiles`

Three distinct paths share one repo (`UserProfileRepository`) and the same B5 typed-validation:

| Path | Route | Service | Repo method | Audit |
|---|---|---|---|---|
| **Explicit edit (PATCH)** | `PATCH /api/v1/users/{id}/profile` | `user_profile_service.update_profile` | `apply_fields(patch, user_id)` (1 tx, per-field `set`; list replaces) | `preference_events(source="user_edit", status="confirmed")` |
| **Confirm suggestion** | `POST /api/v1/users/{id}/profile/deltas/{delta_id}/confirm` | `preference_confirm_service.confirm` | `apply_delta(field, op, value)` (op = set/add/remove; idempotent via `evidence_refs.delta_id`) | `preference_events(status="confirmed")` |
| **Reject suggestion** | `POST .../reject` | `preference_confirm_service.reject` | (no mutation) | `preference_events(status="rejected")` |

**Propose-only invariant (NON-NEGOTIABLE, plan §7.1):** `propose_profile_delta` / `propose_deltas` are 100% read-only. The confirm route is the ONLY writer for suggestions; PATCH is the ONLY writer for explicit edits. Both reuse B5 typed validation through shared `_validate_and_resolve`.

### IDOR Guard (temporary)

All profile **writes** (PATCH, confirm, reject) are wrapped in `Depends(require_dev_only)` (`core/dependencies.py`): allowed when `settings.app_env != "prod"`; **403 + warning log in prod**. Replaced by real auth dependency when it lands (`TODO(AUTH)` markers in `routes/user_routes.py`). GET profile is read-only + carries no PII → not guarded.

---

## Deterministic Profile-Based Ranking (phase-02)

`MerchantSearchService.search` / `nearby_search` apply an **additive** profile score on top of the existing `_calculate_match_score` (see `docs/scoring-methodology.md`). Default behavior is unchanged when no profile is present.

- **Module:** `services/profile_ranking.py` (pure: `profile_score`, `should_hard_filter`).
- **Weights/flags:** `core/ranking_config.py` (`RankingConfig`: `w_budget`, `w_liked`, `w_disliked`, `w_dietary`, `hard_filter_disliked`). Conservative defaults (±≤0.15 nudge).
- **Budget map:** en↔vi (`student↔rẻ`, `standard↔trung bình`, `premium↔cao cấp`) vs `merchant.profile.price_level`.
- **Hard filter:** disliked-cuisine overlap drops the merchant (default ON); dietary=chay hard-filter OFF by default (insufficient merchant veg signal → soft-only).
- **Kill-switch:** `settings.ranking_enabled` (default `True`, conservative; set `False` to revert to baseline ranking).
- **Profile propagation:** the CrewAI search tools (`merchant_search`, `nearby_merchant_search`) take no `user_id` arg, so the loaded profile is propagated via a **request-scoped ContextVar** — `core/profile_context.py`:
  - `customer_flow` sets `profile_scope(profile)` around `crew.kickoff` (both blocking + stream paths, lines ~573 / ~808).
  - `MerchantSearchService` reads it via `get_current_profile()` (fallback `None` → ranking no-op).
  - Token-based reset; propagates through the stream worker's `contextvars.copy_context()`.
- **Internal scores (`overall_score`, `profile_score`) are never surfaced** to the LLM or the API response.

---

## Customer Flow Entry Points

- `POST /api/v1/agent/customer/chat` (+ `/chat/stream` SSE) → `customer_flow`.
- Per turn: `_persist_user_turn` (writes chat_messages) → `context_memory_service.maybe_persist` (F3) → `_load_profile` (server-side, feeds ranking via `profile_scope`) → crew kickoff.
- `get_user_profile` tool returns structured profile + `context_memory.notes` in one payload (crew prompt flags the notes as long-term memory).

---

## References

- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Phase files: `phase-01-backend-profile-rest.md`, `phase-02-deterministic-profile-ranking.md`, `phase-03-context-memory.md`, `phase-04-frontend-cutover.md`
- Eval reports: `plans/reports/tester-260805-*-gt-eval.md`, `plans/reports/code-review-260805-phase0*-*.md`
- Related docs: `docs/scoring-methodology.md`, `docs/database-schema.md`, `docs/customer-agent-testing-guide.md`, `docs/setup-guide.md`
- Merchant vertical: `docs/2026-07-23-merchant-relational-schema-design.md`, `docs/2026-07-21-merchant-ai-agent-complete-design.md`

---

*Last Updated: 2026-08-10*
