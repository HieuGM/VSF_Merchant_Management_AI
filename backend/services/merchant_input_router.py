"""Deterministic, policy-first routing for one prepared merchant request."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from models.merchant_agentic import normalize_text
from models.merchant_input import PreparedRequest
from services.merchant_data_policy import QueryPolicyDecision


@dataclass(frozen=True)
class RoutingDecision:
    """A compact, inspectable outcome chosen before any CrewAI kickoff."""

    outcome: Literal["reject", "fast_answer", "coordinate"]
    reason: str
    reply: str | None = None


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


def conservative_fallback_request(
    *, raw_query: str
) -> PreparedRequest:
    """Keep an unavailable/invalid small model from broadening execution.

    A fallback always delegates; it never attempts a deterministic lookup.
    """
    return PreparedRequest(
        rewritten_query=raw_query.strip() or "Yêu cầu merchant không hợp lệ",
        resolved_references=[],
        scope_candidate="unclear",
        missing_context=[],
        proposed_outcome="coordinate",
    )


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
    immutable_facts: dict[str, ImmutableSessionFact],
) -> RoutingDecision:
    """Select exactly one allowed route without planning or tool execution."""
    if not policy.allowed:
        return RoutingDecision("reject", "merchant_data_policy", reply=policy.reason)

    # Fast answers are deliberately narrower than the analyzer contract. No
    # mutable merchant information can enter this path.
    safe_fact = immutable_facts.get(normalize_text(prepared.rewritten_query))
    if (
        prepared.proposed_outcome == "fast_answer"
        and safe_fact is not None
    ):
        return RoutingDecision(
            "fast_answer", "immutable_session_fact", reply=safe_fact.value
        )

    return RoutingDecision("coordinate", "coordinator_required")
