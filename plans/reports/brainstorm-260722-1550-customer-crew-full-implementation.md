# Brainstorm — Full Customer Discovery Crew (tools + multi-agent wiring)

> Date: 2026-07-22 15:50 · Branch: develop · Context: `docs/2026-07-21-merchant-ai-agent-complete-design.md` §5.2/§5.4 · Plan: `plans/260722-0916-two-dev-parallel-split/`

## Problem statement
User đã hiểu CrewAI, hỏi bước tiếp theo. Quyết định: **viết bộ tools cho Customer agents + wire full multi-agent Customer Crew end-to-end**, owner làm dev chính Track A, assistant implement sau brainstorm.

## Current state
- `flows/customer_flow.py` gọi thẳng `merchant_search` tool — **CHƯA dùng CrewAI** (comment "Phase 0b: no CrewAI yet").
- Gate fork Phase 0.5 yêu cầu: *"agent runs + events emitted with trace_id"* → chưa đạt.
- Đã có: `merchant_search`, `nearby_merchant_search` (real, registered), `get_merchant_profile` (shared fixture), registry + allow-list + event schema + reference listener.

## Customer Crew tool inventory (design §5.4)
| Agent | Tools | Status |
|---|---|---|
| Customer Coordinator (delegate 1 hop) | get_user_profile, get_session_candidates | ❌ new |
| Restaurant Search (no delegation) | merchant_search, nearby_merchant_search | ✅ done |
| Preference Reasoning (no delegation) | get_user_profile, get_session_candidates, get_weather_context, propose_profile_delta | ❌ new |
| Customer Explanation (no delegation) | get_merchant_profile | ✅ fixture |

**4 tool mới:** `get_user_profile`, `get_session_candidates`, `get_weather_context`, `propose_profile_delta`.

## Decisions (locked)
1. **Scope:** đi thẳng full Customer Crew (4 tool + adapter + 4 agent + tasks + flow). Chấp nhận hoãn fork + front-load risk. Owner = dev chính Track A.
2. **Weather:** tích hợp **API thật** (khuyến nghị **Open-Meteo** — free, KHÔNG cần API key → tránh secret management; nếu cần forecast/độ chính xác cao hơn thì OpenWeatherMap + key). Cache qua CachePort + TTL key §8.2.
3. **Executor:** assistant implement sau brainstorm.

## Critical architectural insight
**Trái tim của "wire CrewAI" KHÔNG phải viết thêm tool — mà là adapter Registry→CrewAI `BaseTool`.**
- Tool hiện là plain function + `ToolSpec` (framework-agnostic — GIỮ nguyên pattern này, DRY).
- CrewAI Agent cần `BaseTool`. Cần **1 adapter mỏng** bọc `(ToolSpec, callable)` → `crewai.BaseTool`, **enforce allow-list runtime** (prompt không thể xin tool ngoài registry).
- Adapter là **điểm coupling DUY NHẤT** với CrewAI → tool + service vẫn swappable/test được không cần CrewAI.

## Recommended build order (dependency-correct)
1. **Adapter** `agents/tool_adapter.py` — ToolSpec+callable → CrewAI BaseTool + allow-list guard. (core enabler)
2. **Data/providers** cho 4 tool: `user_profile_repository`, `session_repository` (candidates), preference-delta logic (no persist), **weather provider** (Open-Meteo client + CachePort cache).
3. **Tool functions + ToolSpec register** trong `tools/customer/` + update `allow_list.py` + sync yaml (contract test đã có).
4. **Agents config** `agents/customer/config/agents.yaml`+`tasks.yaml`: 4 agent (coordinator có delegation 1-hop; 3 specialist tắt delegation) — role/goal/backstory/tools/max_iter/timeout/output schema (§5.5).
5. **Crew assembly** `agents/customer/*` — build Crew, gắn tool qua adapter.
6. **`customer_flow.py`** — thay direct-call bằng `Crew.kickoff()`, GIỮ event emission; persist `agent_runs` + `agent_events`.
7. **Tests** — crew loads, allow-list chặn tool trái phép, events emit đủ field, weather cache hit/miss, agents KHÔNG nhận DB session.

## Guardrails (design constraints — MUST)
- Agents **không bao giờ** nhận SQLAlchemy session; tool tự mở/đóng session (pattern `merchant_tools.py`).
- `propose_profile_delta` **chỉ trả proposal**, không ghi `preference_events` (persist = flow/route khác).
- Delegation: chỉ Coordinator, tối đa 1 hop; specialist tắt.
- Allow-list ↔ yaml phải sync (contract test hiện có).
- No LangChain kéo vào (verify dep tree — carry-over Phase 0.5).

## Risks
- **R1 Fork hoãn:** làm trọn Track A trước fork → 2-dev parallel gần như bỏ. Cố ý, chấp nhận.
- **R2 LLM cost/latency:** multi-agent + delegation = nhiều LLM call. Đặt max_iter/timeout chặt; cân nhắc cache.
- **R3 Weather external:** Open-Meteo downtime → tool phải degrade gracefully (trả `weather: null`, không fail cả crew).
- **R4 Non-determinism:** LLM output khó test → assert structure/schema, không assert nội dung.

## Success metrics (đạt GATE Phase 0.5 + hơn)
- UC-04 chạy qua **CrewAI Crew thật**: query → flow → crew → agents → tools → DB → results.
- `agent_runs` + `agent_events` persisted với `trace_id`.
- Allow-list chặn được tool ngoài phạm vi agent.
- Weather cache hit/miss quan sát được qua CachePort.
- Tests pass, no LangChain in dep tree.

## Next steps
1. `/plan` tạo phase breakdown chi tiết (7 bước trên).
2. Implement theo thứ tự dependency.
3. tester → code-reviewer.
4. Update roadmap: Phase 0.5 → thực chất nuốt Track A tools.

## Unresolved questions
1. **[BLOCKER] LLM provider cho CrewAI agents?** Full crew cần 1 LLM configured (API key). Khuyến nghị **Anthropic Claude** (mặc định model Claude mới nhất). Cần chốt + set key trước khi crew chạy thật.
2. **Geocode tool** (`geocode_tool.py` trong ownership map) — §5.4 không liệt kê là direct tool của customer agent; coi là provider hỗ trợ weather/nearby hay defer? (đề xuất: defer, chỉ làm khi weather cần geocode city→lat/lng).
3. Có seed `user_demo` + session fixture chưa để test `get_user_profile`/`get_session_candidates`? (Phase 0.5 deliverable #2 seed chưa làm — cần làm kèm).
