# Code Review — phase-01 unify customer preference/memory store

**Scope:** phase-01 of unify-profile plan (static review; pytest 107/0 + GT 39/39 PARITY pre-confirmed green).
**Branch:** dev-a. **Verdict: APPROVE-WITH-NITS.** All 7 invariants hold; findings are doc/claim mismatches + minor hardening — no blocker.

## Files in scope
| File | LOC | Note |
|---|---|---|
| `backend/core/dependencies.py` | 73 | +`require_dev_only` IDOR guard |
| `backend/models/agent.py` | 157 | +`ProfilePatchRequest` DTO |
| `backend/repositories/user_profile_repository.py` | 191 | refactor + `apply_fields` |
| `backend/routes/user_routes.py` | 163 | GET/PATCH wired, IDOR on 3 writes |
| `backend/services/user_profile_service.py` | 72 | NEW |
| `backend/tests/contract/test_api_stubs.py` | 60 | GET un-stubbed + impl test |
| `backend/scripts/eval_ground_truth.py` | — | harness-only fix |

All ≤200 LOC (rule §6). Kebab-case + comments OK.

## Invariant verification
1. **§7.1 propose-only** — PASS. `services/preference_service.py` unchanged (pure, no DB session). `customer_context_tools.py` untouched. `apply_fields`/`apply_delta` both reached only via explicit write routes. Shared helpers (`_resolve_value`/`_apply_resolved`/`_get_or_create_row`) do not weaken the seam.
2. **B5 typed validation** — PASS. `apply_fields` resolves ALL fields via the SAME `_resolve_value` as `apply_delta` (DRY, no drift). Dict-comp aborts on first bad field → no partial state → row not yet touched → atomic. Empty patch → ValueError → 400.
3. **IDOR guard** — PASS. `require_dev_only` 403s if `environment.lower() ∈ {production, prod}`, warns+allows otherwise. Applied to PATCH/confirm/reject; NOT to GET. Uses existing `settings.environment` (no new field). `_PROD_ENVS` frozenset at `dependencies.py:29`.
4. **Atomic tx + no leak** — PASS with caveat (see M1). `SessionLocal()` opened, closed in `finally`. `apply_fields` commit-before-audit (matches confirm path).
5. **Whitelist** — PASS-security, FAIL-claim (see M2). Defense-in-depth: pydantic DTO bounds body → repo `_APPLY_*` sets final backstop → unknown field raises ValueError → 400. `user_id`/PK/`updated_at` unwritable.
6. **Files ≤200 LOC** — PASS.
7. **Harness-only fix** — PASS. `CAST(:p AS jsonb)` is bindparam-bound (no injection); `message_id=new_id("msg")` mirrors production (`chat_message_repository.py:51`); branch was dormant in baseline so activating it can't regress measured semantics.

## Findings

### MEDIUM

**M1. Audit append is NOT actually best-effort — comment lies; partial-audit risk on multi-field patch**
- `backend/services/user_profile_service.py:52-65`
- Comment: *"audit is best-effort observability and never blocks the edit"* — false. `events.append()` raises → propagates → HTTP 500 (profile row already committed by `apply_fields`). User sees failure despite successful mutation → likely retry → duplicate `set` (idempotent for `set`, but audit trail grows).
- Multi-field patch loop: each `append()` does its own `add`+`commit`. If append N fails mid-loop, appends 1..N-1 are persisted, N..end missing → **partial per-field audit trail** (breaks the "per-field audit trail" rationale in docstring). Single-event `confirm` doesn't have this issue; multi-event PATCH does.
- Concrete fix (choose one):
  ```python
  # Option A — make comment true (best-effort):
  for field, value in patch.items():
      try:
          events.append(user_id=user_id, session_id=None, field=field,
                        operation="set", value=value, scope="confirmed_global",
                        source="user_edit", status="confirmed", evidence_refs=[])
      except Exception:
          logger.exception("user_profile audit append failed user_id=%s field=%s", user_id, field)
  ```
  Option B — atomic audit tx (one commit for the whole loop) is harder since `PreferenceEventRepository.append` self-commits; would need a `append_many` variant. Recommend A.
- Why not auto-fix: behavioral (log-and-continue vs raise). Lead's call.

**M2. `ProfilePatchRequest` silently ignores unknown body fields — violates invariant #5 "PATCH rejects unknown fields (400)"**
- `backend/models/agent.py:121-137` + `backend/routes/user_routes.py:66-90`
- Pydantic v2 default is `extra='ignore'`. Body `{"user_id":"other","liked_cuisines":["phở"]}` → unknown `user_id` silently dropped, request succeeds. Security property holds (repo backstop + DTO bounds), but claim "rejects unknown (400)" is wrong.
- Concrete fix:
  ```python
  from pydantic import BaseModel, ConfigDict, Field
  class ProfilePatchRequest(BaseModel):
      model_config = ConfigDict(extra="forbid")
      ...
  ```
  Yields 422 (FastAPI standard) on unknowns, not 400. Both 4xx; either reword invariant to "rejects with 4xx" or wrap `RequestValidationError` to map → 400.
- Why not auto-fix: behavioral contract change (FE currently sending extras would break). Recommend lead decide.

### LOW

**L1. Contract test GET-half needs live DB; docstring claims "without a DB write"**
- `backend/tests/contract/test_api_stubs.py:27-37`
- `client.get(.../profile)` → `user_profile_service.get_profile` → `SessionLocal()` directly (conftest only overrides `get_db_session`, not `SessionLocal`). If Postgres down → test errors (not 404). PATCH-half is DB-free (route guards empty before service). Docstring "without a DB write" only true for PATCH half.
- Non-blocking (CI has DB); flag for accuracy.

**L2. `require_dev_only` prod-block (403) branch has no direct unit test**
- `backend/core/dependencies.py:52-73`
- Contract test accidentally exercises the dev-allow path. The 403 prod branch (the actual security guarantee) is uncovered. Recommend a unit test monkeypatching `get_settings().environment="production"` asserting PATCH/confirm/reject → 403.

**L3. Test coverage gap on PATCH field validation**
- No test exercises PATCH with valid fields → 200, bad enum → 400, scalar-on-list → 400, list-replace semantics. Contract test only covers empty-body 400. Repo-level validation is covered for `apply_delta` in `test_customer_memory_wireup.py` but NOT for `apply_fields`. Recommend adding repo unit tests for `apply_fields` mirroring the `apply_delta` tests at lines 412-447.

**L4. `request.client.host` is proxy IP when behind reverse proxy**
- `backend/routes/user_routes.py:81` (and existing confirm/reject)
- Not a regression; same pattern already shipped for confirm/reject. Note for future X-Forwarded-For handling — out of phase-01 scope.

### NIT

**N1. Harness local import**
- `backend/scripts/eval_ground_truth.py:177` — `from core.tracing import new_id` inside function. Works; mildly inconsistent with module-level import style. Not worth churn.

**N2. `ProfilePatchRequest` docstring "List fields REPLACE on set"**
- Accurate; could clarify "REPLACE on PATCH (always 'set' semantics)" since this DTO is patch-only. Cosmetic.

## What I auto-fixed
Nothing. Both candidate fixes (M1 try/except, M2 `extra='forbid'`) are behavioral contract changes — left to lead per task spec ("anything behavioral/ambiguous → recommendation").

## Positive observations
- Clean DRY refactor: `_resolve_value`/`_apply_resolved`/`_get_or_create_row` shared by both write paths — drift impossible by construction.
- Atomic validation-then-apply pattern in `apply_fields` is correct (dict-comp + post-resolution write).
- IDOR guard placement is precise (3 writes, NOT GET) — matches read-only nature of GET.
- Defense-in-depth on field whitelist (DTO → route whitelist for confirm → repo `_APPLY_*`).
- Harness fix has clear comment explaining the two latent bugs + why they didn't surface in baseline.
- Pre-existing `preference_confirm_service` patterns mirrored (singleton, `SessionLocal` in `finally`, ValueError→400 mapping) — consistent.
- No PII regression: route logs field NAMES + IP, not field VALUES.

## Recommended actions (priority order)
1. **(M2)** Add `model_config = ConfigDict(extra="forbid")` to `ProfilePatchRequest` OR reword invariant #5. Decides the PATCH contract before FE wires in.
2. **(M1)** Wrap audit loop in try/except (Option A) OR rewrite docstring to drop "best-effort" claim. Multi-field partial-audit risk is real (low-probability).
3. **(L3)** Add repo-level `apply_fields` tests mirroring existing `apply_delta` tests.
4. **(L2)** Add a `require_dev_only` prod-mode 403 unit test — covers the actual security guarantee.
5. **(L1)** Tighten contract-test docstring OR add `_require_db()` skip guard like integration tests.

## Metrics
- LOC reviewed: 6 modified + 1 new ≈ 471 LOC delta (208 added/58 removed per `git diff --stat`).
- Type safety: mypy not run; static read shows no obvious holes. `Any` in `apply_fields(patch: dict[str, Any])` is acceptable (DTO-owned).
- Tests: 107/0 + GT 39/39 (pre-confirmed; not re-run per task).
- Lint: not run; quick scan shows no obvious issues.

## Unresolved questions
1. **(M2)** Is the intent "PATCH 400 on unknowns" or "PATCH silently drops unknowns"? Pydantic default ≠ task invariant #5. Need lead decision before FE contract is frozen.
2. **(M1)** For multi-field PATCH, is per-field audit (current — N rows, partial on failure) desired, or single-row audit (one event summarizing the patch)? Docstring claims per-field; partial-audit may be tolerable given idempotent `set` semantics.
3. (Out of scope) `client.host` proxy handling is system-wide; defer to a dedicated proxy-middleware task?
