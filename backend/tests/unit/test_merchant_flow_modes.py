"""Integration tests for merchant flow rollout execution modes (legacy, shadow, active)."""

from unittest.mock import MagicMock, patch
import pytest

from models.merchant_execution import ExecutionPlan, PlannedTask
from models.merchant_input import PreparedRequest
from services.merchant_data_policy import QueryPolicyDecision
from flows.merchant_flow import MerchantFlowDispatcher


@pytest.fixture
def mock_flow_deps():
    with patch("flows.merchant_flow.InputPreparationService") as mock_prep, \
         patch("flows.merchant_flow.MerchantDataPolicy") as mock_pol, \
         patch("flows.merchant_flow.decide_route") as mock_route, \
         patch("flows.merchant_flow.RunScopedMerchantToolGateway") as mock_gw, \
         patch("flows.merchant_flow.NativeMerchantAdvisorCrew") as mock_crew:

        mock_prep.return_value.prepare.return_value = PreparedRequest(
            rewritten_query="Test query",
            scope_candidate="allowed",
        )
        mock_pol.return_value.query_decision.return_value = QueryPolicyDecision(allowed=True, scope="public")
        mock_route.return_value.outcome = "coordinate"

        mock_crew_instance = MagicMock()
        mock_crew.return_value = mock_crew_instance
        mock_crew_instance.kickoff.return_value = MagicMock(raw='{"status":"completed","answer":"Legacy answer"}')

        yield {
            "prep": mock_prep,
            "policy": mock_pol,
            "route": mock_route,
            "gateway": mock_gw,
            "crew": mock_crew,
            "crew_instance": mock_crew_instance,
        }


def test_flow_legacy_mode_executes_native_crew(mock_flow_deps, monkeypatch):
    monkeypatch.setattr("flows.merchant_flow.get_configured_llm", lambda tier: MagicMock())
    monkeypatch.setattr("flows.merchant_flow.get_settings", lambda: MagicMock(merchant_execution_mode="legacy", environment="test"))

    dispatcher = MerchantFlowDispatcher()

    session_mock = MagicMock()
    session_mock.get.return_value = None
    session_service_mock = MagicMock()
    session_service_mock.get_or_create_session.return_value = MagicMock(session_id="s1")
    session_service_mock.get_compact_history.return_value = []
    session_service_mock.get_session_snapshot.return_value = {}

    with patch("flows.merchant_flow._require_trace_id", return_value="00000000000000000000000000000000"), \
         patch("flows.merchant_flow.ChatSessionService", return_value=session_service_mock):
        res = dispatcher._execute(
            session=session_mock,
            session_service=session_service_mock,
            trace_id="00000000000000000000000000000000",
            session_id="s1",
            merchant_id="m1",
            message="Test query",
            user_id="u1",
            owns_session=False,
        )

    assert res["status"] == "completed"
    assert res["execution_mode"] == "legacy"
    mock_flow_deps["crew_instance"].kickoff.assert_called_once()


def test_flow_shadow_mode_plans_and_executes_legacy_crew(mock_flow_deps, monkeypatch):
    monkeypatch.setattr("flows.merchant_flow.get_configured_llm", lambda tier: MagicMock())
    monkeypatch.setattr("flows.merchant_flow.get_settings", lambda: MagicMock(merchant_execution_mode="shadow", environment="test"))

    shadow_plan = ExecutionPlan(
        mode="parallel",
        tasks=[
            PlannedTask(capability="owner", instruction="Task 1"),
            PlannedTask(capability="market", instruction="Task 2"),
        ],
        response_type="summary",
    )

    with patch("agents.merchant.native_crew.plan_execution", return_value=shadow_plan) as mock_plan_exec, \
         patch("services.merchant_execution_executor.execute_parallel") as mock_parallel:

        dispatcher = MerchantFlowDispatcher()
        session_mock = MagicMock()
        session_mock.get.return_value = None
        session_service_mock = MagicMock()
        session_service_mock.get_compact_history.return_value = []
        session_service_mock.get_session_snapshot.return_value = {}

        with patch("flows.merchant_flow._require_trace_id", return_value="00000000000000000000000000000000"), \
             patch("flows.merchant_flow.ChatSessionService", return_value=session_service_mock):
            res = dispatcher._execute(
                session=session_mock,
                session_service=session_service_mock,
                trace_id="00000000000000000000000000000000",
                session_id="s1",
                merchant_id="m1",
                message="Test query",
                user_id="u1",
                owns_session=False,
            )

        # Shadow mode must generate plan for tracing, but execute legacy hierarchy!
        mock_plan_exec.assert_called_once()
        mock_parallel.assert_not_called()
        mock_flow_deps["crew_instance"].kickoff.assert_called_once()
        assert res["execution_mode"] == "legacy"
        assert res["reply"] == "Legacy answer"


def test_flow_active_mode_direct_bypasses_manager(mock_flow_deps, monkeypatch):
    monkeypatch.setattr("flows.merchant_flow.get_configured_llm", lambda tier: MagicMock())
    monkeypatch.setattr("flows.merchant_flow.get_settings", lambda: MagicMock(merchant_execution_mode="active", environment="test"))

    direct_plan = ExecutionPlan(
        mode="direct",
        tasks=[PlannedTask(capability="owner", instruction="Check owner profile")],
        response_type="fact",
    )

    with patch("agents.merchant.native_crew.plan_execution", return_value=direct_plan), \
         patch("services.merchant_execution_executor.execute_direct") as mock_direct:
        from services.merchant_execution_executor import SpecialistResult
        mock_direct.return_value = SpecialistResult(
            capability="owner",
            instruction="Check owner profile",
            status="completed",
            content="Direct result data",
            duration_ms=15.0,
            tool_calls=1,
        )

        dispatcher = MerchantFlowDispatcher()
        session_mock = MagicMock()
        session_service_mock = MagicMock()

        with patch("flows.merchant_flow._require_trace_id", return_value="00000000000000000000000000000000"), \
             patch("flows.merchant_flow.ChatSessionService", return_value=session_service_mock):
            res = dispatcher._execute(
                session=session_mock,
                session_service=session_service_mock,
                trace_id="00000000000000000000000000000000",
                session_id="s1",
                merchant_id="m1",
                message="Check owner profile",
                user_id="u1",
                owns_session=False,
            )

        assert res["status"] == "completed"
        assert res["execution_mode"] == "direct"
        assert res["reply"] == "Direct result data"
        # Verify hierarchical manager crew kickoff was NEVER called!
        mock_flow_deps["crew_instance"].kickoff.assert_not_called()


def test_active_search_updates_session_snapshot(mock_flow_deps, monkeypatch):
    monkeypatch.setattr("flows.merchant_flow.get_configured_llm", lambda _tier: MagicMock())
    monkeypatch.setattr("flows.merchant_flow.get_settings", lambda: MagicMock(merchant_execution_mode="active"))
    plan = ExecutionPlan(
        mode="direct",
        tasks=[PlannedTask(capability="market", instruction="Tìm tài liệu merchant")],
        response_type="summary",
    )
    merchant = {"merchant_id": "m2", "name": "Merchant 2"}

    with patch("agents.merchant.native_crew.plan_execution", return_value=plan), \
         patch("services.merchant_execution_executor.execute_direct") as direct:
        from services.merchant_execution_executor import SpecialistResult
        direct.return_value = SpecialistResult(
            capability="market", instruction="Tìm tài liệu merchant",
            status="completed", content="Merchant 2", duration_ms=10,
            tool_calls=1, public_merchants=[merchant],
        )
        service = MagicMock()
        service.get_compact_history.return_value = []
        service.get_session_snapshot.return_value = {}
        result = MerchantFlowDispatcher()._execute(
            session=MagicMock(), session_service=service,
            trace_id="0" * 32, session_id="s1", merchant_id="m1",
            message="Tìm merchant", user_id="u1", owns_session=False,
        )

    assert result["merchants"] == [merchant]
    service.update_session_snapshot.assert_called_once()
