"""Deterministic, policy-first routing for one prepared merchant request."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from models.merchant_agentic import normalize_text
from models.merchant_input import PreparedRequest
from services.merchant_data_policy import QueryPolicyDecision


@dataclass(frozen=True)
class RoutingDecision:
    """A compact, inspectable outcome chosen before any CrewAI kickoff."""

    outcome: Literal["reject", "coordinate"]
    reason: str
    reply: str | None = None


@dataclass(frozen=True)
class RouteExecution:
    """Result of the work authorized by one routing decision."""

    outcome: str
    crew_result: Any | None = None


@dataclass(frozen=True)
class ImmutableSessionFact:
    """An immutable fact explicitly bound to one normalized rewritten query."""

    normalized_query: str
    value: str


def immutable_session_facts(snapshot: dict[str, Any]) -> dict[str, ImmutableSessionFact]:
    """Return only explicitly immutable, renderable session facts.

    Mutable merchant facts (notably menu, hours, ratings, and search data) are
    deliberately excluded unless a caller has labelled a concrete text value as
    immutable *and* bound it to the normalized rewritten query it can answer.
    """
    stored = snapshot.get("merchant_agentic.immutable_facts")
    if not isinstance(stored, dict):
        return {}
    facts: dict[str, ImmutableSessionFact] = {}
    for entry in stored.values():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        normalized_query = entry.get("normalized_query")
        if (
            entry.get("source_stability") == "immutable"
            and isinstance(value, str)
            and isinstance(normalized_query, str)
        ):
            safe_value = value.strip()
            query_key = normalize_text(normalized_query)
            if safe_value and query_key:
                facts[query_key] = ImmutableSessionFact(
                    normalized_query=query_key,
                    value=safe_value,
                )
    return facts


def effective_query_policy(
    raw_policy: QueryPolicyDecision,
    rewritten_policy: QueryPolicyDecision,
) -> tuple[QueryPolicyDecision, Literal["raw_query", "rewritten_query"]]:
    """Deny whenever either text requests prohibited merchant data.

    A model rewrite can add useful context but can never erase a hard policy
    denial present in the user's raw request.
    """
    if not raw_policy.allowed:
        return raw_policy, "raw_query"
    return rewritten_policy, "rewritten_query"


def decide_route(
    *,
    prepared: PreparedRequest,
    policy: QueryPolicyDecision,
    immutable_facts: dict[str, ImmutableSessionFact] | None = None,
) -> RoutingDecision:
    """Select exactly one pre-coordinator route without planning or tool execution.

    Routes:
      reject     — hard policy denial or explicit out-of-scope from Input Analyzer.
      coordinate — all other allowed requests; the coordinator decides execution mode.

    The coordinator is the sole semantic execution router. This function must not
    select a mode, capability, agent, or tool.
    """
    if not policy.allowed:
        return RoutingDecision("reject", "merchant_data_policy", reply=policy.reason)

    # Explicit out-of-scope from Input Analyzer is a hard stop.
    if prepared.scope_candidate == "out_of_scope":
        return RoutingDecision(
            "reject",
            "input_scope",
            reply="Câu hỏi nằm ngoài phạm vi hỗ trợ merchant và tài liệu Green SM.",
        )

    return RoutingDecision("coordinate", "coordinator_required")


def execute_routing_decision(
    decision: RoutingDecision,
    *,
    kickoff_coordinator: Callable[[], Any] | None = None,
) -> RouteExecution:
    """Start work only for the coordinate route."""
    if decision.outcome != "coordinate":
        return RouteExecution(outcome=decision.outcome)
    if kickoff_coordinator is None:
        raise ValueError("coordinate route requires a coordinator kickoff")
    return RouteExecution(
        outcome=decision.outcome,
        crew_result=kickoff_coordinator(),
    )
