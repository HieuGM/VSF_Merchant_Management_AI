# Phase 02 — Search-Call Instrumentation Logger (D2)

## Context Links

- Active plan: `plans/260811-1431-hybrid-search-yagni-coordinator-expansion/plan.md`
- Search tools (injection points): `backend/tools/customer/merchant_tools.py:61-131` (`merchant_search`), `:134-194` (`nearby_merchant_search`)
- Existing observability: `backend/database/models.py:396-407` (`InteractionEvent` — has NOT NULL `user_id` FK, NOT suitable for anonymous logging)
- Existing event table: `backend/database/models.py:442-458` (`AgentEvent` — task/tool trace, NOT a search-args dump)
- Settings: `backend/core/settings.py:18-90`

## Overview

Priority: P2. Status: pending. Effort: 2h.

Log every `merchant_search` / `nearby_merchant_search` invocation to a JSONL file: timestamp, session/user id if available, the LLM-decomposed args (query, cuisine, city, min/max_price, min_rating, lat/lng/radius, exclude_merchant_ids), result count, was-empty flag, and a placeholder `hybrid_flag` for the future vector leg. Purpose: 1-week recall-gap analysis to justify/kill the vector leg. Pure logging, no behavior change, GT-neutral.

## Key Insights

1. **Why JSONL file over DB table**:
   - `interaction_events` has NOT NULL `user_id` FK to `user_profiles` → anonymous sessions would violate the constraint or require a sentinel user row.
   - New DB table = migration → review/approve overhead, contract-change protocol.
   - JSONL is append-only, rotation-trivial, requires zero schema work, and a week of data is small (~thousands of rows).
2. **GT-neutrality proof**: the logger runs AFTER results are computed and BEFORE return; it has no effect on ranking, filtering, or which merchants are returned. Wrapped in `try/except` and never raises — even a disk-full error degrades to skipped log, not broken search.
3. **The `hybrid_flag` placeholder**: every log row carries `hybrid_flag: null`. When/if a vector leg ships, this becomes `{vector_recall: N, rrf_k: 60}` or similar — letting us compare recall pre/post on the same query stream without re-instrumenting.

## Requirements

### Functional
- FR1: Every call to `merchant_search` and `nearby_merchant_search` emits one JSONL row.
- FR2: Row contains: `ts` (UTC ISO), `tool`, `session_id`, `user_id`, `args` (the full kwargs dict minus internals), `result_count`, `was_empty`, `hybrid_flag: null`.
- FR3: Logger never raises — all I/O failures caught and logged via stdlib `logging.warning`.
- FR4: Feature-flagged via `settings.search_call_logging_enabled` (default OFF in prod, ON in dev — but additive so safe either way).

### Non-functional
- NFR1: <50 LOC logger module.
- NFR2: O(1) per call (one append, no read).
- NFR3: No DB connection, no schema migration.

## Architecture

```
merchant_search(*args)         nearby_merchant_search(*args)
        │                              │
        ▼                              ▼
  service.search(...)            service.nearby_search(...)
        │                              │
        ▼                              ▼
   results: list                  results: list
        │                              │
        └──────────┬───────────────────┘
                   ▼
        log_search_call(             ◄── new helper (services/search_call_logger.py)
          tool="merchant_search",         wraps Path.open("a") + json.dumps + "\n"
          args={...},                     target: <repo_root>/logs/search_queries.jsonl
          result_count=N,
          was_empty=N==0,
          session_id=ctx_session_id,
          user_id=ctx_user_id,
        )  # try/except — never raises
                   │
                   ▼
              return {...}     (existing return value, unchanged)
```

`session_id`/`user_id` retrieval: read the `tool_call_scope` ContextVar set by `agents.tool_adapter` (already set when CrewAI invokes the tool). If unavailable (script/manual call) → `None`. The logger doesn't fail on None.

## Related Code Files

### Modify
- `backend/tools/customer/merchant_tools.py` — wrap the final return of `merchant_search` (line 113-129) and `nearby_merchant_search` (line 178-192): compute `result_count`, call `log_search_call(...)`, return unchanged. ~3 lines per function. Tool signatures UNCHANGED.
- `backend/core/settings.py` — add `search_call_logging_enabled: bool = True` (default ON — it's pure logging, cheap, and we want data immediately; flip OFF via env if needed).

### Create
- `backend/services/search_call_logger.py` (NEW, <80 LOC):
  ```python
  """Append-only JSONL logger for merchant_search/nearby_merchant_search calls.
  
  Purpose: 1-week recall-gap analysis to justify/kill the deferred vector leg.
  Pure side-effect — no ranking/filter/behavior change. GT-neutral.
  Never raises: all I/O failures caught + logged via stdlib logging."""
  
  import json, logging, os
  from datetime import datetime, timezone
  from pathlib import Path
  
  _LOG = logging.getLogger(__name__)
  _DEFAULT_PATH = Path(__file__).resolve().parents[2] / "logs" / "search_queries.jsonl"
  
  def log_search_call(*, tool: str, args: dict, result_count: int,
                      session_id: str | None = None, user_id: str | None = None,
                      hybrid_flag: dict | None = None,
                      sink: Path | None = None) -> None:
      """Append one JSON row. Never raises."""
      try:
          sink = sink or _DEFAULT_PATH
          sink.parent.mkdir(parents=True, exist_ok=True)
          row = {
              "ts": datetime.now(timezone.utc).isoformat(),
              "tool": tool,
              "session_id": session_id,
              "user_id": user_id,
              "args": _scrub(args),
              "result_count": result_count,
              "was_empty": result_count == 0,
              "hybrid_flag": hybrid_flag,  # placeholder — null until vector leg ships
          }
          with sink.open("a", encoding="utf-8") as f:
              f.write(json.dumps(row, ensure_ascii=False) + "\n")
      except Exception as exc:  # noqa: BLE001 — never break search
          _LOG.warning("search_call_log_failed tool=%s: %s", tool, exc)
  
  def _scrub(args: dict) -> dict:
      """Drop None values + cap exclude_merchant_ids length for log compactness."""
      out = {k: v for k, v in args.items() if v is not None}
      if "exclude_merchant_ids" in out and isinstance(out["exclude_merchant_ids"], list):
          out["exclude_merchant_ids_count"] = len(out["exclude_merchant_ids"])
          out["exclude_merchant_ids"] = out["exclude_merchant_ids"][:10]  # cap
      return out
  ```
- `backend/tests/unit/test_search_call_logger.py` (NEW) — use `tmp_path` sink, assert row shape + that a forced IO error doesn't raise.

### Delete
- None.

## Implementation Steps

1. Create `backend/services/search_call_logger.py` per sketch above.
2. Add `search_call_logging_enabled: bool = True` to `Settings`.
3. In `merchant_tools.py` `merchant_search`: before the `return` block (line 114), compute `count = len(results)`, then:
   ```python
   if get_settings().search_call_logging_enabled:
       from services.search_call_logger import log_search_call
       log_search_call(
           tool="merchant_search",
           args={k: v for k, v in locals().items() if k in {...}},  # or build dict explicitly
           result_count=count,
           session_id=_ctx("session_id"),  # helper reading tool_call_scope
           user_id=_ctx("user_id"),
       )
   ```
   Repeat for `nearby_merchant_search`. (Build the args dict explicitly for clarity, not via `locals()`.
4. Add `logs/.gitignore` (one line `search_queries.jsonl`) — keep logs out of git.
5. Unit tests with `tmp_path` sink: assert row schema, assert IO failure doesn't raise, assert flag-OFF path skips.
6. Run: `PYTHONPATH=backend C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe -m pytest backend/tests/unit/test_search_call_logger.py -v`.

## Todo List

- [ ] Create `services/search_call_logger.py`
- [ ] Add `search_call_logging_enabled` setting
- [ ] Wire `log_search_call` into `merchant_search` + `nearby_merchant_search`
- [ ] Read `session_id`/`user_id` from `tool_call_scope` ContextVar (helper)
- [ ] Add `logs/.gitignore`
- [ ] Unit tests (row schema + IO-failure-is-safe + flag-OFF skip)

## Log Schema (canonical)

```json
{
  "ts": "2026-08-11T07:30:00.123+00:00",
  "tool": "merchant_search" | "nearby_merchant_search",
  "session_id": "string|null",
  "user_id": "string|null",
  "args": {
    "query": "string|null",
    "cuisine": "string|null",
    "city": "string|null",
    "min_price": "int|null",
    "max_price": "int|null",
    "min_rating": "float|null",
    "lat": "float|null",
    "lng": "float|null",
    "radius_km": "float|null",
    "exclude_merchant_ids": ["..."] (capped @10),
    "exclude_merchant_ids_count": "int|null"
  },
  "result_count": 5,
  "was_empty": false,
  "hybrid_flag": null
}
```

## Success Criteria

- 1 week of `logs/search_queries.jsonl` rows accumulates without errors.
- `was_empty=true` rate computable per-cuisine/per-city → real recall-gap signal.
- All existing customer-crew + search-service tests pass unchanged (proves GT-neutrality).
- Forced IO failure (chmod read-only sink) → search returns normally, logger emits stdlib warning only.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Log grows unbounded | M | L | JSONL is tiny (~300B/row); 1 wk @ 1k calls/day = ~2MB; rotate weekly via external logrotate or manual `mv` |
| PII leak via `query` field | M | M | `query` is user text — could carry PII; mitigate by NOT redacting in logger (the DB already stores raw `chat_messages.text` PII-unredacted for the same session), but DOCUMENT in module docstring that the log file is PII-bearing and access-restricted |
| Logger raises → breaks search | L | H (GT regression) | try/except swallowing + unit test asserting non-raise on IO failure |
| ContextVar not set (script call) → KeyError | M | L | Helper returns None gracefully |

## Security Considerations

- **PII**: `query` field carries raw user text. The log file is PII-bearing. Mitigations: (a) `logs/.gitignore` keeps it out of git; (b) document access restriction in module + `logs/README.md`; (c) for prod hardening, add a `redact_pii` call (already exists at `backend/core/pii.py`) — recommend doing this in a follow-up, not blocking ship.
- **No external network** — pure local file append.
- **No credentials logged** — args never include API keys.

## Next Steps

- After 1 week: analysis script `backend/scripts/analyze_search_recall.py` (out of scope here) reads JSONL, groups by cuisine/city, reports `was_empty` rate + zero-result query clusters → the data-driven justification (or kill signal) for the deferred vector leg.
- If vector leg ships: `hybrid_flag` field gets populated with `{vector_recall: N, ...}` for A/B comparison.

## Open Questions

1. **Log retention**: rotate weekly? Cap at N MB? Auto-truncate after analysis? Suggest weekly rotation, manual delete post-analysis.
2. **PII redaction at write time** vs at-analysis-time? Recommend at-analysis-time (keeps logger hot-path simple) but document.
3. **`session_id`/`user_id` from ContextVar** — verify `tool_call_scope` from `agents.tool_adapter` propagates these (need to read that file). If not, accept None and rely on `trace_id` correlation via `agent_events` later.
