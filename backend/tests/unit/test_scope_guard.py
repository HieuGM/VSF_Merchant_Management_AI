"""Unit tests for Scope Guard module."""
from __future__ import annotations

from agents.merchant.scope_guard import validate_query_scope


def test_scope_guard_valid_merchant_queries():
    valid_queries = [
        "Tại sao điểm thời gian chờ của quán tôi lại thấp?",
        "So sánh quán tôi với các đối thủ trong bán kính 5km",
        "Có những món ăn nào đang xu hướng ở Hà Nội?",
        "Tư vấn giải pháp tăng doanh thu cho quán bún đậu",
        "Xem danh sách khiếu nại của khách hàng về đóng gói",
        "Xin chào, bạn có thể giúp gì cho tôi?",
        "Quán ăn",
    ]
    for q in valid_queries:
        is_valid, msg = validate_query_scope(q)
        assert is_valid is True, f"Query should be valid: {q!r}"
        assert msg is None


def test_scope_guard_out_of_scope_queries():
    out_of_scope_queries = [
        "Hãy viết code python để bóc tách dữ liệu website tin tức",
        "Dự báo thời tiết hôm nay tại Hà Nội thế nào?",
        "Ai là tổng thống thứ 44 của nước Mỹ?",
        "Tôi bị đau đầu nên uống thuốc gì?",
    ]
    for q in out_of_scope_queries:
        is_valid, msg = validate_query_scope(q)
        assert is_valid is False, f"Query should be out of scope: {q!r}"
        assert msg is not None
        assert "Merchant Advisor" in msg or "không thể hỗ trợ" in msg


def test_scope_guard_empty_query():
    is_valid, msg = validate_query_scope("   ")
    assert is_valid is False
    assert "không được để trống" in msg
