# Arch-Seam — Trustworthy Baseline (2026-07-31)

First **regression-free, uncontaminated** GT measurement. Quality: **27-28/39 (contaminated) → 34/39 (87.2%)**. Safety floor solid; remaining 5 fails are capability gaps, not integrity breaches.

## TL;DR
- **Critical eval-fidelity fix uncovered:** rounds 1-6 measured on CONTAMINATED sessions — `eval_ground_truth.py` reused `session_id=gt_{cid}` across runs while the DB persists `chat_messages`, so `_load_recent_turns` read STALE prior turns from earlier bench rounds → confabulation. Fixed: per-run `_RUN_STAMP` → unique session/user ids. The prior "69%" was not directly comparable; **87.2% clean is the first trustworthy number.**
- **Arch-seam deterministic fixes (coordinator-free):** prior-context gate fix (no-prior-note now reaches ALL empty-prior queries — was gated behind `_references_prior`), no-prior-referent guard (anaphor + empty prior → refuse, no LLM), post-stream prior-claim sanitizer (backstop).
- **Lever-1 (regression fix):** the no-prior-referent guard false-refused fresh searches because `_DEMONSTRATIVE_RE` tokens (`do`/`nay`) matched "đồ" (food) + "nay" (today). Tightened to `_ANAPHORA_RE` + explicit phrases. Restored TC-06/28/29/34.

## Outcome by cluster
| Cluster | Before (contaminated) | After (clean+archseam+lever1) |
|---|---|---|
| Prior-confabulation (TC-01/26/47/50) | 0/4 (confabulated) | **3/4** (TC-47 fails on evidence) |
| Spurious-guard regression (TC-06/28/29/34) | n/a (new) then broken | **4/4 fixed** |
| Safety (OOD/injection/allergy/abuse/SQLi/parse) | locked | **locked** |
| Anaphora w/ NON-empty prior (TC-09/41/47) | fail | **0/3 — core open hole** |
| Mandatory-clarify (TC-35/51) | fail | 0/2 (slot/unit ambiguity) |

## Remaining 5 fails (capability, not integrity)
1. **Anaphora/ordinal w/ non-empty prior (TC-09/41/47)** — "quán đầu tiên"/"món đó" mis-resolves. TC-09 may be eval-fidelity (DB may lack the GT prior merchants). Needs a referent resolver over persisted prior results + eval-fidelity (harness seeds GT merchants). Opposite failure modes (TC-09 over-denies real prior, TC-41 over-fabricates) suggest a prior-turn ingestion/wiring gap to trace.
2. **Mandatory clarification (TC-35/51)** — bare "50" → assumed 50k; "gà rán" → defaulted HCM, no location ask. Needs a hard clarify-gate before search when a mandatory slot is missing or a value-unit ambiguous.
3. **Explanation evidence (TC-47)** — LLM culinary "common knowledge" leak ("không cay / mắm tôm mặn") with no `evidence_id`. Cite-evidence guard covers empty-prior but not explanation-intent LLM-knowledge.

## Commit verdict — YES (trustworthy baseline)
**Safe to claim:** integrity floor (no fabricated merchants / spurious rows / OOD-injection compliance / system-prompt leak / allergy override); empty-prior anaphor guard 5/5; constraint preservation (min_rating=5.0 not silently lowered); first CLEAN measurement.
**Do NOT claim:** multi-turn anaphora on non-empty prior (0/3); mandatory-clarify on ambiguous/missing slots; explanation-intent evidence discipline.

## Files (this round, uncommitted)
- `backend/flows/customer_flow.py` — prior-context gate fix (`_NO_PRIOR_NOTE` injected for ALL empty-prior); `_pre_search_guard` no-prior-referent branch; `_strip_prior_claims` sanitizer (wired stream + blocking); `_query_references_absent_prior` (Lever-1: dropped noisy `_DEMONSTRATIVE_RE`).
- `backend/scripts/eval_ground_truth.py` — `_RUN_STAMP` unique session/user ids (the contamination fix).
- `backend/tests/unit/test_customer_crew.py` — +tests (referent guard, sanitizer).
- `backend/tests/integration/test_customer_memory_wireup.py` — test-drift fix (`_format_prior_context([])` → `_NO_PRIOR_NOTE`).

## Unresolved
- Q1: Are TC-09/41 `prior_turns` actually ingested into the agent context at runtime, or a harness bug? TC-09 "denied the prior entirely" smells like prior never loaded — trace before blaming the resolver.
- Q2: TC-09 GT prior merchants ("Lẩu Gà Ớt Hiểm", "Phở Thìn Bờ Hồ") — are they in the merchant DB? If not, eval-fidelity seeding can only validate "correct resolution of seeded data", not GT names.
- Q3: Mandatory-clarify gate — hard-block search when slot missing/unit-ambiguous (risk: over-ask), or softer nudge?
