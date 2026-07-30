# Phase 01 — Conversation Memory Storage

## Context Links
- Plan: `plans/260730-customer-agent-memory-wireup/plan.md`
- Flow: `backend/flows/customer_flow.py`
- Models: `backend/database/models.py` (L358 `ChatMessage`, L343 `ChatSession`)
- Repo pattern: `backend/repositories/session_repository.py`, `backend/repositories/user_profile_repository.py`

## Overview
- Priority: P2 | Status: pending | Effort: 3h
- Persist every user + agent turn (with result merchant_ids) to `chat_messages`; load last N at flow entry. Backend-only, no UI change.

## Key Insights
- `chat_messages` columns fit the turn shape EXACTLY: `sender`('user'|'agent'), `text`, `trace_id`, `structured_payload_json` (JSONB for result_merchant_ids), `timestamp`, `session_id` FK. **No migration.**
- Repos here take a `Session` (caller owns lifecycle); tools open their own `SessionLocal`. Flow owns neither — flow helpers open `SessionLocal` inline (precedent: `_direct_nearby_results`).
- `session_id` may be None on first msg → persistence MUST no-op gracefully (can't write FK-less row). FE normally sends one.
- Write latency is off the critical path (after crew run) but MUST NOT block the SSE stream or raise into it.

## Requirements
- F1: After each turn, persist `{sender, text, trace_id, structured_payload={result_merchant_ids, query}}` keyed by session_id.
- F2: At flow entry, load last N=4 turns (most recent last) for prompt injection (consumed in Phase 02).
- F3: Never raise into the flow — persistence failure is logged, swallowed (observability only).
- F4: Idempotent enough for retries — each turn gets a fresh `message_id` (`new_id("msg")`).

## Architecture
```
ChatMessageRepository (NEW) — Session-scoped, pure DB ops
  + append_turn(session_id, sender, text, trace_id, payload) -> None
  + get_recent_turns(session_id, limit=4) -> list[dict]

Flow entry (search_restaurants + _stream):
  prior_turns = _load_recent_turns(session_id)   # opens own SessionLocal, None-safe
Flow exit (success):
  _persist_turns(session_id, trace_id, query, response)  # user msg + agent msg
```
`_load_recent_turns` / `_persist_turns` are module-level helpers in `customer_flow.py` opening their own `SessionLocal` (consistent with `_direct_nearby_results`).

## Related Code Files
- CREATE `backend/repositories/chat_message_repository.py` (~60 lines)
- MODIFY `backend/flows/customer_flow.py`:
  - `search_restaurants()` — load prior_turns at entry (pass to inputs, Phase 02 uses); persist 2 turns after response built (success + out-of-domain branches).
  - `search_restaurants_stream()` — same: load at entry; persist before terminal `run_finished` yield (success + OOD branches).
  - ADD module helpers `_load_recent_turns(session_id)`, `_persist_turns(session_id, trace_id, user_text, response)`.
- DELETE: none.

## Implementation Steps
1. Create `ChatMessageRepository`:
   - `append_turn`: insert `ChatMessage(message_id=new_id("msg"), session_id, sender, text, trace_id, structured_payload_json=payload)`. Commit. Skip silently if `session_id` is None.
   - `get_recent_turns`: `SELECT ... WHERE session_id=? ORDER BY timestamp DESC LIMIT ?` then reverse to chronological. Return `[{sender, text, payload, ts}]`. Empty list if no session/none found.
2. Add `_load_recent_turns(session_id)` in flow — opens `SessionLocal`, calls repo, closes. Returns `[]` on None/error.
3. Add `_persist_turns(session_id, trace_id, user_text, response)`:
   - User turn: `append_turn(sender="user", text=user_text, payload={"query": user_text})`.
   - Agent turn: `append_turn(sender="agent", text=response.answer, trace_id=trace_id, payload={"result_merchant_ids": [r["merchant_id"] for r in response.results if r.get("merchant_id")]})`.
   - Wrapped in try/except — log via existing event mechanism, never raise.
4. Wire into both entry points:
   - Call `_load_recent_turns` after `trace_id` set; store on local var (Phase 02 consumes via `_build_inputs`).
   - Call `_persist_turns(...)` in success path AND out-of-domain path (OOD still produces a real answer+intent). For stream: call it just before `yield {"event":"run_finished"...}`.
   - User msg for stream = `query`; for blocking = `query`.
5. Compile-check: `python -m py_compile backend/repositories/chat_message_repository.py backend/flows/customer_flow.py`.

## Todo List
- [ ] Create `chat_message_repository.py`
- [ ] Add `_load_recent_turns` + `_persist_turns` helpers
- [ ] Wire load+persist into `search_restaurants`
- [ ] Wire load+persist into `search_restaurants_stream` (pre-yield, non-blocking)
- [ ] Verify persistence errors never surface to SSE
- [ ] py_compile both files

## Success Criteria
- A 2-turn conversation writes 4 `chat_messages` rows (2 user + 2 agent) with correct `structured_payload_json.result_merchant_ids`.
- `get_recent_turns(session_id, 4)` returns them chronologically.
- Missing/None session_id → no-op, no exception, flow unaffected.
- `/chat/stream` TTFT unchanged (persistence is post-run, off-stream).

## Risk Assessment
- **R1 Write blocks stream**: mitigate — persist only after answer fully built, outside the token-yield loop; wrap in try/except.
- **R2 Partial turn on error**: user msg persists, agent msg may not — acceptable (honest partial history). Decision: write user msg at entry? NO — write both post-run to keep entry fast; an errored run simply persists nothing (cleaner than half-turns). Revisit if refinement quality needs the user side on crash.
- **R3 session_id None**: handled by no-op guard.

## Security Considerations
- `session_id`/`user_id` are FKs with CASCADE — no injection surface (SQLAlchemy params).
- `text` is user-supplied → stored as-is (no eval); already the case for agent_runs input_payload.

## Next Steps
- Feeds Phase 02 (prior_turns → prompt injection).
- Phase 05 validates end-to-end with these rows.
