# Merchant Input Preparation and Realtime Trace Design

**Status:** Approved design pending user review

## Goal

Make every Merchant Advisor turn easy to inspect while reducing unnecessary
Coordinator, agent, tool, and LLM work.  The run must first turn the user's
message and durable conversation state into one complete, standalone request.
The Coordinator then plans and delegates only when a fresh, non-trivial
investigation is actually required.

## Non-goals

- This does not expose or manufacture hidden chain-of-thought.
- This does not make the Input Layer a planner, tool selector, specialist, or
  business analyst.
- This does not tune implementation against the existing golden dataset.
- This does not show unredacted secrets in the developer dashboard.

## Execution Architecture

```text
HTTP request
  -> Load compact history, session snapshot, selected public merchant, owner context
  -> Input Analyzer (small model, no tools)
  -> Deterministic scope/privacy/freshness validation
  -> reject | clarify | fast_answer | direct_lookup | coordinate
  -> persist response, session state, and trace
```

The Coordinator no longer resolves pronouns, reconstructs past turns, or
decides whether a basic lookup can bypass orchestration.  It receives a
prepared request and compact history, then performs only planning, delegation,
observation handling, and final synthesis.

### Input Analyzer

The Input Analyzer runs for every user turn.  It receives:

- raw user message;
- at most three compact history turns;
- a bounded session snapshot containing pending HITL and the selected public
  merchant, when present;
- the active owner merchant's minimal context (ID, city, location presence).

It has no tools and returns strict JSON matching `PreparedRequest`:

```json
{
  "rewritten_query": "Standalone Vietnamese request with resolved references.",
  "request_kind": "public_hours",
  "resolved_references": [
    {
      "kind": "public_merchant",
      "merchant_id": "68814",
      "name": "Dì Bảy - Bún Mắm & Bún Bò Huế",
      "source": "session.selected_public_merchant",
      "confidence": "high"
    }
  ],
  "scope_candidate": "allowed",
  "missing_context": [],
  "proposed_outcome": "direct_lookup"
}
```

Allowed `request_kind` values are `public_menu`, `public_hours`,
`owner_analysis`, `market_search`, `owner_profile`, and `general`.  Allowed
`proposed_outcome` values are `clarify`, `direct_lookup`, and `coordinate`.
`reject` and `fast_answer` are only assigned by deterministic code.

The analyzer may only resolve context, classify this small request kind,
rewrite the query, identify missing context, and suggest a route.  It must not
name tools, agents, capabilities, plans, data findings, recommendations, or
business conclusions.

### Deterministic Routing Authority

After parsing `PreparedRequest`, application code applies policy in this order:

1. Reject empty, malformed, or explicit out-of-scope/unsafe requests.
2. Apply merchant-data privacy policy.  It always overrides the analyzer's
   `scope_candidate`.
3. Return `clarify` when a necessary entity or constraint is unresolved or
   low-confidence.
4. Return `fast_answer` only for facts whose source metadata declares them
   immutable and valid in the current session.  No merchant menu, hours,
   rating, availability, operational metric, review, or search result may take
   this route.
5. Return `direct_lookup` only for a high-confidence resolved public merchant
   and one whitelist request kind: `public_menu` or `public_hours`.  It invokes
   exactly one current-read detail tool and never kicks off CrewAI.
6. All remaining accepted requests go to `coordinate`.

`direct_lookup` is intentionally not a cache answer.  The direct detail tool
reads current application data, may use its existing read-through cache, and
emits the cache status in the trace.  Its response is fresh relative to the
data source rather than to the conversation history.

### Coordinator Contract

The Coordinator receives only:

```json
{
  "rewritten_query": "...",
  "resolved_references": [],
  "compact_history": [],
  "owner_context": {}
}
```

It does not receive the raw query as a second, competing instruction.  It may
plan, delegate named work to the native specialists, observe tool results, and
produce the final synthesis.  It must not delegate when the prepared request
has already been routed as `reject`, `clarify`, `fast_answer`, or
`direct_lookup`.

## Prompt Budgets and Contents

Prompts must be complete enough to preserve turn context but bounded enough to
avoid repeating entire session history, raw tool observations, or duplicate
instructions.

| Prompt | Required content | Dynamic input budget | Output budget |
|---|---|---:|---:|
| Input Analyzer | role boundary, strict JSON schema, allowed enum values, no-planning rule, raw query, 3 compact turns, bounded session and owner context | <= 1,600 tokens | <= 300 tokens |
| Coordinator | planning/delegation contract, policy boundary, terminal output schema, rewritten query, resolved references, 3 compact turns, owner context | <= 2,400 tokens excluding static instructions | <= 700 tokens per coordinator call |
| Specialist | role objective, allow-listed tools, evidence/output constraints, delegated task, only the bounded observation relevant to that task | <= 1,800 tokens | <= 500 tokens |
| Final synthesis | grounded-answer contract, requested response format, bounded verified findings only | <= 1,400 tokens | <= 600 tokens |

All prompts use temperature 0.  Before insertion, dynamic fields are
structured, redacted, deduplicated, and bounded: raw user query <= 600
characters; compact history <= 1,200 characters total; session context <= 500
characters; owner context <= 300 characters; individual tool observation <=
1,000 characters.  A truncation marker is explicit.  Prompts never include
the complete trace or raw historical tool outputs.

The raw developer trace stores the exact bounded prompt sent by the
application, the actual model/provider output when available, and the parsed
structured result.  Provider-hidden reasoning is represented as
`not_available`, never fabricated.

## Realtime Trace Contract

Each run obtains `trace_id` before context loading.  The trace collector gives
every event an increasing `seq`, `span_id`, `parent_span_id`, phase, actor,
compact display summary, metrics, and bounded debug payload.

```json
{
  "trace_id": "tr-example",
  "seq": 12,
  "span_id": "tool-4",
  "parent_span_id": "agent-market-1",
  "phase": "tool",
  "kind": "finished",
  "actor": {
    "type": "tool",
    "name": "get_public_merchant_detail",
    "requested_by": "market_search"
  },
  "display": {
    "title": "Đọc giờ mở cửa và menu",
    "summary": "Đã nhận 18 món; giờ mở cửa 10:00–22:00",
    "status": "ok"
  },
  "metrics": {"latency_ms": 42, "token_usage": null},
  "debug": {"args": {}, "raw_output": {}}
}
```

For every operation, `span_started` is sent through SSE immediately and
`span_finished` updates the same row.  The UI never waits for the complete run
or reloads the persisted trace to display a newly emitted span.  The collector
deduplicates overlapping CrewAI SDK and gateway callbacks into one semantic
tool span.

The compact timeline displays only title, summary, actor, parent/delegation,
status, latency, and token usage.  Expanding a row reveals developer-only raw
input, raw prompt, raw model output, normalized tool arguments, bounded tool
response, cache status, SQL timing, and errors.

The required hierarchy is:

```text
Input Analyzer
  -> context loaded
  -> scope/rewrite completed
  -> route selected
Coordinator (coordinate route only)
  -> delegation to an agent
    -> agent observation
      -> tool invocation
        -> tool result
      -> agent next action or completion
  -> final synthesis
```

## Durability and Recovery

The trace collector immediately fans out normalized events to the SSE queue,
then persists them through a queue writer with its own SQLAlchemy session.
This avoids cross-thread SQLAlchemy session sharing while allowing an in-flight
run to be inspected.  `agent_events` gains a per-trace sequence and span
metadata sufficient to replay the same stream.

The replay endpoint accepts `after_seq`.  On a broken browser connection, the
frontend reconnects and requests only missing events; its reducer applies
events idempotently by trace ID, sequence, and span ID.

Timeout, cancellation, provider failure, schema-parse failure, and tool error
close every active span with a terminal status.  A malformed Input Analyzer
response gets one schema-repair attempt.  If that fails, Coordinator is not
started and the run returns a controlled clarification or error with the raw
bounded failure artifact.

## Evaluation as Diagnostic Regression

The existing golden dataset is not an optimization target or correctness
oracle.  It may remain for compatibility, but the new suite is a manually
reviewed diagnostic regression suite derived from observed production/development
failures.

Each case asserts routes, trace invariants, and unnecessary-work budgets rather
than matching a final answer string:

| Scenario | Required invariant |
|---|---|
| Context rewrite | `rewritten_query` resolves references such as “quán này”, “ở đây”, and “món đó” using the correct turn state. |
| Scope | Context-aware analyzer candidate is recorded; deterministic scope/privacy policy is the final authority. |
| Fast answer | Zero merchant data tools and zero Crew kickoff; source fact is marked immutable. |
| Direct lookup | One current-read detail tool; zero Crew kickoff, specialist delegation, and follow-on tools. |
| Coordinate | Prepared request is passed to Coordinator; only evidence gaps justify delegation or a repeated tool call. |
| Tool trace | Actor, parent span, normalized args, bounded result, cache state, and latency are present exactly once semantically. |
| Streaming | Started event precedes finished event and reaches the live reducer before `execution_finish`. |
| Recovery | Error/cancelled run has no orphan active span; replay after `seq` does not duplicate UI rows. |
| Cost | Input Analyzer stays within its separate token budget; direct lookup never invokes specialist or coordinator LLM spans. |

Before adding a regression case, the developer reviews a real trace and writes
the intended operational rule.  The suite prevents that rule from regressing;
it never substitutes for engineering judgment about whether the orchestration
was sensible.

## Acceptance Criteria

- Every turn has an Input Analyzer trace with raw bounded input/output,
  structured prepared request, token usage, and latency.
- Coordinator only receives a rewritten query and prepared context, and only
  starts on the `coordinate` route.
- Menu/hour follow-ups with a high-confidence selected merchant take one
  direct current-read tool and no Crew kickoff.
- Live UI renders each normalized span at start and finish without waiting for
  the full response.
- Default trace rows are compact; raw developer payloads are inspectable on
  demand and redacted/truncated.
- Prompt inputs and outputs meet the stated medium-token budgets.
- Diagnostic regression tests cover each routing outcome, trace ordering,
  duplicate prevention, reconnect, and unnecessary-work budgets.
