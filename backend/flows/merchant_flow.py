"""Merchant Advisor Flow — active path only (Design §4.1, §4.2, §5.3, §6.2).

Pipeline:
  Request → Policy gates → NativeMerchantAdvisorCrew (hierarchical) →
  Parse terminal outcome → Persist session + trace → Response.
"""
import json
import time
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Generator
from sqlalchemy.orm import Session

from crewai import LLM

from core.dependencies import get_cache
from core.logging import get_logger
from core.settings import get_settings
from database.connection import SessionLocal
from database.models import Merchant
from services.agent_run_service import AgentRunService
from services.chat_session_service import ChatSessionService
from services.request_telemetry import RequestTelemetry
from services.merchant_trace_collector import (
    COORDINATOR_INPUT_ARTIFACT_KEY,
    TraceCollector,
)
from models.merchant_orchestration import TokenUsage
from services.merchant_data_policy import MerchantDataPolicy
from services.merchant_followup import (
    selected_public_merchant,
    selected_public_merchant_update,
)
from models.merchant_agentic import AgenticRunContext, NativeCrewOutcome
from services.merchant_input_preparation import (
    InputPreparationError,
    InputPreparationService,
)
from services.merchant_input_router import (
    conservative_fallback_request,
    decide_route,
    effective_query_policy,
    immutable_session_facts,
)
from services.merchant_route_executor import execute_routing_decision
from tools.merchant.gateway import RunScopedMerchantToolGateway
from agents.merchant.native_crew import (
    NativeMerchantAdvisorCrew,
    coordinator_advisory_task_prompt,
    build_coordinator_prompt,
    coordinator_task_description,
)

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_configured_llm(tier: str = "large") -> LLM | None:
    """Instantiate CrewAI LLM with model tiering ("small" vs "large"), reading API key and base_url from .env."""
    try:
        settings = get_settings()
        api_key = settings.llm_api_key
        if not api_key:
            return None

        if tier == "small":
            model_name = settings.llm_model_small
        else:
            model_name = settings.llm_model_large
        if not model_name:
            raise ValueError(f"LLM model name for tier '{tier}' is not configured in .env.")

        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "temperature": 0,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
            kwargs["provider"] = "openai"
        elif settings.llm_provider and settings.llm_provider != "openai":
            # Native providers (for example `gemini`) do not need a base URL.
            kwargs["provider"] = settings.llm_provider
        return LLM(**kwargs)
    except Exception as e:
        print(f"[get_configured_llm Warning]: {e}")
        return None


class MerchantFlowDispatcher:
    """High-level flow runner connecting services, CrewAI execution, session state, and trace persistence."""

    def chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
        step_callback: Any = None,
        task_callback: Any = None,
        event_callback: Any = None,
    ) -> dict[str, Any]:
        """Run the native coordinator-led CrewAI merchant advisory workflow.

        This is the only active chat path.  The coordinator decides which
        specialists to delegate to; this flow only owns lifecycle, policy,
        session state, gateway construction, and response persistence.
        """
        started_clock = time.perf_counter()
        session = db or SessionLocal()
        trace_id = f"tr-{uuid.uuid4().hex[:12]}"
        session_svc = ChatSessionService(session)
        run_svc = AgentRunService(session)
        trace_summary: list[dict[str, Any]] = []
        pending_trace_events: list[tuple[str, dict[str, Any], bool]] = []
        trace_lock = threading.Lock()
        flushed_trace_count = 0
        run_started = False

        def notify(event_type: str, payload: dict[str, Any]) -> None:
            enriched = {
                **payload,
                "trace_id": trace_id,
                "timestamp": _utc_now_iso(),
            }
            if event_callback is not None:
                try:
                    event_callback(event_type, enriched)
                except Exception:
                    logger.debug("Merchant trace callback failed", exc_info=True)

        def on_semantic_span(span: dict[str, Any]) -> None:
            # Semantic spans are a live developer signal only.  Do not couple
            # the CrewAI callback path to a separate database writer.
            notify("trace_span", span)

        trace_collector = TraceCollector(trace_id, on_semantic_span)

        def emit(
            event_type: str,
            payload: dict[str, Any],
            *,
            notify_live: bool = True,
        ) -> None:
            clean_payload = RequestTelemetry.persistable_payload(payload)
            # CrewAI may run delegated tools on worker threads.  Persisting with
            # the flow's SQLAlchemy Session here would race with the main run.
            # Queue the event and flush it from this flow thread after kickoff.
            with trace_lock:
                trace_summary.append({"event": event_type, **clean_payload})
                pending_trace_events.append((event_type, dict(payload), notify_live))
            if notify_live:
                # The native CrewAI event bus may invoke this from a worker
                # thread.  `chat_stream` uses a thread-safe queue, while the
                # database write remains deferred to this flow thread.
                notify(event_type, payload)

        def flush_trace_events() -> None:
            nonlocal flushed_trace_count
            with trace_lock:
                queued = pending_trace_events[flushed_trace_count:]
                flushed_trace_count = len(pending_trace_events)
            for event_type, payload, notify_live in queued:
                clean_payload = RequestTelemetry.persistable_payload(payload)
                run_svc.record_event(
                    trace_id=trace_id,
                    event_type=event_type,
                    agent_name=payload.get("agent_name"),
                    task_name=payload.get("task") or payload.get("step_id"),
                    tool_name=payload.get("tool_name"),
                    output_summary_json=clean_payload,
                    duration_ms=payload.get("duration_ms"),
                    status=payload.get("status", "ok"),
                    error_code=payload.get("error_code"),
                )

        try:
            context_started = time.perf_counter()
            session_obj = session_svc.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                context_snapshot={"merchant_id": merchant_id},
            )
            sid = session_obj.session_id
            history = session_svc.get_compact_history(session_id=sid, max_turns=3)
            snapshot = session_svc.get_session_snapshot(sid)
            context_payload = {
                "task": "load_history",
                "status": "ok",
                "history_count": len(history),
                "session_state": RequestTelemetry.sanitize(snapshot),
                "duration_ms": round(
                    (time.perf_counter() - context_started) * 1000,
                    3,
                ),
                "token_usage": None,
            }
            session_svc.append_message(
                session_id=sid,
                sender="user",
                text=message,
                trace_id=trace_id,
            )
            run_svc.start_run(
                trace_id=trace_id,
                session_id=sid,
                user_id=user_id,
                crew_name="native_merchant_advisor_crew",
                intent="coordinator_managed",
            )
            run_started = True
            emit("input_context_loaded", context_payload)
            trace_collector.record(
                phase="input",
                actor_type="system",
                actor_name="session_context",
                title="Nạp ngữ cảnh phiên",
                summary=f"Đã nạp {len(history)} lượt hội thoại gần nhất.",
                debug={
                    "session_id": sid,
                    "history_count": len(history),
                },
            )

            def update_session_state(
                state: dict[str, Any],
                task: str,
                *,
                replace: bool = False,
            ) -> None:
                session_svc.update_session_snapshot(
                    sid,
                    state,
                    last_trace_id=trace_id,
                    replace=replace,
                )

            def gateway_emit(payload: dict[str, Any]) -> None:
                event_type = str(payload.pop("event"))
                emit(event_type, payload)

            gateway = RunScopedMerchantToolGateway(
                context=AgenticRunContext(
                    trace_id=trace_id,
                    session_id=sid,
                    owner_merchant_id=str(merchant_id),
                    user_id=user_id,
                    user_query=message,
                ),
                db=session,
                cache=get_cache(),
                emit=gateway_emit,
                db_factory=SessionLocal if db is None else None,
                sql_event_callback=lambda payload: emit("sql_query", payload),
                trace_collector=trace_collector,
            )

            selected_merchant = selected_public_merchant(snapshot)
            owner = session.get(Merchant, merchant_id)
            owner_context = {
                "merchant_id": merchant_id,
                "city": owner.city if owner else None,
                "city_slug": owner.city_slug if owner else None,
                "has_stored_location": bool(
                    owner and owner.lat is not None and owner.lng is not None
                ),
            }

            settings = get_settings()
            emit(
                "input_analyzer_started",
                {
                    "agent_name": "input_analyzer",
                    "task": "prepare_request",
                    "status": "started",
                    "history_count": len(history),
                    "has_selected_public_merchant": selected_merchant is not None,
                },
            )
            analyzer_status = "ok"
            analyzer_summary = "Đã chuẩn bị yêu cầu cho điều phối viên."
            analyzer_debug: dict[str, Any] = {}
            analyzer_llm = (
                get_configured_llm("small")
                if getattr(settings, "llm_configured", False)
                else None
            )
            if analyzer_llm is None:
                prepared_request = conservative_fallback_request(
                    raw_query=message,
                )
                emit(
                    "input_analyzer_fallback",
                    {
                        "agent_name": "input_analyzer",
                        "task": "prepare_request",
                        "status": "fallback",
                        "reason": "small_llm_not_configured",
                        "prepared_request": prepared_request.model_dump(),
                    },
                )
                analyzer_status = "fallback"
                analyzer_summary = "Dùng tuyến dự phòng không gọi mô hình."
            else:
                try:
                    prepared_request = InputPreparationService(
                        llm=analyzer_llm,
                        trace_callback=lambda _event, payload: emit(
                            "input_analyzer_finished",
                            {
                                "agent_name": "input_analyzer",
                                "task": "prepare_request",
                                "status": (
                                    "ok"
                                    if payload.get("parse_result") in {"ok", "repaired"}
                                    else "failed"
                                ),
                                **payload,
                            },
                        ),
                    ).prepare(
                        raw_query=message,
                        history=history,
                        session_state=snapshot,
                        owner_context=owner_context,
                    )
                except InputPreparationError as error:
                    prepared_request = conservative_fallback_request(
                        raw_query=message,
                    )
                    emit(
                        "input_analyzer_fallback",
                        {
                            "agent_name": "input_analyzer",
                            "task": "prepare_request",
                            "status": "fallback",
                            "reason": str(error),
                            "prepared_request": prepared_request.model_dump(),
                        },
                    )
                    analyzer_status = "fallback"
                    analyzer_summary = "Input analyzer không hợp lệ, dùng tuyến dự phòng."
                    analyzer_debug = {"error": str(error)}

            emit(
                analyzer_summary,
                {
                    "status": analyzer_status,
                    "prepared_request": prepared_request.model_dump(),
                    **analyzer_debug,
                },
            )

            raw_query_policy = MerchantDataPolicy(merchant_id).query_decision(message)
            rewritten_query_policy = MerchantDataPolicy(merchant_id).query_decision(
                prepared_request.rewritten_query
            )
            query_policy, policy_authority = effective_query_policy(
                raw_query_policy,
                rewritten_query_policy,
            )
            route = decide_route(
                prepared=prepared_request,
                policy=query_policy,
                immutable_facts=immutable_session_facts(snapshot),
            )
            emit(
                "route_selected",
                {
                    "agent_name": "input_router",
                    "task": "select_route",
                    "status": "ok",
                    "outcome": route.outcome,
                    "reason": route.reason,
                    "scope_candidate": prepared_request.scope_candidate,
                    "rewritten_query": prepared_request.rewritten_query,
                    "raw_policy_allowed": raw_query_policy.allowed,
                    "rewritten_policy_allowed": rewritten_query_policy.allowed,
                    "policy_authority": policy_authority,
                },
            )
            trace_collector.record(
                phase="route",
                actor_type="system",
                actor_name="input_router",
                title="Chọn tuyến xử lý",
                summary=f"Tuyến {route.outcome}: {route.reason}.",
                status="ok",
                debug={
                    "outcome": route.outcome,
                    "reason": route.reason,
                    "rewritten_query": prepared_request.rewritten_query,
                },
            )

            if route.outcome == "reject":
                if route.reason == "merchant_data_policy":
                    emit(
                        "policy_decision",
                        {
                            "agent_name": "merchant_data_policy",
                            "task": "query_policy_gate",
                            "status": "denied",
                            "scope": query_policy.scope,
                            "private_fields": query_policy.private_fields,
                            "policy_authority": policy_authority,
                            "raw_policy_allowed": raw_query_policy.allowed,
                            "rewritten_policy_allowed": rewritten_query_policy.allowed,
                        },
                    )
                return self._finish_native_response(
                    session_svc=session_svc,
                    run_svc=run_svc,
                    trace_id=trace_id,
                    session_id=sid,
                    merchant_id=merchant_id,
                    query=prepared_request.rewritten_query,
                    reply=route.reply
                    or "Câu hỏi nằm ngoài phạm vi hỗ trợ của Merchant Advisor AI.",
                    status="completed",
                    capabilities=[],
                    trace_summary=trace_summary,
                    started_clock=started_clock,
                    structured_outputs={},
                    flush_trace_events=flush_trace_events,
                )
            if route.outcome == "fast_answer":
                return self._finish_native_response(
                    session_svc=session_svc,
                    run_svc=run_svc,
                    trace_id=trace_id,
                    session_id=sid,
                    merchant_id=merchant_id,
                    query=prepared_request.rewritten_query,
                    reply=route.reply or "",
                    status="completed",
                    capabilities=["immutable_session_fast_answer"],
                    trace_summary=trace_summary,
                    started_clock=started_clock,
                    structured_outputs={},
                    token_usage=TokenUsage(),
                    flush_trace_events=flush_trace_events,
                )
            coordinator_prompt = build_coordinator_prompt(
                prepared_request,
                history,
                owner_context,
            )
            trace_collector.record(
                phase="coordinator",
                actor_type="coordinator",
                actor_name="coordinator",
                title="Nạp đầu vào điều phối viên",
                summary=(
                    "Đã nạp câu hỏi đã viết lại và ngữ cảnh bị giới hạn "
                    f"({coordinator_prompt.estimated_tokens}/2400 token ước tính)."
                ),
                metrics={
                    "input_token_estimate": coordinator_prompt.estimated_tokens,
                    "input_token_limit": 2400,
                    "section_token_estimates": coordinator_prompt.section_estimated_tokens,
                },
                debug={
                    COORDINATOR_INPUT_ARTIFACT_KEY: {
                        "dynamic_context": coordinator_prompt.dynamic_context,
                        "prepared_inputs": {
                            "rewritten_query": coordinator_prompt.rewritten_query,
                            "resolved_references": coordinator_prompt.resolved_references,
                            "compact_history": coordinator_prompt.compact_history,
                            "owner_context": coordinator_prompt.owner_context,
                        },
                        "coordinator_goal_prompt": coordinator_task_description(),
                        "advisory_task_prompt": coordinator_advisory_task_prompt(
                            coordinator_prompt
                        ),
                    },
                },
            )

            coordinator_llm = (
                get_configured_llm("large")
                if getattr(settings, "llm_configured", False)
                else None
            )
            if coordinator_llm is None:
                reply = (
                    "Hiện chưa thể khởi chạy điều phối viên AI để xử lý yêu cầu này. "
                    "Vui lòng cấu hình LLM rồi gửi lại câu hỏi; tôi sẽ không tự suy đoán "
                    "hay chạy một kế hoạch cố định."
                )
                emit(
                    "error",
                    {
                        "agent_name": "coordinator",
                        "task": "native_crew_start",
                        "status": "error",
                        "error_code": "llm_not_configured",
                    },
                )
                trace_collector.record(
                    phase="coordinator",
                    actor_type="coordinator",
                    actor_name="coordinator",
                    title="Không thể khởi chạy điều phối viên",
                    summary="LLM điều phối chưa được cấu hình.",
                    status="llm_not_configured",
                    debug={
                        "prepared_input_token_estimate": coordinator_prompt.estimated_tokens,
                    },
                    kind="failed",
                )
                return self._finish_native_response(
                    session_svc=session_svc,
                    run_svc=run_svc,
                    trace_id=trace_id,
                    session_id=sid,
                    merchant_id=merchant_id,
                    query=prepared_request.rewritten_query,
                    reply=reply,
                    status="failed",
                    capabilities=["coordinator"],
                    trace_summary=trace_summary,
                    started_clock=started_clock,
                    structured_outputs={},
                    flush_trace_events=flush_trace_events,
                )

            crew_started = time.perf_counter()
            execution = execute_routing_decision(
                route,
                kickoff_coordinator=lambda: NativeMerchantAdvisorCrew(
                    gateway=gateway,
                    llm=coordinator_llm,
                    native_event_callback=emit,
                    trace_collector=trace_collector,
                ).kickoff(
                    prepared_request=prepared_request,
                    compact_history=coordinator_prompt.compact_history,
                    owner_context=coordinator_prompt.owner_context,
                    coordinator_prompt=coordinator_prompt,
                ),
            )
            crew_result = execution.crew_result
            crew_duration = round((time.perf_counter() - crew_started) * 1000, 3)
            raw_result = str(
                crew_result.raw if hasattr(crew_result, "raw") else crew_result
            ).strip()
            usage = getattr(crew_result, "token_usage", None)
            token_usage = self._native_trace_token_usage(trace_summary)
            if token_usage.total_tokens == 0:
                token_usage = TokenUsage(
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )

            outcome = self._parse_native_outcome(raw_result)
            if outcome is None:
                reply = (
                    "Điều phối viên trả về định dạng không hợp lệ nên tôi chưa "
                    "thể xác minh câu trả lời. Vui lòng gửi lại yêu cầu."
                )
                status = "failed"
                capabilities = ["coordinator"]
                structured_outputs = {"raw_outcome_rejected": True}
                emit(
                    "error",
                    {
                        "agent_name": "coordinator",
                        "task": "validate_terminal_outcome",
                        "status": status,
                        "error_code": "invalid_native_outcome",
                        "duration_ms": crew_duration,
                        "token_usage": token_usage.model_dump(),
                    },
                )
                return self._finish_native_response(
                    session_svc=session_svc,
                    run_svc=run_svc,
                    trace_id=trace_id,
                    session_id=sid,
                    merchant_id=merchant_id,
                    query=prepared_request.rewritten_query,
                    reply=reply,
                    status=status,
                    capabilities=capabilities,
                    trace_summary=trace_summary,
                    started_clock=started_clock,
                    structured_outputs=structured_outputs,
                    token_usage=token_usage,
                    flush_trace_events=flush_trace_events,
                )
            reply = self._format_native_answer(
                outcome.answer,
                trace_summary,
                public_search_members=gateway.latest_public_search_members(),
            )
            public_search_members = gateway.latest_public_search_members()
            if public_search_members:
                update_session_state(
                    selected_public_merchant_update(
                        reply,
                        public_search_members,
                    ),
                    "update_public_merchant_selection",
                )
            status = "completed"
            delegated_agents = list(
                dict.fromkeys(
                    step.get("agent_name")
                    for step in trace_summary
                    if step.get("agent_name")
                    and step.get("agent_name") != "native_crew"
                )
            )
            capabilities = delegated_agents or ["coordinator", "final_synthesis"]
            structured_outputs = {}
            emit(
                "synthesis",
                {
                    "agent_name": "final_synthesis",
                    "task": "owner_facing_answer",
                    "status": "ok",
                    "duration_ms": crew_duration,
                    "token_usage": token_usage.model_dump(),
                },
            )

            return self._finish_native_response(
                session_svc=session_svc,
                run_svc=run_svc,
                trace_id=trace_id,
                session_id=sid,
                merchant_id=merchant_id,
                query=prepared_request.rewritten_query,
                reply=reply,
                status=status,
                capabilities=capabilities,
                trace_summary=trace_summary,
                started_clock=started_clock,
                structured_outputs=structured_outputs,
                token_usage=token_usage,
                flush_trace_events=flush_trace_events,
            )
        except Exception as error:
            if run_started:
                try:
                    emit(
                        "error",
                        {
                            "agent_name": "coordinator",
                            "task": "native_crew_run",
                            "status": "failed",
                            "error_code": type(error).__name__,
                            "error_message": str(error),
                            "stack_trace": traceback.format_exc(limit=12),
                        },
                    )
                    flush_trace_events()
                    run_svc.finish_run(
                        trace_id=trace_id,
                        status="failed",
                        error_code=type(error).__name__,
                    )
                except Exception:
                    logger.debug("Unable to mark native crew run failed", exc_info=True)
            raise
        finally:
            if db is None:
                session.close()

    @staticmethod
    def _parse_native_outcome(raw_result: str) -> NativeCrewOutcome | None:
        """Parse a terminal answer only from the coordinator's explicit contract."""
        payload = MerchantFlowDispatcher._native_json_payload(raw_result)
        if payload is None or payload.get("status") != "completed":
            return None
        return NativeCrewOutcome.model_validate(payload)

    @staticmethod
    def _native_json_payload(raw_result: str) -> dict[str, Any] | None:
        """Find the final JSON contract even if an LLM mistakenly prefixes prose."""
        decoder = json.JSONDecoder()
        for index, character in enumerate(raw_result):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(raw_result[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("status") == "completed":
                return payload
        return None

    @staticmethod
    def _native_trace_token_usage(trace_summary: list[dict[str, Any]]) -> TokenUsage:
        """Sum SDK LLM spans; CrewOutput can recursively double-count delegation."""
        total = prompt = completion = 0
        for step in trace_summary:
            if step.get("event") != "crewai_llm_finished":
                continue
            usage = step.get("token_usage")
            if not isinstance(usage, dict):
                continue
            total += int(usage.get("total_tokens", 0) or 0)
            prompt += int(usage.get("prompt_tokens", 0) or 0)
            completion += int(usage.get("completion_tokens", 0) or 0)
        return TokenUsage(
            total_tokens=total,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )

    @staticmethod
    def _format_native_answer(
        answer: str,
        trace_summary: list[dict[str, Any]],
        public_search_members: list[dict[str, Any]] | None = None,
    ) -> str:
        """Restore concise evidence sections omitted by a final-synthesis model."""
        executed_tools = {
            step.get("tool_name")
            for step in trace_summary
            if step.get("event") == "tool_finished" and step.get("tool_name")
        }
        if (
            {"search_merchants", "aggregate_public_merchant_cohort"}
            <= executed_tools
            and public_search_members
        ):
            lines: list[str] = []
            member_names: list[str] = []
            for merchant in public_search_members:
                name = merchant.get("name") or "Merchant công khai"
                member_names.append(str(name))
                ratings = merchant.get("ratings")
                rating: Any = merchant.get("rating")
                if rating is None and isinstance(ratings, dict):
                    for platform in ratings.values():
                        if isinstance(platform, dict) and platform.get("rating") is not None:
                            rating = platform["rating"]
                            break
                suffix = f" — {rating} sao" if rating is not None else ""
                lines.append(f"- {name}{suffix}")
            has_member_evidence = any(
                name.casefold() in answer.casefold() for name in member_names
            )
            if not has_member_evidence:
                search_heading = "kết quả tìm kiếm"
                analysis_heading = "phân tích nhóm quán"
                heading_index = answer.casefold().find(search_heading)
                rendered_members = "\n".join(lines)
                rendered_analysis_heading = (
                    "## Phân tích nhóm quán\n\n"
                    if analysis_heading not in answer.casefold()
                    else ""
                )
                if heading_index >= 0:
                    line_end = answer.find("\n", heading_index)
                    line_end = len(answer) if line_end < 0 else line_end
                    answer = (
                        answer[:line_end]
                        + "\n\n"
                        + rendered_members
                        + "\n\n"
                        + rendered_analysis_heading
                        + answer[line_end:]
                    )
                else:
                    answer = (
                        "## Kết quả tìm kiếm\n\n"
                        + rendered_members
                        + "\n\n"
                        + rendered_analysis_heading
                        + answer
                    )
        if answer.lstrip().startswith("#"):
            return answer
        headings = {
            "search_merchants": "Kết quả tìm kiếm",
            "aggregate_public_merchant_cohort": "Phân tích nhóm quán",
            "get_owner_profile_summary": "Chất lượng quán của bạn",
            "get_owner_reviews": "Review của quán",
            "diagnose_owner_merchant": "Điểm yếu và nguyên nhân",
            "recommend_owner_improvements": "Hành động đề xuất",
        }
        # A synthesis can combine several evidence sources.  The section title
        # must describe the strongest evidence type, rather than disappear just
        # because supporting tools also ran.  This is intentionally based on
        # the observed tool trace (not keywords from the user query).
        heading_priority = (
            "recommend_owner_improvements",
            "diagnose_owner_merchant",
            "aggregate_public_merchant_cohort",
            "get_owner_reviews",
            "get_owner_profile_summary",
            "search_merchants",
        )
        heading = next(
            (headings[tool_name] for tool_name in heading_priority if tool_name in executed_tools),
            None,
        )
        return f"## {heading}\n\n{answer}" if heading else answer

    @staticmethod
    def _finish_native_response(
        *,
        session_svc: ChatSessionService,
        run_svc: AgentRunService,
        trace_id: str,
        session_id: str,
        merchant_id: str,
        query: str,
        reply: str,
        status: str,
        capabilities: list[str],
        trace_summary: list[dict[str, Any]],
        started_clock: float,
        structured_outputs: dict[str, Any],
        token_usage: TokenUsage | None = None,
        flush_trace_events: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if flush_trace_events is not None:
            flush_trace_events()
        usage = token_usage or TokenUsage()
        duration_ms = round((time.perf_counter() - started_clock) * 1000)
        token_dict = usage.model_dump()
        run_svc.finish_run(
            trace_id=trace_id,
            status=status,
            token_usage_json=token_dict,
        )
        session_svc.append_message(
            session_id=session_id,
            sender="agent",
            text=reply,
            trace_id=trace_id,
            structured_payload={
                "token_usage": token_dict,
                "capabilities": capabilities,
                "duration_ms": duration_ms,
                "status": status,
            },
        )
        trace_summary.append(
            {
                "event": "query_summary",
                "agent_name": "native_merchant_advisor",
                "task": "complete_query",
                "status": status,
                "duration_ms": duration_ms,
                "token_usage": token_dict,
                "tool_count": MerchantFlowDispatcher._trace_tool_count(trace_summary),
            }
        )
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "merchant_id": merchant_id,
            "intent": "coordinator_managed",
            "capabilities": capabilities,
            "rewritten_query": query,
            "reply": reply,
            "token_usage": token_dict,
            "trace_summary": trace_summary,
            "duration_ms": duration_ms,
            "status": status,
            "merchants": [],
            "competitors": [],
            "structured_outputs": structured_outputs,
            "evidence_status": "native_crew",
        }

    @staticmethod
    def _trace_tool_count(trace_summary: list[dict[str, Any]]) -> int:
        """Count business tool completions across gateway and CrewAI event layers.

        A normal native execution emits a gateway and SDK completion carrying
        the same run-local correlation ID; that exact pair is one business
        execution. SDK-only and gateway-only events each count independently.
        Older payloads without IDs use a conservative per-tool order fallback.
        """
        gateway_events: list[tuple[str, str | None]] = []
        sdk_events: list[tuple[str, str | None]] = []
        for step in trace_summary:
            tool_name = step.get("tool_name")
            if not tool_name:
                continue
            event = step.get("event")
            if event not in {"tool_finished", "crewai_tool_finished"}:
                continue
            correlation = step.get("correlation_id")
            normalized = (
                str(tool_name), str(correlation) if correlation not in (None, "") else None
            )
            if event == "tool_finished":
                gateway_events.append(normalized)
            else:
                sdk_events.append(normalized)

        # Each gateway completion is a concrete execution. Pair only a SDK
        # completion with the same `(tool_name, correlation_id)` once.
        count = len(gateway_events)
        available_gateway_pairs: dict[tuple[str, str], int] = {}
        for tool_name, correlation in gateway_events:
            if correlation is not None:
                pair = (tool_name, correlation)
                available_gateway_pairs[pair] = available_gateway_pairs.get(pair, 0) + 1

        legacy_gateway_by_tool: dict[str, int] = {}
        for tool_name, correlation in gateway_events:
            if correlation is None:
                legacy_gateway_by_tool[tool_name] = (
                    legacy_gateway_by_tool.get(tool_name, 0) + 1
                )
        legacy_sdk_by_tool: dict[str, int] = {}
        for tool_name, correlation in sdk_events:
            if correlation is not None:
                pair = (tool_name, correlation)
                if available_gateway_pairs.get(pair, 0):
                    available_gateway_pairs[pair] -= 1
                else:
                    count += 1
            else:
                legacy_sdk_by_tool[tool_name] = legacy_sdk_by_tool.get(tool_name, 0) + 1

        # Without a correlation ID we cannot prove a pair. Pair in observed
        # order only up to legacy gateway count for the same named tool.
        count += sum(
            max(0, sdk_count - legacy_gateway_by_tool.get(tool_name, 0))
            for tool_name, sdk_count in legacy_sdk_by_tool.items()
        )
        return count


    def chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        """Stream events from the same single chat run used for the final answer."""
        del db  # Worker owns a thread-local SQLAlchemy session.
        import queue
        import threading

        event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        result_box: dict[str, Any] = {}

        def event_cb(event_type: str, payload: dict[str, Any]) -> None:
            event_queue.put((event_type, payload))

        def worker() -> None:
            try:
                result_box["res"] = self.chat(
                    merchant_id=merchant_id,
                    message=message,
                    session_id=session_id,
                    user_id=user_id,
                    event_callback=event_cb,
                )
            except Exception as error:
                result_box["err"] = error
            finally:
                event_queue.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        start_time = time.time()
        timeout_seconds = 300

        while True:
            try:
                event = event_queue.get(timeout=0.2)
                if event is None:
                    break
                event_type, payload = event
                yield (
                    f"event: {event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                )
            except queue.Empty:
                if time.time() - start_time > timeout_seconds:
                    result_box["err"] = RuntimeError(
                        "Hệ thống xử lý quá thời gian chờ 300 giây."
                    )
                    break
                if not thread.is_alive() and event_queue.empty():
                    break

        thread.join(timeout=1.0)
        if "res" in result_box:
            result = result_box["res"]
            reply = result.get("reply", "")
            for index in range(0, len(reply), 24):
                yield (
                    "event: token_chunk\n"
                    f"data: {json.dumps({'text': reply[index:index + 24]}, ensure_ascii=False)}\n\n"
                )
            result_status = str(result.get("status", "completed")).lower()
            terminal_status = {
                "completed": "COMPLETED",
                "failed": "FAILED",
            }.get(result_status, result_status.upper())
            finish = {
                "trace_id": result.get("trace_id", ""),
                "status": terminal_status,
                "capabilities": result.get("capabilities", []),
                "rewritten_query": result.get("rewritten_query", message),
                "token_usage": result.get("token_usage", {}),
                "duration_ms": result.get("duration_ms"),
                "merchants": result.get("merchants", []),
                "competitors": result.get("merchants", []),
                "evidence_status": result.get("evidence_status"),
            }
            yield (
                "event: execution_finish\n"
                f"data: {json.dumps(finish, ensure_ascii=False, default=str)}\n\n"
            )
        else:
            error_text = str(result_box.get("err", "Unknown execution error"))
            yield (
                "event: agent_error\n"
                f"data: {json.dumps({'agent_name': 'MerchantFlow', 'detail': error_text, 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"
            )
            yield (
                "event: execution_finish\n"
                f"data: {json.dumps({'status': 'FAILED', 'error': error_text}, ensure_ascii=False)}\n\n"
            )

# Process-wide singleton instance
merchant_flow = MerchantFlowDispatcher()
