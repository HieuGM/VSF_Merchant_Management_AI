"""Customer Discovery Crew assembly (Phase 05) — direct sequential specialists.

Reads config/agents.yaml + config/tasks.yaml, binds allow-listed tools via the adapter,
assigns a per-agent LLM, and wires the fixed discovery workflow directly. The three
tasks already declare their dependencies (`context:`) and agent assignment (`agent:`),
so a manager LLM only adds latency without adding information to the final response.

Hybrid LLM (OpenAI-compatible, vendor via settings):
  - restaurant_search      → NVIDIA NIM llama-3.1-8b-instruct  (fast tool-calling)
  - preference_reasoning   → FPT Cloud DeepSeek-V4-Flash      (multi-tool reasoning)
  - customer_explanation   → FPT Cloud DeepSeek-V4-Flash      (natural language)

Tests inject fake `llm_nim` / `llm_fpt` so no network/key is required.
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


def _build_nim_llm() -> LLM:
    """Build NVIDIA NIM 8B LLM for the restaurant_search agent (fast tool-calling).

    8B is sufficient for deterministic nearby/merchant tool selection and avoids spending
    DeepSeek budget on a trivial retrieval step. Raises ConfigError if unkeyed."""
    s = get_settings()
    if not s.nvidia_nim_api_key:
        raise ConfigError("NVIDIA_NIM_API_KEY required for NIM LLM")
    return LLM(
        model=f"{s.llm_provider}/{s.llm_model_small}",
        api_key=s.nvidia_nim_api_key,
        base_url=s.llm_base_url,
    )


def _build_fpt_llm() -> LLM:
    """Build FPT Cloud DeepSeek LLM for reasoning/explanation agents.

    DeepSeek-V4-Flash provides strong multi-tool reasoning + natural Vietnamese generation
    with fast inference. Raises ConfigError if FPT not configured."""
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

    def __init__(self, llm_nim: LLM | None = None, llm_fpt: LLM | None = None) -> None:
        # Defer live LLM construction so tests can inject fakes without a key.
        self._llm_nim = llm_nim or _build_nim_llm()
        self._llm_fpt = llm_fpt or _build_fpt_llm()

    # --- agents (method name MUST equal the YAML key) ---
    @agent
    def restaurant_search(self) -> Agent:
        # NIM 8B for search — fast, doesn't need complex reasoning (tool selection only).
        return Agent(
            config=self.agents_config["restaurant_search"],
            llm=self._llm_nim,
            tools=tools_for_crew_agent("restaurant_search"),
        )

    @agent
    def preference_reasoning(self) -> Agent:
        # FPT DeepSeek for complex multi-tool reasoning (profile + weather + delta).
        return Agent(
            config=self.agents_config["preference_reasoning"],
            llm=self._llm_fpt,
            tools=tools_for_crew_agent("preference_reasoning"),
        )

    @agent
    def customer_explanation(self) -> Agent:
        # FPT DeepSeek for natural Vietnamese explanation generation.
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
        return Task(
            config=self.tasks_config["search_task"],
            output_pydantic=SearchTaskOutput,
        )

    @task
    def preference_task(self) -> Task:
        return Task(
            config=self.tasks_config["preference_task"],
            output_pydantic=PreferenceTaskOutput,
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


def build_customer_crew(
    llm_nim: LLM | None = None,
    llm_fpt: LLM | None = None,
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(llm_nim=llm_nim, llm_fpt=llm_fpt).crew()
