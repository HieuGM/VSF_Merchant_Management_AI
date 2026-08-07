# GT Quality Judge Triage — 260807

Bkg: carryover #5 built `judge_gt_quality.py` (no turnkey existed; "87.2%" was manual, never re-run).
Qwen3.6-27B judge on phase-03 snapshot = **26/39 = 66.7%**. This doc triages all 13 FAILs to
find the TRUE quality (floor 66.7%, ceiling 87.2% rolled-fwd), + cross-judges w/ DeepSeek + gpt-oss.

## Triage of 13 FAILs

| ID | cat | FAIL reason (qwen) | verdict | basis |
|----|-----|--------------------|---------|-------|
| TC-02 | happy | "trả bún riêu thay vì bún chả, bịa" | **FALSE** judge err | agent HONEST: "toàn bún riêu, chưa có bún chả", offered real alt 4.7. Zero-result honesty = desired behavior. Judge misread alt-offer as wrong-result. |
| TC-06 | pref_impl | "hỏi lại + bịa chay + bịa mưa" | **FALSE** judge err | profile HAS `chay` (seeded from GT user_profile) → not fabricated. GT `reasoning_must_reference:["mưa to"]` → rain EXPECTED. Judge penalized what GT wants. |
| TC-07 | pref_impl | "trả kết quả, ko hỏi location" | **REAL/border** | GT `should_ask_clarification:true` (location required). Agent returned HN results. But agent hedged "Nếu bạn ở HN...". Real but mild. |
| TC-14 | contradict | "bịa 3 quán rating 5.0" | **FALSE** GT err | DB has **62** merchants `shopeefood_rating=5.0`, all `review_count>0` (avg 12.4). 3 returned (Bon Coffee 10rev, Aoi 3, Bibi 1) are REAL. Agent applied `min_rating=5.0` correctly, no loosen. GT "empty_or_near_empty" assumption factually wrong vs this dataset. |
| TC-22 | noisy | "ko lọc giá <50k" | **REAL/border** | GT `price_max=50000`. Agent returned Cầu Giấy results, price filter likely not applied to noisy input. Check result prices. |
| TC-23 | noisy | "bịa + ko đảm bảo budget 100k" | **REAL/border** | GT `price_max=100000`. Budget filter maybe not enforced. Check. |
| TC-25 | explain | "ko giải thích dựa evidence" | **FALSE** GT fixture | `prior_turns:[]` EMPTY → "Quán này" has NO referent. Agent correctly "chưa gợi ý quán nào trong phiên này". Broken fixture (anaphora q as single-turn). |
| TC-27 | multi_intent | "ko giải thích Hương Liên" | **REAL/border** | GT wants both search + explain Hương Liên. Agent did search, HONESTLY "chưa có thông tin Hương Liên". Can't cite evidence it lacks. Partial. |
| TC-39 | explain | "trả sai ngữ cảnh" | **FALSE** GT fixture | `prior_turns:[]` EMPTY → same as TC-25. Agent correct. |
| TC-41 | refine_multi | "ko resolve 'cái đầu tiên'→Phở Thìn" | **FALSE** judge err | agent DID resolve: "quán phở Thìn ở Bờ Hồ mà bạn vừa hỏi". Judge misread. |
| TC-42 | data_integ | "ko giải thích thiếu data giờ" | **FALSE** GT fixture | `prior_turns:[]` EMPTY → "Quán đó" no referent. Agent correct. |
| TC-48 | profile_conflict | "tự lưu chay, ko xác nhận" | **REAL** (nuanced) | See §TC-48 below. |
| TC-50 | explain | "ko trả lời evidence lịch sử" | **FALSE** GT fixture | `prior_turns:[]` EMPTY → "Quán này" no referent. Agent correct. |

### Roll-up
- **Clear FALSE FAILs (8)**: TC-02, 06, 14, 25, 39, 41, 42, 50 → judge error ×3 (02,06,41) + GT error ×5 (14 fixture-wrong, 25/39/42/50 missing prior_turns).
- **REAL/border (5)**: TC-07, 22, 23, 27, 48.
- **TRUE quality ≈ 31–34/39 = 79–87%** (depending on how the 5 border fall). NOT 66.7%.

## §TC-14 (GT error, NOT agent bug)
DB proof (live `merchant_platform`):
```
62 merchants w/ shopeefood_rating=5.0; all review_count>0 (min 1, max 500, avg 12.4)
Bon Coffee  126916  5.00  10 reviews
Aoi Juice   125725  5.00   3 reviews
Bibi        126721  5.00   1 review
```
Agent applied `min_rating=5.0` (no loosen to 4.x), returned real data → **must_not_hallucinate satisfied**.
GT `note` "gần như chắc chắn không có quán 5.0" wrong for this dataset. **Fix GT**, don't change agent.

## §TC-48 (design tension + real over-claim)
DB proof: eval user `gt_TC-48_<ts>`:
```
dietary = []                       ← structured pref store EMPTY → propose-only HELD ✓
context_memory.notes = ["...ăn chay trường..."]  ← phase-03 auto-persisted ✓
```
Two stores, two rules:
- **`dietary` (structured, drives ranking)**: propose-only held. Agent did NOT auto-write chay.
- **`context_memory.notes` (phase-03 long-term scratch)**: auto-persisted. This IS the feature working (user said "nhớ giúp tôi... khỏi hỏi lại").

**Real bug = agent REPLY over-claim**: "từ giờ mình sẽ **ưu tiên tìm quán chay**" — but ranking uses `dietary` (empty), so it will NOT prioritize chay. Only the crew LLM reads the note. User will be misled ("said it'll prioritize veg, keeps showing non-veg").

### TC-48 — two coherent resolutions (NEEDS USER DECISION)
- **A. Keep phase-03 auto-persist** (recommended): context_memory is the legit always-on memory
  layer; propose-only protects the structured store (which held). Fix = (1) soften agent reply so it
  doesn't claim ranking will change, (2) update TC-48 GT to distinguish the two stores.
- **B. Gate context_memory behind propose-only**: single invariant, TC-48 passes as-is. But kills
  phase-03's core value for the exact cases it targets (allergies, persistent diets) — user must
  confirm before assistant remembers their allergy.

## Cross-judge calibration (part b) — DONE
Same phase-03 snapshot, 3 independent judges (added `--model` flag to `judge_gt_quality.py`):

| judge model | PASS | rate |
|-------------|------|------|
| Qwen3.6-27B | 26/39 | 66.7% |
| DeepSeek-V4-Flash | 23/39 | 59.0% |
| gpt-oss-20b | 15/39 | 38.5% |

**Variance 38–67% across 3 judges → LLM-as-judge unreliable here AS-IS.**

3-way cross-tab vs manual triage:
- ALL-3-PASS (13): TC-08,15,17,18,19,20,24,26,35,36,45,49,51 — solidly good.
- ALL-3-FAIL (9): TC-02,06,07,14,22,23,39,42,48.
- **≥2 judges FAIL 8/8 ARTIFACT cases** (TC-02,06,14,25,39,41,42,50) where the agent was CORRECT.
- ≥2 judges FAIL 4/4 REAL cases (TC-07,22,23,27).

### Key insight
Judges CANNOT separate artifacts from real issues — both groups fail by ≥2 judges. The bias lives
in the **GT fixtures + rubric**, which every judge inherits. So:
- Consensus-voting across judges does NOT narrow toward true quality.
- The 66.7/59.0/38.5% are all UNDERESTIMATES from miscalibrated fixtures, NOT agent regression.
- **Manual triage is the reliable signal**: 8 of the fails are artifacts → TRUE quality ≈ **31–34/39 = 79–87%**, consistent w/ the rolled-forward 87.2%.
- **Fix GT first** (TC-14, TC-25/39/42/50, TC-06), then any judge will measure realistically.

gpt-oss-20b (38.5%) is too strict/weak for this nuanced VN task — drop as a judge, keep qwen+deepseek.

## After GT-fixture + prompt fix (re-run, same 2 judges)

Applied: TC-14 expectation (non_empty_real), TC-25/39/42/50 prior_turns, TC-48 expected (res A) +
tasks.yaml over-claim rule. Re-ran eval (39 cases, 1 flaky TC-41 timeout excluded) + qwen+deepseek.

| metric | BEFORE | AFTER | Δ |
|--------|--------|-------|---|
| qwen single | 26/39 (66.7%) | 24/39 (61.5%) | −5pt |
| deepseek single | 23/39 (59.0%) | 28/39 (71.8%) | +13pt |
| **BOTH-pass (strict ensemble)** | **20/39** | **22/39** | **+2** |
| EITHER-pass (lenient) | 29/39 | 30/39 | +1 |

Single judges swing OPPOSITE (−5 vs +13pt) → confirms run/judge variance dominates. **Ensemble
(both judges agree) is the stable signal: +2 strict / +1 lenient → IMPROVED.**

### Target fixes — verdict
- **TC-42** (prior_turns): BOTH fail→**PASS** ✓✓ definitive.
- **TC-48** (prompt over-claim rule): BOTH fail→**PASS** ✓✓ definitive. New reply: *"mình ghi nhận
  rồi nha. Mình sẽ đề xuất cập nhật sở thích vào hồ sơ, bạn xác nhận nhé?"* (propose+confirm, no
  over-claim) — exactly resolution A.
- **TC-14** (GT expectation): qwen fail→pass ✓; deepseek still fail (MISJUDGE — answer returns the
  SAME 3 real 5.0 merchants both runs; data is correct). GT fix validated.
- **TC-39** (prior_turns): deepseek fail→pass; qwen still fail (asks "which one" — defensible).
- **TC-25/50**: mixed (deepseek pass both runs; qwen fail — asks "which one").

### Regression check (5 cases flipped BOTH-pass True→False: TC-10,28,29,34,47)
Inspected old vs new answers — **ALL run-variance, NOT prompt regression**:
- TC-10/34: honest price answers, equivalent quality.
- TC-28: Sushi Garden (Japanese) fits "không cay/ko đồ chiên" well — defensible.
- TC-47: honest "no spice data" — equivalent.
- TC-29: NEW answer is actually BETTER (flags the user's "không cay" profile conflict).
Prompt change only touched preference-overclaim wording → can't affect these search/explain cases.

### Conclusion
- Fixes verified working (TC-42/48 definitive; TC-14/39 improved). No real regression.
- Ensemble nudged up (+2/+1). **No rollback warranted** (user gate: "rollback if not better").
- True quality remains ~80-87% (LLM-judge floors underestimate due to honest-answer/fixture bias).
- TC-41 = flaky FPT stream timeout (known ~1% issue), excluded — not a quality fail.

### Open questions
- Tighten measurement: re-run eval 3× + average to damp run-variance? (single runs too noisy)
- TC-25/39/50: agent asks "which one" when prior list has >1 — is that the desired behavior, or
  should it explain the first by default? (design call; currently defensible either way)
- Commit GT-fix + prompt-fix + judge `--model` flag + this report now?

## Tight multi-run measurement (3 eval × 2 judges = 6 verdicts/case) — DEFINITIVE

Single runs too noisy (qwen −5pt vs deepseek +13pt). Ran eval 3× (run-1 TC-41 flaked, excluded
there only) + judged each with qwen+deepseek. Aggregator: `scripts/aggregate-multirun-judgments.py`.

**Per-run rates (6 measurements):** 63.2 / 73.7 / 71.8 / 82.1 / 64.1 / 71.8 → **mean ≈ 71%**,
range 63–82%. Artifacts: `gt-eval-results-multirun-{1,2,3}.json` + `gt-quality-judge-multirun-*`.

**Stable buckets (pass-frequency over 6 verdicts):**
- STABLE-PASS (≥5/6): **22** — TC-01,08,09,15,16,17,18,19,20,21,23,24,26,35,36,38,42,43,45,46,49,51.
  (TC-42 = **6/6** — prior_turns fix definitive.)
- BORDERLINE (2-4/6): 11 — TC-10,14,22,25,27,28,29,39,47,48,50. (TC-48 0→4/6, TC-14/25/39/50
  improved from stable-fail to borderline.)
- STABLE-FAIL (≤1/6): 6 — TC-02,06,07,11,34,41.

**True-quality band: 22–33/39 = 56–85%** (stable-pass floor .. +all-borderline). Midpoint ~70%.
This is the honest measured number — the old "87.2%" was a lenient manual ceiling.

### Stable-fail root cause (6) — split real-gap vs judge-miscalibration
Inspecting run-2/3 answers:
- **REAL agent gaps (4, actionable):**
  - **TC-41** anaphora unreliable: run-2 "cái đầu tiên"→*Bánh Mì Chú Tiểu* (WRONG cuisine —
    `_ensure_prior_referent` seeded bánh-mì merchants for a phở query = eval-seed bug); run-3→
    *Phở Thìn+ Lò Đúc* (right cuisine, wrong branch; GT wants Bờ Hồ). Resolution + prior-seed both flaky.
  - **TC-34** price filter: "giá 50k đổ lại" → returns Popeyes w/o price, admits "chưa có giá".
    price_max=50000 not applied (search-extraction gap).
  - **TC-07** location: GT wants ask-only (location missing); agent asks BUT also returns HN
    results. Half-does both.
  - **TC-06** under-delivers: GT wants results (should_ask_clarification=false); agent converses
    + suggests instead of returning concrete merchants.
- **JUDGE MISCALIBRATION (2, agent honest/correct):**
  - **TC-02** honest no-match ("toàn Ba Đình/Hoàn Kiếm, chưa có ở Đống Đa") — no fabrication;
    judges penalize the empty-result honesty.
  - **TC-11** correctly recognizes no valid history + asks clarification (session_expired) —
    exactly what GT wants; judges still fail.

### Net effect of committed fix (f2dad9a)
- TC-42 stable-fail→**6/6 stable-pass** (prior_turns). TC-48 0→4/6 (prompt). TC-14/25/39/50
  stable-fail→borderline (now have referents).
- No NEW stable-fail introduced (the 6 stable-fails are pre-existing — fix touched only
  TC-14/25/39/42/48/50; TC-02/06/07/11/34/41 fixtures + anaphora/seed logic untouched).
- **No rollback** (confirmed with tight data).

### Open questions (updated)
- Fix TC-41 `_ensure_prior_referent` wrong-cuisine seeding (bánh-mì for phở) — eval-fidelity bug,
  unfairly fails the agent + the agent trusts bad referents.
- Fix TC-34 price-filter extraction (noisy input → price_max not parsed).
- TC-07: make Coordinator ask-only (no results) when a required slot is missing?
- TC-02/11: judge rubric still penalizes honest no-match — refine judge prompt or accept as known?

## TC-41 seed fix — VERIFIED end-to-end (commit d271770, new FPT key)
Re-ran eval (0 errors) + qwen+deepseek after the `_pick_prior_merchants` starts-with-keyword fix:
- **TC-41 now resolves correctly**: agent answer "chắc bạn đang nhắc tới **quán phở Thìn ở Bờ Hồ**
  mà bạn vừa hỏi" (was *Bánh Mì Chú Tiểu* — wrong cuisine). deepseek PASS; qwen still FAIL but
  only on elaboration depth ("chưa có thông tin chi tiết"), NOT on resolution — the seed fix's job
  (correct referent) is done.
- **No regression**: 22 stable-pass set → NONE fail both judges. both-pass 22/39 (≈ multirun mean).
- TC-41 expected to move from stable-FAIL toward borderline on a future 3× re-run (resolution now
  correct; only elaboration + judge-variance remain).

## Recommended fixes (prioritized)
1. **GT fixture: TC-25/39/42/50** — add `prior_turns` so "quán này" has a referent (else unfair;
   these are the biggest false-fail cluster, 4/13). Requires re-running EVAL (not just judge) since
   stored answer changes with context.
2. **GT expectation: TC-14** — `empty_or_near_empty` → `non_empty_real` (62 real 5.0 merchants).
3. **GT fixture: TC-06** — inject weather_override w/ rain (GT expects "mưa to" reasoning but eval
   didn't inject it → agent "fabricated" what GT wanted). Or drop "mưa to" from must_reference.
4. **Agent: TC-48 over-claim** — soft-en the reply (don't promise ranking change when dietary empty).
5. **Agent (border, lower pri): TC-07/22/23/27** — location clarification + price/budget filter
   extraction from noisy/multi-intent input.

## Open questions
- TC-48 resolution A vs B? (memory-always-on vs single-propose-only-invariant)
- Re-run full EVAL after GT fixture fixes (needs backend up; ~10 min) to get a clean measured rate?
- TC-22/23: verify returned merchants' actual prices vs the 50k/100k filter (confirm real fail)?
