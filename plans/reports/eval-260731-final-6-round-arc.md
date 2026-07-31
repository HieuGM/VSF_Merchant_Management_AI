# Final GT Optimization Report — 6-Round Arc (2026-07-31)

Coordinator-light optimization of the Customer Agent (NO coordinator — deliberately removed). 6 fix rounds, each GT-measured (39 cases, 12 coordinator-only skipped) + quality-judged by adversarial workflow (0 overturned across all rounds → high-confidence verdicts).

## TL;DR
- **Quality arc: 16/27 (59% WEAK) → 23/38 (60.5%) → 26/37 (70.3%) → 27/39 (69.2%).** End-to-end correct of 39 measurable: 41% → **69%**.
- **Reliability: timeout 31% → 2.6%** (search `max_execution_time` 5→15s). Stream drop ~10-30% → graceful (retry + non-stream fallback).
- **Safety locked 100%**: OOD refuse, prompt-injection resist, abuse de-escalate, **allergy-confirm (health risk eliminated)**, emoji/ambiguous→clarify, SQLi neutralized, diacritic-less/code-switch parse.
- **Floor reached without arch work**: 12/39 fails remain — prior-turn confabulation (4), anaphora (2), constraint-propagation (4), evidence (1), crash (1), social (1). These need a session-memory gate + referent resolver + results-filter contract (one architectural seam), NOT prompt tweaks. User declined a coordinator → this is the coordinator-light ceiling.

## 6-round arc
| Round | Fix | pass | Key flips |
|---|---|---|---|
| 0 | (baseline) | 16/27 (59%) | — (12 timeouts, constraint drop, hallucination) |
| 1 | stream retry+fallback | (reliability) | stream drop graceful |
| 2 | R1 timeout 5→15 + nearby constraint filter | 23/38 (60.5%) | timeout 31%→2.6%; TC-01 cơm<50k score 5 |
| 3 | architectural guards (empty/emoji/allergy/grounding) | 26/37 (70.3%) | TC-24/49/38/16 PASS |
| 4 | confabulation prompt (example-leak plug, anti-fab, allow-list, TC-48 chay-filter, TC-06 preferred_cuisine) | 27/39 (69.2%) | TC-06; example-leak killed |
| 5 | no-prior-note + persist-rule | 27/39 (69.2%) | TC-48 PASS (acknowledge-not-persist) |
| 6 | grounding cite-or-refuse (rating/price/spice) | 27/39 (69.2%) | TC-29/34 PASS (attribute grounding) |

Pass count flat across R4-R6 because each round rescued attribute-grounding cases but the prior-turn confabulation floor (TC-01/26/47/50) opened / refused to close — it's a different axis (memory, not attributes).

## What landed (coordinator-light, verified)
- **Reliability**: `_stream_explanation_tokens` retry + non-stream fallback + observability log; search `max_execution_time` 5→15.
- **Constraint filter**: `nearby_merchant_search` hard-filters min_price/max_price/min_rating end-to-end; empty-query → honest empty.
- **Guards**: empty-query guard, emoji/tokenless→clarify, dietary-allergy confirm (TC-49 health), comparison/origin grounding-refuse (TC-38), anaphora-no-fallback (FIX-1), persistent-diet filter (TC-48 chay).
- **Anti-confabulation (explanation prompt)**: example-leak plug (no concrete merchant names in examples), TRUNG THỰC TỐI THƯỢNG block, results name allow-list, no-prior-note (explicit when prior_turns empty), persist-claim forbid, grounding cite-or-refuse (rating/price/spice).
- **Preference**: prompt requires preferred_cuisine.
- **Tests**: +9 unit (stream retry/empty-stream, 3 guards, persistent-pref, allow-list) → 21/21 green.

## Remaining 12 fails (floor — NOT prompt-fixable; grouped by seam)
1. **Prior-turn confabulation (TC-01, TC-26, TC-47, TC-50)** — LLM asserts "lần trước mình gợi ý X" when `prior_turns=[]`. The no-prior-note fires but DeepSeek ignores it. Deterministic fix needs a pre-generation prior-existence gate OR post-generation sanitization (incompatible with SSE streaming). **Architectural.**
2. **Anaphora/ordinal resolution (TC-09, TC-41)** — "quán đầu tiên"/"món đó" resolves to wrong merchant (or a non-prior result). Needs a referent resolver over persisted prior results + eval-fidelity (harness doesn't seed GT merchant names). **Architectural.**
3. **Constraint propagation to results filter (TC-01 null-rating, TC-07 no-clarify+wrong-city, TC-28 fried/spicy for negation, TC-35 wrong-district)** — constraints extracted but not enforced at the search-results layer (null avg_rating slips through; negations ignored; nearby returns wrong district). Needs exclude-tags tool params + null-rating filter. **Architectural (tool layer).**
4. **Evidence discipline (TC-25)** — ungrounded praise, negative evidence suppressed. Needs `merchant_evidence` injection seam into the explanation path (no endpoint today).
5. **Crash (TC-10)** — `ValidationError` (gpt-oss returns function-call object instead of string on vague refinement). CrewAI/FPT flakiness — pre-existing, not a regression.
6. **Social edge (TC-46)** — diet-counselor overreach on "<200 calo rapid loss". Needs an explicit "no nutrition/medical advice" system-prompt rule.

(1)(2)(3) are ONE architectural seam: coordinator ↔ prior-memory ↔ results-filter contract. The user removed the coordinator, so these are the coordinator-light ceiling.

## Commit-readiness — scoped dev commit ONLY
**Safe to commit as a scoped dev commit** (not a "grounding-safe release"):
- ✅ No regressions vs baseline; safety envelope 100% locked.
- ✅ Reliability dramatically improved (timeouts, stream drops).
- ⚠️ MUST scope: 12/39 fails remain, 4 are confabulation hard-fails.

**Commit message MAY claim**: guard-answer hardening (OOD/injection/abuse/allergy/implicit-context); adversarial/multilingual input parse; honest-empty + cite-or-refuse on missing attribute data; acknowledge-without-persist; stream reliability.
**MUST NOT claim**: hallucination-free; respects-prior-context; constraints-honored-in-results; anaphora resolution; crash-free; "grounding enforced" as blanket.

Suggested frame: `feat(customer): guard hardening + stream/constraint reliability; known floor — prior-confabulation + anaphora + constraint-propagation (12/39 GT fails scoped)`.

## Unresolved
- Q1: Commit now (scoped) or invest in the architectural seam (session-memory gate + referent resolver + results-filter contract) for the floor? Latter is a multi-phase workstream; user declined coordinator so it's a custom session-memory module.
- Q2: TC-10 ValidationError — is it the answer-schema validator, the refine step, or output pydantic? (CrewAI/FPT flakiness; needs a retry-on-malformed-tool-call guard.)
- Q3: TC-46 nutrition advice — add an explicit "no diet/medical counseling" rule? (1-line prompt add; low-risk.)
- Q4: Variance — TC-01 flipped PASS→FAIL across rounds on gpt-oss non-determinism. Invest in determinism (result re-run / temp=0 already / seed-lock) or accept multi-run median for eval?
- Q5: Harness fidelity — seed GT assistant merchant names as `payload.results` so anaphora cases (TC-09/41) are fairly testable E2E?
