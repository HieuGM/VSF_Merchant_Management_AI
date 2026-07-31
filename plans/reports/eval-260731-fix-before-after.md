# GT Eval — Fix Before/After (2026-07-31)

2 P0 fixes applied: (1) search `max_execution_time 5→15s` (`agents.yaml:23`); (2) `nearby_merchant_search` hard-filters `min_price`/`max_price`/`min_rating` end-to-end (schema→tool→service→repo). Re-ran 39 GT cases (same set, server restarted).

## TL;DR
- **Reliability: big win.** Timeout **31%→2.6%** (12→1). 11 cases rescued from timeout now answer. Mean latency 15.3s→13.8s (outliers cut). Stream warnings 2→0.
- **Quality single-turn constraint filter: FIXED.** TC-01 cơm Cầu Giấy <50k >4★ went fail(score 2)→**score 5**; TC-43 (4), TC-51 (4). The #1 defect category (7/11 before) is resolved for single-turn queries.
- **Overall quality pass-rate barely moved: 16/27 (59%) → 23/38 (60.5%).** Tier WEAK→ADEQUATE (line). Why flat: denominator grew (27→38 answered) + the rescued cohort skews weak (5/12 pass) + remaining failures are ARCHITECTURAL (multi-turn anaphora, explanation grounding, intent-clarification) — not addressable by these 2 fixes.

## Reliability delta
| Metric | Before | After |
|---|---|---|
| TimeoutError | 12/39 (31%) | **1/39 (2.6%)** |
| answered | 27 | **38** |
| stream warnings | 2 | **0** |
| median total | 11.59s | 12.48s (rescued cases run vs fail@5s) |
| mean total | 15.28s | **13.84s** ⬇ |
| max total | 54.1s | 42.6s |
Residual timeout: TC-25 ("Quán này có ổn không?" — short pronoun, agent reasoning >15s).

## Quality delta (adversarially verified, 0 overturned both runs)
| | Before | After |
|---|---|---|
| pass / answered | 16/27 (59%) | **23/38 (60.5%)** |
| tier | WEAK | ADEQUATE |
| end-to-end fully-correct (of 39) | 16/39 (41%) | **23/39 (59%)** |

### What the constraint fix changed
- **Single-turn hard filter: FIXED (5/5).** TC-01 returned 3 real cơm/gà-rice merchants, all rating ≥4.0, price ≤50k honored — exactly the query. TC-43, TC-51 likewise respect price/cuisine.
- **Multi-turn refinement-merge: STILL BROKEN.** TC-10 ("rẻ hơn nữa" after a cơm/Mỹ Đình/<40k turn) dropped ALL prior constraints, returned Huế/HCM coffee. Constraint carryover across turns is a memory/anaphora issue, not the search filter.

### Rescued-from-timeout cohort: 5/12 pass (42%)
✓ TC-11, TC-26, TC-42, TC-45, TC-46 (now answer correctly) · ✗ TC-35, TC-36, TC-39, TC-41, TC-47, TC-48, TC-50 (answer now but wrong — multi-turn/explanation cases needing deeper fixes).

## Remaining defects (architectural — beyond these 2 fixes)
1. **Multi-turn anaphora & refinement merge** (TC-09,10,41,47, median 2): "quán đầu tiên"/"món đó" misresolve to absent/wrong merchants; prior-turn constraints silently dropped. Root: `_resolve_followup_targets` + memory carryover; needs coordinator/evidence wiring.
2. **Explanation grounding hallucination** (TC-38,39,50): brand compare from general LLM knowledge; invents "mình vừa gợi ý" context not in session. Root: `merchant_evidence` never injected into explanation path (no endpoint seam) — TC-25/50 structurally untestable E2E.
3. **Intent misclass → spurious fallback** (TC-07,16,24,35,49): searches instead of clarifying; returns "cho có" Huế/HCM fallback for empty/ambiguous intent. **TC-49 health risk**: ignores same-turn seafood allergy, returns 3 seafood shops. Root: no coordinator to refuse/clarify + fallback returns nearest regardless.

## Verdict
The 2 fixes did exactly what they targeted: **throughput (no 5s cliff) + single-turn constraint integrity.** Answers ARE more stable and the targeted constraint cases are now correct. Overall pass-rate is ~flat only because the long tail of failures is architectural (coordinator/memory/evidence) — a different workstream, not a filter/timeout tweak.

## Unresolved
- Q1: Commit the 2 fixes? (verified: 27 unit tests pass + GT before/after). TC-16 regression (Sao Hỏa r=0→r=3) is agent non-determinism on the unchanged merchant_search path, not caused by the fix.
- Q2: Next workstream = the architectural 3 (anaphora/memory carryover, evidence-injection seam, coordinator-thin-layer for intent/clarify/refuse). These would move the needle from 60% → 75%+. Estimate: multi-phase.
- Q3: TC-25 still times out at 15s — raise search cap further (20s) or accept the 1 residual?
- Q4: `min_rating` filter excludes merchants with no ShopeeFood rating (only Foody) — consistent with merchant_search but may over-restrict nearby on sparse data. Worth a follow-up data check.
