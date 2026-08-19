"""Merchant advisory flow driven by Mem0 semantic retrieval and single-call planner."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Generator

from crewai import LLM
from langfuse import get_client, observe
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.merchant.planner import plan_request
from agents.merchant.synthesis import synthesize_results
from core.dependencies import get_cache
from core.logging import get_logger
from core.settings import get_settings
from database.connection import SessionLocal
from database.models import Merchant
from models.merchant_agentic import AgenticRunContext
from models.merchant_execution import PlannerDelegate, PlannerRespond
from services.chat_session_service import ChatSessionService
from services.mem0_service import Mem0Service, Mem0WriteDispatcher, memory_identity
from services.merchant_execution_executor import (
    SpecialistResult,
    execute_parallel,
    execute_specialist,
)
from tools.merchant.gateway import RunScopedMerchantToolGateway

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_trace_id(value: str | None) -> str:
    if value is None or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise RuntimeError("merchant flow requires an active Langfuse trace")
    return value


class MerchantFlowDispatcher:
    """Dispatches merchant advisory chat through Mem0 retrieval and planner reasoning."""

    def __init__(
        self,
        memory_service: Mem0Service | None = None,
        memory_writer: Mem0WriteDispatcher | None = None,
        planner_fn: Callable[..., Any] | None = None,
        execute_specialist_fn: Callable[..., Any] | None = None,
        execute_parallel_fn: Callable[..., Any] | None = None,
        synthesize_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.memory_service = memory_service or Mem0Service()
        self.memory_writer = memory_writer or Mem0WriteDispatcher(service=self.memory_service)
        self.planner = planner_fn or plan_request
        self.execute_specialist = execute_specialist_fn or execute_specialist
        self.execute_parallel = execute_parallel_fn or execute_parallel
        self.synthesize = synthesize_fn or synthesize_results

    def _get_llm(self, model_override: str | None = None) -> Any:
        settings = get_settings()
        api_key = settings.llm_api_key or "dummy"
        base_url = settings.llm_base_url
        model = model_override or settings.llm_model_small or "v-llm-v1-small"
        return LLM(
            model=f"openai/{model}",
            api_key=api_key,
            base_url=base_url,
            temperature=0.2,
        )

    def _load_owner_context(self, session: Session, merchant_id: str) -> dict[str, Any]:
        merchant = session.execute(
            select(Merchant).where(Merchant.merchant_id == merchant_id)
        ).scalar_one_or_none()
        if merchant is None:
            return {"merchant_id": merchant_id}
        return {
            "merchant_id": merchant.merchant_id,
            "name": merchant.name,
            "city": merchant.city_slug or merchant.city,
            "cuisine": merchant.cuisine,
        }

    @observe(
        name="merchant-advisor-flow",
        as_type="agent",
        capture_input=False,
        capture_output=False,
    )
    def chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        start_time = time.monotonic()
        client = get_client()
        client.update_current_span(input=message)

        origin_trace_id = None
        try:
            origin_trace_id = client.get_current_trace_id()
        except Exception:
            pass

        owned_db = False
        session = db
        if session is None:
            session = SessionLocal()
            owned_db = True

        try:
            # 1. Resolve / create PostgreSQL session & persist user message
            session_svc = ChatSessionService(session)
            chat_sess = session_svc.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                context_snapshot={"merchant_id": merchant_id},
            )
            actual_session_id = chat_sess.session_id
            session_svc.append_message(
                session_id=actual_session_id,
                sender="user",
                text=message,
                trace_id=origin_trace_id,
            )

            # 2. Build MemoryIdentity & retrieve from Mem0
            identity = memory_identity(user_id=user_id, merchant_id=merchant_id, session_id=actual_session_id)
            with client.start_as_current_observation(
                name="memory.search",
                as_type="retriever",
                input=message,
                metadata={"user_id": identity.user_id, "agent_id": identity.agent_id},
            ) as mem_obs:
                memories = self.memory_service.search(message, identity)
                mem_obs.update(output=[{"memory": hit.memory, "score": hit.score} for hit in memories])

            # 3. Load owner context & plan request
            owner_context = self._load_owner_context(session, merchant_id)
            planner_llm = self._get_llm()
            decision = self.planner(
                query=message,
                memories=memories,
                owner_context=owner_context,
                llm=planner_llm,
                label=label,
            )

            # 4. Route execution
            execution_mode = "respond"
            capabilities_run: list[str] = []
            public_merchants: list[dict[str, Any]] = []
            reply = ""

            trace_ctx = {"trace_id": origin_trace_id} if origin_trace_id else None

            if isinstance(decision, PlannerRespond):
                execution_mode = "respond"
                reply = decision.answer

            elif isinstance(decision, PlannerDelegate):
                tasks = decision.tasks
                capabilities_run = [t.capability for t in tasks]

                def gateway_factory() -> tuple[RunScopedMerchantToolGateway, Session | None]:
                    ctx = AgenticRunContext(
                        session_id=actual_session_id,
                        trace_id=origin_trace_id or "0" * 32,
                        owner_merchant_id=merchant_id,
                        user_id=user_id,
                        user_query=message,
                    )
                    gw = RunScopedMerchantToolGateway(
                        context=ctx,
                        db_session_factory=SessionLocal,
                        cache=get_cache(),
                    )
                    return gw, None

                if len(tasks) == 1:
                    execution_mode = "single"
                    gw, branch_db = gateway_factory()
                    try:
                        spec_res = self.execute_specialist(
                            tasks[0],
                            gateway=gw,
                            llm=planner_llm,
                            trace_context=trace_ctx,
                            label=label,
                        )
                        reply = spec_res.content
                        public_merchants.extend(spec_res.public_merchants)
                    finally:
                        if branch_db is not None:
                            branch_db.close()
                else:
                    execution_mode = "parallel"
                    results = self.execute_parallel(
                        tasks,
                        gateway_factory=gateway_factory,
                        llm=planner_llm,
                        trace_context=trace_ctx,
                        label=label,
                    )
                    for r in results:
                        public_merchants.extend(r.public_merchants)
                    reply = self.synthesize(query=message, results=results, llm=planner_llm, label=label)

            # 5. Persist assistant message
            session_svc.append_message(
                session_id=actual_session_id,
                sender="agent",
                text=reply,
                trace_id=origin_trace_id,
            )

            # 6. Background write to Mem0
            self.memory_writer.submit(
                user_text=message,
                assistant_text=reply,
                identity=identity,
                origin_trace_id=origin_trace_id,
            )

            duration_ms = (time.monotonic() - start_time) * 1000
            client.update_current_span(
                output=reply,
                metadata={
                    "merchant_id": merchant_id,
                    "execution_mode": execution_mode,
                    "capabilities": capabilities_run,
                    "status": "completed",
                    "memory_count": len(memories),
                    "duration_ms": duration_ms,
                },
            )

            return {
                "reply": reply,
                "session_id": actual_session_id,
                "trace_id": origin_trace_id,
                "execution_mode": execution_mode,
                "public_merchants": public_merchants,
                "created_at": _utc_now_iso(),
            }
        finally:
            if owned_db and session is not None:
                session.close()

    def stream_chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream events to client via Queue and yield SSE chunks."""
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def _run() -> None:
            try:
                result = self.chat(
                    merchant_id=merchant_id,
                    message=message,
                    session_id=session_id,
                    user_id=user_id,
                )
                reply_text = result.get("reply", "")
                q.put({"type": "message", "content": reply_text})
                q.put({
                    "type": "finish",
                    "status": "COMPLETED",
                    "session_id": result.get("session_id"),
                    "trace_id": result.get("trace_id"),
                    "merchants": result.get("public_merchants", []),
                    "public_merchants": result.get("public_merchants", []),
                    "evidence_status": "grounded",
                })
            except Exception as exc:
                logger.error("stream_chat_error in background runner: %s", exc, exc_info=True)
                q.put({"type": "agent_error", "error": type(exc).__name__, "message": "An error occurred during execution"})
                q.put({
                    "type": "finish",
                    "status": "FAILED",
                    "session_id": session_id,
                    "trace_id": None,
                    "public_merchants": [],
                    "merchants": [],
                })
            finally:
                q.put(None)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        while True:
            item = q.get()
            if item is None:
                break
            yield item

    def chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        """Yield Server-Sent Events (SSE) for chat stream."""
        for event in self.stream_chat(
            merchant_id=merchant_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
        ):
            event_type = event.get("type", "message")
            if event_type == "message":
                event_name = "token_chunk"
                payload = {
                    "text": event.get("content", ""),
                    "chunk": event.get("content", ""),
                }
            elif event_type == "finish":
                event_name = "execution_finish"
                payload = event
            elif event_type == "agent_error":
                event_name = "agent_error"
                payload = event
            elif event_type == "error":
                event_name = "error"
                payload = event
            else:
                event_name = event_type
                payload = event
            yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


merchant_flow = MerchantFlowDispatcher()
