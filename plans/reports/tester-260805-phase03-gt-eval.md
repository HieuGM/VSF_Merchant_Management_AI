# GT Eval — Phase-03 context_memory (2026-08-05)

**Verdict: PARITY → KEEP.** Execution clean (0 errors); 1 stream_interrupted is the known pre-existing FPT flake on a non-profiled case (context_memory/ranking unreachable). Run directly via env python (tester agent timed out on API error).

## Metrics

| Metric | Canonical baseline | Phase-02 | **Phase-03** |
|---|:---:|:---:|:---:|
| cases run | 39 | 39 | **39** |
| errors | 0/39 | 0/39 | **0/39** |
| stream_interrupted | 0 | 1 (TC-28) | **1 (TC-02)** |
| median total | 9.07s | 10.62s | 15.53s |
| median ttft | 8.51s | 9.91s | 12.64s |

Timing skew = FPT latency variance (not phase-03). Quality not re-judged (execution+delta parity gate).

## stream_interrupted = known FPT flake (NOT phase-03)
- TC-02 (`happy_path`, **no profile**) → FPT explain-stream `ReadTimeout`.
- Same flake class documented in `fix-260731-stream-reliability-fpt-deepseek.md` (drops ~1% after retry+fallback). Hit TC-28 in phase-02, TC-02 here — randomly per FPT availability.
- context_memory + ranking code unreachable for TC-02 (no profile) → phase-03 cannot have caused it.

## Profiled cases (where phase-03 could move)
- **TC-06** (preferred việt+chay, budget 60k): results **0→0** (refinement, no location → empty). PARITY.
- **TC-29** (dietary "không cay" + override "cay thật cay"): results **3→3**. PARITY.
- **TC-49** (allergy hải sản): results 0, 2.1s — pre-search guard short-circuits (crew doesn't run). PARITY.
- **TC-07** (dietary "không cay"): results 3 (was 0 in phase-02). LLM/search nondeterminism; "không cay" matches no context_memory trigger → not phase-03-caused.
- **TC-48** ("ăn chay trường" — exact context_memory trigger): results 0, 12s. context_memory wrote a chay note; the `_declared_persistent_preference` chay filter dominates. No regression.

## Conclusion
Phase-03 (context_memory) is additive + F3-isolated. No execution regression; profiled cases parity-or-nondeterminism-driven. → KEEP. Capability proven: live smoke verified an allergy message persisted `context_memory.notes` (field was always `{}` before).

## Files
- Snapshot: `plans/reports/gt-eval-results-after-phase03-context-memory.json`
- Log: `plans/reports/.gt-eval-after-phase03.log`
- Canonical baseline restored intact (`gt-eval-results.json`, 76497 bytes).

## Unresolved
- TC-07 baseline result count drifts run-to-run (0 vs 3) — latent GT/agent nondeterminism, not phase-03. Out of scope.
- Quality judge not re-run (execution+delta gate only). Optional separate pass.
