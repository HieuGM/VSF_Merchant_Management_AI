#!/usr/bin/env python
"""Quick performance/quality probe for the customer crew (mocked — no LLM calls).

Measures end-to-end CustomerFlow latency with a fake crew, to isolate flow/overhead
from LLM inference time. Mock data matches the real Pydantic output schemas.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from models.customer_tasks import (  # noqa: E402
    MerchantCandidate,
    PreferenceTaskOutput,
    SearchTaskOutput,
)


def _fake_outputs():
    """Build schema-valid task outputs (no LLM). Explanation is free-text (a raw string),
    matching the real crew where explanation_task dropped output_pydantic."""
    search = SearchTaskOutput(
        candidates=[
            MerchantCandidate(
                merchant_id="m001", name="Phở Le", cuisine="Vietnamese",
                address="123 Nguyễn Huệ, Q.1", distance_km=0.5,
                avg_rating=4.5, match_score=0.9,
            ),
            MerchantCandidate(
                merchant_id="m002", name="Phở Gia Truyền", cuisine="Vietnamese",
                address="456 Lê Lợi, Q.1", distance_km=1.2,
                avg_rating=4.2, match_score=0.7,
            ),
        ],
        applied_filters={"query": "phở", "city": "", "cuisine": ""},
        count=2,
    )
    preference = PreferenceTaskOutput(
        suggestions=[],  # no strong signal → empty is valid
        weather_summary=None,
        reasoning="Demo mock — no preference delta.",
    )
    answer_text = (
        "Mình gợi ý Phở Le — gần bạn (0.5km), rating 4.5, hợp gu món Việt. "
        "Phở Gia Truyền cũng đáng thử nếu muốn đổi vị."
    )
    return search, preference, answer_text


def _mock_crew():
    """Mock crew whose kickoff returns the 3 task outputs (search/preference structured,
    explanation free-text on the last task's .raw)."""
    search, preference, answer_text = _fake_outputs()
    mock_output = SimpleNamespace(
        raw="ok",
        tasks_output=[
            SimpleNamespace(pydantic=search),
            SimpleNamespace(pydantic=preference),
            SimpleNamespace(raw=answer_text),
        ],
    )
    crew = Mock()
    crew.kickoff = Mock(return_value=mock_output)
    return crew


def main():
    print("\n=== Customer Flow — mocked latency probe ===\n")
    from flows.customer_flow import CustomerFlow

    queries = [
        {"query": "phở gần đây"},
        {"query": "quán cà phê giá rẻ"},
        {"query": "nhà hàng cơm gia đình"},
    ]
    results = []
    for i, params in enumerate(queries, 1):
        print(f"Test {i}: {params['query']}")
        with patch.object(CustomerFlow, "__init__", lambda self: None):
            flow = CustomerFlow()
            flow._repo = Mock()
            flow._repo.add_event = Mock()
            flow._repo.create_run = Mock()
            flow._repo.finish_run = Mock()
        start = time.perf_counter()
        try:
            resp = flow.search_restaurants(
                crew=_mock_crew(), user_id="user_demo", session_id=f"perf_{i}", **params
            )
            dt = time.perf_counter() - start
            results.append((params["query"], dt, len(resp.results), len(resp.answer)))
            print(f"  ✓ {dt:.3f}s | results={len(resp.results)} | answer={len(resp.answer)} chars")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {type(exc).__name__}: {exc}")
            results.append((params["query"], -1, 0, 0))

    ok = [r for r in results if r[1] > 0]
    print("\n=== Summary ===")
    if ok:
        print(f"  avg latency: {sum(r[1] for r in ok) / len(ok):.3f}s (mocked, no LLM)")
    print(f"  passed: {len(ok)}/{len(results)}")


if __name__ == "__main__":
    main()
