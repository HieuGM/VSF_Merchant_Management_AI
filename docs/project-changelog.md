# Project Changelog

This document tracks all significant changes, features, fixes, and security improvements made to the VSF Merchant Management AI platform.

---

## [2026-07-30] Customer Agent Memory Wire-up (Multiturn + Profile + Weather)

### Problem
Customer agent was stateless per-query: `chat_messages` had no writer, `preference_suggestions` were propose-only forever, `weather_override` dropped at the route → ~28/51 `ground_truth_customer.json` cases untestable (all multiturn `refinement_multiturn`, `preference_implicit`, `profile_conflict`). Memory infra (tables, read tools, agent config) existed but was disconnected.

### Changes
- **Conversation memory** (`backend/repositories/chat_message_repository.py` NEW, `backend/flows/customer_flow.py`): persist user+agent turns per `session_id` (get-or-create anonymous `ChatSession`, B1 FK fix), load last-4 into crew. TTL 24h filter (B2 → TC-11 honest-empty on stale). PII redaction on persist+render (`backend/core/pii.py` NEW).
- **Anaphora resolution** (`customer_flow.py`, `config/tasks.yaml`): `NGỮ CẢNH PHIÊN TRƯỚC` prompt block (no coordinator); `exclude_merchant_ids` arg on `merchant_search`/`nearby_merchant_search` + service (`backend/tools/customer/merchant_tools.py`, `backend/services/merchant_search_service.py`) — deterministic TC-30.
- **Weather** (`customer_flow.py`, `routes/customer_agent_routes.py`): thread `weather_override` → preference + server-side short-circuit via `preference_service.propose_deltas` (B3 → TC-06 deterministic).
- **Profile confirm** (`routes/user_routes.py`, `repositories/user_profile_repository.py`, `services/preference_confirm_service.py` NEW, `models/agent.py`): implement `/confirm`+`/reject` with typed `apply_delta` (whitelist + per-field set/add/remove, B5), `evidence_refs_json` idempotency (B6), audit log + P1 auth TODO (B7, user choice: not 403-gate). Propose path stays 100% read-only (canary extended).
- **FE** (`frontend/src/customer/**`): Lưu/Bỏ qua suggestion buttons, `session_id` localStorage-persisted + regenerate on New chat, `weather_override` field.
- **GT** (`ground_truth_customer.json`): `diet`→`dietary` (JSONB list) on TC-07/29/48.

### Verification
- 32/32 tests green (`test_customer_memory_wireup.py` 18 + propose-only canary 3 + crew 11); app import restored.
- E2e multiturn smoke (real LLM): turn-2 "quán đầu tiên" → resolved turn-1's #1 (Thanh Hằng Quán) + truth-first (no fabricated price); memory persisted.
- E2e confirm/reject HTTP smoke: apply + idempotent + reject(body/no-body) + 400-on-bad-field.
- **Status:** ✅ 9/10 targeted TCs achievable; TC-49 out-of-scope (no coordinator).
- Plan + adversarial audit: `plans/260730-customer-agent-memory-wireup/`.
- **Known limits:** FPT explanation transient flakiness (pre-existing F3, graceful fallback); double user-turn by-design (deduped on read); B4 flow→tool forward LLM-dependent.

---

## [2026-07-22] Critical Bug Fixes (Security & Correctness)

### Security Fixes
- **SQL Injection Protection** (`backend/repositories/merchant_repository.py`)
  - Added LIKE special character escaping for query patterns
  - Escapes `\`, `%`, `_` characters to prevent SQL injection in search functionality
  - Applied `escape="\\"` parameter in all `ilike()` calls
  - **Severity:** Critical
  - **Status:** ✅ Verified via 10 validation tests

### Input Validation
- **Merchant Search Parameter Validation** (`backend/routes/merchant_search_routes.py`)
  - Added Pydantic validators to `MerchantSearchRequest` model and Query parameters:
    - `lat`: latitude bounds `ge=-90, le=90`
    - `lng`: longitude bounds `ge=-180, le=180`
    - `radius_km`: positive radius `gt=0, le=500` (max 500km)
    - `limit`: results bounds `ge=1, le=100`
  - Prevents invalid coordinate and radius data from reaching business logic
  - **Severity:** High (data integrity and system stability)
  - **Status:** ✅ Verified via 10 validation tests

### Test Corrections
- **API Stub Test Expectation Fix** (`backend/tests/contract/test_api_stubs.py`)
  - Removed `/api/v1/merchants/search` from stub routes list (was expecting HTTP 501)
  - Added `test_merchant_search_endpoint_implemented()` to verify HTTP 200 response
  - Validates response structure: `trace_id`, `merchants`, `total`, `filters_applied`, `cache_status`
  - **Status:** ✅ Verified

### Test Suite Enhancement
- **Expanded test coverage:** 18 existing + 10 new tests = 28 total tests
- **New validation test file:** `backend/tests/unit/test_merchant_search_validation.py`
- **Coverage achieved:**
  - `routes/merchant_search_routes.py`: 78%
  - `repositories/merchant_repository.py`: 59%
  - `flows/customer_flow.py`: 82%
- **All tests passing:** 28/28 (0.38s execution time)

### Reports
- **Validation Report:** `plans/reports/tester-260722-1132-bug-fix-validation.md`
- **Code Review Report:** `plans/reports/code-reviewer-260722-1135-bug-fixes-review.md`

### Impact
- **UC-04 Restaurant Search:** Now secure and validated
- **Phase 0.5 Walking Skeleton:** Route endpoint verified and protected before fork
- **Developer Handoff:** Bug fixes ensure contract reliability for parallel development

---

## [2026-07-22] Phase 0 Complete: Shared Foundation & Seams

### Infrastructure
- **Backend Core:** Settings, errors, logging, tracing, cache (CachePort + in-memory adapter), dependencies
- **Database Models:** API contracts, agent/event schemas, preferences, events, merchant profiles
- **Tool Registry:** Metadata schema, allow-list artifact, per-domain auto-discovery
- **App Factory:** Extension seam for startup hooks, middleware, exception handlers
- **Migration Chain:** 4 new tables + indexes (chain 026b→a1b2)

### Frontend
- **Vite + React + TypeScript + Tailwind CSS** setup
- **Router shell + layout + shared API client**
- **Customer/Merchant domain directories** prepared

### Testing
- **15 tests passing / 2 skipped** (Postgres integration without Docker)
- **Contract tests:** Allow-list sync, API stubs, event emission
- **Unit tests:** Cache adapter, tool registry

### Configuration
- **Docker Compose:** Per-dev isolated PostgreSQL + Redis (ports/volumes separated)
- **CrewAI:** Pinned to v1.15.5 (standalone)

---

## Template for Future Entries

### [YYYY-MM-DD] Feature/Bugfix Title

#### Summary
Brief description of what changed

#### Changes
- **File** `path/to/file`: Description of change
  - Technical details
  - Severity (if applicable)

#### Testing
- Test coverage added
- Test results

#### Impact
- What features/systems affected
- Breaking changes (if any)

#### Reports
- Links to relevant reports/docs

---
