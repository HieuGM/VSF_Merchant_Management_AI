# Phase 05 — Integration Validation + FE Wire

## Context Links
- Depends: Phases 01–04
- Ground truth: `ground_truth_customer.json` (root)
- FE: `frontend/src/customer/hooks/use-customer-chat.ts`, `use-customer-identity.ts`, `pages/customer-chat.tsx`
- Docs: `docs/development-roadmap.md`, `docs/project-changelog.md`

## Overview
- Priority: P2 | Status: pending | Effort: 3h
- Close the loop: FE sends stable `session_id` + `weather_override`; confirm wires through; end-to-end ground-truth cases pass; docs updated.

## Key Insights
- FE already generates a `sessionId` via `use-customer-identity` and passes it — verify it stays STABLE across turns within one conversation (required for Phase 01/02 to work). "New chat" resets it (correct).
- `weather_override` is currently never sent by FE — decide: FE auto-detects rain? OUT OF SCOPE per YAGNI. Wire only the passthrough (so the field is usable by tests/future). Document that FE omits it today by design.
- The `use-customer-chat` `ChatMessage` type already carries `suggestions`; confirm callback (Phase 04) needs a home — keep it local to `SuggestionRow` state to avoid bloating the chat state machine.
- `ground_truth_customer.json` is the authoritative assertion set — drive validation from it, don't hand-roll cases.

## Requirements
- F1: `/chat` + `/chat/stream` accept and forward `weather_override` + stable `session_id` end-to-end (FE→DB).
- F2: All targeted ground-truth cases pass (multiturn + pref/weather sets below).
- F3: Existing single-turn behavior + propose-only invariant + TTFT regression-checked.
- F4: Docs updated (roadmap status + changelog entries for the 4 goals).

## Ground-Truth Cases to Validate (from `ground_truth_customer.json`)
- Multiturn: TC-09 ("quán đầu tiên"), TC-10 ("rẻ hơn"), TC-11 (session_expired→empty), TC-30 (pagination exclude), TC-41 (ordinal), TC-47 ("món đó"→dish).
- Pref/weather: TC-06 (rain + profile), TC-29 (explicit override), TC-48 (persist "ăn chay trường"), TC-49 (cross-turn allergy conflict).

## Architecture
```
Integration test (NEW): backend/tests/integration/test_customer_memory_wireup.py
  - fixtures: seed user_profiles + 2-turn chat_messages history
  - asserts: prior_turns injected, anaphora resolved, weather threaded, confirm persists
FE smoke (manual or e2e-lite):
  - multiturn refinement; confirm button → saved state; reload → profile retained
```

## Related Code Files
- CREATE `backend/tests/integration/test_customer_memory_wireup.py` (~180 lines)
- MODIFY `frontend/src/customer/hooks/use-customer-chat.ts`: ensure `session_id` reused per conversation (verify, likely no change); pass through `weather_override` field if/when available (leave `null` by default).
- MODIFY `frontend/src/customer/api/customer-agent-client.ts`: `CustomerChatRequest` add `weather_override?: Record<string, unknown> | null` (optional, default null) — keeps TS honest with backend.
- MODIFY `docs/development-roadmap.md` + `docs/project-changelog.md`.
- DELETE: none.

## Implementation Steps
1. Write integration test with a fake-LLM crew (inject via `crew=` param for blocking path; assert `_build_inputs` contains `prior_context` non-empty after seeding history).
2. Seed a 2-turn `chat_messages` history for a session; call flow; assert search_task input + explanation messages contain the prior merchant names + the exclude rule text.
3. Assert `weather_override={"is_rain":true}` reaches `_build_inputs["weather_hint"]` non-empty and `_build_explanation_messages` sig_bits.
4. Assert confirm service: confirm a delta → `user_profiles` changed + `preference_events` row; idempotent repeat; reject → event only.
5. Re-run `test_customer_context_tools_db.py` (propose-only) + existing customer flow tests — must stay green.
6. Manual FE smoke (or playwright if present): two-turn chat resolves "quán đầu tiên"; Lưu button persists; reload shows retained preference.
7. Verify `/chat/stream` still streams token-by-token (TTFT unchanged) with the new inputs.
8. Update roadmap (mark memory wire-up phase) + changelog (4 entries: conversation memory, anaphora, weather, confirm).

## Todo List
- [ ] Integration test: prior_turns injection
- [ ] Integration test: anaphora/exclude prompt presence
- [ ] Integration test: weather threading
- [ ] Integration test: confirm + reject + idempotency
- [ ] Regression: propose-only + existing flow tests green
- [ ] FE: session_id stability check + weather_override TS field
- [ ] FE smoke: multiturn + confirm + reload
- [ ] Stream TTFT spot-check
- [ ] Docs: roadmap + changelog

## Success Criteria
- All 10 targeted TCs pass (asserted, not eyeballed).
- No regression in single-turn / propose-only / streaming.
- Confirmed preference survives a page reload (DB-backed).
- Docs reflect the 4 delivered goals.

## Risk Assessment
- **R1 LLM nondeterminism in multiturn cases**: tests should assert WIRING (prompt content, persistence, tool args) not free-text answer equality — deterministic + flake-free. Reserve answer-quality for manual smoke.
- **R2 session_id rotates mid-conversation** (FE bug): surfaces as "no memory"; fix in `use-customer-identity` if found — small.
- **R3 Test DB fixtures heavy**: reuse existing conftest pattern from `test_customer_context_tools_db.py`.

## Security Considerations
- No new surface beyond what 01–04 add; integration tests must not seed real PII.

## Next Steps
- Hand off to `code-reviewer` then `tester` per primary-workflow.
- Future enhancements (out of scope): FE weather auto-detect, auth on user routes, `exclude_merchant_ids` tool arg if TC-30 prompt-only proves flaky, Preference Center GET from confirmed profile.
