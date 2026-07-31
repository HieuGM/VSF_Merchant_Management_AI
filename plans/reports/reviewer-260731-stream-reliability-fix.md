# Code Review — Stream Reliability Fix (`_stream_explanation_tokens`)

**Reviewer:** code-reviewer | **Date:** 2026-07-31 | **Verdict:** APPROVE with 1 high-pri follow-up

## Scope
- `backend/flows/customer_flow.py` — `_stream_explanation_tokens` (L1362-1430), + caller fallback L514-539
- `backend/tests/unit/test_customer_crew.py` — 4 new tests + 2 fakes (`_ScriptedOpenAI`, `_DroppingStream`)
- `backend/scripts/bench_customer_agent.py` — `warnings` capture (4 edits)
- `backend/scripts/stress_stream_explanation.py` — new isolated stress harness
- LOC: ~70 prod + ~130 test | Tests: **16/16 pass** (0.22s)

## Overall Assessment
Sound fix. Generator semantics are correct (no prefix duplication), partial-drop re-raise preserves already-streamed tokens, fallback yields a REAL answer. Docstring is exemplary (explains WHY + tradeoff). The FPT drop class is well-modelled. One real gap (observability) + a couple of principled-but-benign notes.

## Adversarial Walkthrough (focus areas)

### Generator semantics — PASS
- **Prefix duplication?** No. `yielded` is set True *before* `yield delta`; on mid-stream exception `if yielded: raise` exits the generator immediately. Pre-prefill fail keeps `yielded=False` → retry/fallback. No dup path exists.
- **`yielded` set/reset across loop?** Correct — reset to False at top of each of the 2 iterations.
- **Empty-stream silent return?** Verified empirically: stream outcomes `['','']` (no exc, no tokens) → `last_exc=RuntimeError('empty_stream')` → loops to attempt 2 → non-stream fallback yields REAL answer. History `['stream','stream','nonstream']`. Correct fall-through, NOT a silent return.
- **Bare `return` after success** — clean StopIteration, caller for-loop exits normally. Good.

### Partial output preservation — PASS
Mid-stream re-raise: partial deltas already yielded to caller (in `answer_parts` + sent as SSE `answer_delta`). Caller L518-539 except branch: `answer_parts` non-empty → appends a natural-language tail (`" (mình vừa bị ngắt kết nối nhỏ, ...)"`). FE keeps the partial answer + tail. No duplication, no data loss. Correct tradeoff (can't un-send SSE bytes).

### Timeout values — httpx.Timeout(30.0) → read=30s is PER-READ, not total — PASS
Verified `httpx.Timeout(30.0)` → `{read:30, connect:30, write:30, pool:30}`. Read timeout is per-read-operation (max gap between bytes), so a normal stream (chunks every ~10ms) never fires it. Comment at L1388 is accurate. 45s non-stream is total (one shot) — reasonable.

**Worst-case latency bomb:** 2×30 (stream stalls) + 45 (non-stream) = **~105s**. Mitigated: route SSE `events.get(timeout=15)` emits `": ping"` while the worker blocks → client/proxy connection survives. A global wall-clock budget (e.g. abort all after 60s) could tighten it, but the failure mode (FPT silent for 30s straight ×2) is rare. **Low priority.**

### Broad `except Exception` — acceptable, principled alternative noted
All `httpx.TransportError` (ReadTimeout, RemoteProtocolError, ConnectError) AND `openai.APIError` (401/400/429) get retried. 401/400 are config bugs (caught in testing, not prod). 429 retried with no backoff — slightly anti-social but only 3 rapid calls max; FPT volume unlikely to trip rate limits. As noted in the task, a 401 ultimately hits non-stream then re-raises to the apology — benign. **A narrower predicate** (retry only on `httpx.TransportError`/empty-stream; let `openai.APIStatusError` skip straight to re-raise) would be more principled but the current behavior is correct and the waste is bounded. **Medium-low.**

### Test fidelity — PASS
- `_DroppingStream` faithfully models the OpenAI chunk iterator + mid-stream drop (`__next__` yields content chunks then raises exc).
- `_ScriptedOpenAI` models stream=per-char-deltas, non-stream=full-content, FIFO outcomes, records (mode, timeout) — asserts both call sequence AND timeout pass-through (30.0/45.0).
- 4 tests cover: happy path, prefill-fail×2→non-stream, partial-drop-not-retried, total-fail-reraise.
- **Minor gap:** no explicit empty-stream test (verified manually above — logic correct). Real OpenAI also emits an initial role chunk (`delta.content=None`) before content; fakes skip it but prod `if delta:` handles None/"" correctly — no behavioral diff.

### Regression risk — NONE
Route layer (`customer_agent_routes.py`) unchanged. Caller fallback L514-539 contract unchanged: generator yields `answer_delta` strings, may raise. New internal recovery means caller's except fires LESS often (only mid-stream-drop or total-fail). No new exception types escape — all paths either yield tokens or re-raise an Exception subclass the caller already handles.

## Critical Issues
None.

## High Priority
1. **Observability gap — successful fallback is invisible.** When stream fails but non-stream recovers the answer, NOTHING is emitted: no `_LOG`, no `stream_warnings`, no `agent_events` row. Operators cannot detect FPT streaming sickness in prod, and the bench's `explanation_stream_interrupted: 0/N` metric stays 0 even when the fix recovered 30% of calls — **the bench cannot validate the fix is working.** `_LOG` already exists (used L755/776/1177/1204) but is not called here. Fix: in the fallback branch, add `_LOG.warning("fpt stream recovered via non-stream fallback: %s", type(last_exc).__name__)` and consider surfacing a `"stream_recovered"` warning on `CustomerChatResponse` so FE/ops/bench can count recoveries.

## Medium Priority
2. **Broad retry predicate** — optionally narrow to `httpx.TransportError`+empty-stream; let permanent `openai.APIStatusError` skip retry. Bounded waste today, principled improvement.
3. **No backoff between the 2 stream attempts** — for transient FPT drops, immediate retry is fine (typically a fresh connection); add a tiny `time.sleep(0.2)` only if FPT rate-limits become an issue. Skip for now.

## Low Priority
4. **Empty-stream case not unit-tested** — add `test_empty_stream_falls_back` (`stream_outcomes=['','']`). 5 lines; confirms an otherwise only-manually-verified branch.
5. **Worst-case 105s latency** unbounded by a global budget — rare; SSE heartbeat keeps client alive. Document or cap if ops reports slow-recovery complaints.

## Edge Cases Verified
- Pre-prefill fail → retry → fallback: PASS (test 2)
- Mid-stream drop → re-raise, partial preserved: PASS (test 3)
- Empty stream (no exc, no tokens) → retry → fallback: PASS (manual + empirical)
- All paths fail → re-raise last exc (non-stream): PASS (test 4)
- Happy path untouched: PASS (test 1, exactly 1 stream call)
- Non-stream returns empty content → falls through to re-raise `last_exc`: PASS (by inspection; `if content:` guards)

## Positive Observations
- Docstring at L1363-1376 is excellent: documents the failure class (FPT 10-30% drops), strategy, and the partial-no-retry rationale (would dup prefix). Future-self-friendly.
- `yielded`-before-`yield` pattern is the correct way to distinguish pre-prefill vs mid-stream failure.
- Non-stream fallback yields the FULL real answer as a single delta — user gets a real answer (just no typewriter) instead of an apology. Real UX win over commit 53884da.
- Fakes record call history including timeouts — tests assert both behavior AND config pass-through.
- Stress script isolates the FPT path from search/preference overhead — clean signal for validating the fix live.
- `# noqa: BLE001` annotations on the broad catches signal intent (linter-aware).

## Recommended Actions (ordered)
1. **Add telemetry to the recovery path** (High) — `_LOG.warning` on successful non-stream fallback + optional `stream_recovered` warning. Enables ops detection + bench validation.
2. **Add empty-stream unit test** (Low) — 5 lines, locks in the manually-verified branch.
3. (Optional) Narrow retry predicate to transient-only (Medium) — principled but benign today.

## Metrics
- Type coverage: N/A (no new types; existing `Iterator[str]`)
- Test coverage: 4 new tests, all branches covered except empty-stream (manual-verified)
- Linting issues: 0 new (`# noqa` on intentional broad catches)
- Tests: 16/16 pass (0.22s)

## Unresolved Questions
1. Should the non-stream fallback's 45s total timeout be lowered now that it's the LAST resort (not the first)? If FPT non-stream also stalls, the user waits up to 45s for the apology — is that acceptable, or cap non-stream at ~20s?
2. Is there FPT-side guidance on whether a dropped stream indicates the next stream will also drop (correlated) vs independent? If correlated, the 2nd stream attempt is mostly waste and could be skipped (go straight to non-stream after 1 stream fail). The current 2-attempt design assumes independence.
3. Should `stream_recovered`/`stream_failed` counters be added to `agent_events` (DB) for dashboarding, or is structured logging sufficient?
