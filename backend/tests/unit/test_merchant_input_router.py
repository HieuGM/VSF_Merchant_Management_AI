"""Deterministic routing contracts; no database or LLM is used."""

from models.merchant_input import PreparedRequest
from services.merchant_data_policy import QueryPolicyDecision
from services.merchant_input_router import ImmutableSessionFact, decide_route


ALLOWED = QueryPolicyDecision(allowed=True, scope="public")


def prepared(
    *,
    scope: str = "allowed",
    outcome: str = "coordinate",
    query: str = "Quy trình bồi hoàn đơn bị hủy là gì?",
) -> PreparedRequest:
    return PreparedRequest(
        rewritten_query=query,
        scope_candidate=scope,
        missing_context=[],
        proposed_outcome=outcome,
    )


def test_scope_candidate_out_of_scope_is_a_real_rejection_gate():
    route = decide_route(
        prepared=prepared(scope="out_of_scope"),
        policy=ALLOWED,
        immutable_facts={},
    )

    assert route.outcome == "reject"
    assert route.reason == "input_scope"


def test_document_question_enters_coordinator_for_later_rag_delegation():
    route = decide_route(
        prepared=prepared(outcome="coordinate"),
        policy=ALLOWED,
        immutable_facts={},
    )

    assert route.outcome == "coordinate"
    assert route.reason == "coordinator_required"


def test_unclear_document_candidate_enters_coordinator():
    route = decide_route(
        prepared=prepared(scope="unclear", outcome="coordinate"),
        policy=ALLOWED,
        immutable_facts={},
    )

    assert route.outcome == "coordinate"


def test_policy_denial_has_priority_over_every_analyzer_route():
    denied = QueryPolicyDecision(
        allowed=False,
        scope="competitor_private",
        reason="denied",
    )
    route = decide_route(
        prepared=prepared(outcome="coordinate"),
        policy=denied,
        immutable_facts={},
    )

    assert route.outcome == "reject"
    assert route.reason == "merchant_data_policy"


def test_fast_answer_requires_an_exact_immutable_fact():
    query = "Tên sản phẩm cố định là gì?"
    route = decide_route(
        prepared=prepared(outcome="fast_answer", query=query),
        policy=ALLOWED,
        immutable_facts={
            "ten san pham co dinh la gi?": ImmutableSessionFact(
                normalized_query="ten san pham co dinh la gi?",
                value="Green SM Merchant",
            )
        },
    )

    assert route.outcome == "fast_answer"
    assert route.reply == "Green SM Merchant"
