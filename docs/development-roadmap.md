# Development Roadmap

This document tracks project phases, milestones, and overall progress.

---

## Phase Overview

| Phase | Name | Owner | Status | Progress | Dependencies |
|-------|------|-------|--------|----------|-------------|
| 0 | Shared Foundation & Seams | Owner (solo) → handoff | ✅ COMPLETE | 100% | None |
| 0.5 | Walking Skeleton (UC-04) | Owner (solo) → handoff | 🔄 IN PROGRESS | 25% | Phase 0 |
| 1 | Track A — Customer Vertical | Dev A | ☐ NOT STARTED | 0% | Phase 0.5 |
| 2 | Track B — Merchant Vertical | Dev B | ☐ NOT STARTED | 0% | Phase 0.5 |
| 3 | Integration & Evaluation | 2 dev pair | ☐ NOT STARTED | 0% | Phase 1 + 2 |

**Overall Progress:** 20% (2 of 10 major milestones)

---

## Phase 0: Shared Foundation & Seams ✅ COMPLETE

**Status:** Complete (2026-07-22)
**Owner:** Owner (solo) → handoff

### Deliverables (ALL COMPLETE)
- ✅ Backend core infrastructure (settings, errors, logging, tracing, cache)
- ✅ Database models + migrations (4 new tables + indexes)
- ✅ Tool registry + allow-list artifact
- ✅ App factory + extension seam (startup hooks, middleware)
- ✅ Agent config layout (customer/merchant separated)
- ✅ Event schema + CrewAI listener contract
- ✅ Router wiring (9 route stubs at 501)
- ✅ Frontend skeleton (Vite + React + TS + Tailwind)
- ✅ Docker Compose (per-dev isolated DB/Redis)
- ✅ Test harness (15 tests passing)

### Success Criteria Met
- ✅ Health endpoint returns DB + Redis status
- ✅ Migration chain creates all tables + indexes
- ✅ Tests pass without Docker (in-memory cache)
- ✅ Frontend `npm run dev` runs successfully
- ✅ All frozen seams ready for handoff

### Handoff Ready
**Yes** — All contracts and interfaces defined. Phase 0.5 walking skeleton will prove these contracts before fork.

---

## Phase 0.5: Walking Skeleton (UC-04 End-to-End) 🔄 IN PROGRESS

**Status:** In Progress (2026-07-22)
**Owner:** Owner (solo) → handoff
**Progress:** 25% (1 of 4 major deliverables complete)

### Purpose
Build one vertical slice of UC-04 (restaurant search) through entire stack to prove all Phase 0 contracts are correct before forking parallel development.

### Deliverables Status

| # | Deliverable | Status | Notes |
|---|-------------|--------|-------|
| 1 | Route `GET /merchants/search` (real, not stub) | ✅ COMPLETE | Returns 200, input validation secured, SQL injection protected |
| 2 | Migration + seed (merchants/menu/reviews) | ☐ NOT STARTED | Resettable additive seed, migration-chain proven |
| 3 | `merchant_repository` + `merchant_search_service` | ☐ NOT STARTED | Basic query implementation |
| 4 | `merchant_search_tool` via registry | ☐ NOT STARTED | Proven tool metadata + allow-list |
| 5 | `nearby_merchant_search` tool (Haversine) | ☐ NOT STARTED | Front-loaded for Dev B (Competitor) |
| 6 | Shared read-only tools proven | ☐ NOT STARTED | `get_merchant_profile`, `get_trending_dishes` fixtures |
| 7 | `customer_flow` + event emission | ☐ NOT STARTED | Reference listener persists agent_events |
| 8 | React search page calling API | ☐ NOT STARTED | Render results from real API |

### Recent Progress (2026-07-22)
**Bug Fixes Completed & Validated:**
- Fixed test expectation mismatch (endpoint returns 200, not 501 stub)
- Added input validation (lat/lng/radius_km/limit with Pydantic validators)
- Secured SQL injection protection (LIKE special character escaping)
- **Test Results:** 28/28 tests passing (10 new validation tests added)

### Success Criteria (GATE before Phase 1/2 fork)
- ☐ UC-04 runs end-to-end: query → API → tool → DB → React results
- ☐ Agent runs + events emitted with trace_id (event schema proven)
- ☐ Cache hits/misses with in-memory adapter (CachePort proven)
- ☐ Registry allow-list blocks unauthorized tools (security proven)
- ☐ `alembic upgrade head` + reset seed runs idempotently

### Once Complete
- Tag `phase0-freeze`
- Fork Track A (Dev A) and Track B (Dev B) branches
- Both tracks proceed in parallel using proven contracts

---

## Phase 1: Track A — Customer Discovery Vertical ☐ NOT STARTED

**Owner:** Dev A (full-stack BE + FE)
**Status:** Not started
**Estimated Effort:** 2-3 weeks

### Scope
- **UC-04:** Restaurant search (completion of Phase 0.5)
- **UC-05:** Preference/context reasoning
- **Features:** E (Preferences), F (Tools/Providers), G (Customer Agent), K (Map/Context UI)

### File Ownership
```
backend/repositories/{merchant,user_profile,session,preference_event,interaction_event}_repository.py
backend/services/{merchant_search,customer_context,preference,session,weather,geocode,map}_service.py
backend/providers/{cache,weather,geocode,routing}/*
backend/tools/{merchant_search,nearby_merchant,user_profile,profile_delta,weather,geocode}_tool.py
backend/agents/customer/* (+ config)
backend/flows/customer_flow.py
backend/routes/{merchant_search,user,event,map,customer_agent}_routes.py
frontend/src/customer/*
```

### Dependencies
- Phase 0.5 walking skeleton complete and frozen
- `nearby_merchant_search` tool schema (provided by Dev A, consumed by Dev B)

---

## Phase 2: Track B — Merchant Advisor Vertical ☐ NOT STARTED

**Owner:** Dev B (full-stack BE + FE)
**Status:** Not started
**Estimated Effort:** 2-3 weeks

### Scope
- **UC-01:** Merchant profile (8 dimensions)
- **UC-02:** Diagnosis & recommendations
- **UC-03:** Competitor analysis
- **Features:** I (Evidence), J (Observability), L (Merchant UI)

### File Ownership
```
backend/repositories/{merchant_profile,evidence}_repository.py
backend/services/{merchant_profile,evidence,recommendation,competitor,agent_run}_service.py
backend/tools/{merchant_profile,evidence,competitor,trend}_tool.py
backend/agents/merchant/* (+ config)
backend/agents/listeners/* (+ config)
backend/flows/merchant_flow.py
backend/routes/{merchant_profile,merchant_agent,trace}_routes.py
frontend/src/merchant/*
```

### Dependencies
- Phase 0.5 walking skeleton complete and frozen
- `get_merchant_profile` tool (shared read-only from Phase 0)
- `nearby_merchant_search` tool (consumed from Dev A's Track A)

---

## Phase 3: Integration & Evaluation ☐ NOT STARTED

**Owner:** 2 dev pair
**Status:** Not started
**Estimated Effort:** 1-2 weeks

### Scope
- End-to-end integration of Track A + Track B
- CI pipeline validation
- Cross-domain contract verification
- Performance testing
- Documentation handoff

### Success Criteria
- All UC-01 through UC-05 scenarios pass end-to-end
- Cache + event observability integrated
- Cross-domain tools (nearby_merchant_search, get_merchant_profile) working
- Merge to `develop` branch successful
- Production deployment ready

---

## Milestones

| # | Milestone | Target Date | Status |
|---|-----------|-------------|--------|
| M1 | Phase 0 foundation complete | 2026-07-22 | ✅ COMPLETE |
| M2 | Phase 0.5 walking skeleton complete | TBD | 🔄 IN PROGRESS |
| M3 | Track A (Customer) complete | TBD | ☐ NOT STARTED |
| M4 | Track B (Merchant) complete | TBD | ☐ NOT STARTED |
| M5 | Integration complete | TBD | ☐ NOT STARTED |
| M6 | Production deployment | TBD | ☐ NOT STARTED |

---

## Risk Tracking

| Risk | Severity | Mitigation | Status |
|------|----------|------------|--------|
| Phase 0 bottleneck (both dev waiting) | HIGH | Keep Phase 0 minimal, pair-code | ✅ MITIGATED |
| Cross-dependency tools cause conflict | MEDIUM | Freeze tool I/O schemas in Phase 0 | 🔄 IN PROGRESS |
| CachePort contract insufficient | MEDIUM | Validate in Phase 0.5 walking skeleton | 🔄 IN PROGRESS |
| Event schema incomplete | MEDIUM | Contract test + reference listener in Phase 0 | ✅ MITIGATED |

---

## Next Steps

1. **Complete Phase 0.5 Walking Skeleton**
   - Finish merchant repository implementation
   - Complete customer flow with event emission
   - Build React search page
   - Run full end-to-end validation

2. **Tag `phase0-freeze`**
   - Once Phase 0.5 gate criteria met
   - Freeze all contracts and interfaces
   - Document any contract change protocol

3. **Fork Development Tracks**
   - Dev A: Branch for Track A (Customer)
   - Dev B: Branch for Track B (Merchant)
   - Both reference frozen contracts

4. **Parallel Development**
   - Weekly CI cadence (rebase/merge develop ≥2×/week)
   - Smoke test: main.py + registries + flows load
   - Cross-domain integration checkpoints

---

## References

- **Design Doc:** `docs/2026-07-21-merchant-ai-agent-complete-design.md`
- **Implementation Plan:** `plans/260722-0916-two-dev-parallel-split/plan.md`
- **Code Standards:** `docs/code-standards.md`
- **Risk Log:** `docs/risk-log.md`

---

*Last Updated: 2026-07-22*
