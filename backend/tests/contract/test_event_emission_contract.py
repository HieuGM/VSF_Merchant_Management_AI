"""Event emission contract — red-team H8 ("emit đủ field").

Both flows must populate every REQUIRED_EMIT_FIELD; a gap is caught here pre-merge.
"""
from __future__ import annotations

import pytest

from agents.listeners.crewai_listener import (
    RecordingListener,
    assert_emittable,
    build_event_record,
)
from models.agent import REQUIRED_EMIT_FIELDS


def test_build_event_record_has_required_fields():
    rec = build_event_record(
        trace_id="trace_001",
        event_type="tool_started",
        tool_name="get_merchant_profile",
        input_payload={"merchant_id": "68814"},
    )
    data = rec.model_dump()
    for field in REQUIRED_EMIT_FIELDS:
        assert data.get(field), f"missing {field}"
    assert data["input_hash"]  # derived from payload


def test_reference_listener_records():
    listener = RecordingListener()
    listener.handle(build_event_record(trace_id="t1", event_type="run_started"))
    assert len(listener.events) == 1


def test_unknown_event_type_rejected():
    with pytest.raises(ValueError):
        build_event_record(trace_id="t1", event_type="not_a_real_event")


def test_assert_emittable_flags_missing_field():
    rec = build_event_record(trace_id="t1", event_type="run_finished")
    rec.trace_id = ""  # simulate a flow that forgot to set it
    with pytest.raises(ValueError):
        assert_emittable(rec)
