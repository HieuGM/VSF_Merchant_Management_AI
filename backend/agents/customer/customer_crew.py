"""Customer Discovery Crew assembly (Phase 05) — @CrewBase + NVIDIA NIM 2-tier LLM.

Reads config/agents.yaml + config/tasks.yaml, binds allow-listed tools via the adapter,
assigns a per-agent LLM tier, and wires a hierarchical crew with the coordinator as
manager (1-hop delegation, §5.2).

LLM vendor is pluggable via settings (`active_llm_vendor`, OpenAI-compatible for both):
  - fpt (auto-selected when FPT_* set): FPT Cloud DeepSeek — ~9-20x faster than the NIM
    free tier; used for BOTH tiers (validated fast + faithful structured output).
  - nvidia_nim (default fallback): per-agent 2-tier (plan §3) —
    large  meta/llama-3.3-70b-instruct → customer_coordinator (manager) + restaurant_search
    small  meta/llama-3.1-8b-instruct  → preference_reasoning + customer_explanation

Tests inject fake `llm_large` / `llm_small` so no network/key is required.
"""
from __future__ import annotations

from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from agents.tool_adapter import tools_for_crew_agent
from core.errors import ConfigError
from core.settings import get_settings
from models.customer_tasks import (
    ExplanationTaskOutput,
    PreferenceTaskOutput,
    SearchTaskOutput,
)


def _build_llm(tier: str) -> LLM:
    """Build the LLM for a tier ("large"|"small") using the active vendor (settings).

    FPT Cloud (DeepSeek) when configured, else NVIDIA NIM 2-tier. Both are OpenAI-compatible
    (CrewAI's native `openai` provider + custom base_url). Raises ConfigError if unkeyed."""
    s = get_settings()
    if not s.llm_configured:
        raise ConfigError(
            "LLM chưa được cấu hình — cần FPT_* (DeepSeek) hoặc NVIDIA_NIM_API_KEY trong .env."
        )
    if s.active_llm_vendor == "fpt":
        # FPT DeepSeek for both tiers (validated: fast + faithful structured output).
        return LLM(
            model=f"openai/{s.fpt_model_deepseek}",
            api_key=s.fpt_api_key,
            base_url=s.fpt_base_url,
        )
    # NVIDIA NIM (default): per-agent 2-tier.
    model = s.llm_model_large if tier == "large" else s.llm_model_small
    return LLM(
        model=f"{s.llm_provider}/{model}",  # e.g. openai/meta/llama-3.3-70b-instruct @ NIM base_url
        api_key=s.nvidia_nim_api_key,
        base_url=s.llm_base_url,
    )


@CrewBase
class CustomerDiscoveryCrew:
    """CrewAI hierarchical crew for customer restaurant discovery (UC-04/UC-05)."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, llm_large: LLM | None = None, llm_small: LLM | None = None) -> None:
        # Defer live LLM construction so tests can inject fakes without a key.
        self._llm_large = llm_large or _build_llm("large")
        self._llm_small = llm_small or _build_llm("small")

    # --- agents (method name MUST equal the YAML key) ---
    @agent
    def customer_coordinator(self) -> Agent:
        # NOTE: used exclusively as the hierarchical `manager_agent`. CrewAI's hierarchical
        # process rejects a manager that owns tools ("Manager agent should not have tools")
        # — the manager only orchestrates via delegation. The coordinator's allow-listed
        # tools (get_user_profile / get_session_candidates) stay reachable through
        # preference_reasoning, which is allow-listed for them too.
        return Agent(
            config=self.agents_config["customer_coordinator"],
            llm=self._llm_large,
            tools=[],
        )

    @agent
    def restaurant_search(self) -> Agent:
        return Agent(
            config=self.agents_config["restaurant_search"],
            llm=self._llm_large,
            tools=tools_for_crew_agent("restaurant_search"),
        )

    @agent
    def preference_reasoning(self) -> Agent:
        return Agent(
            config=self.agents_config["preference_reasoning"],
            llm=self._llm_small,
            tools=tools_for_crew_agent("preference_reasoning"),
        )

    @agent
    def customer_explanation(self) -> Agent:
        return Agent(
            config=self.agents_config["customer_explanation"],
            llm=self._llm_small,
            tools=tools_for_crew_agent("customer_explanation"),
        )

    # --- tasks (structured output bound here, not in YAML) ---
    @task
    def search_task(self) -> Task:
        return Task(config=self.tasks_config["search_task"], output_pydantic=SearchTaskOutput)

    @task
    def preference_task(self) -> Task:
        return Task(
            config=self.tasks_config["preference_task"], output_pydantic=PreferenceTaskOutput
        )

    @task
    def explanation_task(self) -> Task:
        return Task(
            config=self.tasks_config["explanation_task"], output_pydantic=ExplanationTaskOutput
        )

    # --- crew (hierarchical, coordinator = manager, not in agents list) ---
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.restaurant_search(),
                self.preference_reasoning(),
                self.customer_explanation(),
            ],
            tasks=[self.search_task(), self.preference_task(), self.explanation_task()],
            process=Process.hierarchical,
            manager_agent=self.customer_coordinator(),
            verbose=True,
        )


def build_customer_crew(llm_large: LLM | None = None, llm_small: LLM | None = None) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(llm_large=llm_large, llm_small=llm_small).crew()
