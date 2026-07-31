from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
from scripts.merchant_trace_renderer import MerchantTraceRenderer


def _capture_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger("test.merchant.trace")
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger, stream


def test_compact_renderer_shows_lifecycle_metrics_without_large_payloads():
    logger, stream = _capture_logger()
    renderer = MerchantTraceRenderer(logger=logger)

    renderer.handle(
        "context",
        {
            "history_count": 4,
            "history_source": "database",
            "history_cache_status": "disabled",
            "history_preview": [{"text": "private " * 100}],
            "duration_ms": 1.25,
            "token_usage": None,
        },
    )
    renderer.handle(
        "plan",
        {
            "original_query": "ăn dễ tiêu",
            "rewritten_query": "Ăn dễ tiêu Đà Nẵng",
            "capabilities": ["restaurant_search"],
            "filters": {"query": "dễ tiêu", "city": "da_nang"},
            "duration_ms": 12.5,
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )
    renderer.handle(
        "tool_call",
        {
            "tool_name": "search_merchants",
            "args": {"query": "dễ tiêu", "city": "da_nang"},
        },
    )
    renderer.handle(
        "cache",
        {
            "tool_name": "search_merchants",
            "operation": "lookup",
            "status": "miss",
            "backend": "InMemoryCache",
            "cache_key": "agent:merchant_search:abc",
            "duration_ms": 0.2,
            "token_usage": None,
        },
    )
    renderer.handle(
        "tool_args_normalized",
        {
            "tool_name": "search_merchants",
            "removed_fields": ["district", "diet"],
            "reason": "not_grounded_in_owner_request",
        },
    )
    renderer.handle(
        "tool_result",
        {
            "tool_name": "search_merchants",
            "result": {
                "count": 1,
                "merchants": [
                    {
                        "merchant_id": "1",
                        "name": "Cháo ngon",
                        "private_blob": "secret " * 100,
                    }
                ],
            },
            "duration_ms": 4,
            "token_usage": None,
        },
    )
    renderer.handle(
        "query_summary",
        {
            "duration_ms": 30,
            "tool_count": 1,
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )
    assert "SUMMARY" not in stream.getvalue()
    renderer.render_summary({})

    output = stream.getvalue()
    assert "CONTEXT history=4 source=database cache=disabled" in output
    assert "PLAN rewrite='Ăn dễ tiêu Đà Nẵng'" in output
    assert "TOOL search_merchants args=" in output
    assert "CACHE search_merchants lookup=miss" in output
    assert "TOOL POLICY search_merchants removed=[\"district\", \"diet\"]" in output
    assert "RESULT search_merchants count=1 merchants=[1:Cháo ngon]" in output
    assert "SUMMARY tools=1 cache(hit=0,miss=1,store=0,bypass=0,error=0)" in output
    assert "wall=30ms" in output
    assert "tokens=15 (p=10, c=5)" in output
    assert "private_blob" not in output
    assert "secret" not in output


def test_full_renderer_emits_complete_sanitized_event_json():
    logger, stream = _capture_logger()
    renderer = MerchantTraceRenderer(logger=logger, full=True)

    renderer.handle(
        "tool_result",
        {
            "tool_name": "search_merchants",
            "result": {"count": 0, "debug": {"sql": "SELECT merchants"}},
            "duration_ms": 3,
            "token_usage": None,
        },
    )

    output = stream.getvalue()
    assert '"event": "tool_result"' in output
    assert '"sql": "SELECT merchants"' in output
    assert "tokens=N/A" in output
