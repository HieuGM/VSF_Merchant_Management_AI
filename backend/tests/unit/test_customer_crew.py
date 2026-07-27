"""Customer crew assembly with fake LLM — no network/key (Phase 07 tests 8, 8b).

Sequential process: 3 specialists, no coordinator/manager. Hybrid LLM: gpt-oss-20b
(fast) for search+preference, DeepSeek-V4-Flash (strong) for explanation.
"""
from __future__ import annotations

from crewai import Process

from agents.customer.customer_crew import build_customer_crew
from tools.registry import registry


def _ensure_tools():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def test_crew_builds_without_network(fake_llm_fast, fake_llm_strong):
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    # Sequential process — no manager agent.
    assert crew.process == Process.sequential
    assert crew.manager_agent is None
    assert len(crew.agents) == 3  # 3 specialists, no coordinator
    assert len(crew.tasks) == 3


def test_per_agent_llm_tiers(fake_llm_fast, fake_llm_strong):
    """search + preference use the fast model; explanation uses the strong model."""
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    search = next(a for a in crew.agents if "Tìm kiếm" in a.role)
    preference = next(a for a in crew.agents if "Suy luận" in a.role)
    explanation = next(a for a in crew.agents if "thân thiện" in a.role)
    assert search.llm.model == "openai/gpt-oss-20b"
    assert preference.llm.model == "openai/gpt-oss-20b"
    assert explanation.llm.model == "openai/DeepSeek-V4-Flash"


def test_specialists_do_not_delegate(fake_llm_fast, fake_llm_strong):
    """Sequential specialists never delegate (no coordinator to hand off to)."""
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    assert all(a.allow_delegation is False for a in crew.agents)


def test_agents_only_have_allowlisted_tools(fake_llm_fast, fake_llm_strong):
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    names = {t.name for t in reasoning.tools}
    assert "merchant_search" not in names  # not allow-listed for this agent
