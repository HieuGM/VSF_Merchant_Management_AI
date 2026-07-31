# GT Eval — Architectural Fixes (2026-07-31, round 3)

Coordinator-light guards on top of the R1+constraint fixes. Targeted the 3 architectural defect groups from the research workflow.

## TL;DR
- **Quality arc: 16/27 (59% WEAK) → 23/38 (60.5%) → 26/37 (70.3%, ADEQUATE borderline GOOD).** +9.8pts this round.
- **All 4 guards landed & verified PASS** (0 overturned by adversarial verify): TC-24 emoji→clarify, TC-49 allergy-confirm (**health risk eliminated**), TC-38 no-grounding refuse, TC-16 honest-empty.
- **Regressions caught & fixed in-loop:** TC-14 (Fix A over-fired on rating-only), TC-15 (regex `chinh goc` matched cuisine descriptor) — both restored before final run.
- **Caveat — run-to-run variance:** TC-01 flipped PASS→FAIL this run (gpt-oss returned 1 not 3 results + DeepSeek hallucinated a prior). NOT caused by the fixes (TC-01 hits no guard); it's gpt-oss non-determinism. The 70.3% is therefore a noisy point estimate — the confirmed signal is "4 guards land + no regression on refusal/constraint cases."

## Fixes implemented (this round)
| Fix | File | Effect | Cases |
|---|---|---|---|
| Fix A (refined) | `merchant_search_service.py` `search()` | empty-query → honest empty (rating/price count as discriminative so TC-14 stays) | TC-16, TC-24, TC-07, TC-36 |
| FIX-1 | `customer_flow.py` follow-up branch | anaphora unresolved → DON'T fall back to fresh search | TC-47 |
| Fix B | `_is_unparseable` | emoji/tokenless → clarify | TC-24 |
| Fix C | `_detect_dietary_conflict` | allergy in prior turn + same food requested → confirm (health) | TC-49 |
| B-Fix-1 | `_grounding_guard_answer` | no results + comparison/origin query → truthful refuse | TC-38, TC-50 |
All wired into BOTH `/chat` (blocking) and `/chat/stream`. 3 unit tests added (20/20 green).

## Per-category (post-refine, 37 answered)
| Category | Pass |
|---|---|
| Guardrails & safety (injection/OOD/allergy) | **8/8 (100%)** |
| Honesty / empty / no-data | **3/3 (100%)** |
| Constraint satisfaction (price/rating) | **3/3 (100%)** |
| Clarification & slot extraction | 7/8 (88%) |
| Preference / profile | 2/4 (50%) |
| Explanation / evidence citation | 2/6 (33%) |
| Hallucination resistance (fabricated state/merchants) | 1/5 (20%) |

Strong: guards, honesty, constraints. Weak: **confabulation cluster** (anaphora + session-state fabrication).

## Remaining fails (11) — what they need
- **Need coordinator/session-state work (9):** TC-01 (fabricated prior+merchants), TC-09 (wrong anaphora + fabricated price), TC-11 (placeholder in results[]), TC-25 (session bleed + needs evidence injection), TC-35 (assumed price unit), TC-41 (wrong ordinal + praise), TC-47 (entity-type misresolve), TC-48 (auto-persist without re-confirm), TC-50 (fabricated 4 merchants from empty prior).
- **Pure agent-prompt tuning (2):** TC-02 (ungrounded flavor praise "nước dùng đậm đà"), TC-06 (preferred_cuisine ignored in deltas).

## Realistic path forward
- Near-term (readily flippable): TC-11, TC-35, TC-48, TC-25(harness), TC-02, TC-06 → **31–33/39 (79–85%)**.
- Deep confabulation (TC-01/09/41/47/50) needs anaphora + session-state honesty rework → ceiling ~35/39 (90%).
- TC-48 (preference persistence) is the one genuine coordinator dependency (Preference agent only PROPOSES; durable confirm+persist needs a coordinator flow).

## Files changed (all 3 rounds, uncommitted)
- `backend/agents/customer/config/agents.yaml` — search `max_execution_time` 5→15.
- `backend/services/merchant_search_service.py` — `search()` empty-guard; `nearby_search` +min_price/max_price/min_rating hard-filters.
- `backend/tools/customer/merchant_tools.py` — `nearby_merchant_search` exposes min_price/max_price/min_rating.
- `backend/flows/customer_flow.py` — `_stream_explanation_tokens` retry+fallback (round 1); FIX-1 follow-up; `_is_unparseable`/`_detect_dietary_conflict`/`_grounding_guard_answer` + pre-search guard wiring (both paths).
- `backend/tests/unit/test_customer_crew.py` — +8 tests (stream retry, empty-stream, 3 guards).
- `backend/scripts/{bench_customer_agent,stress_stream_explanation,eval_ground_truth}.py` — eval tooling.

## Unresolved
- Q1: Commit all 3 rounds? (R1+constraint already approved-style verified; architectural 20/20 tests + GT 59→70%.) Or split commits per round?
- Q2: Is a real anaphora/ordinal resolver + session-state honesty in scope next, or is "refuse-to-resolve-when-uncertain" the acceptable floor for the confabulation cluster?
- Q3: TC-01/09/47 run-to-run flipping — invest in determinism (temperature 0 already; would need result-rerun or seed-lock) or accept variance + multi-run median for eval?
- Q4: Harness fidelity ceiling — TC-09/41/47 partly fail because the harness seeds only prior USER turns, not the GT assistant's merchant names. Seed GT merchants as `payload.results` to fairly test anaphora, or leave as-is (tests the real E2E path)?
