"""Customer crew assembly with fake LLM — no network/key (Phase 07 tests 8, 8b)."""
from __future__ import annotations

from crewai import Process

from agents.customer.customer_crew import build_customer_crew
from tools.registry import registry


def _ensure_tools():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def test_crew_builds_without_network(fake_llm_large, fake_llm_small):
    _ensure_tools()
    crew = build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)
    assert crew.process == Process.hierarchical
    assert crew.manager_agent is not None
    assert len(crew.agents) == 3  # manager is separate, not in agents list
    assert len(crew.tasks) == 3


def test_per_agent_llm_tier(fake_llm_large, fake_llm_small):
    _ensure_tools()
    crew = build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)
    by_role = {a.role.split("(")[0].strip(): a for a in crew.agents}
    by_role["manager"] = crew.manager_agent

    # manager (coordinator) + restaurant_search → large (70b)
    assert "70b" in crew.manager_agent.llm.model
    search = next(a for a in crew.agents if "Tìm kiếm" in a.role)
    assert "70b" in search.llm.model
    # preference_reasoning + explanation → small (8b)
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    explanation = next(a for a in crew.agents if "Giải thích" in a.role)
    assert "8b" in reasoning.llm.model and "8b" in explanation.llm.model


def test_only_coordinator_delegates(fake_llm_large, fake_llm_small):
    _ensure_tools()
    crew = build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)
    assert crew.manager_agent.allow_delegation is True
    assert all(a.allow_delegation is False for a in crew.agents)


def test_agents_only_have_allowlisted_tools(fake_llm_large, fake_llm_small):
    _ensure_tools()
    crew = build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    names = {t.name for t in reasoning.tools}
    assert "merchant_search" not in names  # not allow-listed for this agent
