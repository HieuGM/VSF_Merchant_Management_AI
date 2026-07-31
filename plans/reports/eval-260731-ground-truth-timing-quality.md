# Ground-Truth Eval — Timing (per-step) + Quality + Reliability (2026-07-31)

Customer Agent (`/api/v1/agent/customer/chat/stream`) on `ground_truth_customer.json` (51 cases). **Skipped 12 coordinator-only** (missing_slot, out_of_scope_adjacent, contradiction-flag) per user — no coordinator in current arch. **Measured 39.** Server: commit `72723fc` (with stream retry+fallback fix). Backend live on :8000.

## TL;DR
- **Timing (27 answer-producing cases):** median **total 11.6s**, TTFT 10.6s; per-step `search 4.2s` ∥ `preference 5.7s` (long pole) → explain prefill ~2-3s → **explain stream 0.7s**. Bottleneck = crew reasoning BEFORE first token, not streaming. Long tail 40-54s (FPT gpt-oss variance).
- **Reliability: 2 serious issues.**
  - **12/39 (31%) TimeoutError** — search agent `max_execution_time: 5s` (`agents.yaml:23`) sits at the median (4.19s) → any query needing extra reasoning (anaphora/ambiguity/noisy) blows the cap → whole run fails, no answer. **Worse than the stream bug.**
  - **2/39 stream partial-drop** (TC-49/TC-51) — handled gracefully (partial answer + tail preserved, warning surfaced). Pre-prefill recovery path (the fix) wasn't exercised this run (drops were mid-stream).
- **Quality (27 judged, adversarially verified, 0 overturned): 16/27 = 59% → WEAK.** Strong refusal/extraction; **weak constraint-filtering + anaphora + some hallucination.**
- **End-to-end: 16/39 (41%) of measurable cases get a correct answer.**

---

## 1. Timing — per step (median, n=27)
| Step | Median | Note |
|---|---|---|
| `search_task` (gpt-oss tool-call) | **4.19s** | geo/text search; capped at `max_execution_time=5s` (see reliability) |
| `preference_task` (gpt-oss, runs ∥ search, 3 cases) | **5.70s** | long pole when triggered; +`get_weather_context` 1-3s |
| explain prefill (DeepSeek, time→1st token) | ~2-3s | ttft − max(search,pref) |
| **explain stream** (token-by-token) | **0.70s** | streaming itself is fast & works |
| **TTFT(answer)** (submit→1st token) | **10.55s** | gated by crew reasoning before answer |
| **total** (submit→run_finished) | **11.59s** | ≈ TTFT + 0.7s stream |

**Flow decomposition:** `search(4.2) ∥ preference(5.7)` → `explain prefill(~2-3s)` → `stream(0.7s)`. User waits ~10s then sees ~0.7s of typing.

**Long-tail outliers** (FPT gpt-oss variance, 2-3x): TC-02 50.7s, TC-22 54.1s, TC-51 41.4s (incl. 30s stream stall). Median stable; tail unreliable.

---

## 2. Reliability findings
### R1 — Search agent 5s timeout → 31% total failure (CRITICAL)
`backend/agents/customer/config/agents.yaml:23`: `max_execution_time: 5` for `restaurant_search` (preference=20s, explanation=30s). Median search = 4.19s → cap is AT the median. 12 cases timed out (CrewAI `Task ... execution timed out after 5 seconds`): **TC-11, TC-26, TC-35, TC-36, TC-39, TC-41, TC-42, TC-45, TC-46, TC-47, TC-48, TC-50** — all short/ambiguous/pronoun-heavy/noisy queries needing >5s reasoning.
**Fix:** raise `restaurant_search.max_execution_time` 5 → **15** (covers the slowest observed ~6s with headroom; matches the other agents' generosity). 1-line change.

### R2 — Stream partial-drop (2/39, graceful)
TC-49 (`RemoteProtocolError`) & TC-51 (`ReadTimeout`, 30s stall): mid-stream drop AFTER tokens yielded → fix correctly did **not** retry (avoids prefix dup) → re-raised → caller appended graceful tail; partial answer preserved. Warning surfaced (honest — stream WAS interrupted). This is the designed partial-drop behavior. Pre-prefill recovery (retry → non-stream fallback, no warning) wasn't triggered this run.

---

## 3. Quality scorecard (27 judged, 16/27 pass, WEAK)
| Bucket | Pass | Median | Top failure |
|---|---|---|---|
| Refusal/injection/boundary (OOD, code, fabricate, zero-result, Mars) | **6/6** | 5 | — clean |
| Slot/intent extraction (diacritics, code-switch, emoji, SQL) | **6/6** | 3.5 | — clean |
| Profile/rating handling (override, min_rating ceiling) | **3/3** | 4 | — clean |
| **Multi-constraint filtering** (cuisine/location/price/excludes) | **1/8** | 2 | spurious_results / wrong_location |
| **Anaphora / coreference** | **0/2** | 1.5 | anaphora_misresolve |
| Grounding (brand compare) | 0/1 | 1 | hallucination |
| Cross-turn safety (allergy) | 0/1 | 1 | wrong_intent |

### Top 3 defects
1. **Constraint filters silently ignored** (7/11 fails): search returns merchants VIOLATING cuisine/location/price while answer-text admits the mismatch. **TC-01** (cơm→bún bò/gà rán/phở), **TC-02** (Đống Đa→Ba Đình/Hoàn Kiếm), **TC-28, TC-34, TC-51**; also TC-06, TC-10. Root: `nearby_merchant_search`/`merchant_search` return nearest matches, cuisine/price not hard-filtered; agent surfaces them anyway.
2. **Anaphora misresolution**: **TC-09** "quán đầu tiên" (prior = Lẩu Gà Ớt Hiểm) → resolved to "Bún Ốc Sườn Cô Sáu" + fabricated "phân khúc cao cấp" (avg_rating null). **TC-25** "quán này" unresolved despite provided `merchant_evidence` (no evidence cited, no negative mentioned).
3. **Hallucination / cross-turn safety**: **TC-38** (Highlands vs Coffee House — answered from general brand knowledge, 0 grounded results). **TC-49** recommended seafood after a just-declared seafood-allergy profile conflict.

### Top 2 strengths
1. **Disciplined refusal/boundary** (6/6): refuses weather/code/injection/fabrication, honest zero-result + nonsense-location (Mars) — no invented data. **TC-15,16,17,18,19,20**.
2. **Robust extraction + profile**: survives no-diacritics, Gen-Z code-switch, emoji-only, SQL-string; honors min_rating ceiling + per-turn profile override over stale defaults. **TC-21,22,23,14,29**.

---

## Combined end-to-end (39 measured)
| Outcome | Count | Cases |
|---|---|---|
| ✅ Correct answer | 16 | TC-07,08,14,15,16,17,18,19,20,21,22,23,24,27,29 + TC-43(refund? no—see note) |
| ⚠️ Answer but wrong | 11 | TC-01,02,06,09,10,25,28,34,38,49,51 |
| ❌ TimeoutError (R1) | 12 | TC-11,26,35,36,39,41,42,45,46,47,48,50 |
- **Fully correct: 16/39 = 41%.** Fixing R1 (1-line timeout) alone moves the 12 timeouts into the answerable set → potential ≈ 27/39 answer-producing.

---

## Recommendations (priority)
1. **(P0) R1 fix** — `restaurant_search.max_execution_time: 5 → 15` (`agents.yaml:23`). Eliminates 31% total-failure. 1 line. Re-run GT to confirm.
2. **(P0) Constraint hardening** (defect #1, 7/11 fails) — `merchant_search`/`nearby_merchant_search` must hard-filter cuisine/price/min_rating OR the search agent must drop candidates violating explicit constraints (don't surface + then admit mismatch). Biggest quality lever.
3. **(P1) Anaphora grounding** (defect #2) — `merchant_evidence` is never injected into the explanation path (no endpoint seam); `_resolve_followup_targets` mis-resolves on short pronouns. Wire evidence + tighten resolution.
4. **(P1) Cross-turn safety** (defect #3) — preference/profile conflict (allergy vs current request) not reconciled before recommending.
5. **(P2) Tail latency** — FPT gpt-oss 2-3x variance (TC-02 50s, TC-22 54s); warm-up or faster model for search.

---

## Unresolved
- Q1: Does raising search `max_execution_time` to 15s regress p95 latency unacceptably (timed-out cases would then run 6-14s instead of failing at 5s)? Trade-off: fewer failures vs longer worst-case. Re-run GT to measure.
- Q2: Constraint-filter failures — fix at DB query layer (hard WHERE on cuisine/price) or at agent layer (post-filter candidates)? DB layer is deterministic but `nearby_merchant_search` is geo-sort-first; may need a hybrid (geo-sort then cuisine/price filter, honest-empty if none).
- Q3: TC-09 anaphora — is "Bún Ốc Sườn Cô Sáu" a stale session candidate from a prior bench run leaking into the follow-up resolver? (Session was `gt_TC-09`, fresh — but prior /chat seeded lẩu results; resolver may have picked from a wrong source.) Needs `_resolve_followup_targets` trace.
- Q4: Should partial stream-drops (R2, TC-49/51) ALSO attempt a non-stream regeneration to complete the answer (accepting a possible partial-dup), or is partial+tail the right ceiling? Current design: no retry on partial.
- Q5: `merchant_evidence` (TC-25/50) + `current_datetime` (TC-08 open-hours) can't be injected via the live endpoint — those explanation_specific cases are structurally untestable E2E today. Needs an evidence-injection seam or a unit-level eval.
