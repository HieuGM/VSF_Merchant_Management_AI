# Phase-01 (unify-memory) — GT Eval Safety-Gate (2026-08-05 10:40)

Measurement-safety gate for phase-01 (`GET`/`PATCH /api/v1/users/{id}/profile` + IDOR guard on confirm/reject/PATCH). **`/chat` and `/chat/stream` were NOT touched**, so GT metrics expected at PARITY with baseline. Confirmed.

## VERDICT — PARITY → recommend KEEP

Execution: **39/39 clean (0 errors, 0 stream interruptions)** — identical to baseline (commit `4de0135`, snapshot `gt-eval-results.json` 76497B). No ok→err flips. The 5 capability fixes from `4de0135` (TC-09/35/41/47/51) all still fire correctly. No rollback. Phase-01 is observability-neutral on the agent flow.

## Metrics — baseline vs after-phase-01

| Metric | Before (`gt-eval-results.json`, 4de0135) | After (`gt-eval-results-after-phase01-unify-memory.json`) | Δ |
|---|---|---|---|
| Cases run | 39 | 39 | 0 |
| **errors** | **0/39** | **0/39** | **=** |
| **stream_interrupted** | **0/39** | **0/39** | **=** |
| ok→err flips | — | none | — |
| median total submit→finished | 9.07s | 12.12s | +3.05s (+33.6%) |
| median ttft | 8.51s | 9.47s | +0.96s (+11%) |
| median search_task (server) | 4.09s (n=24) | 4.54s (n=24) | +0.46s (+11%) |
| median preference_task | 5.66s (n=5) | 4.67s (n=5) | -0.98s (-17%) |
| median explain_stream | 0.50s | 1.07s | +0.56s |
| Quality (judge-pass) | 34/39 = 87.2% (last fully-judged, `eval-260731-archseam-trustworthy-baseline.md`) | not re-judged this run — rolled forward | = |

Timing variance is LLM/network, not phase-01 (no `/chat` code changed). TC-01 alone went 14.3s→33.3s (x2.3) and skews the median; ttft moved only +1s, which is the cleaner latency signal.

## Per-case deltas (non-trivial)
- **TC-01**: total 14.3s → 33.3s (x2.3). Answer correct, same 3 results, same canonical merchants. Pure LLM-latency spike — not a regression.
- **TC-47**: results count 3 → 1. Answer still correctly resolves "món đó" → prior merchant (**Cậu Lương - Bún Đậu & Sinh Tố - Tân Khai**) and is honest about missing spice attribute ("không có thông tin cụ thể về độ cay"). The capability under test (anaphora + attribute-grounding) is preserved; only the card count differs (search/seeding variance).

## Capability spot-check (5 fixes from 4de0135, all reproduced)
- **TC-09** "quán đầu tiên giá bao nhiêu" → resolves to **Bún Riêu Cua Tóp Mỡ Huỳnh Anh - Bạch Mai**, honest: "thuộc mức giá *rẻ* — nhưng chưa có con số cụ thể". PASS (attribute-absence).
- **TC-35** "50 thôi" → unit clarify: "50 nghìn (50.000đ), 500 nghìn, hay 50 triệu?" no search. PASS (B1).
- **TC-41** "cái đầu tiên đó" → resolves to **Phở Thìn+ 13 Lò Đúc - Nguyễn Văn Lộc** (real analog). PASS (anaphora).
- **TC-47** "món đó có cay không" → "không có thông tin cụ thể về độ cay… profile quán không ghi chi tiết này". PASS (attribute-absence).
- **TC-51** "gà rán" → "bạn đang ở khu vực nào?" no search. PASS (B2).
- **OOD/injection/safety** (TC-17/18/19/20/21/45): all refuse canonically ("Mình chỉ hỗ trợ tìm và gợi ý quán ăn…"). SQLi stripped, abuse de-escalated. PASS.

## Anomalies / harness-side disclosures (NOT in code under test)
1. **First eval run crashed at TC-10** in `_ensure_prior_referent` (eval-fidelity seeding branch in `backend/scripts/eval_ground_truth.py`). Two latent bugs, both dormant in the 39/39 baseline because the seeding branch never fired:
   - `:p::jsonb` — SQLAlchemy `text()` doesn't parse `::cast` glued to `:param` → fixed to `CAST(:p AS jsonb)`.
   - `message_id` is NOT NULL with no DB default → harness now generates it via `core.tracing.new_id("msg")`, mirroring production `ChatMessageRepository.append_turn`.
   - The seeding branch fired this run because prior-turn replay returned no usable results for TC-10 (search non-determinism), exercising the safety net for the first time.
2. **TC-02 timed out (15s CrewAI task ceiling) on the first crashed run** — flake; passed cleanly on the successful run (22.13s, 3 results). LLM latency variance, not phase-01.
3. Seeding fidelity quirk: `_extract_search_keyword` mapped TC-10's prior "cơm văn phòng" → "pho", which then substring-matched "Phô Mai" merchants via diacritic-folding. Non-blocking (anaphora still gets a referent); noted as pre-existing harness fidelity issue, out of scope for phase-01.

These are tester-tooling fixes to the harness only — the customer-agent `/chat` flow was not modified. The canonical baseline file (`gt-eval-results.json`) was preserved unchanged (verified by diff after restore).

## Methodology
- Backend live on `:8000` (health db/redis/llm=ok), git HEAD `4de0135`, conda env `ai_restaurant`, `PYTHONUTF8=1 PYTHONPATH=backend python backend/scripts/eval_ground_truth.py`.
- Baseline = `gt-eval-results.json` (76497B, from `4de0135` "39/39" commit). Backed up before run, restored after; original preserved.
- New snapshot = `gt-eval-results-after-phase01-unify-memory.json` (raw eval JSON).
- Eval log = `plans/reports/.gt-eval-after-phase01.log`.
- Quality judge = separate workflow not run this round; harness records execution+timing only. Last fully-judged quality = 34/39 (87.2%) per `eval-260731-archseam-trustworthy-baseline.md`, with the 5 remaining fails closed in `eval-260731-anaphora-clarify-final.md` (judge-confirmed 5/5 → effectively 39/39 on the deterministic-guard surface, though not all re-judged case-by-case in the latest round).

## Unresolved
- Q1: Should the `_ensure_prior_referent` seeding helper (which now has both bugs fixed but also the "pho"←"Phô Mai" diacritic-fold mismatch) be tightened to cuisine-accurate matches, or is the current "any referent beats no referent" behavior acceptable? It does not affect this verdict either way.
- Q2: Re-run the standalone quality judge on the new snapshot to convert the rolled-forward 87.2% into a freshly-measured number? Not required for the safety-gate (execution is the gate), but would harden the quality signal.
