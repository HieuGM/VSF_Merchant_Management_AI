# Code Review — phase-04 FE cutover (localStorage → backend profile API)

Branch: `dev-a` (uncommitted working tree, 4 files)
Verdict: **APPROVE-WITH-NITS** (2 safe fixes applied; rest recommendations/nits)
Build: green per task (`tsc -b && vite build`, oxlint). Live round-trip verified.

## Scope
- `frontend/src/customer/api/customer-agent-client.ts` (+50: `UserProfile`, `ProfilePatch`, `getProfile`, `patchProfile`)
- `frontend/src/customer/hooks/use-preferences.ts` (rewrite: taste→API, geo→localStorage, +notes/+sync, debounced PATCH, one-shot migration)
- `frontend/src/customer/pages/preference-center.tsx` (+`notes` section, `SYNC_LABEL`)
- `frontend/src/customer/pages/customer-chat.tsx` (drop `preferencesToContext`; geo unchanged)

## Invariant verification
1. Race/StrictMode — **PARTIAL** (fixed). `cancelled` flag + cleanup OK; MIGRATED_KEY race window existed (see H-1). Fixed.
2. Debounced PATCH — OK. Timer cleared; TASTE-only trigger; optimistic; loading→synced/offline.
3. FE↔BE mapping — OK. snake_case PATCH, camelCase load, `budget:""↔null`.
4. Error handling — OK. 404→null; net error→offline+cache; PATCH fail→offline, next edit retries.
5. No regression — OK. 3 consumers destructure subsets; geo flow intact.
6. Migration idempotency — OK after fix. MIGRATED_KEY now set before await; no PATCH when no cached taste.
7. `preferencesToContext` — OK. `rg preferencesToContext frontend/src` → 0 matches.

## Critical
None.

## High
### H-1 — StrictMode dev double-mount CAN double-migrate (FIXED)
`use-preferences.ts:128-147` (original). `MIGRATED_KEY` was set AFTER `await patchProfile`. Two concurrent dev mounts both pass the `getItem` check, both fire `patchProfile`. Task spec claimed this was guarded — it wasn't.
- Impact: dev-only; PATCH idempotent (same fields); prod unaffected (no StrictMode double-invoke).
- Fix applied: set `MIGRATED_KEY="1"` synchronously BEFORE the await; updated comment to drop false "will retry next load" claim (it never did — flag was set even after swallowed failure). No behavior change re: retries (identical before/after); only closes the race.

### H-2 — `patchTimer` not cleared on unmount (FIXED)
`use-preferences.ts`. No cleanup cleared the pending 500ms timer. User toggles then navigates within 500ms → timer fires post-unmount → wasted fetch + `setSync` on gone component.
- Impact: low (React 19 silently no-ops the setState); mostly a hygiene + minor network leak.
- Fix applied: added a mount `useEffect` returning `() => { if (patchTimer.current) clearTimeout(patchTimer.current); }`.

## Medium
### M-1 — In-flight PATCH not aborted on unmount (recommendation only)
Even with H-2, a PATCH already past the timer (fetch in flight) continues after unmount. Consider passing an `AbortController` signal into `patchProfile` and aborting on unmount. The `streamChat` API already takes a `signal`, so the pattern exists. Not applied — would change `patchProfile` signature (diverges from `confirmDelta`/`rejectDelta` sibling APIs).

### M-2 — Cross-tab `storage` listener ignores `notes`/`sync`
`use-preferences.ts:~212`. When tab B PATCHes (→ persist → storage event), tab A updates `prefs` only; `notes`/`sync` don't refresh. Slow-changing data, acceptable. Note only.

### M-3 — `schedulePatch` async callback can call `setSync` after unmount
Counterpart of M-1: timer fired, fetch resolves after unmount → `setSync` on gone component. React 19 no-ops silently. Cheap mitigation: a `mountedRef.current` guard at the top of the timer callback. Not applied (low impact; would add another ref). Acceptable as-is.

## Low / Nits
- **L-1**: `profileToTaste` casts `budget_level as Budget` without validation. Backend returning unexpected value (e.g. "luxury") → no chip selected, value preserved in state. Cosmetic. (use-preferences.ts:75)
- **L-2**: PATCH body always sends all 4 taste fields (snapshot), not just changed ones. Idempotent server-side; ~a few extra bytes. Acceptable simplification.
- **L-3**: `ProfilePatch` type lists `distance_preference_km` but FE never sends it. Dead-ish. Drop or keep for future. (customer-agent-client.ts:202)
- **L-4**: `notes` list key `${i}-${n.slice(0,12)}` (preference-center.tsx:189) — fragile if 2 notes share the first 12 chars. Use stable id when backend supplies one.
- **L-5**: `load` effect deps `[]` — fine because `getCustomerUserId()` is stable per browser identity. If a "reset identity" feature ever lands, this hook won't re-load. Not a current issue.
- **L-6**: `MIGRATED_KEY` is per-browser, not per-user. Multi-user-per-browser (rare for anon app) → 2nd user won't migrate. Acceptable edge.
- **L-7**: GET /profile 404 logs as browser console "error" for new users (known benign). Suggest a one-line code comment near `getProfile` noting this is expected and handled, so future reviewers don't chase it.

## Positive observations
- `getProfile` returns `null` on 404 (not throw) — clean separation of "no profile yet" vs network failure.
- TASTE vs GEO field split is crisp: `TASTE_KEYS` gate on the API path; geo stays local.
- `cancelled` flag in load effect correctly suppresses set-state after unmount.
- `schedulePatch` clears prior timer → rapid toggles coalesce to one PATCH (last-write-wins). ✓
- StrictMode consideration present in chat (`seededRef`) — author clearly aware of the dev double-mount.
- `data-sync` attribute on the status line enables CSS state styling without extra classes.
- Notes section gated on `notes.length > 0` — clean empty state.
- snake_case/camelCase mapping confined to two pure fns (`profileToTaste`, `tasteToPatch`) — easy to test.

## What I changed
1. `use-preferences.ts` migrate block: `MIGRATED_KEY` set BEFORE `await patchProfile` (closes H-1 StrictMode race); comment corrected (no longer claims retry).
2. `use-preferences.ts`: added unmount `useEffect` clearing `patchTimer` (H-2).

Both edits are TypeScript-safe and behavior-preserving for the mounted happy path. No re-build run (task said green; changes are pure logic/comment moves).

## Unresolved questions
1. Should `patchProfile` accept an `AbortSignal` (M-1)? Would align with `streamChat` but diverge from `confirmDelta/rejectDelta`. Your call.
2. Backend `budget_level` validation surface — is an unexpected string a 422 or silently stored? Affects whether L-1 needs a guard.
3. Notes source-of-truth across tabs (M-2) — acceptable stale-till-reload, or wire a `storage`-event refresh?
