"""Unit tests for NativeMerchantAdvisorCrew and coordinator plan_execution."""

from unittest.mock import MagicMock
import pytest
from models.merchant_execution import ExecutionPlan, PlannedTask
from models.merchant_input import PreparedRequest
from agents.merchant.native_crew import NativeMerchantAdvisorCrew, plan_execution


class FakeLLM:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    def call(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response_text


@pytest.fixture(autouse=True)
def mock_prompts(monkeypatch):
    mock_p = MagicMock()
    mock_p.prompt = "Test prompt"
    monkeypatch.setattr("agents.merchant.native_crew.get_merchant_prompt", lambda name: mock_p)


def test_plan_execution_parses_valid_direct_json():
    json_response = '{"mode": "direct", "tasks": [{"capability": "owner", "instruction": "Check profile"}], "response_type": "fact"}'
    llm = FakeLLM(json_response)
    prepared = PreparedRequest(rewritten_query="Check profile", scope_candidate="allowed")

    plan = plan_execution(prepared, history=[], owner_context={}, llm=llm)

    assert isinstance(plan, ExecutionPlan)
    assert plan.mode == "direct"
    assert plan.tasks[0].capability == "owner"
    assert plan.response_type == "fact"


def test_crew_for_tasks_builds_only_requested_specialists():
    gateway = MagicMock()
    gateway.tools_for.return_value = []
    mock_llm = "openai/gpt-4o-mini"

    crew_builder = NativeMerchantAdvisorCrew(gateway=gateway, llm=mock_llm)

    tasks = [
        PlannedTask(capability="owner", instruction="Task 1"),
        PlannedTask(capability="policy", instruction="Task 2"),
    ]

    crew = crew_builder.crew_for_tasks(tasks)

    # Worker agents built should be: owner (self_analysis) and policy (policy_document)
    roles = [agent.role for agent in crew.agents]
    assert "Owner Performance Analysis Specialist" in roles
    assert "Green SM Policy Document Specialist" in roles
    # final_synthesis should NOT be in worker delegation agents pool
    assert "Merchant Owner Answer Specialist" not in roles
    # Should NOT build market_search or cohort_analysis
    assert "Public Market Search Specialist" not in roles
    assert "Public Cohort Analysis Specialist" not in roles
