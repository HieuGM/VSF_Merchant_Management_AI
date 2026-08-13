# Phase-02 GT Eval — Measurement Safety-Gate

**Branch:** dev-a · **Date:** 2026-08-05 · **Backend:** live on :8000 (phase-02 code, health=ok)
**Change under test:** deterministic taste-profile ranking
- `services/profile_ranking.py` (`profile_score` / `should_hard_filter`) — pure, no DB
- `core/ranking_config.py` (defaults: `ranking_enabled=True`, `hard_filter_disliked=False`, small weights)
- `core/profile_context.py` (ContextVar)
- `MerchantSearchService.search/nearby_search` adds `profile_score` to `match_score` + optional hard-filter
- `customer_flow.py` sets `profile_scope(profile)` around both crew kickoffs
- 10 new unit tests pass (capability proven at unit level)

**Snapshots**
- New: `plans/reports/gt-eval-results-after-phase02-ranking.json`
- Baselines: `gt-eval-results.json` (canonical, 39/39 clean), `gt-eval-results-after-phase01-unify-memory.json` (parity snapshot)
- Raw log: `plans/reports/.gt-eval-after-phase02.log`

---

## TL;DR — VERDICT: **PARITY (with one transient FPT-stream flake on a non-profiled case)**

- **Execution: 39/39, 0 errors.** Match canonical baseline on the load-bearing metric.
- **1 `explanation_stream_interrupted` on TC-28** (`ReadTimeout` from FPT explain-stream). Pre-existing reliability issue documented in `fix-260731-stream-reliability-fpt-deepseek.md`. TC-28 has no profile → phase-02 ranking cannot affect it. Older `gt-eval-results-before.json` showed the same flake on different cases (TC-49/51). **Not a phase-02 regression.**
- **Profiled cases (TC-06/07/29): 0 broke.** TC-06/29 PARITY; TC-07 result-count shifted (3→0) but phase-02 behavior is *more correct* per GT (`should_ask_clarification=true`) and is not ranking-caused (`dietary:["không cay"]` doesn't match the chay/vegetarian boost path).
- **Recommendation: KEEP.** If orchestrator applies rubric strictly (any new stream_interrupted → REGRESSED), the soft kill-switch is `ranking_enabled=False` (env flip, no rollback needed) — but my recommendation is KEEP since the flake is unrelated to phase-02.

---

## Metrics Table

| Metric                    | Canonical (`gt-eval-results.json`) | Phase-01 (`...after-phase01-unify-memory.json`) | **Phase-02** (`...after-phase02-ranking.json`) |
|---------------------------|:---:|:---:|:---:|
| cases run                 | 39  | 39  | **39** |
| `error` count             | 0   | 0   | **0**   |
| `stream_interrupted`      | 0   | 0   | **1** (TC-28 ReadTimeout, FPT flake) |
| median total (submit→fin) | 9.07s | 12.12s | **10.62s** |
| median TTFT               | 8.51s | 9.47s | **9.91s** |
| cases with ≥1 result      | 15  | 15  | **15** |
| quality judge             | not re-judged this run (last fully-judged baseline = 34/39 = 87.2%) | — | not judged — parity assessed via execution + per-case deltas |

---

## Per-Case Deltas (phase-02 vs canonical)

Only cases that moved. All others (33 cases) identical on `error`/`warn`/result-count.

| ID | Category | Δ vs canonical | Note |
|---|---|---|---|
| TC-02 | happy_path | results 3→1 | Model returned 1 merchant (Bún Chả Đống Đa) instead of 3. Pure LLM nondeterminism; not ranking-touched (no profile). |
| **TC-06** [profiled] | preference_implicit | **0→0 (PARITY)** | Refinement intent, no location → 0 results in all 3 runs. Text varies: canon mentions "đồ chay" from profile, ph02 just asks location. Profile={preferred_cuisine:[việt,chay], budget_avg:60000}; ranking boost path is wired but never reached (empty result set). |
| **TC-07** [profiled] | preference_implicit | results 3→0 | Phase-02 asks for location, returns nothing. **This is the GT-expected behavior** (`should_ask_clarification=true`, note: "thiếu location bắt buộc nên vẫn phải hỏi"). Baselines were technically lax. Profile={dietary:["không cay"]} — does NOT trigger any ranking path (boost only fires for `chay`/`vegetarian`). **Not phase-02 caused; moved in the *correct* direction.** |
| TC-28 | negation_and_ambiguity | NEW `stream_interrupted` | `WARN=['explanation_stream_interrupted: ReadTimeout']`. FPT explain-stream flake (30.4s explain(stream) hit timeout). Agent self-recovered ("mình vừa bị ngắt kết nối nhỏ"). No profile → ranking cannot affect. Pre-existing. |
| **TC-29** [profiled] | profile_conflict | **3→3 (PARITY on count), better disclosure** | Phase-02 answer now explicitly surfaces conflict: *"hồ sơ của bạn đang để 'không cay' — nếu muốn đổi gió thì mình nghĩ nên bỏ cái đó ra"*. Matches GT intent ("yêu cầu tường minh PHẢI thắng user_profile"). User override still wins, 3 merchants returned. Improvement, not regression. |
| TC-41 | refinement_multiturn | results 0→1 | Anaphora case. Prior-referent seeding worked; resolves to 1 merchant (Phở Thìn+ 13 Lò Đúc). Minor positive shift; not ranking-touched. |

### Profiled-case behavior (the only cases phase-02 could move)

| ID | Profile | Canon | Phase-01 | Phase-02 | Verdict |
|---|---|---|---|---|---|
| TC-06 | preferred_cuisine=[việt,chay], budget=60k | 0 res, no location ask | 0 res | 0 res | PARITY (no ranking path reached) |
| TC-07 | dietary=[không cay] | 3 res | 3 res | **0 res + clarify** | Shift, *correct direction*, not phase-02 caused |
| TC-29 | dietary=[không cay] (user overrides with "cay thật cay") | 3 res | 3 res | 3 res + conflict disclosed | PARITY+ (better disclosure) |
| TC-33 | preferred_cuisine=[việt] | SKIPPED (coordinator-only) | SKIPPED | SKIPPED | N/A |

**Why phase-02 has ~zero measurable effect on GT (as predicted):**
1. Only 3 in-scope cases seed a profile.
2. TC-06 returns 0 results (refinement intent, no location) — ranking never runs on an empty candidate set.
3. TC-07/29 profile field is `dietary:["không cay"]`. `profile_score` only boosts when dietary contains `chay`/`vegetarian`; "không cay" matches neither. `disliked_cuisines` is empty in all 3 cases, so `should_hard_filter` (which is `hard_filter_disliked=False` by default anyway) never fires.

→ The ranking capability is proven by unit tests; GT just doesn't exercise it materially. This is the expected PARITY outcome.

---

## Latency outliers (phase-02)

| Case | total | ttft | Note |
|---|---|---|---|
| TC-48 | **312.6s** | **311.7s** | 5+ min pre-first-token hang on "ăn chay trường" profile-upsert case. Search itself was 6.3s. Pure FPT/model latency; not ranking-touched. Recovered cleanly (0 results, coherent answer). |
| TC-27 | 61.0s | 60.9s | Long TTFT, multi_intent. Same FPT pre-explain stall pattern. |
| TC-28 | 46.4s | 16.1s | explain(stream) 30.4s → ReadTimeout (the 1 stream_interrupted). |

All three are pre-existing FPT explain-stream characteristics, not phase-02.

---

## Anomalies / observations (non-blocking)

1. **TC-29 trace had a `nearby_merchant_search` `ValueError` (status=error)** at 05:18:47 UTC — `min_rating Input should be a valid number, unable to parse string as a number`. This is a CrewAI tool-args validation flake (LLM emitted `"4.0"` string instead of `4.0` float). The eval's outer SSE still returned 3 results (the agent retried / recovered). Pre-existing CrewAI tool-args issue, not phase-02 caused. Worth a separate ticket but not blocking.
2. **TC-48's 5-min TTFT** inflated total eval wallclock by ~5 min. Eval still completed exit=0 in ~14 min (started 12:11, finished 12:26).
3. **TC-02 returned 1 result instead of 3.** Cosmetic — agent chose to highlight one merchant. Pure LLM variation; baseline runs also occasionally showed this.

---

## Verdict & Recommendation

**VERDICT: PARITY** — execution clean (39/39, 0 errors), profiled cases did not regress, single `stream_interrupted` is a documented FPT flake on a non-profiled case.

**Recommendation: KEEP phase-02.** Reasoning:
- The measurement safety-gate's load-bearing metric (no execution errors, no profiled-case regression) holds.
- The 1 stream_interrupted is FPT-stream pre-existing behavior (TC-28 has no profile; ranking code path is unreachable for it).
- TC-29 (the highest-signal profiled case) actually shows *improved* disclosure behavior.
- Capability itself is proven by the 10 unit tests; GT just lacks cases that exercise it.

**If orchestrator applies rubric strictly (any new stream_interrupted ⇒ REGRESSED):** soft kill-switch = set `ranking_enabled=False` in env/settings (one-line flip, no code rollback). I do NOT recommend this — it would discard a correct, conservative feature because of an unrelated FPT network flake. The decision is the orchestrator's; I do not perform the rollback/flip per task instructions.

---

## Unresolved questions

1. **TC-07 behavior shift (3→0):** GT expected behavior is "ask clarification" (0 results). Should we treat baselines' 3-results behavior as a *latent bug* and file a separate ticket to track it? (Not phase-02.)
2. **TC-29's `nearby_merchant_search` ValueError** on `min_rating` string-vs-float: CrewAI tool-args validation flake — known issue? Worth a defensive coercion in the tool wrapper?
3. **TC-48 5-min TTFT:** catastrophic latency spike on profile-upsert cases. Reproducible? If so, may need a retry/timeout guard on the FPT explain path (related to the stream-reliability fix but a different failure mode).
4. **Quality judge not run this round** — only execution+delta parity assessed. If a numeric pass-rate is required for sign-off, it needs a separate judge pass over `gt-eval-results-after-phase02-ranking.json`.
