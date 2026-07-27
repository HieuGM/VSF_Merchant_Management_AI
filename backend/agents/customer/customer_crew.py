"""Customer Discovery Crew assembly (Phase 05) — direct sequential specialists.

Reads config/agents.yaml + config/tasks.yaml, binds allow-listed tools via the adapter,
assigns a per-agent LLM, and wires the fixed discovery workflow directly. The three
tasks already declare their dependencies (`context:`) and agent assignment (`agent:`),
so a manager LLM only adds latency without adding information to the final response.

LLM: FPT Cloud DeepSeek-V4-Flash for ALL three specialists. An earlier hybrid design
(NIM llama-3.1-8b for search) was reverted: the 8B model skipped the search tool on
queries matching its parametric knowledge (e.g. "sushi ở Mộc Châu") and fabricated
plausible merchants instead of calling merchant_search — a hallucination failure mode
the prompt could not fix. DeepSeek follows the tool-calling contract reliably.

Tests inject a fake `llm_fpt` so no network/key is required.
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


def _build_fpt_llm() -> LLM:
    """Build FPT Cloud DeepSeek LLM for all specialists (tool-calling + reasoning + NLG).

    Raises ConfigError if FPT not configured."""
    s = get_settings()
    if not s.fpt_configured:
        raise ConfigError(
            "FPT Cloud AI chưa được cấu hình — cần FPT_API_KEY, FPT_BASE_URL, FPT_MODEL_DEEPSEEK"
        )
    return LLM(
        model=f"openai/{s.fpt_model_deepseek}",
        api_key=s.fpt_api_key,
        base_url=s.fpt_base_url,
    )


@CrewBase
class CustomerDiscoveryCrew:
    """CrewAI sequential crew for customer restaurant discovery (UC-04/UC-05).

    No manager/coordinator: the task graph (search → preference → explanation) is fixed via
    `context:` deps + per-task `agent:` in YAML, so each task runs its assigned specialist
    directly. This removes a manager LLM hop per task (latency) and the hierarchical timeout
    failure mode."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, llm_fpt: LLM | None = None) -> None:
        # Defer live LLM construction so tests can inject a fake without a key.
        self._llm_fpt = llm_fpt or _build_fpt_llm()

    # --- agents (method name MUST equal the YAML key) ---
    @agent
    def restaurant_search(self) -> Agent:
        # DeepSeek (was NIM-8b): the 8B model skipped the search tool on parametric-knowledge
        # queries and fabricated merchants. DeepSeek calls the tool reliably → no hallucination.
        return Agent(
            config=self.agents_config["restaurant_search"],
            llm=self._llm_fpt,
            tools=tools_for_crew_agent("restaurant_search"),
        )

    @agent
    def preference_reasoning(self) -> Agent:
        return Agent(
            config=self.agents_config["preference_reasoning"],
            llm=self._llm_fpt,
            tools=tools_for_crew_agent("preference_reasoning"),
        )

    @agent
    def customer_explanation(self) -> Agent:
        return Agent(
            config=self.agents_config["customer_explanation"],
            llm=self._llm_fpt,
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
    # search_task → preference_task (context: search) → explanation_task (context: both).
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


def build_customer_crew(llm_fpt: LLM | None = None) -> Crew:
    """Factory — returns a ready Crew. Pass a fake LLM in tests to avoid network/key."""
    return CustomerDiscoveryCrew(llm_fpt=llm_fpt).crew()
