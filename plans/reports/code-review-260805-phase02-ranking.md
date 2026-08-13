# Code Review — phase-02 deterministic profile-based ranking

**Scope:** phase-02 of unify-preference-memory-store (static review; pytest 119/0 incl. 10 new ranking tests + GT 39/39 PARITY pre-confirmed green; 1 unrelated FPT stream flake).
**Branch:** dev-a. **Verdict: APPROVE-WITH-NITS.** All 8 invariants hold; one safe wiring fix applied (M1); remainder are doc/nit-level — no blocker.

## Files in scope
| File | LOC | Note |
|---|---|---|
| `backend/core/profile_context.py` | 37 | NEW — `_current_profile` ContextVar + `profile_scope` ctx-mgr |
| `backend/core/ranking_config.py` | 38 | NEW — `RankingConfig` dataclass + `get_ranking_config()` (lru_cache) |
| `backend/services/profile_ranking.py` | 101 | NEW — pure `profile_score` + `should_hard_filter` + `_fold` |
| `backend/tests/unit/test_profile_ranking.py` | 88 | NEW — 10 table-driven tests |
| `backend/core/settings.py` | +12 | +7 ranking knobs (conservative defaults) |
| `backend/services/merchant_search_service.py` | +28 | `search`/`nearby_search` +`profile` param + ranking wiring |
| `backend/flows/customer_flow.py` | +12/-4 | capture `profile = _load_profile(user_id)` (2 sites) + wrap kickoff in `profile_scope` |

All NEW files ≤200 LOC (rule §6). Kebab-case + comments OK.

## Invariant verification

1. **Additive + no-profile no-op** — PASS. `profile_score(None, ...) → 0.0` (early return L54); `should_hard_filter(..., profile=None) → False` (L95). `ranking_on = cfg.enabled and profile is not None` short-circuits the entire `if` block in both services (L132, L250). No-profile path is byte-equivalent to baseline (modulo the cfg fetch, which is cached).
2. **ContextVar lifecycle** — PASS. `profile_scope` uses `token = _current_profile.set(profile)` + `_current_profile.reset(token)` in `finally` (profile_context.py:33-37). Default None (L20-22). **Stream path verified:** `profile = _load_profile(user_id)` at L739 runs BEFORE `_run_one` is defined (L803) → closure captures `profile` correctly. `profile_scope(profile)` is INSIDE `_run_one` body (L804) → holds within the worker's `copy_context().run(_run_one, …)`; token reset is scoped to the worker's copied context, no parent leak. Empirically confirmed: 2 parallel workers each setting scope on their own copy see their own value; parent's ContextVar is untouched. **No cross-request bleed.**
3. **Thread-safety** — PASS. `search_crew` and `pref_crew` each get a fresh `contextvars.copy_context()` at submit time (L811, L814); each worker's `_current_profile.set/reset` is isolated to its own Context. The shared `profile` object is read-only across both workers (no mutation race). Note: `pref_crew` (mode="preference") does not invoke merchant_search anyway — but even if it did, both would observe the same profile value.
4. **budget en↔vi mapping** — PASS. `_BUDGET_TO_PRICE = {"student": "rẻ", "standard": "trung bình", "premium": "cao cấp"}` (profile_ranking.py:18-22). Values exactly match the DB CHECK `price_level IN ('rẻ','trung bình','cao cấp')` (models.py:190). Compared via `_fold(want) == _fold(have)` → diacritics-folded so `"rẻ"→"re"`, `"trung bình"→"trung binh"`, `"cao cấp"→"cao cap"` on both sides. `UserProfilePublic.budget_level` is the en enum (preference.py:28).
5. **Conservative defaults** — PASS. Weights sum to a max positive `profile_score` of `0.06 + 2·0.03 + 0.04 = 0.16` (budget + 2-liked-cap + dietary); max negative `-0.05` (single disliked penalty, not per-cuisine). `hard_filter_disliked=False` default (soft only). See L2 below re clamp semantics.
6. **No N+1 / no merchant mutation** — PASS. `profile_score` reads only `merchant.cuisine`, `merchant.taste_tags` (column on `Merchant`, models.py:38 — always loaded with the row), `merchant.profile.price_level` (eager `joinedload` in `search_merchants`, merchant_repository.py:107). No `setattr`, no DB session touches. Pure function.
7. **Files ≤200 LOC** — PASS. Max is `profile_ranking.py` at 101. Kebab-case filenames. Comments explain *why*, not *what*.
8. **Closure capture in `nearby_search`** — PASS. `geo_filter` (L267) closes over `ranking_on`/`profile`/`cfg` defined at L248-250 — all bound before `geo_filter` declaration. Verified by reading the method body; no late-binding hazard.

## Edge cases (static)
- profile=None everywhere → `profile_score=0`, `should_hard_filter=False`. ✓
- Empty liked/disliked/dietary → `or []` + `if x and …` guards → 0 contribution. ✓
- `_fold("Món Việt")=="viet"`, `"Món Chay"=="chay"`, `"Trà Sữa"=="tra sua"`, `None→""`, `""→""`. ✓
- disliked overlap → `any(…)` single penalty (not per-cuisine). ✓
- liked cap → `min(hits, liked_cap) * w_liked`. ✓
- dietary chay fires only when BOTH user dietary has chay/vegetarian AND merchant has chay in cuisine/taste_tags. ✓
- `ranking_on` short-circuit → no work when no profile. ✓

## Findings

### MEDIUM

**M1. Fallback path `_direct_nearby_results` was silent ranking no-op — APPLIED FIX**
- `backend/flows/customer_flow.py:579` (blocking) + `:828` (stream) + `_direct_nearby_results` signature L1031.
- Both call sites fire AFTER `profile_scope(profile)` has exited (the `with` wraps only `crew.kickoff`). The function calls `svc.nearby_search(...)` without `profile=`, so it fell back to `get_current_profile()` → None → `ranking_on=False`. Result: primary search path applied profile ranking; reliability-fallback path silently did NOT. Behavioral inconsistency, not a crash.
- **Fix applied** (3 edits, safe):
  - `_direct_nearby_results(..., profile: Any = None)` — added optional param (default None = back-compat).
  - Forwards `profile=profile` into `svc.nearby_search(...)`.
  - Both call sites pass `profile=profile` (variable is already in scope at both — L540 blocking, L739 stream).
- Why safe: default None preserves prior behavior; no tests exercise this fallback with a profile; restores intent stated in plan §FR-2/FR-4 ("profile truyền vào service call — 2 site") and the phase-02 task framing.
- Verified: `python -c ast.parse` clean post-edit; file 1879 LOC (was 1875; +4 net).

### LOW

**L1. `match_score` can exceed 1.0 after profile boost (cosmetic)**
- `merchant_search_service.py:182` + `:281` — `match_score += profile_score(...)` is added AFTER the base is clamped (`_calculate_match_score` returns `min(score, 1.0)` at L378).
- Max possible `match_score`: 1.0 (base name match) + 0.16 (max profile boost) = **1.16**. Min: -0.05.
- Surfaced to LLM via `to_dict()` L77 (`round(self.match_score, 3)`) and `customer_flow.py:1067`. The agent prompt at `flows/customer_flow.py:1044-1046` documents "match_score 1.0 = nearby" — an LLM seeing 1.06 has no defined semantic.
- **Not a ranking bug** — relative ordering is preserved, which is what matters for sort. Re-clamping post-boost would defeat the purpose (a 1.0 name-match + budget match would become indistinguishable from a 1.0 name-match alone). Recommend: leave as-is; if LLM confusion observed, document "match_score may exceed 1.0 when profile boosts apply" in `docs/scoring-methodology.md` or in the agent prompt.
- Plan stated "max match_score is clamped to 1.0" — that holds for the BASE only, not post-boost. Worth a docstring clarification.

**L2. `get_ranking_config()` `@lru_cache` ignores runtime settings mutations**
- `core/ranking_config.py:26` — `@lru_cache` (no args) caches the `RankingConfig` for process lifetime. Settings changes via env require restart. Already documented in docstring ("cached per process; flip via env to kill-switch"). Acceptable for kill-switch semantics — but a test that mutates `os.environ["RANKING_ENABLED"]` mid-process will NOT take effect without `get_ranking_config.cache_clear()`. No current test does this (the 10 unit tests construct `RankingConfig()` directly, bypassing the cache). Note only.

### NIT

**N1. Double `_fold` computation across `profile_score` + `should_hard_filter`**
- `merchant_search_service.py:180-182` + `:279-281` — when `hard_filter_disliked=True`, each merchant's disliked list + cuisine is folded twice (once per function). Micro-perf; at ~50 merchants × ~5 disliked × fold-cost-negligible it is not worth memoizing. Note for future if profiling shows hot-spot.

**N2. `_cuisines_overlap` substring logic could false-positive on short folded strings**
- `profile_ranking.py:43-46` — `fa in fb or fb in fa`. Edge: user dislikes "cơm" (`"com"`) would substring-match any merchant whose folded cuisine contains "com" (e.g. "com binh" — unlikely in VN cuisine domain). Practical risk low given the cuisine vocabulary. Keep as-is; revisit if false positives appear in GT eval.

**N3. `_fold` strips `mon ` prefix unconditionally**
- `profile_ranking.py:38-40` — any folded cuisine beginning with `"mon "` loses 4 chars. Intended for `"Món Việt"→"viet"`; harmless for the VN cuisine domain. Documented in docstring.

## What I fixed
- **M1** (only): applied the 3-edit wiring fix so the reliability-fallback path (`_direct_nearby_results`) honors the loaded profile. Mechanical, back-compat (default `profile=None`), no test breakage risk. See M1 above for diff rationale.

## Positive observations
- Token-based `profile_scope` reset in `finally` — correct ContextVar hygiene; no leak even on exception.
- Stream-path `profile_scope` placement INSIDE `_run_one` (not at the parent `with pool:`) is exactly right for `copy_context().run(…)` semantics — non-trivial to get right.
- Conservative defaults (max ±0.16 / -0.05, hard-filter off) — nudges, doesn't dominate. Plan correctly preferred conservative + kill-switch over heavy rewrites.
- Pure-function factorization (`profile_score`/`should_hard_filter`/`_fold`) — fully unit-testable without DB or CrewAI. Test coverage hits every branch incl. cap, single-penalty, dietary both-sides, hard-filter on/off, signals stacking.
- `_BUDGET_TO_PRICE` map is the single source of truth for the en→vi translation; folded comparison makes it diacritics-tolerant on both sides.
- Comment quality is high — explains *why* (e.g., why `_fold` strips "mon ", why hard-filter is default off, why budget maps en→vi).
- Closure capture ordering (`profile = _load_profile(...)` BEFORE `_run_one` def) is correct — Python late-binding would have bitten here otherwise.

## Recommended actions (priority order)
1. **(done)** M1 fix applied — verify on next pytest run that the 119 still pass.
2. **(optional)** L1: add a one-line note to `docs/scoring-methodology.md` that `match_score` may exceed 1.0 by up to +0.16 when profile boosts apply; OR clamp in `to_dict()` only (cosmetic display) without touching the sort-time value.
3. **(optional)** L2: if future tests need to flip `ranking_enabled` at runtime, expose `get_ranking_config.cache_clear()` in test setup.
4. **(defer)** N1/N2/N3: no action; revisit only if GT eval or profiling surfaces a real issue.

## Metrics
- **Type coverage**:~100% (all new code annotated; `Any` used only for duck-typed merchant/profile params — matches existing `_load_profile -> Any` style).
- **Test coverage**: 10 new unit tests, branch-complete for `profile_ranking`. No tests exercise the ContextVar propagation end-to-end (acceptable — the unit tests prove the math; integration tests already exercise the flow paths).
- **Linting issues**: 0 (py_compile clean post-edit; CRLF warnings only).
- **LOC discipline**: all NEW files ≤200; modified files modest (+12, +28, +12 net).

## Unresolved questions
1. **`pref_crew` ranking scope**: the preference crew (mode="preference") also runs inside `profile_scope(profile)` via `_run_one`. It does not invoke merchant_search today, so the scope is a no-op for it. If a future change makes the preference crew query merchants, both crews would share the same profile (intended). Worth noting in `docs/system-architecture.md` if preference-crew behavior evolves.
2. **Profile-scoped ContextVar for non-flow callers**: `MerchantSearchService.search/nearby_search` now reads `get_current_profile()` even when called from outside the flow (e.g., direct API or script). Default None → no-op, so safe. But if a future caller wants ranking without going through `customer_flow`, they must either pass `profile=` explicitly or set `profile_scope` themselves. Document this contract in `docs/scoring-methodology.md`?
3. **TC-07 3→0 shift** flagged by GT-eval as "moved in correct direction, not phase-02-caused" — out of scope here, but worth tracking per the tester report's open Q1.
