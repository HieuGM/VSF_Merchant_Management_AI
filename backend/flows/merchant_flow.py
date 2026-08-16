"""Merchant advisory flow traced by Langfuse and CrewAI OpenInference."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Generator

from crewai import LLM
from langfuse import get_client, observe, propagate_attributes
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from agents.merchant.native_crew import NativeMerchantAdvisorCrew, build_coordinator_prompt
from core.dependencies import get_cache
from core.logging import get_logger, safe_exception_trace
from core.settings import get_settings
from database.connection import SessionLocal
from database.models import Merchant
from models.merchant_agentic import AgenticRunContext, NativeCrewOutcome, normalize_text
from models.merchant_input import PreparedRequest
from services.chat_session_service import ChatSessionService
from services.merchant_data_policy import MerchantDataPolicy
from services.merchant_input_preparation import InputPreparationError, InputPreparationService
from services.merchant_input_router import (
    decide_route,
    effective_query_policy,
    immutable_session_facts,
)

from tools.merchant.gateway import RunScopedMerchantToolGateway

logger = get_logger(__name__)
_SELECTED_PUBLIC_MERCHANT = "merchant_agentic.selected_public_merchant"
_LAST_PUBLIC_SEARCH = "merchant_agentic.last_public_search"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_trace_id(value: str | None) -> str:
    if value is None or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise RuntimeError("merchant flow requires an active Langfuse trace")
    return value


def _selected_public_merchant(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    selected = snapshot.get(_SELECTED_PUBLIC_MERCHANT)
    return selected if isinstance(selected, dict) and selected.get("merchant_id") else None


def _deduplicate_merchants(merchants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in merchants:
        mid = str(item.get("merchant_id")) if item.get("merchant_id") is not None else None
        if mid and mid not in seen:
            seen.add(mid)
            result.append(item)
    return result


def _public_merchant_selection_update(answer: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    public_candidates = [
        {
            key: candidate[key]
            for key in (
                "merchant_id", "name", "cuisine", "address", "ratings",
                "distance_km", "menu_price_min", "menu_price_median", "menu_price_max",
            )
            if candidate.get(key) is not None
        }
        for candidate in candidates[:5]
        if candidate.get("merchant_id") and candidate.get("name")
    ]
    update: dict[str, Any] = {_LAST_PUBLIC_SEARCH: public_candidates}
    normalized_answer = normalize_text(answer)
    mentioned = [
        candidate for candidate in public_candidates
        if str(candidate["merchant_id"]) in answer
        or normalize_text(str(candidate["name"])) in normalized_answer
    ]
    if len(mentioned) == 1:
        update[_SELECTED_PUBLIC_MERCHANT] = mentioned[0]
    elif len(public_candidates) == 1:
        update[_SELECTED_PUBLIC_MERCHANT] = public_candidates[0]
    return update


def _named_other_merchant(session: Session, query: str, owner_id: str) -> Merchant | None:
    return session.execute(
        select(Merchant)
        .where(
            Merchant.merchant_id != str(owner_id),
            Merchant.is_active.is_(True),
            func.length(Merchant.name) >= 6,
            func.strpos(func.lower(literal(query)), func.lower(Merchant.name)) > 0,
        )
        .limit(1)
    ).scalar_one_or_none()


def _correct_named_public_request(
    prepared: PreparedRequest, raw_query: str, names_other_merchant: bool
) -> PreparedRequest:
    if not names_other_merchant:
        return prepared
    return prepared.model_copy(update={
        "rewritten_query": raw_query[:1200],
        "scope_candidate": "allowed",
        "resolved_references": [],
    })


def get_configured_llm(tier: str = "large") -> LLM | None:
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    model = settings.llm_model_small if tier == "small" else settings.llm_model_large
    if not model:
        logger.error("llm_model_missing tier=%s", tier)
        return None
    options: dict[str, Any] = {
        "model": model,
        "api_key": settings.llm_api_key,
        "temperature": 0,
        "timeout": 300,
    }
    if settings.llm_base_url:
        options.update(base_url=settings.llm_base_url, provider="openai")
    elif settings.llm_provider != "openai":
        options["provider"] = settings.llm_provider
    try:
        return LLM(**options)
    except Exception as error:
        logger.error("llm_construction_failed tier=%s\n%s", tier, safe_exception_trace(error))
        return None


class MerchantFlowDispatcher:
    @observe(
        name="merchant-advisor-flow",
        as_type="agent"
    )
    def chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
        **_obsolete_callbacks: Any,
    ) -> dict[str, Any]:
        session = db or SessionLocal()
        try:
            session_service = ChatSessionService(session)
            chat_session = session_service.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                context_snapshot={"merchant_id": merchant_id},
            )
            trace_id = _require_trace_id(get_client().get_current_trace_id())
            settings = get_settings()
            with propagate_attributes(
                user_id=user_id or merchant_id,
                session_id=chat_session.session_id,
                tags=["merchant-agent", "crewai"],
                metadata={"merchant_id": merchant_id},
                trace_name="merchant-advisor-flow",
                environment=settings.environment,
            ):
                return self._execute(
                    session=session,
                    session_service=session_service,
                    trace_id=trace_id,
                    session_id=chat_session.session_id,
                    merchant_id=merchant_id,
                    message=message,
                    user_id=user_id,
                    owns_session=db is None,
                )
        except Exception as error:
            logger.error(
                "merchant_chat_failed error_code=%s\n%s",
                type(error).__name__,
                safe_exception_trace(error),
            )
            raise
        finally:
            if db is None:
                session.close()

    def _execute(
        self,
        *,
        session: Session,
        session_service: ChatSessionService,
        trace_id: str,
        session_id: str,
        merchant_id: str,
        message: str,
        user_id: str | None,
        owns_session: bool,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        history = session_service.get_compact_history(session_id=session_id, max_turns=3)
        snapshot = session_service.get_session_snapshot(session_id)
        session_service.append_message(
            session_id=session_id, sender="user", text=message, trace_id=trace_id
        )
        owner = session.get(Merchant, merchant_id)
        owner_context = {
            "merchant_id": merchant_id,
            "name": owner.name if owner else None,
            "city": owner.city if owner else None,
            "city_slug": owner.city_slug if owner else None,
            "has_stored_location": bool(owner and owner.lat is not None and owner.lng is not None),
        }
        named_target = _named_other_merchant(session, message, merchant_id)
        analyzer = get_configured_llm("small")
        if analyzer is None:
            return self._complete(
                session_service, trace_id, session_id, merchant_id, message,
                "Input Analyzer chưa được cấu hình.", "failed", [], started,
            )
        try:
            prepared = InputPreparationService(llm=analyzer).prepare(
                raw_query=message,
                history=history,
                session_state=snapshot,
                owner_context=owner_context,
            )
        except InputPreparationError as error:
            blocked = str(error) == "prompt_injection_blocked"
            return self._complete(
                session_service, trace_id, session_id, merchant_id, message,
                "Yêu cầu bị chặn bởi bộ lọc an toàn đầu vào."
                if blocked else "Input Analyzer trả về kết quả không hợp lệ.",
                "completed" if blocked else "failed", [], started,
            )
        logger.info(f"NLU: {prepared}")
        prepared = _correct_named_public_request(prepared, message, named_target is not None)
        raw_policy = MerchantDataPolicy(merchant_id).query_decision(
            message, targets_other_merchant=named_target is not None
        )
        rewritten_policy = MerchantDataPolicy(merchant_id).query_decision(
            prepared.rewritten_query, targets_other_merchant=named_target is not None
        )
        policy, _authority = effective_query_policy(raw_policy, rewritten_policy)
        route = decide_route(
            prepared=prepared,
            policy=policy,
            immutable_facts=immutable_session_facts(snapshot),
        )
        if route.outcome == "reject":
            return self._complete(
                session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                route.reply or "Câu hỏi nằm ngoài phạm vi hỗ trợ của Merchant Advisor AI.",
                "completed", [], started,
            )
        # if route.outcome == "clarify":
        #     missing = ", ".join(prepared.missing_context[:3])
        #     reply = f"Vâng, tôi cần thêm thông tin để trả lời chính xác: {missing}." if missing else "Bạn có thể cung cấp thêm chi tiết không?"
        #     return self._complete(
        #         session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
        #         reply, "completed", [], started,
        #     )

        gateway = RunScopedMerchantToolGateway(
            context=AgenticRunContext(
                trace_id=trace_id,
                session_id=session_id,
                owner_merchant_id=str(merchant_id),
                user_id=user_id,
                user_query=message,
            ),
            db=session,
            cache=get_cache(),
            emit=lambda _payload: None,
            db_factory=SessionLocal if owns_session else None,
        )
        gateway.allow_public_merchant_ids([
            str(reference.merchant_id)
            for reference in prepared.resolved_references
            if reference.kind == "public_merchant" and reference.merchant_id
        ])

        settings = get_settings()
        mode_setting = settings.merchant_execution_mode.lower()
        coordinator_llm = get_configured_llm("large")
        small_llm = get_configured_llm("small") or coordinator_llm

        if mode_setting in ("legacy", "shadow") and coordinator_llm is None:
            return self._complete(
                session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                "LLM điều phối chưa được cấu hình.", "failed", ["coordinator"], started,
                execution_mode=mode_setting,
            )

        # 1. Shadow or Active mode: generate ExecutionPlan
        plan: ExecutionPlan | None = None
        if mode_setting in ("shadow", "active"):
            try:
                from agents.merchant.native_crew import plan_execution
                plan = plan_execution(prepared, history, owner_context, llm=small_llm or coordinator_llm)
                logger.info("execution_plan_generated mode=%s plan_mode=%s tasks_count=%d", mode_setting, plan.mode, len(plan.tasks))
            except Exception as plan_err:
                logger.warning("execution_plan_generation_failed mode=%s error=%s", mode_setting, plan_err)
                if mode_setting == "active":
                    return self._complete(
                        session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                        "Không thể lập kế hoạch xử lý cho yêu cầu này.", "failed", ["coordinator"], started,
                        execution_mode=mode_setting,
                    )

        # 2. Active Mode: Execute direct, parallel, or hierarchical based on plan
        if mode_setting == "active" and plan is not None:
            from services.merchant_execution_executor import execute_direct, execute_parallel, merge_parallel_results

            if plan.mode == "direct":
                task = plan.tasks[0]
                spec_res = execute_direct(task, gateway=gateway, llm=small_llm, response_type=plan.response_type)
                reply = spec_res.content if spec_res.status == "completed" else "Không thể xử lý yêu cầu trực tiếp."
                merchants = _deduplicate_merchants(spec_res.public_merchants or gateway.latest_public_search_members())
                if merchants:
                    session_service.update_session_snapshot(
                        session_id,
                        _public_merchant_selection_update(reply, merchants),
                        last_trace_id=trace_id,
                    )
                return self._complete(
                    session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                    reply, "completed" if spec_res.status == "completed" else "failed",
                    [task.capability], started, merchants=merchants, execution_mode=plan.mode,
                )

            elif plan.mode == "parallel":
                def gateway_factory() -> tuple[RunScopedMerchantToolGateway, Session | None]:
                    branch_session = SessionLocal()
                    branch_gw = RunScopedMerchantToolGateway(
                        context=AgenticRunContext(
                            trace_id=trace_id,
                            session_id=session_id,
                            owner_merchant_id=str(merchant_id),
                            user_id=user_id,
                            user_query=message,
                        ),
                        db=branch_session,
                        cache=get_cache(),
                        emit=lambda _payload: None,
                        db_factory=None,  # reuse branch_session without opening 2nd session
                    )
                    branch_gw.allow_public_merchant_ids([
                        str(r.merchant_id) for r in prepared.resolved_references
                        if r.kind == "public_merchant" and r.merchant_id
                    ])
                    return branch_gw, branch_session

                par_results = execute_parallel(plan.tasks, gateway_factory=gateway_factory, llm=small_llm, response_type=plan.response_type)
                reply = merge_parallel_results(par_results)

                # Combine & deduplicate public search members across all parallel branches
                all_merchants = []
                for res in par_results:
                    if res.public_merchants:
                        all_merchants.extend(res.public_merchants)
                merchants = _deduplicate_merchants(all_merchants)

                if merchants:
                    session_service.update_session_snapshot(
                        session_id,
                        _public_merchant_selection_update(reply, merchants),
                        last_trace_id=trace_id,
                    )

                # Determine status
                if all(r.status == "failed" for r in par_results):
                    final_status = "failed"
                elif any(r.status == "failed" for r in par_results):
                    final_status = "partial"
                else:
                    final_status = "completed"

                caps = [t.capability for t in plan.tasks]
                return self._complete(
                    session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                    reply, final_status, caps, started, merchants=merchants, execution_mode=plan.mode,
                )

            elif plan.mode == "hierarchical":
                if coordinator_llm is None:
                    return self._complete(
                        session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                        "LLM điều phối chưa được cấu hình.", "failed", ["coordinator"], started,
                        execution_mode=plan.mode,
                    )
                context = build_coordinator_prompt(prepared, history, owner_context)
                result = NativeMerchantAdvisorCrew(gateway=gateway, llm=coordinator_llm).kickoff(
                    prepared_request=prepared,
                    compact_history=context.compact_history,
                    owner_context=context.owner_context,
                    coordinator_prompt=context,
                    plan_tasks=plan.tasks,
                )
                raw = str(result.raw if hasattr(result, "raw") else result).strip()
                outcome = self._parse_native_outcome(raw)
                if outcome is None:
                    return self._complete(
                        session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                        "Điều phối viên trả về định dạng không hợp lệ.", "failed", ["coordinator"], started,
                        execution_mode=plan.mode,
                    )
                merchants = _deduplicate_merchants(gateway.latest_public_search_members())
                if merchants:
                    session_service.update_session_snapshot(
                        session_id,
                        _public_merchant_selection_update(outcome.answer, merchants),
                        last_trace_id=trace_id,
                    )
                caps = [t.capability for t in plan.tasks]
                return self._complete(
                    session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                    outcome.answer, "completed", caps, started, merchants=merchants, execution_mode=plan.mode,
                )

        # 3. Legacy mode or Shadow fallback mode: Execute native crew hierarchy
        if coordinator_llm is None:
            return self._complete(
                session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                "LLM điều phối chưa được cấu hình.", "failed", ["coordinator"], started,
                execution_mode="legacy",
            )
        context = build_coordinator_prompt(prepared, history, owner_context)
        result = NativeMerchantAdvisorCrew(gateway=gateway, llm=coordinator_llm).kickoff(
            prepared_request=prepared,
            compact_history=context.compact_history,
            owner_context=context.owner_context,
            coordinator_prompt=context,
        )
        raw = str(result.raw if hasattr(result, "raw") else result).strip()
        outcome = self._parse_native_outcome(raw)
        if outcome is None:
            logger.error("invalid_native_outcome")
            return self._complete(
                session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
                "Điều phối viên trả về định dạng không hợp lệ.",
                "failed", ["coordinator"], started,
                execution_mode="legacy",
            )
        merchants = gateway.latest_public_search_members()
        if merchants:
            session_service.update_session_snapshot(
                session_id,
                _public_merchant_selection_update(outcome.answer, merchants),
                last_trace_id=trace_id,
            )
        return self._complete(
            session_service, trace_id, session_id, merchant_id, prepared.rewritten_query,
            outcome.answer, "completed", ["coordinator", "final_synthesis"], started,
            merchants=merchants, execution_mode="legacy",
        )

    @staticmethod
    def _parse_native_outcome(raw: str) -> NativeCrewOutcome | None:
        decoder = json.JSONDecoder()
        for index, character in enumerate(raw):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("status") == "completed":
                return NativeCrewOutcome.model_validate(payload)
        return None

    @staticmethod
    def _complete(
        session_service: ChatSessionService,
        trace_id: str,
        session_id: str,
        merchant_id: str,
        query: str,
        reply: str,
        status: str,
        capabilities: list[str],
        started: float,
        *,
        merchants: list[dict[str, Any]] | None = None,
        execution_mode: str = "legacy",
    ) -> dict[str, Any]:
        duration_ms = round((time.perf_counter() - started) * 1000)
        session_service.append_message(
            session_id=session_id,
            sender="agent",
            text=reply,
            trace_id=trace_id,
            structured_payload={"capabilities": capabilities, "status": status, "execution_mode": execution_mode},
        )
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "merchant_id": merchant_id,
            "capabilities": capabilities,
            "execution_mode": execution_mode,
            "rewritten_query": query,
            "reply": reply,
            "duration_ms": duration_ms,
            "status": status,
            "merchants": merchants or [],
            "competitors": [],
            "evidence_status": "langfuse",
        }

    def chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        del db
        result: dict[str, Any] = {}

        def worker() -> None:
            try:
                result["response"] = self.chat(
                    merchant_id=merchant_id,
                    message=message,
                    session_id=session_id,
                    user_id=user_id,
                )
            except Exception as error:
                result["error"] = error

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        last_heartbeat = time.monotonic()
        while thread.is_alive():
            thread.join(timeout=0.5)
            if thread.is_alive() and time.monotonic() - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
        if "response" in result:
            response = result["response"]
            reply = response.get("reply", "")
            for index in range(0, len(reply), 24):
                yield "event: token_chunk\n" + "data: " + json.dumps(
                    {"text": reply[index:index + 24]}, ensure_ascii=False
                ) + "\n\n"
            finish = {
                "trace_id": response["trace_id"],
                "status": str(response.get("status", "completed")).upper(),
                "merchants": response.get("merchants", []),
                "competitors": response.get("competitors", []),
                "evidence_status": response.get("evidence_status"),
            }
            yield "event: execution_finish\n" + "data: " + json.dumps(
                finish, ensure_ascii=False
            ) + "\n\n"
            return
        error = result.get("error")
        error_code = type(error).__name__ if isinstance(error, Exception) else "ExecutionError"
        safe_message = "Không thể hoàn tất yêu cầu. Vui lòng thử lại."
        yield "event: agent_error\n" + "data: " + json.dumps({
            "detail": safe_message,
            "error_code": error_code,
            "timestamp": _utc_now_iso(),
        }, ensure_ascii=False) + "\n\n"
        yield "event: execution_finish\n" + "data: " + json.dumps({
            "status": "FAILED", "error": safe_message, "error_code": error_code
        }, ensure_ascii=False) + "\n\n"


merchant_flow = MerchantFlowDispatcher()
