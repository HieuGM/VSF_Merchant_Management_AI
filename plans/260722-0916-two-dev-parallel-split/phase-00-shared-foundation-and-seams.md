# Phase 0 — Shared Foundation & Seams

> Owner: **bạn (owner) solo** → bàn giao. Làm TRƯỚC khi tách. Mục tiêu: dựng skeleton + **đóng băng mọi file dùng chung** để Phase 1/2 chạy song song 0 xung đột.
> <!-- Updated: Validation Session 1 - owner solo Phase 0/0.5 -->
> **[Handoff note]** Vì bạn làm solo, 2 dev sẽ học contract khi nhận. Giảm rủi ro: (a) walking skeleton Phase 0.5 = reference chạy được để đọc; (b) mỗi seam ghi rõ input/output trong file này; (c) buổi walkthrough ngắn khi handoff.

## Nguyên tắc
Chỉ skeleton + contract. KHÔNG nhồi business logic (để Track A/B tự làm phần domain). Xong Phase 0 → commit, tag `phase0-freeze`, 2 dev branch ra từ đó.

## Deliverables (map task doc)
### Backend foundation (Feature A)
- [x] A-01 `backend/app/main.py` app factory + `routes/health.py`
- [x] A-02 `core/settings.py`, `core/errors.py` (error envelope §11.10), `core/logging.py`, `core/tracing.py` (request/trace ID), `core/dependencies.py`
- [x] A-03 wire PostgreSQL (đã có) + Redis port; **[Validation S1] docker-compose per-dev** (Postgres+Redis isolated, port/volume riêng mỗi dev) + pin `crewai==1.15.5` trong requirements.txt (verify không kéo LangChain)
- [x] A-04 test harness: pytest command + in-memory cache fixture; test chạy KHÔNG cần Docker

### Contracts + DB (Feature B, phần chung)
- [x] B-01 Pydantic base: `models/api.py` (envelope, paging), split domain stubs `models/profile.py` `models/agent.py` `models/preference.py` `models/events.py`
- [x] B-02 **Migrations tạo HẾT bảng cả 2 domain 1 lần** (§6.2): merchant_profiles ext, preference_events, interaction_events, agent_runs, agent_events, chat ext + toàn bộ index §6.2
- [x] B-04 import projection framework (`scripts/db/import_dataset.py` đã có — chuẩn hoá + validator schema_version)

### Cache port (Feature D-01)
- [x] `core/cache.py` **CachePort** interface + key builder (§8.2 keys)
- [x] **[H4] in-memory adapter reference ship LUÔN ở đây** (không đợi D-02) — cả 2 dev test không cần Redis. Dev A D-02 chỉ còn thêm Redis adapter.

### Tool registry core (Feature F-01)
- [x] `tools/registry.py`: metadata schema (§9.1) + **[C1] allow-list = 1 artifact dữ liệu chung frozen** (tool-name/version/allowed_agents §5.4) + **auto-discovery per-domain package** (không shared import manifest → tránh 2 dev cùng sửa)
- [x] **[C1] shared read-only tools vào frozen surface**: `get_merchant_profile`, `get_trending_dishes` (design §9.2 consumer = cả Customer+Merchant) + 1 profile fixture tối thiểu

### [H5] App-factory extension seam (để main.py không bị re-touch)
- [x] Startup-hook registry (listener/lifespan/Redis đăng ký qua đây)
- [x] Middleware + exception-handler registry (CORS FE, X-Request-ID, error envelope)
- [x] Đặt **owner** cho sửa main.py bất khả kháng

### [C2] Migration-chain & contract owner
- [x] Chỉ định 1 người owner migration-chain + contract seam (duyệt mọi PR đổi file frozen)
- [x] Viết runbook "freeze break" (PR serialize vào develop, version-bump, cả 2 rebase trong ngày)

### Agent config layout (freeze — sai lệch có chủ đích)
- [x] Tạo `agents/customer/config/{agents,tasks}.yaml` (rỗng/stub) + `agents/merchant/config/{agents,tasks}.yaml` (rỗng/stub) — 2 dev sở hữu riêng, không đụng nhau

### Event schema (Feature J interface)
- [x] `models/agent.py` định nghĩa event record (§6.2 agent_events fields) + CrewAI event type list (§11.4). 2 flow emit theo schema này; listener impl → Dev B
- [x] **[H8] contract test "emit đủ field"** + reference listener tối thiểu — cả 2 dev verify emission (trace_id, input_hash, duration...) trên branch mình, KHÔNG đợi Phase 3 merge mới phát hiện thiếu field

### Router wiring (freeze main.py)
- [x] `app/main.py` include SẴN (stub 501) tất cả router: health, merchant_search, merchant_profile, customer_agent, merchant_agent, user, event, map, trace. Sau đó mỗi dev chỉ sửa FILE ROUTER của mình, không sửa main.py

### Frontend skeleton
- [x] `frontend/` init Vite + React + TailwindCSS (doc §4 mobile-first)
- [x] Router shell + layout + `frontend/src/shared/` (API client base theo §11 contract, design tokens/components từ UI design có sẵn)
- [x] Tạo thư mục trống `frontend/src/customer/` (Dev A) + `frontend/src/merchant/` (Dev B)

## Related files (tạo mới)
`backend/app/main.py`, `backend/core/*.py`, `backend/models/*.py`, `backend/tools/registry.py`, `backend/routes/health.py`, migrations mới, `frontend/**` skeleton.

## Success criteria
- `GET /health` trả status db + redis (§11.1)
- `alembic upgrade head` tạo đủ bảng + index §6.2
- pytest chạy pass không cần Docker (in-memory cache)
- FE `npm run dev` mở được app shell rỗng
- **main.py, models/api.py, core/*, database/models.py, registry.py, migrations = FROZEN** (không sửa ở Phase 1/2)

## Freeze checklist
> **[C3] KHÔNG tag freeze ở cuối Phase 0.** Freeze diễn ra sau **Phase 0.5 walking skeleton** (khi contract đã proven). Phase 0 chỉ dựng skeleton.
- [ ] API contract §11 (2 route tách) + isolated DB/Redis per-dev quyết định
- [ ] CachePort + event schema + registry metadata **đã proven qua slice UC-04** (Phase 0.5) rồi mới freeze
- [ ] Migration-chain owner + freeze-break runbook có sẵn
- [ ] → chuyển sang [Phase 0.5](phase-00b-walking-skeleton.md); tag `phase0-freeze` + fork branch SAU khi slice pass

## Depends on
- ✅ **CrewAI = 1.15.5** (chốt). Pin trong `requirements.txt`. Registry/event/tool-wrapper freeze theo API bản này. **Verify `pip show crewai` KHÔNG kéo LangChain** vào dependency graph (điều khoản §2 doc). Walking skeleton (Phase 0.5) xác nhận API thật khớp trước khi freeze.
