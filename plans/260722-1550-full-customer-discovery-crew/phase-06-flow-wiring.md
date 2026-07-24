# Phase 06 — Wire customer_flow → Crew.kickoff + persist runs/events

**Priority:** P1 · **Status:** ✅ (2026-07-23) · **Depends:** P05 (crew)

## Overview
Thay đoạn "Phase 0b: gọi tool trực tiếp" trong `flows/customer_flow.py` bằng
`build_customer_crew(inputs).kickoff()`. GIỮ event emission. Persist `agent_runs` + `agent_events`
qua listener kết nối CrewAI event bus.

## Key insights
- `customer_flow.py` hiện: tạo `trace_id`, emit run_started/tool_finished/run_finished qua
  `RecordingListener` (in-memory), gọi `merchant_search` trực tiếp. → thay bằng crew.
- `agents/listeners/crewai_listener.py` có `build_event_record` + `RecordingListener` (in-memory) +
  `assert_emittable`. Cần **listener persist**: subclass CrewAI `BaseEventListener` → nhận event bus →
  map sang `AgentEventRecord` → ghi `agent_events`; đồng thời ghi `agent_runs` (1 row/run).
- DB models sẵn: `AgentRun`, `AgentEvent` (`database/models.py`). Cần repo ghi.
- CrewAI event bus (1.15.5): `crewai.utilities.events` — listener subscribe các event
  (agent/task/tool start/finish). Verify tên event bản 1.15.5.

## Requirements
1. `agent_run_repository.py`: `create_run(AgentRunRecord)`, `finish_run(trace_id, status, ...)`,
   `add_event(AgentEventRecord)`. Tự quản session.
   > ⚠️ Ownership: vốn Dev B (`agent_run_service`). Owner gộp Track A nên làm; flag Phase 3 reconcile.
2. Persisting listener (`agents/listeners/persisting_listener.py`): subclass BaseEventListener,
   map CrewAI events → `build_event_record` → `add_event`. Registers vào crewbus lúc flow chạy
   (H5 extension seam — không sửa main.py).
3. `customer_flow.search_restaurants(...)` (và/hoặc `chat(...)`):
   - tạo trace_id, `create_run` (status=running)
   - build inputs từ params (query/cuisine/city/budget/lat/lng/user_id/session_id)
   - `crew.kickoff(inputs=...)`
   - map crew output → `CustomerChatResponse` (models/agent.py)
   - `finish_run(status=ok|error)`; giữ try/except emit error như hiện tại
4. Route `customer_agent_routes.py` (stub 501) → wire vào flow (nếu muốn end-to-end qua HTTP).

## Related files
- CREATE: `backend/repositories/agent_run_repository.py`
- CREATE: `backend/agents/listeners/persisting_listener.py`
- EDIT: `backend/flows/customer_flow.py` (thay direct-call bằng crew.kickoff)
- EDIT (optional): `backend/routes/customer_agent_routes.py` (bỏ 501, gọi flow)

## Implementation steps
1. agent_run_repository (create/finish run, add_event) + map Pydantic↔ORM (JSONB fields `*_json`).
2. persisting_listener subscribe event bus → persist; giữ `assert_emittable` guard.
3. Refactor customer_flow: crew.kickoff, run lifecycle, output→CustomerChatResponse.
4. (optional) wire customer_agent_routes.
5. Verify: chạy flow với fake LLM (mock kickoff) → agent_runs +1, agent_events > 0, trace_id khớp.

## Todo
- [ ] agent_run_repository (runs + events persist)
- [ ] persisting_listener (CrewAI event bus → agent_events)
- [ ] customer_flow dùng crew.kickoff, giữ trace_id + run lifecycle
- [ ] output → CustomerChatResponse
- [ ] (optional) customer_agent_routes wired

## Success criteria
- 1 lần chạy flow → 1 row `agent_runs` (status ok/error) + ≥1 `agent_events`, cùng `trace_id`.
- Event có đủ REQUIRED_EMIT_FIELDS (assert_emittable pass).
- Lỗi trong crew → run status=error, không crash process.
- allow-list vẫn chặn: agent không gọi được tool ngoài phạm vi (kiểm ở P07).

## Risks
- CrewAI event bus API 1.15.5 khác tài liệu mới → verify tên/subscribe (`ck:docs-seeker`).
- Mapping token_usage từ crew output → `token_usage_json` (optional, để {} nếu chưa có).
- Ownership overlap listener/agent_run (flag).

## Next
→ Phase 07 tests toàn bộ chuỗi.
