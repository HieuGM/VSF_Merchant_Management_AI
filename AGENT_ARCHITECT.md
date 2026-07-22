# Agent Architecture - Merchant AI Platform

> Phiên bản rút gọn dành cho implementation và review.
> Nguồn contract đầy đủ: `docs/2026-07-21-merchant-ai-agent-complete-design.md`.
> Nếu hai tài liệu khác nhau, tài liệu đầy đủ luôn được ưu tiên.

## 1. Mục tiêu và phạm vi

Hệ thống cung cấp hai nhóm use case:

| Nhóm | Use case |
|---|---|
| Merchant Owner | Chẩn đoán nguyên nhân, đề xuất cải thiện, so sánh đối thủ |
| Customer | Tìm quán theo món, giá, khoảng cách, thời tiết và preference |
| Reviewer | Theo dõi request, agent, task, tool, evidence và lỗi theo trace |

Đây là kiến trúc đích hoàn chỉnh. Roadmap được chia theo feature, không chia theo
level agent đơn giản đến nâng cao.

## 2. Quyết định bắt buộc

- Backend: FastAPI, SQLAlchemy, Alembic.
- Runtime database: PostgreSQL 15; dữ liệu pipeline được import từ JSONL.
- Agent orchestration: Native CrewAI; không sử dụng LangChain service, tool hoặc
  orchestration.
- LLM: OpenAI-compatible API, cấu hình bằng environment variables.
- Cache: Redis chỉ giữ dữ liệu tạm; PostgreSQL là nguồn dữ liệu bền vững.
- Frontend: React/Vite, TailwindCSS, mobile-first.
- Vị trí: Browser Geolocation API; luôn cần quyền của người dùng.
- Thời tiết: Open-Meteo.
- Reverse geocode: Nominatim với cache và rate limit.
- Tìm quán gần: PostgreSQL Haversine trên catalog nội bộ.
- Map: backend tạo GeoJSON và Leafmap HTML; React nhúng bằng iframe.
- Route/ETA đường bộ: OSRM tùy chọn; fallback về khoảng cách đường chim bay.
- Google Places không thuộc scope hiện tại.
- Dữ liệu mocked/synthetic được phép trong demo nhưng phải khai báo source.

Các hard rule:

1. Agent không truy cập ORM hoặc database session.
2. Route không gọi repository trực tiếp.
3. Tool chỉ là typed adapter; business rule nằm trong service.
4. LLM không được tự ghi preference toàn cục.
5. Mọi kết luận Merchant Agent phải có evidence.
6. `overall_score` chỉ dùng nội bộ; API/tool/agent không được hiển thị score
   tổng hợp cho merchant hoặc customer.
7. `waiting_time` chỉ đo preparation time. Late delivery chỉ thuộc
   `delivery_quality`.

## 3. Kiến trúc tổng thể

~~~mermaid
flowchart TD
    UI[React UI / Chat / Preference Center] --> API[FastAPI Routes]
    API --> APP[Application Services]
    APP --> FLOW[CrewAI Flows]
    FLOW --> CREW[Customer Crew / Merchant Crew]
    CREW --> AGENT[CrewAI Agents]
    AGENT --> REG[Tool Registry]
    REG --> TOOL[Native CrewAI BaseTool]
    TOOL --> SERVICE[Domain Services]
    SERVICE --> REPO[Repositories]
    REPO --> PG[(PostgreSQL)]
    SERVICE --> CACHE[(Redis)]
    TOOL --> EXT[Open-Meteo / Nominatim / OSRM]
    FLOW --> TRACE[Event Listener / Agent Events]
    SERVICE --> GEO[GeoJSON / Leafmap]
~~~

Luồng request:

~~~text
HTTP request
  -> route validation
  -> application service
  -> load session/user context
  -> CrewAI Flow
  -> Crew coordinator
  -> specialist task
  -> registered tool
  -> domain service
  -> repository/provider
  -> structured result
  -> evidence validation
  -> persist chat/events/confirmed deltas
  -> API response hoặc SSE
~~~

Dependency direction:

~~~text
routes -> services -> flows/crews -> agents -> tools
       -> domain services -> repositories/providers -> PostgreSQL/Redis/external API
~~~

## 4. CrewAI design

CrewAI chịu trách nhiệm orchestration, prompt assembly, task handoff, delegation và
execution events. CrewAI không chứa business rule hoặc ORM query.

### Customer Discovery Crew

| Agent | Trách nhiệm | Tool |
|---|---|---|
| Customer Coordinator | Phân loại intent, delegate, merge output | get_user_profile, get_session_candidates |
| Restaurant Search | Chuẩn hóa constraint, tìm và rank merchant | merchant_search, nearby_merchant_search |
| Preference Reasoning | Kết hợp profile, session, weather; tạo delta candidate | get_user_profile, get_session_candidates, get_weather_context, propose_profile_delta |
| Customer Explanation | Giải thích lý do gợi ý | get_merchant_profile |

### Merchant Advisor Crew

| Agent | Trách nhiệm | Tool |
|---|---|---|
| Merchant Coordinator | Route diagnosis, recommendation, competitor analysis | get_merchant_profile |
| Profile Analyst | Đọc profile, xác định dimension yếu | get_merchant_profile, get_profile_evidence |
| Diagnosis | Sinh tối đa 5 nguyên nhân có evidence | get_merchant_profile, get_profile_evidence, diagnose_merchant |
| Recommendation | Sinh action theo dimension yếu và trend | get_merchant_profile, get_profile_evidence, get_trending_dishes, recommend_improvements |
| Competitor | So sánh merchant cùng cuisine và khu vực | nearby_merchant_search, compare_competitors |
| Evidence Verifier | Kiểm tra semantic grounding | get_profile_evidence |

Delegation:

- Chỉ coordinator được delegate.
- Tối đa một coordinator-to-specialist hop.
- Specialist có `allow_delegation=false`.
- Tool allow-list được registry enforce, không dựa riêng vào prompt.
- Specialist lỗi không bắt buộc phải làm hỏng toàn bộ request; coordinator có thể trả
  partial result kèm warning.

Evidence validation có hai lớp:

1. Structural guardrail trong `merchant_flow.py`: kiểm tra schema,
   `evidence_ref` tồn tại và số liệu khớp record. Claim lỗi bị loại.
2. Evidence Verifier Agent: kiểm tra evidence có thực sự hỗ trợ ý nghĩa và quan hệ
   của claim. Claim không đạt bị regenerate hoặc trả `insufficient_data`.

Mọi task trả Pydantic-compatible structured output. Free text chỉ dùng cho câu trả
lời cuối; không log hoặc trả hidden chain-of-thought.

## 5. Data, memory và cache

### Source of truth

- `data/profiles.jsonl`: nguồn chuẩn của generated dataset.
- PostgreSQL: nguồn chuẩn của API và agent sau import.
- Agent không đọc trực tiếp JSON/JSONL.

Merchant Profile có 8 scored dimensions:

~~~text
food_quality, image_quality, delivery_quality, packaging,
service, waiting_time, menu_diversity, price_level
~~~

Mỗi dimension bắt buộc có `score`, `basis` và
`evidence[]`. Năm descriptive attributes gồm customer segments, peak time,
competitors, trending dishes và operation KPIs; delivery stats là dữ liệu hỗ trợ
operation KPIs.

Runtime cần thêm hoặc mở rộng:

| Table | Mục đích |
|---|---|
| merchant_profiles | profile_json, schema_version, source_kind |
| preference_events | Audit candidate/confirmed/rejected/expired delta |
| interaction_events | Click, search, feedback và review signals |
| agent_runs | Một record cho mỗi Flow run |
| agent_events | Agent/task/tool/delegation events theo trace |
| chat_sessions | Context snapshot và last_trace_id |
| chat_messages | Structured payload và trace_id |

### Preference lifecycle

| Scope | Cách xử lý |
|---|---|
| session | Dùng trong phiên hiện tại |
| candidate_global | Hiển thị để người dùng xác nhận |
| confirmed_global | Chỉ ghi PostgreSQL sau thao tác Ghi nhớ |

Click, search và review history chỉ tạo observation/evidence. Allergy, dietary và
health preference luôn cần xác nhận. UI phải hỗ trợ:

~~~text
Ghi nhớ | Chỉ dùng phiên này | Bỏ qua
~~~

Preference Center hiển thị confirmed preference, session constraint, pending
candidate, nguồn evidence, edit và delete.

### Redis

| Key | TTL |
|---|---:|
| agent:session:{id}:context:v1 | 30 phút |
| agent:session:{id}:candidates:{hash} | 5 phút |
| agent:user:{id}:profile_snapshot:v1 | 15 phút |
| agent:weather:{lat}:{lng} | 10 phút |
| agent:geocode:{query_hash} | 24 giờ |
| agent:run:{trace_id} | 24 giờ |

Confirm/reject/edit/delete preference phải invalidate profile snapshot. Thay đổi
location, weather hoặc search constraint phải invalidate candidate cache.

## 6. Tool Registry

Mỗi tool khai báo name, version, description, input/output schema, allowed agents,
timeout, retry policy, cache policy, side-effect flag và source kind.

| Tool | Implementation |
|---|---|
| merchant_search | SQLAlchemy repository + search service |
| nearby_merchant_search | PostgreSQL Haversine |
| get_merchant_profile | Profile repository |
| get_profile_evidence | Evidence repository |
| get_trending_dishes | Profile cache/table |
| compare_competitors | Location/cuisine/profile service |
| diagnose_merchant | Deterministic profile/evidence service |
| recommend_improvements | Recommendation/trend services |
| get_user_profile | User profile repository |
| propose_profile_delta | Preference service, không persist |
| get_session_candidates | Redis adapter |
| get_weather_context | Open-Meteo adapter |
| reverse_geocode | Nominatim adapter |

Tool phải validate input trước khi gọi service/provider, trả structured output,
không tự thay đổi confirmed profile và dùng typed error.

## 7. API surface

| Endpoint | Mục đích |
|---|---|
| GET /health | Kiểm tra database, Redis và LLM config |
| GET /api/v1/merchants/search | Search/filter/radius merchant |
| GET /api/v1/merchants/{id}/profile | Profile theo dimension; loại overall_score |
| GET /api/v1/merchants/{id}/evidence/{type}/{evidence_id} | Evidence detail |
| POST /api/v1/agent/customer/chat | Customer Crew, JSON hoặc SSE |
| POST /api/v1/agent/merchant/chat | Merchant Crew |
| GET /api/v1/users/{id}/profile | Confirmed preference và pending delta |
| POST /api/v1/users/{id}/profile/deltas/{delta_id}/confirm | Confirm delta |
| POST /api/v1/users/{id}/profile/deltas/{delta_id}/reject | Reject delta |
| DELETE /api/v1/users/{id}/preferences/{field} | Xóa preference đã nhớ |
| POST /api/v1/users/{id}/events | Ghi interaction event |
| GET /api/v1/maps/merchants.geojson | Map data |
| GET /api/v1/users/{id}/sessions | Danh sách session |
| GET /api/v1/sessions/{session_id} | Session detail |
| GET /api/v1/agent/runs/{trace_id} | Development/admin trace |

Mọi agent response có `trace_id`. Server trả `X-Request-ID`.
Customer chat chỉ trả preference candidate; không trả một profile update đã tự ghi.
Merchant response liên kết diagnosis/recommendation với dimension và evidence refs.

Stable error codes:

~~~text
validation_error, unauthorized, forbidden, not_found, insufficient_data,
provider_error, timeout, conflict, internal_error
~~~

## 8. Backend layout

~~~text
backend/
  app/              FastAPI entrypoint
  core/             settings, errors, logging, tracing, dependencies
  models/           API/domain/Pydantic contracts
  database/         ORM connection, models, Alembic migrations
  providers/        Redis, Open-Meteo, Nominatim, OSRM adapters
  repositories/     PostgreSQL access only
  services/         deterministic business and application logic
  tools/            registry and CrewAI BaseTool wrappers
  agents/
    config/         agents.yaml, tasks.yaml
    customer/       Customer Discovery Crew
    merchant/       Merchant Advisor Crew
    listeners/      CrewAI event listener
  flows/            customer_flow.py, merchant_flow.py
  routes/           health, merchant, agent, user, event, map, trace
  tests/            unit, contract, integration, fixtures
~~~

## 9. Feature roadmap

| Feature | Phạm vi | Exit criteria |
|---|---|---|
| A - Foundation | FastAPI, settings, errors, DB/Redis, test harness | Health chạy; unit test không cần Docker |
| B - Contracts | Pydantic schemas, migrations, 5-10 hoặc 18 hero fixtures | Đủ 8 dimensions và evidence |
| C - Data/domain | Repositories, search, ranking, diagnosis, recommendation | Chỉ repository query ORM |
| D - Cache/context | CachePort, Redis/memory adapters, snapshots, invalidation | TTL và invalidation tests pass |
| E - Preferences | Event ingestion, delta candidate, confirm/reject/delete, UI | Không signal nào tự ghi global profile |
| F - Tools/providers | Registry, BaseTool, weather/geocode/map/routing | Tool typed, provider replaceable |
| G - Customer Agent | Customer Crew, chat/SSE, UC-04/UC-05 tests | Search có lý do; delta chưa confirmed |
| H - Merchant Agent | Diagnosis, recommendation, competitor, evidence 2 lớp | UC-01 đến UC-03 có evidence |
| I - Coordination | One-hop delegation, timeout, partial result | Allow-list và delegation traceable |
| J - Observability | Event listener, run/tool events, trace inspection | Theo dõi được request đến response |
| K - Map/UI | Leafmap, result sync, weather, Preference Center | Map/list cùng khoảng cách và selection |
| L - Evaluation | Fixed cases, metrics, resettable seed, E2E | 5 use case pass với demo data |

Không bắt đầu feature bằng code ngay. Trước mỗi feature:

1. Tạo plan với task ID, files, tests và contract changes.
2. Reviewer duyệt plan.
3. Implement task đã duyệt.
4. Cập nhật `docs/superpowers/progress/FEATURE-<letter>.md` sau từng task.
5. Chạy test và ghi kết quả.
6. Reviewer accept trước feature phụ thuộc.

## 10. Testing và Definition of Done

Test bắt buộc:

- Unit: Haversine, profile validation, delta/conflict rule, cache, provider
  normalization, tool validation, structural evidence guardrail.
- Contract: route, tool, CrewAI output, evidence và SSE events.
- Integration: PostgreSQL, Redis invalidation, mocked provider, Crew với fake tools.
- E2E: 5 product use cases, preference confirm/reject, map và trace.

Demo hoàn thành khi:

- PostgreSQL và Redis khởi động cùng backend.
- Customer search chạy với dataset nhỏ.
- Location/weather có permission hoặc manual override.
- Preference toàn cục luôn cần xác nhận và có audit.
- Leafmap render đúng GeoJSON.
- Merchant profile đủ 8 dimension và evidence.
- Diagnosis, recommendation và competitor comparison qua evidence validation hai lớp.
- Delegation chỉ đi qua coordinator.
- Trace chứa agent/task/tool event và không lộ secret.
- Demo seed có thể reset và toàn bộ E2E pass.

## 11. Open decisions

Hai quyết định chưa chặn Feature A-E nhưng phải đóng trước feature liên quan:

1. Trước Feature F/G/H: chốt phiên bản CrewAI standalone không kéo LangChain vào
   dependency graph.
2. Trước Feature B/H: chọn dùng đủ 18 hero merchant hiện có hay subset 5-10 merchant
   cho fixture demo.

Thay đổi API, database, profile schema, tool schema hoặc agent output contract phải
quay lại design review trước khi implement.

## 12. Tài liệu tham chiếu

- `docs/2026-07-21-merchant-ai-agent-complete-design.md`: contract đầy đủ.
- `docs/data-pipeline-and-dictionary.md`: data pipeline và profile schema.
- `docs/scoring-methodology.md`: scoring rules và quy tắc overall_score.
- `docs/prd-merchant-management-ai-v2.md`: product requirements.

