# Plan: Chia việc 2 dev code song song (Customer vs Merchant vertical)

> Date: 2026-07-22 · Branch: develop · Nguồn contract: `docs/2026-07-21-merchant-ai-agent-complete-design.md`

## Mục tiêu
Chia toàn bộ việc sắp tới (Feature A→L) cho **2 dev full-stack** sao cho code song song, **không đụng file của nhau**. UI design đã có sẵn (chỉ cần build React theo design). FE + BE đều trong scope.

## Mô hình chia: Domain Vertical
- **Dev A — Customer Discovery** (tìm quán, preference, map, weather, customer agent) — BE + FE.
- **Dev B — Merchant Advisor** (profile 8 chiều, diagnosis, recommendation, competitor, evidence, observability) — BE + FE.
- Module layout backend (doc §12) đã tách sẵn `agents/customer/*` vs `agents/merchant/*` → hợp trục này.

## Nguyên tắc độc lập (KEY)
Xung đột chỉ xảy ra ở **file dùng chung**. Ta gom hết file dùng chung vào **Phase 0** rồi ĐÓNG BĂNG. Sau Phase 0, mỗi dev sở hữu glob file riêng, giao tiếp qua **interface/contract đã freeze** (Pydantic models, CachePort, tool registry, event schema, API contract) — depend qua interface KHÔNG phải sửa file chung.

## Phases
| Phase | Tên | Owner | Song song? | Status |
|---|---|---|---|---|
| 0 | Shared Foundation & Seams | **Owner (bạn) solo** → handoff | Không — làm TRƯỚC | ✅ skeleton done (freeze chờ 0.5) |
| 0.5 | **Walking Skeleton** (UC-04 search end-to-end) | **Owner (bạn) solo** → handoff | Không — TRƯỚC khi fork | 🔄 IN PROGRESS — route endpoint verified & secured |
| 1 | Track A — Customer Vertical | Dev A | Song song với Phase 2 | ☐ |
| 2 | Track B — Merchant Vertical | Dev B | Song song với Phase 1 | ☐ |
| 3 | Integration & Evaluation | 2 dev pair | Sau khi 1+2 xong (+ CI liên tục) | ☐ |

Chi tiết: [phase-00](phase-00-shared-foundation-and-seams.md) · [phase-00b (walking skeleton)](phase-00b-walking-skeleton.md) · [phase-01 (Dev A)](phase-01-track-a-customer-vertical.md) · [phase-02 (Dev B)](phase-02-track-b-merchant-vertical.md) · [phase-03](phase-03-integration-and-evaluation.md)

> **[Red-team C3]** Không freeze contract "trên giấy" rồi mới fork. Phase 0.5 build 1 vertical slice (UC-04) CHUNG để **chứng minh** pattern cache/tool/route/event/migration là ĐÚNG, rồi mới đóng băng. Freeze = contract đã proven, không phải đoán.

## Bản đồ sở hữu file (sau Phase 0)
| Layer | Dev A (Customer) | Dev B (Merchant) |
|---|---|---|
| repositories | merchant, user_profile, session, preference_event, interaction_event | merchant_profile, evidence |
| services | merchant_search, customer_context, preference, session, weather, geocode, map | merchant_profile, evidence, recommendation, competitor, agent_run |
| providers | weather/, geocode/, routing/, cache/ | (dùng CachePort của A qua interface) |
| tools | merchant_search, nearby_merchant, user_profile, profile_delta, weather, geocode | merchant_profile, evidence, competitor, trend |
| agents | agents/customer/* (+ customer config) | agents/merchant/*, agents/listeners/* (+ merchant config) |
| flows | flows/customer_flow.py | flows/merchant_flow.py |
| routes | merchant_search_routes, user_routes, event_routes, map_routes, customer_agent_routes | merchant_profile_routes, merchant_agent_routes, trace_routes |
| frontend | frontend/src/customer/* | frontend/src/merchant/* |

## Các "đường nối" đóng băng ở Phase 0 (KHÔNG sửa sau đó)
1. `database/models.py` + migrations — **tạo HẾT bảng của cả 2 domain 1 lần** (customer: user_profiles, preference_events, interaction_events, chat_* ext; merchant: merchant_profiles ext, agent_runs, agent_events). **[C2] 1 owner migration-chain duy nhất** (xem protocol dưới).
2. `models/api.py` + base Pydantic contracts; model theo domain tách file riêng.
3. `core/*` (settings, errors, logging, tracing, **CachePort + in-memory adapter reference**, dependencies). **[H4]** memory adapter ship LUÔN ở Phase 0 (không đợi D-02) để cả 2 test không cần Redis.
4. `app/main.py` — include SẴN router cả 2 domain (stub) + **[H5] extension seam**: startup-hook list + middleware/exception-handler registry (để listener/CORS/lifespan gắn vào KHÔNG sửa main.py). Đặt owner cho sửa main.py bất khả kháng.
5. `tools/registry.py` core + **[C1] bảng allow-list tool-name/version/allowed_agents = 1 artifact dữ liệu chung frozen** (không phải code 2 dev cùng sửa). Auto-discovery per-domain package (không cần shared import manifest).
6. **[C1] Shared read-only tools vào Phase 0 frozen**: `get_merchant_profile`, `get_trending_dishes` (cả 2 domain consume — design §5.4/§9.2) + 1 profile fixture tối thiểu, để Customer Explanation/Competitor không block chờ nhau.
7. `agents/{customer,merchant}/config/*` — tách 2 file yaml theo domain (**[M10]** git merge yaml nhỏ là chuyện vặt, KHÔNG cần vòng design-review formal).
8. CrewAI **event schema** (listener contract) + **[H8] contract test "emit đủ field"** + reference listener tối thiểu — 2 flow verify emission trên branch mình, không đợi merge.
9. Frontend skeleton (Vite+React+Tailwind, router, API client, shared UI components từ design).

## [C2] Contract-change protocol (khi seam frozen sai giữa chừng)
Freeze KHÔNG có nghĩa bất biến — có nghĩa **đổi phải qua cửa hẹp**:
1. Mọi thay đổi file frozen (models, migration, event schema, tool schema, CachePort) = **PR nhỏ serialize vào `develop`**, KHÔNG commit thẳng vào feature branch.
2. **1 owner** duyệt (migration-chain owner cho schema; contract owner cho Pydantic/tool). Version-bump + announce.
3. Cả 2 dev **rebase lên `develop` trong ngày**.
4. Cấm 2 dev tự tạo Alembic revision song song → tránh 2-head. Nếu lỡ có, Phase 3 pre-plan `alembic merge heads`.

## [H6] DB/Redis isolation & seed ownership
- Mỗi dev **DB + Redis riêng** (docker-compose per-dev) HOẶC prefix Redis key theo dev (§8.2 key giống hệt 2 dev → collision).
- Seed **additive/idempotent**, KHÔNG truncate catalog chung. Owner seed = migration-chain owner.
- Owner-to-merchant mapping + `user_demo` seed (§11.5): gán rõ cho Dev owner (mặc định Dev A vì customer/session). Resettable seed (L-03) **kéo lên Phase 0.5**, không đợi Phase 3.

## [C3/Failure] CI cadence (không big-bang merge)
- 2 branch **rebase/merge `develop` ≥ 2 lần/tuần** + boot smoke test (main.py + 2 registry + 2 flow load được).
- **Checkpoint tích hợp giữa kỳ** (giữa Phase 1/2) — không dồn hết rủi ro vào Phase 3.
- **[H7]** Front-load deliverable upstream của Dev A: `providers/cache` (đã ở Phase 0), `nearby_merchant_search` tool → Phase 0.5 để Dev B (Competitor) không chờ.

## Sai lệch có chủ đích so với design doc
- Doc §5.1 dùng chung `agents/config/agents.yaml` + `tasks.yaml`. Để tránh 2 dev cùng sửa 1 yaml → **tách theo domain** `agents/customer/config/` và `agents/merchant/config/`. Cần review approve (đổi contract layout).
- Doc §11 gộp merchant search + profile trong `merchant_routes.py`. Tách thành `merchant_search_routes.py` (Dev A) và `merchant_profile_routes.py` (Dev B) để rạch ròi sở hữu.

## Rủi ro & giảm thiểu
- **R1 Phase 0 là điểm nghẽn:** cả 2 chờ Phase 0 xong. → Giữ Phase 0 tối thiểu (skeleton + freeze contract), pair-code cho nhanh, không nhồi business logic.
- **R2 Cross-dependency tool:** Merchant Competitor cần `nearby_merchant_search` (Dev A sở hữu). → Freeze input/output schema tool ở Phase 0; Dev B consume qua registry, không sửa file A.
- **R3 Observability ghi cả 2 flow:** → dùng event-driven; 2 flow emit CrewAI event, listener của Dev B subscribe. Không gọi service chéo.
- **R4 CachePort:** Dev B cache profile snapshot bằng CachePort (interface freeze Phase 0), Dev A implement adapter. Depend interface, không đụng file.

## Resolved decisions (2026-07-22)
1. ✅ **CrewAI version = 1.15.5** (standalone). Registry/event/tool-wrapper freeze theo API bản này — verify không kéo LangChain vào dependency graph khi cài (doc TBD-R3 → phải check `pip show crewai` deps).
2. ✅ **Fixture = 18 hero** (không subset). B-03 + profile fixture Phase 0 dùng đủ 18.
3. ✅ **Migration-chain owner / contract owner = bạn (người làm)** — mọi PR đổi file frozen bạn duyệt & serialize vào `develop`.

## Implementation Log

### Phase 0 — 2026-07-22 (skeleton complete, NOT yet frozen)
Built shared foundation + all frozen seams. Tests: 15 pass / 2 skip (Postgres integration, no Docker). FE builds clean (Vite+React+TS+Tailwind).
- **Backend:** `core/*` (settings, errors §11.10, logging, tracing, cache CachePort+keys §8.2, dependencies) · `app/main.py` (frozen factory) + `app/extensions.py` (H5 startup/middleware/exception seam, CORS from settings) · `models/*` (api, profile §6.4, agent+event schema §6.2, preference §7.1, events) · `database/models.py` + migration `a1b2c3d4e5f6` (4 new tables + §6.2 indexes, chain 026b→a1b2) · `providers/cache/memory_adapter.py` (H4) · `tools/` split shared/customer/merchant + `registry.py` §9.1 + `allow_list.py` §5.4 (C1) + shared read-only tools + fixture · 9 route stubs (501) · reference CrewAI listener + emission helper (H8) · agent config yaml stubs.
- **Infra:** docker-compose per-dev A/B (isolated PG+Redis ports/volumes, H6) · pinned `crewai==1.15.5`.
- **Post code-review fixes:** PREFERENCE_SCOPES aligned to §7.1 · CORS no longer wildcard+credentials · tools split into per-domain packages (real isolation) · YAML↔allow-list sync contract test · new tables added to integration test assertion.
- **⚠️ Carry to Phase 0.5:** verify `pip install crewai==1.15.5` does NOT pull LangChain (§2, clean-env dep-tree check) BEFORE tagging `phase0-freeze`.

### Bug Fix Session — 2026-07-22 (Critical security & correctness fixes)
Validated 3 critical bug fixes affecting merchant search UC-04. All 28 tests passing (10 new validation tests added).
- **Fix 1:** Test expectation mismatch in `backend/tests/contract/test_api_stubs.py` — removed `/api/v1/merchants/search` from stub routes, added `test_merchant_search_endpoint_implemented()` to verify 200 response (not 501 stub).
- **Fix 2:** Input validation in `backend/routes/merchant_search_routes.py` — added Pydantic validators for `lat` (ge=-90, le=90), `lng` (ge=-180, le=180), `radius_km` (gt=0, le=500), `limit` (ge=1, le=100). Applied to both `MerchantSearchRequest` model and query parameters in both route functions.
- **Fix 3:** SQL injection protection in `backend/repositories/merchant_repository.py` — escaped LIKE special characters (`\`, `%`, `_`) in `query_pattern` using `escape="\\"` parameter in `ilike()` calls.
- **Test coverage:** 78% (routes), 59% (repositories) — SQL injection protection confirmed via 10 validation tests covering special chars, wildcards, injection attempts.
- **Reports:** `plans/reports/tester-260722-1132-bug-fix-validation.md` · `plans/reports/code-reviewer-260722-1135-bug-fixes-review.md`.

## Validation Log

### Session 1 — 2026-07-22
**Trigger:** post red-team validate trước khi implement. **Questions:** 4.
1. **[Risk]** DB+Redis 2 dev → **Isolated per-dev** (docker-compose riêng, port/volume riêng). Không clobber data, không collision key §8.2.
2. **[Architecture]** Git model → **Feature branch + CI cadence** (rebase develop ≥2×/tuần + smoke test).
3. **[Scope/Risk]** Ai làm Phase 0+0.5 → **Owner (bạn) solo rồi bàn giao.** ⚠️ 2 dev phải học contract sau → mitigation: walking skeleton (Phase 0.5) làm **reference demo chạy được** + seam doc rõ trong phase-00 để handoff nhanh.
4. **[Scope]** Task tracking → **Hydrate Claude Tasks theo phase.**

**Confirmed:** isolated DB/Redis · feature-branch+CI · owner-solo Phase 0/0.5 · hydrate tasks.
**Impact:** Phase 0 owner đổi 2-dev-pair → owner solo; thêm handoff note. Docker-compose per-dev thêm vào Phase 0 A-03.

## Red Team Review

### Session — 2026-07-22
**Findings:** 10 (9 accepted, 1 rejected) · **Reviewers:** Assumption Destroyer, Failure Mode Analyst, Scope & Complexity Critic
**Severity:** 3 Critical, 5 High, 2 Medium

| # | Finding | Sev | Disposition | Applied To |
|---|---|---|---|---|
| C1 | Cross-dep ẩn: shared tools (get_merchant_profile, get_trending_dishes) + allow-list cross-domain | Critical | Accept | Phase 0 (seam #5,#6) |
| C2 | Không có thaw protocol + migration-chain owner → Alembic 2-head | Critical | Accept | plan.md (protocol), Phase 0 |
| C3 | Freeze trước consumer = premature; big-bang merge cuối | Critical | Accept | Phase 0.5 walking skeleton + CI cadence |
| H4 | In-memory CachePort adapter B cần nhưng A sở hữu | High | Accept | Phase 0 (seam #3) |
| H5 | main.py frozen nhưng listener/middleware cần startup hook | High | Accept | Phase 0 (seam #4) |
| H6 | DB/Redis không isolate + seed owner mờ | High | Accept | plan.md (isolation) |
| H7 | Lệch tải, Dev A là upstream bottleneck | High | Accept | plan.md (front-load), Phase 0.5 |
| H8 | Observability: emission flow A không verify tới lúc merge | High | Accept | Phase 0 (seam #8) |
| M9 | Gold-plating demo (OSRM/AMP/SSE/trace-UI/Layer-2) | Medium | **Reject** | User giữ full scope A→L |
| M10 | Tách yaml phải qua design-review formal | Medium | Accept | Phase 0 (seam #7) |
