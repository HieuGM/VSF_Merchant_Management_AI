"""Customer crew assembly with fake LLM — no network/key (Phase 07 tests 8, 8b).

Sequential process: 3 specialists, no coordinator/manager.
"""
from __future__ import annotations

from crewai import Process

from agents.customer.customer_crew import build_customer_crew
from tools.registry import registry


def _ensure_tools():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def test_crew_builds_without_network(fake_llm_nim, fake_llm_fpt):
    _ensure_tools()
    crew = build_customer_crew(llm_nim=fake_llm_nim, llm_fpt=fake_llm_fpt)
    # Sequential process — no manager agent.
    assert crew.process == Process.sequential
    assert crew.manager_agent is None
    assert len(crew.agents) == 3  # 3 specialists, no coordinator
    assert len(crew.tasks) == 3


def test_per_agent_llm_tier(fake_llm_nim, fake_llm_fpt):
    _ensure_tools()
    crew = build_customer_crew(llm_nim=fake_llm_nim, llm_fpt=fake_llm_fpt)
    # restaurant_search uses NIM 8B (fast for search).
    search = next(a for a in crew.agents if "Tìm kiếm" in a.role)
    assert "8b" in search.llm.model
    # preference_reasoning + customer_explanation use FPT DeepSeek (strong reasoning).
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    explanation = next(a for a in crew.agents if "Giải thích" in a.role)
    assert "DeepSeek" in reasoning.llm.model and "DeepSeek" in explanation.llm.model


def test_specialists_do_not_delegate(fake_llm_nim, fake_llm_fpt):
    """Sequential specialists never delegate (no coordinator to hand off to)."""
    _ensure_tools()
    crew = build_customer_crew(llm_nim=fake_llm_nim, llm_fpt=fake_llm_fpt)
    assert all(a.allow_delegation is False for a in crew.agents)


def test_agents_only_have_allowlisted_tools(fake_llm_nim, fake_llm_fpt):
    _ensure_tools()
    crew = build_customer_crew(llm_nim=fake_llm_nim, llm_fpt=fake_llm_fpt)
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    names = {t.name for t in reasoning.tools}
    assert "merchant_search" not in names  # not allow-listed for this agent
