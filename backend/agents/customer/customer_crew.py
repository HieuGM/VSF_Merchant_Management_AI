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

import functools
from pathlib import Path

import yaml
from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from agents.tool_adapter import tools_for_crew_agent
from core.errors import ConfigError
from core.settings import get_settings
from models.customer_tasks import (
    PreferenceTaskOutput,
    SearchTaskOutput,
)

_CONFIG_DIR = Path(__file__).parent / "config"


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

    def __init__(
        self,
        llm_fast: LLM | None = None,
        llm_strong: LLM | None = None,
        has_location: bool = False,
        mode: str = "full",
    ) -> None:
        # Defer live LLM construction so tests can inject fakes without a key.
        self._llm_fast = llm_fast or _build_fast_llm()
        self._llm_strong = llm_strong or _build_strong_llm()
        # When the user supplied coords, lock the search agent to nearby_merchant_search
        # (haversine hard-filter → correct city). Otherwise it only gets merchant_search
        # (text/cuisine, all-VN). This removes the LLM's freedom to pick the non-geo tool
        # and leak far-away results (the HCM-instead-of-HN bug).
        self._has_location = has_location
        # mode controls which tasks the crew runs:
        #   "full"       → search + preference + explanation (blocking /chat path).
        #   "search"     → search only (1-task crew).
        #   "preference" → preference only (1-task crew).
        # The SSE path runs "search" and "preference" crews CONCURRENTLY (two single-task
        # crews in parallel threads) for true parallelism, then streams the explanation via
        # a separate direct DeepSeek call. CrewAI crew-level streaming is unreliable with the
        # tool-calling agents on FPT, and a 2-task async crew can't satisfy CrewAI's
        # "end with at most one async task" rule without serializing — so we sidestep both.
        self._mode = mode

    # --- agents (method name MUST equal the YAML key) ---
    @agent
    def restaurant_search(self) -> Agent:
        # Fast model (gpt-oss-20b): tool selection is trivial, runs on the parallel/hidden path.
        # Tool set is LOCKED by location (see __init__): nearby_merchant_search only when coords
        # are known (haversine hard-filter → correct city), merchant_search only otherwise.
        tools = tools_for_crew_agent("restaurant_search")
        wanted = "nearby_merchant_search" if self._has_location else "merchant_search"
        tools = [t for t in tools if t.name == wanted]
        return Agent(
            config=self.agents_config["restaurant_search"],
            llm=self._llm_fast,
            tools=tools,
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
        # async_execution only in "full" mode (parallel with preference_task; explanation_task
        # is the trailing sync task that awaits both). In single-task "search" mode it's sync.
        return Task(
            config=self.tasks_config["search_task"],
            output_pydantic=SearchTaskOutput,
            async_execution=self._mode == "full",
        )

    @task
    def preference_task(self) -> Task:
        # async_execution only in "full" mode (explanation is the trailing sync task). In
        # single-task "preference" mode it's sync.
        return Task(
            config=self.tasks_config["preference_task"],
            output_pydantic=PreferenceTaskOutput,
            async_execution=self._mode == "full",
        )

    @task
    def explanation_task(self) -> Task:
        # Free-text output (no output_pydantic): the answer is conversational Vietnamese,
        # and structured JSON would make streamed tokens unreadable on the UI
        # (chunks would be JSON fragments like `{"answer": "Hôm`). Free-text lets the
        # SSE stream forward readable token deltas; the full text IS the answer.
        # `reasons`/`referenced_signals` (former ExplanationTaskOutput fields) were never
        # surfaced to the FE, so dropping them is quality-neutral.
        return Task(
            config=self.tasks_config["explanation_task"],
        )

    # Task graph by mode:
    #   "full"           → search(async) + preference(async) + explanation(sync): search &
    #                      preference run concurrently (explanation, the trailing sync task,
    #                      awaits both). Blocking /chat path when the query has taste signals.
    #   "search_explain" → search + explanation (skip preference) — blocking path for
    #                      pure-discovery queries (no taste/dietary signals → preference would
    #                      return empty anyway, ~15s saved).
    #   "search"         → search only (sync, single-task).
    #   "preference"     → preference only (sync, single-task).
    # The SSE path runs "search" + "preference" crews concurrently in two threads.
    @crew
    def crew(self) -> Crew:
        if self._mode == "search":
            agents = [self.restaurant_search()]
            tasks = [self.search_task()]
        elif self._mode == "preference":
            agents = [self.preference_reasoning()]
            tasks = [self.preference_task()]
        elif self._mode == "search_explain":
            agents = [self.restaurant_search(), self.customer_explanation()]
            tasks = [self.search_task(), self.explanation_task()]
        else:  # "full"
            agents = [
                self.restaurant_search(),
                self.preference_reasoning(),
                self.customer_explanation(),
            ]
            tasks = [
                self.search_task(),
                self.preference_task(),
                self.explanation_task(),
            ]
        return Crew(
            agents=agents,
            tasks=tasks,
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
    has_location: bool = False,
    mode: str = "full",
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key.
    `has_location` locks the search agent to nearby_merchant_search (geo hard-filter).
    `mode`: "full" (3-task, blocking path) | "search" | "preference" (1-task crews the SSE
    path runs concurrently, then streams the explanation via a separate DeepSeek call)."""
    return CustomerDiscoveryCrew(
        llm_fast=llm_fast,
        llm_strong=llm_strong,
        has_location=has_location,
        mode=mode,
    ).crew()


@functools.lru_cache(maxsize=1)
def _load_config(name: str) -> dict:
    """Load a customer crew YAML config (agents/tasks). Cached — the YAML rarely changes."""
    with open(_CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def explanation_prompt_pieces() -> dict:
    """Persona + instruction for the free-text explanation, sourced from agents.yaml +
    tasks.yaml (single source of truth — same files the CrewAI agents read).

    Used by the streaming flow to build a DIRECT DeepSeek streaming call: CrewAI's
    crew-level streaming (Crew(stream=True)) is unreliable with the tool-calling
    search/preference agents on FPT, so the SSE path runs search+preference non-streaming
    and streams the explanation answer outside the crew. Returns:
      - system: the agent backstory + role (+ output-format reminder)
      - instruction: the explanation task description (references {query} etc.)
    """
    agent_cfg = _load_config("agents.yaml")["customer_explanation"]
    task_cfg = _load_config("tasks.yaml")["explanation_task"]
    system = (
        f"{str(agent_cfg['backstory']).strip()}\n\n"
        f"Vai trò: {str(agent_cfg['role']).strip()}\n\n"
        f"Yêu cầu định dạng output:\n{str(task_cfg['expected_output']).strip()}"
    )
    return {
        "system": system,
        "instruction": str(task_cfg["description"]),
    }
