# Phase 07 — Tests (unit + contract + integration)

**Priority:** P1 · **Status:** ✅ (53 passed / 0 failed / 0 skipped, 2026-07-23) · **Depends:** P06

## Overview
Kiểm chứng toàn chuỗi + guardrails. LLM là non-deterministic → test theo **schema/structure +
allow-list + persistence**, KHÔNG assert nội dung LLM.

## Test matrix
| # | Test | Loại | Assert |
|---|---|---|---|
| 1 | adapter wrap tool | unit | `tools_for_crew_agent("restaurant_search")` = 2 BaseTool; unknown role = [] |
| 2 | allow-list enforcement | unit | agent chỉ nhận tool trong allow_list.py; tool ngoài → không có mặt |
| 3 | weather cache hit/miss | unit | gọi 2 lần → 1 HTTP call (monkeypatch httpx); offline → `weather:null` |
| 4 | propose_profile_delta no persist | unit | sau gọi, `preference_events` count không đổi |
| 5 | get_user_profile | unit/integration | `user_demo` → profile; unknown → NotFoundError |
| 6 | yaml ↔ allow-list sync | contract | (test hiện có) allowed_tools yaml == allow_list.py |
| 7 | event emit đủ field | contract | `assert_emittable` pass mọi event flow phát (H8) |
| 8 | crew builds w/ fake LLM | unit | `build_customer_crew` không cần network/key |
| 8b | per-agent LLM tier | unit | coordinator+search → model chứa `llama-3.3-70b`; reasoning+explanation → `llama-3.1-8b`; provider `nvidia_nim` |
| 9 | flow persists run+events | integration | 1 run row + ≥1 event, cùng trace_id (fake/mock kickoff) |
| 10 | no LangChain in deps | contract | `pip show crewai` / import guard — LangChain absent |
| 11 | agents get no DB session | unit | tool tự mở session; agent config không truyền session |

## Related files
- CREATE: `backend/tests/unit/test_tool_adapter.py`, `test_customer_tools.py`, `test_weather_provider.py`
- CREATE: `backend/tests/integration/test_customer_flow_crew.py`
- EXTEND: `backend/tests/contract/*` (yaml sync, emit fields, no-langchain)

## Implementation steps
1. Fake LLM fixture (monkeypatch `crewai.LLM` hoặc inject `llm_override`) — mọi crew test dùng.
2. Monkeypatch httpx cho weather (không gọi mạng thật trong CI).
3. Integration dùng test DB (Postgres) hoặc transaction rollback fixture; seed user_demo.
4. Chạy `pytest` (venv conda `ai_restaurant`), coverage ≥ mức Phase 0 (~78% routes).
5. Fix tới khi xanh hết — KHÔNG skip test để pass build.

## Todo
- [x] Fake LLM + httpx monkeypatch fixtures
- [x] 11 test theo matrix
- [x] Integration flow persist run/events
- [x] no-LangChain contract test
- [x] Toàn bộ pytest xanh, coverage không giảm

## Success criteria (GATE Phase 0.5 đạt)
- UC-04 chạy qua CrewAI Crew thật (fake LLM ở test, real LLM khi có key).
- agent_runs + agent_events persisted, trace_id đúng.
- allow-list chặn tool trái phép (test 2).
- weather cache hit/miss quan sát được (test 3).
- No LangChain (test 10).
- Tất cả test pass.

## Risks
- Postgres cho integration test cần chạy (container `gsm_merchant_postgres`). Nếu CI không có →
  đánh dấu integration `@pytest.mark.integration`, unit vẫn chạy độc lập.
- Non-determinism LLM: tuyệt đối không assert text; chỉ structure/side-effect.

## Next
→ Delegate `tester` chạy full suite → `code-reviewer` → update `docs/development-roadmap.md`
(Phase 0.5 → thực chất hoàn tất Track A tools) + `project-changelog.md`.
