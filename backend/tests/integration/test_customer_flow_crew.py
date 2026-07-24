"""Flow persists run + events with a mocked crew kickoff (Phase 07 test 9).

Requires Postgres (skips when unreachable). Uses a mock crew so no LLM/network runs;
verifies agent_runs + agent_events are written under one trace_id."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.connection import SessionLocal, engine
from database.models import AgentEvent, AgentRun
from models.agent import CustomerChatResponse
from models.customer_tasks import (
    ExplanationTaskOutput,
    MerchantCandidate,
    SearchTaskOutput,
)


def _require_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


class _MockCrew:
    def kickoff(self, inputs=None):
        search = SearchTaskOutput(
            candidates=[MerchantCandidate(merchant_id="m001", name="Phở Le", match_score=0.9)],
            count=1,
        )
        explanation = ExplanationTaskOutput(answer="Gợi ý Phở Le vì gần và hợp khẩu vị.")
        return SimpleNamespace(
            raw="ok",
            tasks_output=[
                SimpleNamespace(pydantic=search),
                SimpleNamespace(pydantic=explanation),
            ],
        )


def test_flow_persists_run_and_events():
    _require_db()
    from flows.customer_flow import customer_flow

    resp = customer_flow.search_restaurants(
        query="phở gần đây",
        user_id="user_demo",
        session_id="session_demo",
        crew=_MockCrew(),
    )
    assert isinstance(resp, CustomerChatResponse)
    assert resp.answer and len(resp.results) == 1

    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter_by(trace_id=resp.trace_id).one()
        events = db.query(AgentEvent).filter_by(trace_id=resp.trace_id).all()
    finally:
        db.close()

    assert run.status == "ok" and run.crew_name == "customer_discovery"
    assert len(events) >= 1
    assert all(e.trace_id == resp.trace_id for e in events)


def test_flow_error_marks_run_error():
    _require_db()
    from flows.customer_flow import customer_flow

    class _Boom:
        def kickoff(self, inputs=None):
            raise RuntimeError("kickoff failed")

    with pytest.raises(RuntimeError):
        customer_flow.search_restaurants(query="x", crew=_Boom())

    db = SessionLocal()
    try:
        run = (
            db.query(AgentRun)
            .filter_by(status="error", error_code="RuntimeError")
            .order_by(AgentRun.started_at.desc())
            .first()
        )
    finally:
        db.close()
    assert run is not None
