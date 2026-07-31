from flows.merchant_flow import MerchantFlowDispatcher


def test_native_outcome_parser_accepts_only_explicit_completed_contract():
    parsed = MerchantFlowDispatcher._parse_native_outcome(
        '{"status":"completed","answer":"Đây là câu trả lời đã kiểm chứng."}'
    )

    assert parsed is not None
    assert parsed.status == "completed"
    assert parsed.answer == "Đây là câu trả lời đã kiểm chứng."


def test_native_outcome_parser_rejects_unstructured_text():
    assert MerchantFlowDispatcher._parse_native_outcome(
        "Tôi nghĩ bạn nên thử tìm quán sushi."
    ) is None
