# Cấu trúc dự án & Ranh giới sở hữu 2 Dev

> Tài liệu handoff cho mô hình **2 dev full-stack code song song** (Customer vs Merchant vertical).
> Nguồn contract: `docs/2026-07-21-merchant-ai-agent-complete-design.md` · Kế hoạch chia việc: `plans/260722-0916-two-dev-parallel-split/`.
> Trạng thái: **Phase 0 (skeleton) xong** — chưa tag `phase0-freeze` (freeze sau Phase 0.5).

---

## 1. Mô hình chia việc

| | Dev A — Customer Discovery | Dev B — Merchant Advisor |
|---|---|---|
| Domain | Tìm quán, preference, map, weather, chat khách hàng | Profile 8 chiều, chẩn đoán, gợi ý, đối thủ, evidence, observability |
| Backend glob | `agents/customer/*`, `tools/customer/*`, các file customer bên dưới | `agents/merchant/*`, `agents/listeners/*`, `tools/merchant/*`, các file merchant |
| Frontend glob | `frontend/src/customer/*` | `frontend/src/merchant/*` |

**Nguyên tắc vàng:** xung đột chỉ xảy ra ở **file dùng chung (FROZEN)**. Mọi file frozen đã dựng xong ở Phase 0. Sau freeze, mỗi dev sở hữu glob riêng và **giao tiếp qua interface/contract đã đóng băng** (Pydantic models, CachePort, tool registry, event schema, API contract) — depend qua interface, KHÔNG sửa file chung.

**3 loại file:**
- 🔒 **FROZEN (dùng chung)** — không sửa trên feature branch. Đổi phải qua "cửa hẹp" (mục 4).
- 🅰️ **Dev A** — chỉ Dev A sửa.
- 🅱️ **Dev B** — chỉ Dev B sửa.

---

## 2. Cây thư mục Backend (`backend/`)

```
backend/
├── app/
│   ├── main.py                 🔒 App factory. Include SẴN 9 router. KHÔNG sửa file này.
│   └── extensions.py           🔒 "Seam" mở rộng (H5): đăng ký startup hook / middleware /
│                                   exception handler / router phụ → gắn thêm mà không đụng main.py.
│                                   Chỉ contract owner sửa.
├── core/                       🔒 Toàn bộ core = FROZEN.
│   ├── settings.py                Config (env, DB url, CORS origins, cache backend, LLM).
│   ├── errors.py                  AppError + mã lỗi ổn định + error envelope (§11.10).
│   ├── logging.py                 Cấu hình log + inject request_id.
│   ├── tracing.py                 Sinh & lưu request/trace ID (contextvar).
│   ├── cache.py                   CachePort (interface) + CacheKeys (§8.2) + TTL.
│   └── dependencies.py            FastAPI deps: get_db_session / get_cache / get_settings.
├── models/                     🔒 Pydantic contract dùng chung (FROZEN).
│   ├── api.py                     Envelope, Page, Health, Location.
│   ├── profile.py                 Merchant Profile + search item (§6.4). 8 chiều điểm.
│   ├── agent.py                   Chat req/resp 2 domain + event schema CrewAI (§6.2, H8).
│   ├── preference.py              User profile + preference event / delta (§6.5, §6.6, §7.1).
│   └── events.py                  Interaction event (§11.7).
├── database/
│   ├── connection.py           🔒 Engine + SessionLocal + Base.
│   └── models.py               🔒 SQLAlchemy tables (cả 2 domain). Đổi schema qua migration owner.
├── migrations/                 🔒 Alembic. **1 migration chain duy nhất** (cấm tạo head song song).
│   └── versions/
│       ├── 026b4a8e16d0_*.py      Schema gốc (10 bảng catalog).
│       └── a1b2c3d4e5f6_*.py      §6.2 runtime: preference/interaction/agent_runs/agent_events + index.
├── providers/
│   ├── cache/
│   │   ├── memory_adapter.py   🔒 In-memory CachePort (test không cần Redis, H4).
│   │   └── redis_adapter.py    🅰️ (Dev A tạo ở D-02) — thêm nhánh Redis trong dependencies.get_cache.
│   ├── weather/                🅰️ Open-Meteo adapter (Dev A).
│   ├── geocode/                🅰️ Nominatim adapter (Dev A).
│   └── routing/                🅰️ OSRM adapter (Dev A, optional).
├── tools/
│   ├── registry.py             🔒 ToolRegistry + ToolSpec (§9.1) + auto_discover per-package.
│   ├── allow_list.py           🔒 Bảng agent→tool (§5.4) = DATA frozen (C1). Runtime enforce.
│   ├── shared/
│   │   └── shared_readonly_tools.py 🔒 get_merchant_profile, get_trending_dishes (cả 2 domain xài).
│   ├── customer/               🅰️ Tool của Dev A (merchant_search, nearby, user_profile, weather...).
│   └── merchant/               🅱️ Tool của Dev B (merchant_profile, evidence, competitor, trend...).
├── agents/
│   ├── customer/               🅰️ Crew khách hàng + config/{agents,tasks}.yaml.
│   ├── merchant/               🅱️ Crew merchant + config/{agents,tasks}.yaml.
│   └── listeners/
│       └── crewai_listener.py  🔒 Reference listener + emit helper (H8). Dev B viết listener thật.
├── repositories/               Chia theo domain (xem bảng mục 3). Mỗi dev tạo file của mình.
├── services/                   Chia theo domain (xem bảng mục 3).
├── flows/
│   ├── customer_flow.py        🅰️ Flow Customer (Dev A tạo).
│   └── merchant_flow.py        🅱️ Flow Merchant (Dev B tạo).
├── routes/
│   ├── health.py               🔒 GET /health.
│   ├── stub_helpers.py         🔒 Helper trả 501 cho stub.
│   ├── merchant_search_routes.py   🅰️ §11.2 (Dev A).
│   ├── customer_agent_routes.py    🅰️ §11.4 (Dev A).
│   ├── user_routes.py              🅰️ §11.6/§11.9 (Dev A).
│   ├── event_routes.py             🅰️ §11.7 (Dev A).
│   ├── map_routes.py               🅰️ §11.8 (Dev A).
│   ├── merchant_profile_routes.py  🅱️ §11.3 (Dev B).
│   ├── merchant_agent_routes.py    🅱️ §11.5 (Dev B).
│   └── trace_routes.py             🅱️ §11.9 trace (Dev B).
├── fixtures/
│   └── merchant_profiles.json  🔒 1 profile mẫu tối thiểu (để shared tool chạy được).
├── tests/                      Mỗi dev thêm test của mình; test/contract + test/unit là chung.
├── requirements.txt            🔒 Đổi dependency qua contract owner (đã pin crewai==1.15.5).
└── pytest.ini                  🔒 Cấu hình test (pythonpath=.).
```

> **Router**: mỗi dev **chỉ sửa FILE ROUTER của mình**, KHÔNG sửa `app/main.py` (đã include sẵn stub 501). Thêm route con thì thêm trong file router của domain, hoặc đăng ký router phụ qua `app/extensions.register_router()`.

---

## 3. Bảng sở hữu chi tiết (repositories / services / providers)

| Layer | 🅰️ Dev A (Customer) | 🅱️ Dev B (Merchant) | 🔒 Shared frozen |
|---|---|---|---|
| repositories | merchant, user_profile, session, preference_event, interaction_event | merchant_profile, evidence | — |
| services | merchant_search, customer_context, preference, session, weather, geocode, map | merchant_profile, evidence, recommendation, competitor, agent_run | — |
| providers | weather/, geocode/, routing/, cache/redis_adapter | (dùng CachePort của A qua interface) | cache/memory_adapter |
| tools | tools/customer/* | tools/merchant/* | tools/shared/*, registry, allow_list |
| agents | agents/customer/* | agents/merchant/*, agents/listeners/* | — |
| flows | flows/customer_flow.py | flows/merchant_flow.py | — |
| routes | search, customer_agent, user, event, map | merchant_profile, merchant_agent, trace | health, stub_helpers |
| frontend | src/customer/* | src/merchant/* | src/shared/*, App.tsx (router shell) |

---

## 4. Quy tắc truy cập file FROZEN 🔒 (cửa hẹp — plan §[C2])

Freeze **KHÔNG phải bất biến**, mà là **đổi phải qua cửa hẹp**:

1. Mọi thay đổi file frozen (models, migration, event schema, tool schema, CachePort, main.py, extensions.py, allow_list, registry, requirements) = **PR nhỏ serialize vào `develop`**, KHÔNG commit thẳng vào feature branch.
2. **1 owner duyệt**: migration-chain owner (schema/migration) hoặc contract owner (Pydantic/tool). Version-bump + announce.
3. Cả 2 dev **rebase lên `develop` trong ngày**.
4. **Cấm 2 dev tự tạo Alembic revision song song** → tránh 2-head. Lỡ có thì Phase 3 `alembic merge heads`.

**Đổi allow-list / tool schema:** sửa `tools/allow_list.py` (nguồn chân lý §5.4) → test `tests/contract/test_allow_list_sync.py` bắt buộc yaml khớp; cập nhật cả `agents/*/config/agents.yaml`.

---

## 5. Isolation DB/Redis (plan §[H6])

Mỗi dev DB + Redis **riêng** (không clobber data, không collision key §8.2):

```bash
# Dev A: Postgres :5433, Redis :6380
docker compose -f docker-compose.dev-a.yml up -d
# Dev B: Postgres :5434, Redis :6381
docker compose -f docker-compose.dev-b.yml up -d
```

Seed **additive/idempotent**, KHÔNG truncate catalog chung. Owner seed = migration-chain owner.

---

## 6. Frontend (`frontend/`)

```
frontend/src/
├── main.tsx            🔒 Entry + BrowserRouter.
├── App.tsx             🔒 Router shell: / → /customer, /merchant. Không tái cấu trúc switch top-level.
├── index.css           🔒 Tailwind base.
├── shared/
│   ├── layout.tsx      🔒 App shell (mobile-first, §4).
│   └── api-client.ts   🔒 apiFetch + xử lý error envelope (§11.10). Thêm helper endpoint trong domain.
├── customer/           🅰️ Toàn bộ UI khách hàng (Dev A).
└── merchant/           🅱️ Toàn bộ UI cửa hàng (Dev B).
```

---

## 7. Chạy & kiểm thử

```bash
# Backend
cd backend
pip install -r requirements.txt
PYTHONPATH=. alembic upgrade head          # cần Postgres đang chạy
uvicorn app.main:app --reload              # http://localhost:8000  · /health · /docs
python -m pytest                           # 15 pass / 2 skip (skip = integration cần Docker)

# Frontend
cd frontend
npm install
npm run dev                                # http://localhost:5173 (proxy /api → :8000)
npm run build                              # tsc --noEmit + vite build
```

---

## 8. Việc cần làm TRƯỚC khi tag `phase0-freeze`

- [ ] Phase 0.5 walking skeleton (UC-04 search end-to-end) chứng minh pattern cache/tool/route/event/migration ĐÚNG.
- [ ] Verify `pip install crewai==1.15.5` **KHÔNG kéo LangChain** vào dependency graph (§2) — check clean-env.
- [ ] Freeze-break runbook + migration-chain owner sẵn sàng (đã ghi ở mục 4).
