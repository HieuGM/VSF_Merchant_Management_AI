from models.merchant_input import PreparedRequest
from flows.merchant_flow import (
    MerchantFlowDispatcher,
    _correct_named_public_request,
    _public_merchant_selection_update,
)


def test_public_merchant_selection_is_bounded_and_requires_one_match():
    candidates = [
        {"merchant_id": str(index), "name": f"Quan {index}"}
        for index in range(7)
    ]
    update = _public_merchant_selection_update("Toi chon Quan 3", candidates)
    assert len(update["merchant_agentic.last_public_search"]) == 5
    assert update["merchant_agentic.selected_public_merchant"]["merchant_id"] == "3"


def test_named_public_request_preserves_raw_target():
    prepared = PreparedRequest(
        rewritten_query="owner target",
        scope_candidate="allowed",
    )
    corrected = _correct_named_public_request(prepared, "Compare exact public merchant", True)
    assert corrected.rewritten_query == "Compare exact public merchant"
    assert corrected.resolved_references == []


def test_native_outcome_parser_accepts_completed_json_after_prose():
    result = MerchantFlowDispatcher._parse_native_outcome(
        'prefix {"status":"completed","answer":"Grounded answer"}'
    )
    assert result is not None
    assert result.answer == "Grounded answer"


def test_native_outcome_parser_rejects_non_completed_json():
    assert MerchantFlowDispatcher._parse_native_outcome(
        '{"status":"failed","answer":"unsafe"}'
    ) is None
