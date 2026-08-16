"""Deterministic routing contracts; no database or LLM is used."""

import pytest
from models.merchant_input import PreparedRequest
from services.merchant_data_policy import QueryPolicyDecision
from services.merchant_input_router import ImmutableSessionFact, decide_route


ALLOWED = QueryPolicyDecision(allowed=True, scope="public")


def prepared(
    *,
    scope: str = "allowed",
    query: str = "Quy trình bồi hoàn đơn bị hủy là gì?",
    missing_context: list[str] | None = None,
) -> PreparedRequest:
    return PreparedRequest(
        rewritten_query=query,
        scope_candidate=scope,
        missing_context=missing_context or [],
    )


def test_scope_candidate_out_of_scope_is_a_real_rejection_gate():
    route = decide_route(
        prepared=prepared(scope="out_of_scope"),
        policy=ALLOWED,
    )

    assert route.outcome == "reject"
    assert route.reason == "input_scope"


def test_document_question_enters_coordinator():
    route = decide_route(
        prepared=prepared(),
        policy=ALLOWED,
    )

    assert route.outcome == "coordinate"
    assert route.reason == "coordinator_required"


def test_unclear_scope_candidate_enters_coordinator():
    route = decide_route(
        prepared=prepared(scope="unclear"),
        policy=ALLOWED,
    )

    assert route.outcome == "coordinate"


def test_policy_denial_has_priority_over_every_analyzer_result():
    denied = QueryPolicyDecision(
        allowed=False,
        scope="competitor_private",
        reason="denied",
    )
    route = decide_route(
        prepared=prepared(),
        policy=denied,
    )

    assert route.outcome == "reject"
    assert route.reason == "merchant_data_policy"


def test_extra_fields_are_rejected_by_prepared_request():
    """PreparedRequest must reject any execution-choice fields."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PreparedRequest(
            rewritten_query="test",
            scope_candidate="allowed",
            mode="direct",  # forbidden: execution choice
        )


@pytest.mark.parametrize("forbidden_field", [
    {"proposed_outcome": "coordinate"},
    {"route": "fast_answer"},
    {"capability": "owner"},
    {"agent": "coordinator"},
    {"tool": "get_rating"},
    {"tasks": []},
])
def test_prepared_request_rejects_execution_fields(forbidden_field):
    """PreparedRequest with extra='forbid' must reject any execution-selection field."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PreparedRequest(
            rewritten_query="test",
            scope_candidate="allowed",
            **forbidden_field,
        )
