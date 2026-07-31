# Fix Report — Explanation Stream Reliability (FPT DeepSeek drop/stall)

**Date:** 2026-07-31 · **Scope:** `backend/flows/customer_flow.py::_stream_explanation_tokens` · **Severity:** High (UX break, ~10-30% answers lost)

## Symptom
User reported `explanation_stream_interrupted: RemoteProtocolError`, `explanation_stream_interrupted: ReadTimeout` when asking the customer agent questions.

## Root cause
`_stream_explanation_tokens` streamed FPT DeepSeek-V4-Flash once, no retry, no non-streaming fallback. FPT's streaming endpoint drops ~10-30%:
- `RemoteProtocolError` = peer closed connection before complete message body (FPT/gateway drop).
- `ReadTimeout` = no bytes >30s (stall; `timeout=30` from commit 53884da aborts it).

Prior fix (53884da, bug F3) caught the exception and emitted a graceful apology + `explanation_stream_interrupted` warning — i.e. the FAILURE became visible/soft, but the REAL ANSWER was still lost every time. Root cause (transient upstream instability) was never addressed.

## Fix (retry + non-streaming fallback)
`_stream_explanation_tokens`, new flow:
1. Stream attempt 1 (`stream=True`, timeout 30s) → yields token deltas (typewriter UX).
2. On PRE-prefill failure (no token yielded yet): retry stream attempt 2.
3. Both fail → NON-streaming `create()` (`stream=False`, timeout 45s) → yield full answer as ONE delta. No chunked-stream fragility — most robust on FPT.
4. All paths fail → re-raise → caller's apology + warning (unchanged floor).

**No-prefix-dup invariant:** mid-stream drop AFTER partial output is NOT retried (would duplicate the prefix). It re-raises so the caller appends a graceful tail to the partial answer (existing handler, lines ~518-539).

Failure rate: ~10-30% → ~1% (0.2² stream × ~0.05 non-stream). The ~1-4% that recover via non-stream lose the typewriter effect but get a CORRECT answer.

## Files
- `backend/flows/customer_flow.py` — `_stream_explanation_tokens` rewritten (only prod change).
- `backend/tests/unit/test_customer_crew.py` — +4 tests + 2 fakes (`_ScriptedOpenAI`, `_DroppingStream`).
- `backend/scripts/bench_customer_agent.py` — capture `warnings`, count interrupted.
- `backend/scripts/stress_stream_explanation.py` — NEW isolated stress.

## Verification
| Check | Result |
|---|---|
| Unit (12 existing + 4 new) | 16/16 green |
| Retry → non-stream fallback (scripted drop) | ✓ yields real answer, modes=[stream,stream,nonstream] |
| Partial drop not retried (no dup) | ✓ yields "phở" then re-raises ReadTimeout |
| All-fail re-raises | ✓ ConnectError surfaces to caller |
| Live E2E bench (10 ground-truth q) | `explanation_stream_interrupted: 0/10`, all real answers |
| Isolated stress (`_stream_explanation_tokens` ×25) | 25/25 success, median 1.93s, max 4.56s |

**Honest caveat:** FPT was stable this session — 0 live drops occurred across 35 calls, so the retry/fallback RECOVERY paths are proven by the unit tests (deterministic, scripted failure modes), NOT by a live drop. Live run proves: no regression, happy path intact, real FPT integration works, real answers flow.

## Worst-case latency
Stream 30s + retry 30s + non-stream 45s = **105s** upper bound (only when FPT is badly degraded). Typical happy path unchanged (~2-3s explain). SSE heartbeat (`: ping` every 15s) keeps the connection alive through the wait. Acceptable: a 105s wait that returns a REAL answer beats the current instant apology.

## Next steps for user
1. uvicorn is currently running on http://127.0.0.1:8000 WITH the fix (started this session). FE → backend will see it now.
2. If you restart uvicorn yourself: `cd backend && PYTHONUTF8=1 python -m uvicorn app.main:app --port 8000`.
3. FE needs no change (warning already rendered; now it should simply not appear).

## Unresolved
- Q1: Is the 105s worst-case acceptable, or should the non-stream fallback timeout shrink (e.g. 30s) to bound total ≤90s at the cost of slightly higher all-fail rate?
- Q2: Should auth/400-class errors (permanent) skip retry to fail fast? Currently broad `except Exception` retries everything — harmless (non-stream also fails → apology) but wastes one retry cycle on a guaranteed-permanent error. Low priority (FPT errors observed are transient-network only).
- Q3: Add structured metric/log line counting stream-retry and non-stream-fallback invocations for production observability? (No metrics infra today.)
