"""Customer Discovery Crew assembly (Phase 05) — direct sequential specialists.

Reads config/agents.yaml + config/tasks.yaml, binds allow-listed tools via the adapter,
assigns a per-agent LLM, and wires the fixed discovery workflow directly. The three
tasks already declare their dependencies (`context:`) and agent assignment (`agent:`),
so a manager LLM only adds latency without adding information to the final response.

Hybrid LLM (FPT, OpenAI-compatible):
  - restaurant_search + preference_reasoning → gpt-oss-20b (fastest tool-caller ~0.69s;
    tool selection + multi-tool reasoning are well within 20B capability, and these run
    on the parallel/hidden part of the graph).
  - customer_explanation → DeepSeek-V4-Flash (stronger Vietnamese NLG + reasoning for the
    final user-facing answer). This is the visible quality lever.

Tests inject fake `llm_fast` / `llm_strong` so no network/key is required.
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


def _build_fast_llm() -> LLM:
    """gpt-oss-20b for search + preference — fastest tool-caller on FPT (~0.69s/call)."""
    s = get_settings()
    if not s.fpt_configured:
        raise ConfigError(
            "FPT Cloud AI chưa được cấu hình — cần FPT_API_KEY, FPT_BASE_URL, FPT_MODEL_FAST"
        )
    return LLM(
        model=f"openai/{s.fpt_model_fast}",
        api_key=s.fpt_api_key,
        base_url=s.fpt_base_url,
    )


def _build_strong_llm() -> LLM:
    """DeepSeek-V4-Flash for explanation — stronger Vietnamese NLG + reasoning for the
    final user-facing answer."""
    s = get_settings()
    if not s.fpt_configured:
        raise ConfigError(
            "FPT Cloud AI chưa được cấu hình — cần FPT_API_KEY, FPT_BASE_URL, FPT_MODEL_DEEPSEEK"
        )
    model = s.fpt_model_deepseek or "DeepSeek-V4-Flash"
    return LLM(
        model=f"openai/{model}",
        api_key=s.fpt_api_key,
        base_url=s.fpt_base_url,
    )


@CrewBase
class CustomerDiscoveryCrew:
    """CrewAI sequential crew for customer restaurant discovery (UC-04/UC-05).

    No manager/coordinator: the task graph (search → preference → explanation) is fixed via
    `context:` deps + per-task `agent:` in YAML, so each task runs its assigned specialist
    directly. Hybrid LLM: fast model for search/preference, strong model for explanation."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, llm_fast: LLM | None = None, llm_strong: LLM | None = None) -> None:
        # Defer live LLM construction so tests can inject fakes without a key.
        self._llm_fast = llm_fast or _build_fast_llm()
        self._llm_strong = llm_strong or _build_strong_llm()

    # --- agents (method name MUST equal the YAML key) ---
    @agent
    def restaurant_search(self) -> Agent:
        # Fast model (gpt-oss-20b): tool selection is trivial, runs on the parallel/hidden path.
        return Agent(
            config=self.agents_config["restaurant_search"],
            llm=self._llm_fast,
            tools=tools_for_crew_agent("restaurant_search"),
        )

    @agent
    def preference_reasoning(self) -> Agent:
        # Fast model: 4 tool calls + structured delta — within 20B capability.
        return Agent(
            config=self.agents_config["preference_reasoning"],
            llm=self._llm_fast,
            tools=tools_for_crew_agent("preference_reasoning"),
        )

    @agent
    def customer_explanation(self) -> Agent:
        # Strong model (DeepSeek): user-facing Vietnamese NLG + tone — the quality lever.
        return Agent(
            config=self.agents_config["customer_explanation"],
            llm=self._llm_strong,
            tools=tools_for_crew_agent("customer_explanation"),
        )

    # --- tasks (structured output bound here, not in YAML) ---
    # Agent assignment is read from `agent:` in tasks.yaml by CrewAI's @CrewBase metaclass
    # (map_all_task_variables), so no explicit `agent=` kwarg is needed here.
    @task
    def search_task(self) -> Task:
        # async_execution=True: runs in parallel with preference_task (no runtime dep — preference
        # reads profile/weather/session, not search output). explanation_task waits for both via its
        # context. Saves ~10s (the search duration) off the critical path.
        return Task(
            config=self.tasks_config["search_task"],
            output_pydantic=SearchTaskOutput,
            async_execution=True,
        )

    @task
    def preference_task(self) -> Task:
        # async_execution=True: runs in parallel with search_task.
        return Task(
            config=self.tasks_config["preference_task"],
            output_pydantic=PreferenceTaskOutput,
            async_execution=True,
        )

    @task
    def explanation_task(self) -> Task:
        return Task(
            config=self.tasks_config["explanation_task"],
            output_pydantic=ExplanationTaskOutput,
        )

    # Task graph: fixed sequential execution.
    # search_task → preference_task (parallel) → explanation_task (context: both).
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.restaurant_search(),
                self.preference_reasoning(),
                self.customer_explanation(),
            ],
            tasks=[
                self.search_task(),
                self.preference_task(),
                self.explanation_task(),
            ],
            process=Process.sequential,
            verbose=True,
            cache=True,
            # memory=False: CrewAI memory needs an embedder (CHROMA_OPENAI_API_KEY / OPENAI_API_KEY
            # for text-embedding-3-large) which this env doesn't configure; enabling it spammed
            # Memory Query/Save errors every task with no benefit. Re-enable once an embedder is set.
            memory=False,
            respect_context_window=True,
        )


def build_customer_crew(
    llm_fast: LLM | None = None,
    llm_strong: LLM | None = None,
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(llm_fast=llm_fast, llm_strong=llm_strong).crew()
