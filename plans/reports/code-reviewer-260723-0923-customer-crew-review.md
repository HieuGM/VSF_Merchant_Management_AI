# Code Review — Customer Discovery Crew (Phases 1-7)

Date: 2026-07-23 · Reviewer: code-reviewer · Branch: develop (uncommitted)
Plan: plans/260722-1550-full-customer-discovery-crew/plan.md

## Scope
Adapter, crew assembly, listener, flow, 3 repos, 2 services, weather provider, 3 customer tool
modules, task models, modified core/{cache,errors,settings}, registry, 2 yaml. ~1000 LOC new.
53 tests pass (unit+contract+integration; DB integration skips when Postgres down).

## Overall
Solid, contract-disciplined implementation. All 7 guardrails hold and most are enforced by
tests, not just code. No critical/security issues. SQL-injection fix confirmed correct. Findings
are robustness/observability polish, not blockers.

## Guardrail verification (all PASS)
1. No session to agents — tools open/close own `SessionLocal` + `finally`; repos that take a
   `Session` are constructed inside tools. Enforced by `test_tools_take_no_db_session`. ✓
2. `propose_profile_delta` proposal-only — reads profile, delegates to pure `preference_service`,
   no writes; `has_side_effect=False`. Enforced by `test_propose_profile_delta_does_not_persist`
   (asserts `preference_events` count unchanged). ✓
3. Delegation 1-hop — coordinator `allow_delegation: true`, 3 specialists `false`; enforced by
   `test_only_coordinator_delegates`. ✓
4. Allow-list ↔ yaml ↔ ToolSpec sync — registry cross-checks `allowed_agents` vs `allow_list.py`
   on register; `test_allow_list_sync` diffs yaml vs table; tools derive via `agents_allowed_for`. ✓
5. Weather degrades — provider catches all exceptions → `None`; tool returns `weather: null`.
   Enforced by `test_http_failure_degrades_to_none`. ✓
6. Tools return string, never raise — adapter double-`except` + `json.dumps(default=str)`.
   Enforced by `test_run_error_becomes_string_not_raise`. ✓
7. No LangChain — `test_no_langchain` (crewai reqs + import side-effects). ✓

## Security
- SQLi (merchant search): FIXED correctly. `search_merchants` escapes LIKE metachars
  (backslash-first, then `%`/`_`) and passes `escape="\\"`; all filters are ORM-parameterized. No
  string interpolation into SQL anywhere reviewed. ✓
- No secrets logged: `input_hash` stores a sha256 prefix, never raw payloads. ✓
- Weather HTTP has 3s timeout; no SSRF surface (lat/lng only, fixed host). ✓

## Threading note (investigated, NOT a bug)
CrewAI event bus dispatches sync handlers on a ThreadPoolExecutor but wraps each submit in
`contextvars.copy_context()`, so the `run_scope` ContextVar propagates into handler threads —
trace_id binding is correct even under the thread pool, and concurrent flows stay isolated.
Handler exceptions are caught by the bus (`is_call_handler_safe`, console-print only), so a DB
write failure in the listener will NOT crash the crew. See "Medium #4" for the flip side.

## Medium
1. **Naive/aware datetime mix in `finish_run`** (agent_run_repository.py:70). Fallback
   `datetime.utcnow()` is naive while `_parse_ts` yields tz-aware (from isoformat). Same column
   gets both flavors → possible `TypeError` on aware/naive comparison or inconsistent storage.
   Use `datetime.now(timezone.utc)`.
2. **Manager agent assigned tools** (customer_crew.py:62). `customer_coordinator` is
   `manager_agent` in `Process.hierarchical` AND gets `get_user_profile`/`get_session_candidates`.
   Some CrewAI versions ignore or reject manager tools (manager is meant to delegate, not act).
   Build succeeds, but no test proves the manager can actually invoke these at kickoff — verify
   at runtime, else move those tools onto a specialist and let the manager delegate.
3. **Listener field mapping is unvalidated** (persisting_listener.py). Handlers pull
   `event.agent_role`, `event.tool_name`, `event.tool_args`, `event.task.agent.role` via `getattr`
   with silent `None` fallback. If any attribute name differs from the real CrewAI event schema,
   rows persist with all-null fields and nobody notices (no unit test feeds real event objects).
   Add a test constructing real CrewAI event instances and asserting mapped fields are non-null.
4. **Event persistence is fire-and-forget + swallowed errors.** Combined with the threading note:
   a transient DB error while writing an `agent_event` is logged to console only, event lost, no
   retry, and ordering vs `run_finished` is not guaranteed. Acceptable for observability but
   document it; consider a bounded retry or a dropped-event counter.
5. **`get_weather_context` reports `"cached": False` unconditionally** (weather_tools.py:29). The
   provider caches internally and the tool can't reflect a cache hit, so this observability field
   is always wrong. Either drop it or have the provider return a cache flag.

## Low
1. `tools/customer/__init__.py` now does `from tools.customer.merchant_tools import register` —
   pointless and misleading: `auto_discover` iterates submodules, never the package-level symbol.
   Adds an import side-effect. Revert to docstring-only.
2. `create_run` uses `db.merge` (SELECT+upsert) where a plain insert suffices; masks accidental
   duplicate trace_id and adds a round-trip.
3. Per-event `SessionLocal`+commit → N short transactions per run. Fine now; batch later if event
   volume grows.
4. `_RAIN_CODES = set(range(80,100))` includes non-WMO codes 83-94 (harmless); snow 71-77 falls to
   "other"/not-rain (acceptable but note).
5. Flow's registry-discovery guard is coarse (all-or-nothing per package). Works only because all
   customer tools live in one package; adding a tool to a partially-registered package would skip
   it. Guard on the specific tool being registered, or make `register` idempotent.
6. NIM routing depends on `settings.llm_provider` (default "openai") to build the model prefix
   `openai/meta/llama-...` + `base_url`. Plan specified litellm `nvidia_nim/` provider; deviation
   is documented in settings comment, but setting `LLM_PROVIDER` would silently misroute NIM.
   Consider hardcoding the NIM prefix in `_nim_llm` rather than reusing `llm_provider`.

## Test gaps
- Listener event-field mapping untested against real CrewAI events (see Medium #3) — highest-value
  gap; current tests only exercise the flow's own run_started/run_finished, not tool/task handlers.
- No concurrent-run isolation test (two overlapping `run_scope`s → distinct trace_ids).
- No test proving manager_agent's allow-listed tools are usable at kickoff (only structural asserts
  on specialists).
- Real adapter→tool→DB path inside a crew kickoff is only covered via a mock crew (understandable;
  needs a live/fake LLM driving tool calls). Consider a scripted fake LLM that emits one tool call.

## Positive
- Clean single CrewAI coupling point (tool_adapter) keeps tools/services framework-agnostic.
- Adapter's `default=str` + double-except is a robust "never crash the loop" boundary.
- Guardrail-2 and weather-degrade have explicit dedicated tests — good instinct.
- Registry↔allow-list↔yaml triple-sync with a contract test is a strong anti-drift design.
- Files are small and well under the 200-line rule; docstrings state the contract each module owns.

## Unresolved questions
1. Does the running CrewAI version actually let a hierarchical `manager_agent` invoke its own tools,
   or does it drop them? (Medium #2 — needs a live kickoff to confirm.)
2. Are `ToolUsageStartedEvent.agent_role/tool_name/tool_args` and `TaskStartedEvent.task.agent.role`
   the correct attribute names for CrewAI 1.15.5? (Medium #3 — confirm against event dataclasses.)
