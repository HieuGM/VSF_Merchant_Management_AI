# Project Changelog

This document tracks all significant changes, features, fixes, and security improvements made to the VSF Merchant Management AI platform.

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
