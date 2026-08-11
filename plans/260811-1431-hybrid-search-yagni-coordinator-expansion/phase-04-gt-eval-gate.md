# Phase 04 — GT Eval Gate ≥0.82 + Rollback Guard (D4)

## Context Links

- Active plan: `plans/260811-1431-hybrid-search-yagni-coordinator-expansion/plan.md`
- GT eval runner: `backend/scripts/eval_ground_truth.py` (writes `plans/reports/gt-eval-results.json` — **OVERWRITES**; back up first)
- Metrics: `backend/scripts/compute_gt_metrics.py` (writes `plans/reports/gt-metrics.json`; `routing.accuracy` is the gate field)
- Baseline: `plans/reports/gt-eval-results.json` (current) + `plans/reports/gt-metrics.json` line 32 `"accuracy": 0.8205128205128205` (32/39 — the gate floor)
- Project memory (GT-eval gotcha): `~/.claude/projects/.../memory/conda-run-flaky-use-env-python.md` — back up canonical `gt-eval-results.json` BEFORE re-running eval, restore after saving the per-phase snapshot.
- Env-python (do NOT use `conda run`): `C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe`

## Overview

Priority: P2. Status: pending (blocked by phase-01). Effort: 2h.

After D1 lands (default OFF, then flag-flipped ON for the A/B), re-run the GT eval and gate on: `routing_accuracy >= 0.82`, zero-result cases (TC-15 sushi Moc Chau, TC-16 Sao Hỏa) stay empty, clarify cases (TC-07/24/26/35) unaffected, tone cases (TC-22 toneless 'pho') unaffected. **Standing user constraint**: if the change does not improve (or regresses) GT → ROLLBACK.

## Key Insights

1. **The gate is structural, not quality**: `routing_accuracy` (in `compute_gt_metrics.py:65-84` `pred_action`) measures coarse ACTION (ask/answer/refuse), computed from results-count + tools-presence + refuse-markers. It is structurally blind to semantic-recall gains (per the research verdict) but EXPOSED to recall-loss regressions (a vague-descriptor hint that causes the agent to drop a query or over-broaden could flip an "answer" case to "ask" or empty). So the gate is a one-sided regression guard, not an improvement signal.
2. **`eval_ground_truth.py` OVERWRITES `gt-eval-results.json`** (line 35 `OUT_PATH` + line 338 `OUT_PATH.write_text`). The canonical baseline MUST be backed up before re-running — otherwise a regression destroys the reference. This is the documented project gotcha.
3. **Determinism caveat**: the eval re-runs the live CrewAI crew, which is non-deterministic (LLM in the loop). The 0.82 baseline itself has ±1 case noise (the baseline run hit 32/39; a re-run with the same code can hit 31 or 33). The gate is therefore a SOFT 0.82: ≥0.82 with the same set of failure cases as baseline (no NEW failure case) is the real bar. A re-run that flips from 32 to 31 on an UNRELATED case is noise, not a regression caused by D1.
4. **Rollback = env flip, not code revert**: because `coordinator_descriptor_expansion_enabled` defaults OFF, rollback is `COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=false` + backend restart. No git revert needed. This is why phase-01's flag design matters.

## Requirements

### Functional
- FR1: Back up `plans/reports/gt-eval-results.json` → `.bak_path_a_phase1` BEFORE re-eval.
- FR2: Restart backend with `COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=true` (phase-01 flag).
- FR3: Run `eval_ground_truth.py` → save snapshot as `gt-eval-results-after-path-a-phase1.json`.
- FR4: Run `compute_gt_metrics.py --snapshot gt-eval-results-after-path-a-phase1.json` → `gt-metrics-after-path-a-phase1.json`.
- FR5: Restore `gt-eval-results.json` from backup (so the canonical baseline file is unchanged post-eval).
- FR6: Compare cases one-by-one against the baseline. Gate: `routing.accuracy >= 0.82` AND no new failure case introduced AND TC-15/16/07/24/26/35/22 unchanged.
- FR7: If gate fails → set flag back to `false`, restart backend, record failure in `plans/reports/gt-eval-results-path-a-phase1-ROLLBACK.md`.

### Non-functional
- NFR1: Total eval runtime ~10–15 min (39 cases × ~15s avg). Plan for one eval run + one backup-restore round-trip.
- NFR2: No `.env` reads. Env vars set in the shell.

## Architecture

```
1. BACKUP    cp plans/reports/gt-eval-results.json plans/reports/gt-eval-results.json.bak_path_a_phase1
2. SERVER    COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=true; PYTHONPATH=backend uvicorn app.main:app --port 8000
3. EVAL      PYTHONPATH=backend <env-python> scripts/eval_ground_truth.py
             (writes plans/reports/gt-eval-results.json — OVERWRITES the baseline!)
4. SAVE      cp plans/reports/gt-eval-results.json plans/reports/gt-eval-results-after-path-a-phase1.json
5. RESTORE   cp plans/reports/gt-eval-results.json.bak_path_a_phase1 plans/reports/gt-eval-results.json
6. METRICS   PYTHONPATH=backend <env-python> scripts/compute_gt_metrics.py \
                 --snapshot plans/reports/gt-eval-results-after-path-a-phase1.json \
                 --out plans/reports/gt-metrics-after-path-a-phase1.json
7. COMPARE   read gt-metrics-after-path-a-phase1.json → routing.accuracy ≥ 0.82?
             per-case diff vs baseline failures (use compute_gt_metrics confusion-matrix + per_category)
8. GATE      pass  → merge phase-01 (flag default OFF in main; flip ON at deploy time)
             fail  → ROLLBACK (flag=false, restart, write rollback report)
```

## Related Code Files

### Modify
- None. This phase runs scripts only.

### Create
- `plans/reports/gt-eval-results.json.bak_path_a_phase1` (backup of canonical baseline)
- `plans/reports/gt-eval-results-after-path-a-phase1.json` (post-change snapshot)
- `plans/reports/gt-metrics-after-path-a-phase1.json` (post-change metrics)
- `plans/reports/gt-eval-results-path-a-phase1-verdict.md` (pass/fail + per-case diff; or `-ROLLBACK.md` on fail)

### Delete
- None. Backup file `.bak_path_a_phase1` is kept as audit trail (do NOT auto-delete).

## Implementation Steps

1. **Pre-flight**: confirm `git status` clean on `plans/reports/gt-eval-results.json` (no uncommitted baseline drift). Confirm flag default OFF in `core/settings.py`.
2. **Backup**: `cp plans/reports/gt-eval-results.json plans/reports/gt-eval-results.json.bak_path_a_phase1` (Bash from repo root).
3. **Restart backend with flag ON**:
   ```bash
   export COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=true
   export FPT_API_KEY=...  # user provides
   cd backend
   PYTHONPATH=. C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe -m uvicorn app.main:app --port 8000
   ```
4. **Run eval** (separate shell):
   ```bash
   cd backend
   PYTHONUTF8=1 PYTHONPATH=. C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe scripts/eval_ground_truth.py
   ```
   (Output overwrites `plans/reports/gt-eval-results.json`.)
5. **Save + restore**:
   ```bash
   cp plans/reports/gt-eval-results.json plans/reports/gt-eval-results-after-path-a-phase1.json
   cp plans/reports/gt-eval-results.json.bak_path_a_phase1 plans/reports/gt-eval-results.json
   ```
6. **Compute metrics**:
   ```bash
   PYTHONPATH=backend C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe \
       backend/scripts/compute_gt_metrics.py \
       --snapshot plans/reports/gt-eval-results-after-path-a-phase1.json \
       --out plans/reports/gt-metrics-after-path-a-phase1.json
   ```
7. **Read metrics**: extract `routing.accuracy`, `per_category[*].routing_accuracy`, `capabilities.clarify_when_required`, `capabilities.result_presence`.
8. **Per-case diff**: load baseline + post-change snapshots, diff `pred_action` per case ID. List newly-failing cases (cases that were `answer`/`ask` correct in baseline and now wrong).
9. **Verdict**:
   - **PASS** if: `accuracy >= 0.82` AND zero NEW failure cases AND TC-15/16 results empty AND TC-07/24/26/35 unchanged AND TC-22 unchanged. Write `gt-eval-results-path-a-phase1-verdict.md`.
   - **FAIL** otherwise: ROLLBACK (flip flag to `false`, restart backend, write `gt-eval-results-path-a-phase1-ROLLBACK.md` documenting which case(s) regressed).
10. **Cleanup**: leave the backup + snapshots in place as audit trail. Do NOT delete.

## Todo List

- [ ] Pre-flight: clean git, flag default OFF confirmed
- [ ] Backup canonical `gt-eval-results.json`
- [ ] Restart backend with flag ON
- [ ] Run eval_ground_truth.py
- [ ] Save snapshot + restore canonical
- [ ] Run compute_gt_metrics.py on snapshot
- [ ] Per-case diff vs baseline
- [ ] Verdict (PASS → ready to merge; FAIL → rollback)
- [ ] Write verdict/rollback report

## Gate Criteria (canonical)

| Check | Threshold | Source |
|---|---|---|
| `routing.accuracy` | ≥ 0.82 | `gt-metrics-after-path-a-phase1.json:routing.accuracy` |
| New failure cases | 0 | per-case `pred_action` diff vs baseline |
| TC-15 (sushi Moc Chau) | results empty (unchanged) | snapshot case `results` field |
| TC-16 (Sao Hỏa) | results empty (unchanged) | snapshot case `results` field |
| TC-07/24/26/35 (clarify) | `pred_action == "ask"` (unchanged) | snapshot + `pred_action` |
| TC-22 (toneless 'pho') | `pred_action == "answer"` AND results non-empty (unchanged) | snapshot |

## Success Criteria

- Gate criteria all PASS → phase-01 cleared to merge (flag still default OFF; flip at deploy time once committed).
- Or FAIL → rollback cleanly (flag back to OFF; backend restarted; canonical `gt-eval-results.json` unchanged — verified identical to backup via `diff`).
- Audit trail: backup + snapshot + metrics + verdict/rollback report all present in `plans/reports/`.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Eval overwrites baseline before backup | L | H (destroys reference) | Step 2 (backup) BEFORE step 3 (eval); project memory documents this exact gotcha |
| Non-determinism causes spurious regression (32→31 on UNRELATED case) | M | M | Per-case diff reveals WHICH case flipped; if the new failure is NOT a descriptor case (e.g. an OOD case flipped), it's noise → re-run once; if persists, judge manually |
| Vector leg red herring: D1 improves recall but gate is blind (research finding) | H (expected) | L | This is BY DESIGN — the gate is a regression guard, not an improvement signal. D2 (instrumentation) is what surfaces real recall gains over 1 wk. Document in verdict report. |
| Backend restart with flag ON fails to take effect (env not exported) | M | M | Verify via `GET /api/v1/agent/customer/health` or a debug log line showing the flag value; print the flag in server startup |
| LLM 401/exhaustion mid-eval (FPT key under heavy load — known issue per project memory) | M | H (eval aborts) | Re-run after refreshing FPT_API_KEY per project memory `fpt-key-401-after-heavy-load` |

## Security Considerations

- `FPT_API_KEY` exported in shell — not committed, not logged. Per project policy.
- No `.env` reads in any script.
- Backup/snapshot files contain no PII beyond what's already in the canonical `gt-eval-results.json` (chat messages — same sensitivity).

## Next Steps

- **On PASS**: phase-01 merges (flag default OFF). Lead decides when to flip the flag ON in production (after a week of D2 data + a re-run of D4 in prod-like conditions).
- **On FAIL**: rollback per step 9. Diagnostic: was the regression caused by a specific dictionary entry mis-leading the agent? If so, narrow the entry (or remove it) and re-run D4. The flag design makes this iterative without code reverts.
- **Standing constraint reminder**: per the user's directive, if the change does not improve GT, ROLLBACK. "Does not improve" includes "no change" — if accuracy stays at 0.82 with the same case set (no NEW pass), the change is quality-neutral on GT but may still be worth shipping for the D2 recall-gap signal. Flag this as a lead-decision point.

## Open Questions

1. **Should the flag default flip to ON if D4 PASSES?** Suggest: NO — keep default OFF until 1 week of D2 data confirms no production regression; lead flips at deploy time.
2. **How to handle ±1-case noise?** If a non-descriptor case flips on re-run, is it noise or signal? Suggest: re-run once; if the same case flips twice, treat as real.
3. **Should we run the LLM-judge quality pass** (`judge_gt_quality.py` with `--judge` flags on `compute_gt_metrics.py`) as well? It's noisier but catches NL-quality regressions the structural gate misses. Suggest: optional follow-up, not a gate.
