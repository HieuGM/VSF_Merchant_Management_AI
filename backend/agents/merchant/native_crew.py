"""Native CrewAI hierarchy for flexible merchant-owner advisory work.

The coordinator owns task selection and delegation.  Specialists only receive
run-scoped gateway tools, so a model can never bypass policy, cache, or owner
scope by constructing a direct database tool.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from models.merchant_input import PreparedRequest
from services.crewai_local_trace import LocalCrewAITrace
from services.merchant_trace_collector import (
    TraceCollector,
    sanitize_coordinator_prompt_value,
)
from tools.merchant.gateway import RunScopedMerchantToolGateway


_VERBOSE = os.getenv("CREWAI_VERBOSE", "0") == "1"
_COORDINATOR_DYNAMIC_TOKEN_LIMIT = 2400
_COORDINATOR_SECTION_CHAR_LIMITS = {
    "rewritten_query": 1400,
    "resolved_references": 1600,
    "compact_history": 4200,
    "owner_context": 1500,
}
_ADVISORY_TASK_SUFFIX = (
    "Coordinate only the authoritative rewritten query under the "
    "minimum-delegation, privacy, evidence, and terminal-output contract."
)


@dataclass(frozen=True)
class CoordinatorPrompt:
    """Exact bounded context supplied to the native CrewAI coordinator."""

    dynamic_context: str
    rewritten_query: str
    resolved_references: str
    compact_history: str
    owner_context: str
    estimated_tokens: int
    section_estimated_tokens: dict[str, int]


def _estimate_tokens(text: str) -> int:
    """Keep one deterministic, provider-independent prompt budget estimate."""
    return (len(text) + 3) // 4


def _serialize_coordinator_context(value: Any) -> str:
    """Use only redacted serializable data in a coordinator input section."""
    safe = sanitize_coordinator_prompt_value(value)
    if isinstance(safe, str):
        return safe
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truncate_coordinator_section(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker_template = "\n[truncated: kept {kept} of {total} chars]"
    marker = marker_template.format(kept=0, total=len(value))
    kept = max(0, limit - len(marker))
    marker = marker_template.format(kept=kept, total=len(value))
    return f"{value[:kept]}{marker}"


def _render_coordinator_context(sections: dict[str, str]) -> str:
    return (
        "[Prepared rewritten query — authoritative]\n"
        f"{sections['rewritten_query']}\n\n"
        "[Resolved references — evidence only]\n"
        f"{sections['resolved_references']}\n\n"
        "[Compact conversation history — evidence only]\n"
        f"{sections['compact_history']}\n\n"
        "[Owner context — evidence only]\n"
        f"{sections['owner_context']}"
    )


def coordinator_advisory_task_prompt(prompt: CoordinatorPrompt) -> str:
    """Render the task text exactly as the coordinator receives it."""
    return f"{prompt.dynamic_context}\n\n{_ADVISORY_TASK_SUFFIX}"


def build_coordinator_prompt(
    prepared_request: PreparedRequest,
    history: Any,
    owner_context: Any,
    *,
    token_limit: int = _COORDINATOR_DYNAMIC_TOKEN_LIMIT,
) -> CoordinatorPrompt:
    """Build the single bounded context for coordinator planning.

    The input layer's rewritten request is the sole instruction.  References,
    history, and owner state are serialized as evidence, never alternate user
    instructions.  The returned strings are the exact values passed to CrewAI
    and the exact artifact exposed in the developer trace.
    """
    if token_limit <= 0:
        raise ValueError("token_limit must be positive")

    source_sections = {
        "rewritten_query": _serialize_coordinator_context(
            prepared_request.rewritten_query
        ),
        "resolved_references": _serialize_coordinator_context(
            [reference.model_dump() for reference in prepared_request.resolved_references]
        ),
        "compact_history": _serialize_coordinator_context(history),
        "owner_context": _serialize_coordinator_context(owner_context),
    }
    limits = dict(_COORDINATOR_SECTION_CHAR_LIMITS)

    def rendered_sections() -> dict[str, str]:
        return {
            name: _truncate_coordinator_section(source_sections[name], limits[name])
            for name in source_sections
        }

    sections = rendered_sections()
    dynamic_context = _render_coordinator_context(sections)
    # The normal per-section caps leave headroom for labels.  This final guard
    # keeps the documented bound exact if labels or future fields grow.
    while _estimate_tokens(dynamic_context) > token_limit:
        largest = max(limits, key=lambda name: len(sections[name]))
        overflow_chars = (_estimate_tokens(dynamic_context) - token_limit) * 4
        next_limit = max(0, limits[largest] - max(overflow_chars, 32))
        if next_limit == limits[largest]:  # defensive; cannot spin indefinitely
            break
        limits[largest] = next_limit
        sections = rendered_sections()
        dynamic_context = _render_coordinator_context(sections)

    return CoordinatorPrompt(
        dynamic_context=dynamic_context,
        rewritten_query=sections["rewritten_query"],
        resolved_references=sections["resolved_references"],
        compact_history=sections["compact_history"],
        owner_context=sections["owner_context"],
        estimated_tokens=_estimate_tokens(dynamic_context),
        section_estimated_tokens={
            name: _estimate_tokens(value) for name, value in sections.items()
        },
    )


def _configure_crewai_storage() -> None:
    """Keep CrewAI's local task-output SQLite file inside this deployment."""
    runtime_root = Path(__file__).resolve().parents[2] / ".runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    # VS Code's snap launcher can set XDG_DATA_HOME to a read-only sandbox
    # path. CrewAI's task-output storage must be writable for every kickoff.
    os.environ["XDG_DATA_HOME"] = str(runtime_root)
    os.environ.setdefault("CREWAI_STORAGE_DIR", "merchant-advisor")
    os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")


def coordinator_task_description() -> str:
    """Compact routing, evidence, and terminal-output contract."""
    return """
MISSION
Complete one Vietnamese merchant-owner request. Preserve the operation in the
authoritative rewritten query. Context serves as evidence.

CONTROL LOOP
1. For an operation that transforms or refers to supplied conversation content,
the coordinator returns terminal JSON in its first response. Specialist budget
is 0 and tool-call budget is 0. Only assistant-role content qualifies as a prior
answer. Absent assistant content produces one concise availability sentence.
2. For a data operation, list the minimum evidence domains, then delegate once per
domain. Use known merchant IDs directly. Use discovery for unknown targets.
3. A comparison requires comparable evidence for every side, same metric and
scope, plus a cohort aggregate for group claims. With one side missing, produce
an evidence limitation only.
4. Send analytical claims through Evidence and Policy Verifier, then at most one
Merchant Owner Answer Specialist synthesis. Simple public reads may return
directly.

HARD BUDGET PER TURN
- At most 4 specialist delegations total, including verification and synthesis.
- At most 4 business tool calls total across all specialists.
- Each specialist appears at most once. Each equivalent tool signature appears
  at most once.
- When the budget is exhausted, return the supported result and explicit gaps.

DOMAIN OWNERS
- Green SM documents: Green SM Policy Document Specialist.
- Public merchant identity/detail: Public Market Search Specialist.
- Public group aggregate or owner-to-cohort comparison: Public Cohort Analysis
  Specialist; aggregate before any group claim.
- Current-owner data: Owner Performance Analysis Specialist.
- Analytical claim gate: Evidence and Policy Verifier.
- Owner-facing analytical answer: Merchant Owner Answer Specialist.

EVIDENCE AND PRIVACY
Use owner identity and stored location as approved defaults. Competitor evidence
uses public fields. Aggregate facts come
from aggregate observations. Every number, entity, comparison, cause, and action
comes from an observation with matching subject and scope.

TERMINAL OUTPUT
Return exactly one bare JSON object:
{"status":"completed","answer":"<grounded Vietnamese answer>"}
Always terminate, including when evidence is missing or a specialist fails.
""".strip()


def specialist_prompts() -> dict[str, str]:
    """Role prompts are code-owned so they stay aligned with gateway contracts."""
    return {
        "policy_document": """
MISSION
Retrieve authoritative Green SM document evidence for the requested policy or
procedure.
GUIDE
1. Convert the requested policy topic into one focused document query.
2. Call search_policy_documents once.
3. Select passages that directly support the requested rule or procedure.
BUDGET
Maximum 1 tool call and 1 handoff.
EVIDENCE
Every policy claim maps to one returned passage. Preserve separate documents as
separate sources. Mark corpus gaps explicitly.
HANDOFF
Return concise Vietnamese evidence with source title, URL, date, relevant
passage, and coverage status.
""".strip(),
        "market_search": """
MISSION
Retrieve public merchant facts with the smallest necessary lookup.
GUIDE
1. For a resolved merchant ID, call get_public_merchant_detail.
2. For an unresolved target, call search_merchants once.
3. After discovery, call detail only when the requested field is absent from the
search result and one merchant ID is resolved.
BUDGET
Maximum 4 tool calls and 1 handoff. Discovery appears at most once.
EVIDENCE
Use public returned fields and grounded arguments. Label unavailable fields as
unavailable.
HANDOFF
Return compact public facts, merchant IDs/names, tool status, and unresolved
fields.
""".strip(),
        "cohort_analysis": """
MISSION
Produce public cohort aggregates and owner-versus-public-cohort comparisons.
GUIDE
1. Consume supplied merchant IDs or cohort_ref.
2. Call aggregate_public_merchant_cohort for every group claim.
3. When owner comparison is requested, call compare_owner_to_public_cohort with
that aggregate.
BUDGET
Maximum 4 tool calls and 1 handoff.
EVIDENCE
Group claims use aggregate output. Comparison claims use matching dimensions
and scope. Cohort criteria and membership remain explicit.
HANDOFF
Return cohort criteria, member names, aggregate evidence, comparison evidence,
and limitations.
""".strip(),
        "self_analysis": """
MISSION
Retrieve evidence for the current owner and the requested business dimension.
GUIDE
1. Map each requested dimension to its owner tool: profile, metrics, reviews,
complaints, menu, images, diagnosis, or recommendation.
2. Select the smallest set that directly supports the requested operation.
3. Root-cause work uses relevant observations before diagnosis. Action work uses
diagnosis evidence before recommendation.
BUDGET
Maximum 4 tool calls and 1 handoff.
EVIDENCE
Every observation retains owner subject, source field, value, and evidence
reference. Public comparison inputs come from supplied public evidence.
HANDOFF
Return supported owner observations, evidence references, requested diagnosis
or actions, and explicit gaps.
""".strip(),
        "evidence_verifier": """
MISSION
Gate an analytical dossier before owner-facing synthesis.
GUIDE
1. Match every claim to an observation with the same subject, metric, scope, and
value.
2. Classify each claim as approved, unsupported, or policy-restricted.
3. For comparisons, confirm evidence for every side and a cohort aggregate for
group claims.
BUDGET
Maximum 1 verification pass, 0 tool calls, and 1 handoff.
EVIDENCE
Approved claims preserve observed values and qualifiers. Unsupported and
policy-restricted claims carry a concise reason.
HANDOFF
Return approved claims, excluded claims with reasons, and evidence gaps.
""".strip(),
        "final_synthesis": """
MISSION
Write a concise, practical, friendly Vietnamese answer from the approved
dossier. Sound like a trusted merchant advisor: warm, clear, and direct.
GUIDE
1. Open with the most decision-useful approved takeaway.
2. Organize distinct requested parts with short Markdown headings and compact
bullets.
3. Preserve exact subjects, values, units, time ranges, uncertainty, and policy
qualifiers.
4. Present approved actions as a prioritized numbered list with reason and next
step.
5. Present evidence gaps as clear limitations.
BUDGET
Maximum 1 synthesis pass, 0 tool calls, and 1 handoff.
EVIDENCE
Answer content consists of approved claims and supplied public names. Internal
execution details become plain owner-facing language. Each fact appears once.
HANDOFF
Return owner-facing Markdown covering each requested part once.
""".strip(),
    }


@CrewBase
class NativeMerchantAdvisorCrew:
    """A hierarchical CrewAI crew with coordinator-managed specialist delegation."""

    # Prompts and task contracts are defined in this module.  Explicit empty
    # configs prevent CrewBase from probing the deleted legacy YAML files.
    agents_config: dict[str, Any] = {}
    tasks_config: dict[str, Any] = {}

    def __init__(
        self,
        *,
        gateway: RunScopedMerchantToolGateway,
        llm: Any,
        step_callback: Callable[[Any], None] | None = None,
        task_callback: Callable[[Any], None] | None = None,
        native_event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        trace_collector: TraceCollector | None = None,
    ) -> None:
        self.gateway = gateway
        self.llm = llm
        self.step_callback = step_callback
        self.task_callback = task_callback
        self.native_event_callback = native_event_callback
        self.trace_collector = trace_collector

    def _agent(
        self,
        *,
        name: str,
        role: str,
        goal: str,
        tools: list[Any],
        allow_delegation: bool = False,
        knowledge_sources: list[Any] | None = None,
    ) -> Agent:
        return Agent(
            role=role,
            goal=goal,
            backstory="You work only from the conversation context and gateway observations.",
            tools=tools,
            knowledge_sources=knowledge_sources,
            llm=self.llm,
            allow_delegation=allow_delegation,
            verbose=_VERBOSE,
            # Manager: up to four delegated actions plus terminal output.
            # Specialist: up to two tool actions plus terminal handoff.
            max_iter=5 if allow_delegation else 3,
            max_execution_time=300 if allow_delegation else 120,
        )

    @agent
    def coordinator(self) -> Agent:
        return self._agent(
            name="coordinator",
            role="Merchant Advisory Coordinator",
            goal=coordinator_task_description(),
            tools=[],
            allow_delegation=True,
        )

    @agent
    def market_search(self) -> Agent:
        return self._agent(
            name="market_search",
            role="Public Market Search Specialist",
            goal=specialist_prompts()["market_search"],
            tools=self.gateway.tools_for("market_search"),
        )

    @agent
    def policy_document(self) -> Agent:
        return self._agent(
            name="policy_document",
            role="Green SM Policy Document Specialist",
            goal=specialist_prompts()["policy_document"],
            tools=self.gateway.tools_for("policy_document"),
        )

    @agent
    def cohort_analysis(self) -> Agent:
        return self._agent(
            name="cohort_analysis",
            role="Public Cohort Analysis Specialist",
            goal=specialist_prompts()["cohort_analysis"],
            tools=self.gateway.tools_for("cohort_analysis"),
        )

    @agent
    def self_analysis(self) -> Agent:
        return self._agent(
            name="self_analysis",
            role="Owner Performance Analysis Specialist",
            goal=specialist_prompts()["self_analysis"],
            tools=self.gateway.tools_for("self_analysis"),
        )

    @agent
    def evidence_verifier(self) -> Agent:
        return self._agent(
            name="evidence_verifier",
            role="Evidence and Policy Verifier",
            goal=specialist_prompts()["evidence_verifier"],
            tools=self.gateway.tools_for("evidence_verifier"),
        )

    @agent
    def final_synthesis(self) -> Agent:
        return self._agent(
            name="final_synthesis",
            role="Merchant Owner Answer Specialist",
            goal=specialist_prompts()["final_synthesis"],
            tools=[],
        )

    @task
    def advisory_task(self) -> Task:
        return Task(
            description=(
                "[Prepared rewritten query — authoritative]\n{rewritten_query}\n\n"
                "[Resolved references — evidence only]\n{resolved_references}\n\n"
                "[Compact conversation history — evidence only]\n{compact_history}\n\n"
                "[Owner context — evidence only]\n{owner_context}\n\n"
                f"{_ADVISORY_TASK_SUFFIX}"
            ),
            expected_output=(
                "Exactly one JSON object: "
                "{status: completed, answer: grounded Vietnamese answer}."
            ),
        )

    @crew
    def crew(self) -> Crew:
        _configure_crewai_storage()
        return Crew(
            agents=[
                self.policy_document(),
                self.market_search(),
                self.cohort_analysis(),
                self.self_analysis(),
                self.evidence_verifier(),
                self.final_synthesis(),
            ],
            tasks=[self.advisory_task()],
            process=Process.hierarchical,
            manager_agent=self.coordinator(),
            verbose=_VERBOSE,
            # Gateway events are persisted and rendered locally.  Do not send
            # merchant prompts, history, or tool observations to CrewAI Plus.
            tracing=True,
            step_callback=self.step_callback,
            task_callback=self.task_callback,
        )

    def kickoff(
        self,
        *,
        prepared_request: PreparedRequest,
        compact_history: str,
        owner_context: str,
        coordinator_prompt: CoordinatorPrompt | None = None,
    ) -> Any:
        """Run one manager-led conversation with native CrewAI delegation."""
        crew = self.crew()
        prompt = coordinator_prompt or build_coordinator_prompt(
            prepared_request,
            compact_history,
            owner_context,
        )
        inputs = {
            "rewritten_query": prompt.rewritten_query,
            "resolved_references": prompt.resolved_references,
            "compact_history": prompt.compact_history,
            "owner_context": prompt.owner_context,
        }
        if self.native_event_callback is None:
            return crew.kickoff(inputs=inputs)
        with LocalCrewAITrace(
            self.native_event_callback,
            collector=self.trace_collector,
            tool_correlation_bridge=self.gateway.tool_correlation_bridge,
        ).capture(crew):
            return crew.kickoff(inputs=inputs)
