"""Tests for developer-monitoring trace envelope aggregation."""
from __future__ import annotations

from sqlalchemy import text

from services.request_telemetry import RequestTelemetry, SqlQueryMonitor


def test_envelope_preserves_native_tool_arguments_and_aggregates_usage():
    envelope = RequestTelemetry.build_envelope(
        trace_id="tr-monitoring",
        status="completed",
        run_token_usage={"total_tokens": 13, "prompt_tokens": 8, "completion_tokens": 5},
        events=[
            {
                "event_type": "crewai_tool_requested",
                "tool_name": "search_merchants",
                "output_summary": {"args": {"query": "tôm", "city": "da_nang"}},
                "duration_ms": 12,
                "status": "ok",
            },
            {
                "event_type": "cache",
                "output_summary": {"status": "miss", "cache_key": "merchant:search:1"},
                "duration_ms": 1,
                "status": "ok",
            },
            {
                "event_type": "sql_query",
                "output_summary": {"statement": "SELECT merchants", "row_count": 2},
                "duration_ms": 4,
                "status": "ok",
            },
        ],
        session_state={"merchant_id": "94"},
    )

    assert envelope["events"][0]["output_summary"]["args"]["city"] == "da_nang"
    assert envelope["cache"][0]["status"] == "miss"
    assert envelope["sql_queries"][0]["row_count"] == 2
    assert envelope["llm_usage"]["total_tokens"] == 13
    assert envelope["session_state"] == {"merchant_id": "94"}
    assert envelope["summary"]["event_count"] == 3


def test_persistable_payload_keeps_bounded_tool_result_and_redacts_secrets():
    payload = RequestTelemetry.persistable_payload(
        {
            "tool_name": "search_merchants",
            "args": {"query": "tôm", "api_key": "secret"},
            "result": {"count": 1, "merchants": [{"name": "Quán Tôm"}]},
        }
    )

    assert payload["args"]["api_key"] == "<redacted>"
    assert payload["result"]["merchants"][0]["name"] == "Quán Tôm"


def test_sql_query_monitor_records_template_duration_and_row_count(db_session):
    events: list[dict] = []

    with SqlQueryMonitor(events.append).capture(db_session):
        db_session.execute(text("SELECT 1")).all()

    assert len(events) == 1
    assert events[0]["statement"].startswith("SELECT 1")
    assert events[0]["duration_ms"] >= 0
    assert "parameters" not in events[0]


def test_envelope_tolerates_a_truncated_llm_usage_payload():
    envelope = RequestTelemetry.build_envelope(
        trace_id="tr-truncated-usage",
        status="completed",
        run_token_usage=None,
        events=[
            {
                "event_type": "crewai_llm_finished",
                "output_summary": {"token_usage": "<truncated>"},
            }
        ],
        session_state={},
    )

    assert envelope["llm_usage"]["total_tokens"] == 0
