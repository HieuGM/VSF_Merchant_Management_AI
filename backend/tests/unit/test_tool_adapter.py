"""Adapter Registry→CrewAI BaseTool + allow-list enforcement (Phase 07 tests 1, 2, 11)."""
from __future__ import annotations

import inspect
import json

import pytest
from crewai.tools import BaseTool

from agents.tool_adapter import build_crewai_tool, tools_for_crew_agent
from tools.registry import registry


@pytest.fixture(autouse=True)
def _discover():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def test_restaurant_search_gets_two_tools():
    tools = tools_for_crew_agent("restaurant_search")
    assert [t.name for t in tools] == ["merchant_search", "nearby_merchant_search"]
    assert all(isinstance(t, BaseTool) for t in tools)


def test_unknown_role_returns_empty():
    assert tools_for_crew_agent("does_not_exist") == []


# DB-gated: these tests exercise REAL queries (route → repo → Postgres). On CI (no
# Postgres) they'd fail with connection refused — skip there, matching the pattern
# integration tests already use (_require_db).
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.connection import engine

try:
    with engine.connect() as _c:
        _c.execute(text("SELECT 1;"))
    _HAS_DB = True
except OperationalError:
    _HAS_DB = False

pytestmark = pytest.mark.skipif(not _HAS_DB, reason="Postgres not reachable")


def test_allow_list_enforced_per_agent():
    # preference_reasoning may NOT call merchant_search (not in its allow-list).
    names = {t.name for t in tools_for_crew_agent("preference_reasoning")}
    assert "merchant_search" not in names
    assert names == {
        "get_user_profile",
        "get_session_candidates",
        "get_weather_context",
        "propose_profile_delta",
    }


def test_run_returns_json_string():
    tool = build_crewai_tool(registry.get("get_session_candidates"))
    out = tool._run(session_id="no_such_session")
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert parsed["candidates"] == [] and parsed["total"] == 0


def test_run_error_becomes_string_not_raise():
    # get_user_profile on unknown id raises NotFoundError inside the tool → adapter
    # must return a string, never propagate (would crash the agent loop).
    tool = build_crewai_tool(registry.get("get_user_profile"))
    out = tool._run(user_id="definitely_missing_user")
    assert isinstance(out, str)
    assert out.startswith("[tool_error:")


def test_args_schema_has_fields():
    tool = build_crewai_tool(registry.get("get_weather_context"))
    assert set(tool.args_schema.model_fields) == {"lat", "lng"}


def test_tools_take_no_db_session():
    """Guardrail: agents never receive a DB session — tool functions expose no db/session arg."""
    for name in ("get_user_profile", "get_session_candidates", "propose_profile_delta",
                 "get_weather_context", "merchant_search"):
        params = inspect.signature(registry.get(name).fn).parameters
        assert "db" not in params and "session" not in params, name
