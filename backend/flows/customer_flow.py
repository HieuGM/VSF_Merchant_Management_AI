"""Customer flow (G-02) — CrewAI Crew orchestration + run/event persistence.

Phase 06: replaces the Phase-0b direct tool call with a real `CustomerDiscoveryCrew`
kickoff. The flow owns the run lifecycle (agent_runs + run_started/run_finished events);
the PersistingListener persists tool/task trace events emitted by CrewAI during kickoff.
Every run carries a `trace_id` (§11.4) so events and results correlate.
"""
from __future__ import annotations

import concurrent.futures
import contextvars
import unicodedata
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from agents.listeners.crewai_listener import build_event_record
from agents.listeners.persisting_listener import install_persisting_listener, run_scope
from agents.tool_adapter import tool_call_scope
from core.tracing import new_id
from models.agent import AgentRunRecord, CustomerChatResponse
from repositories.agent_run_repository import AgentRunRepository
from tools.registry import registry

_CREW_NAME = "customer_discovery"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Keywords that signal the query carries taste/dietary/context the preference agent would
# act on. Their ABSENCE means a pure-discovery query (food + location only, e.g.
# "phở gần Cầu Giấy") — preference_task would return empty anyway, so we skip it (~15s saved,
# TTFT ~19s → ~7s). Conservative: any keyword present → run preference.
#
# Curation notes (avoid Vietnamese false positives — diacritics are stripped before matching,
# and Vietnamese is monosyllabic): single words only for UNAMBIGUOUS terms (chay, cay);
# everything ambiguous uses multi-word phrases. Specifically AVOID: "đường"/"duong" (also
# "street" — ubiquitous in addresses), "nhẹ"/"nhe" (matches the particle "nhé"), "mưa"/"mua"
# (matches "mua" = buy).
_PREFERENCE_SIGNAL_KEYWORDS = (
    # dietary / health (unambiguous singles + phrases)
    "chay", "cay", "healthy", "eat clean", "kiêng", "ăn kiêng", "an kieng",
    "ít dầu", "it dau", "ít mỡ", "it mo", "giảm cân", "giam can",
    "dạ dày", "da day", "tiêu hóa", "tiep hoa", "thanh đạm", "thanh dam",
    # audience
    "người lớn tuổi", "nguoi lon tuoi", "người già", "nguoi gia",
    "trẻ em", "tre em", "cho bé", "cho be", "cho trẻ", "cho tre", "gia đình", "gia dinh",
    # weather / mood (phrases only — "trời X" avoids standalone false positives)
    "trời lạnh", "troi lanh", "trời nóng", "troi nong", "trời mưa", "troi mua",
    "trời mát", "troi mat", "trời nắng", "troi nang",
    # explicit preference ask
    "theo gu", "khẩu vị", "khau vi", "sở thích", "so thich", "hợp gu", "hop gu",
)


def _norm_vi(value: str) -> str:
    """Lowercase + strip Vietnamese diacritics (so 'cay' ≡ 'cay' ≡ 'CAY')."""
    nfd = unicodedata.normalize("NFD", value)
    no_mark = "".join(c for c in nfd if not unicodedata.combining(c))
    return no_mark.replace("đ", "d").replace("Đ", "d").lower()


def _query_has_preference_signals(query: str | None) -> bool:
    """True if the query carries taste/dietary/context signals worth running preference_task.

    Pure-discovery queries (food + location) return False → preference is skipped. The
    preference agent is only valuable with real signals (profile/weather/taste); without them
    it returns empty by its truth-first rule, so skipping is quality-neutral and ~15s faster.
    Conservative — any keyword → run preference."""
    if not query:
        return False
    q = _norm_vi(query)
    return any(_norm_vi(sig) in q for sig in _PREFERENCE_SIGNAL_KEYWORDS)


class CustomerFlow:
    """Customer discovery flow — runs the CrewAI crew and persists observability."""

    def __init__(self) -> None:
        # Discover the customer + shared tools once so the registry/adapter can bind them.
        # Guarded so constructing multiple flows never double-registers (registry is a
        # process singleton and raises on duplicate names).
        existing = set(registry.names())
        if "get_merchant_profile" not in existing:
            registry.auto_discover("tools.shared")
        if "merchant_search" not in existing:
            registry.auto_discover("tools.customer")
        install_persisting_listener()
        self._repo = AgentRunRepository()

    def search_restaurants(
        self,
        *,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        budget: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        crew: Any = None,
    ) -> CustomerChatResponse:
        """Run the Customer Discovery Crew for a discovery query (UC-04/UC-05).

        `crew` may be injected (tests pass a mock/crew with fake LLMs); otherwise the
        live NVIDIA NIM crew is built. Returns a `CustomerChatResponse`."""
        trace_id = new_id("trace")

        self._repo.create_run(
            AgentRunRecord(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                crew_name=_CREW_NAME,
                intent="restaurant_discovery",
                status="running",
                started_at=_utc_now_iso(),
            )
        )
        self._repo.add_event(
            build_event_record(
                trace_id=trace_id,
                event_type="run_started",
                agent_name="customer_flow",
                task_name="search_restaurants",
                input_payload={
                    "query": query,
                    "cuisine": cuisine,
                    "city": city,
                    "budget": budget,
                    "location": {"lat": lat, "lng": lng} if lat is not None else None,
                },
            )
        )

        # Geo: when the user supplied coords, default radius to 5km so the search_task
        # prompt has a concrete radius (and the search agent is locked to nearby_merchant_search
        # — see build_customer_crew(has_location=...)). Without this, radius_km="" leaks through
        # and the agent can return country-wide results.
        has_location = lat is not None and lng is not None
        if has_location and radius_km is None:
            radius_km = 5.0

        inputs = _build_inputs(
            query=query, cuisine=cuisine, city=city, budget=budget,
            lat=lat, lng=lng, radius_km=radius_km,
            user_id=user_id, session_id=session_id,
        )

        try:
            if crew is None:
                from agents.customer.customer_crew import build_customer_crew

                # Pure-discovery query (no taste/dietary signals) → skip preference_task
                # (it would return empty anyway). ~15s faster.
                mode = "full" if _query_has_preference_signals(query) else "search_explain"
                crew = build_customer_crew(has_location=has_location, mode=mode)

            with run_scope(trace_id, self._repo), tool_call_scope():
                crew_output = crew.kickoff(inputs=inputs)

            response = _to_chat_response(trace_id, session_id, crew_output)

            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="run_finished",
                    agent_name="customer_flow",
                    task_name="search_restaurants",
                    output_summary={"result_count": len(response.results)},
                )
            )
            self._repo.finish_run(trace_id, status="ok", finished_at=_utc_now_iso())
            return response

        except Exception as exc:  # noqa: BLE001 - persist error, never crash the process
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="error",
                    agent_name="customer_flow",
                    task_name="search_restaurants",
                    status="error",
                    error_code=type(exc).__name__,
                    output_summary={"error": str(exc)},
                )
            )
            self._repo.finish_run(
                trace_id,
                status="error",
                error_code=type(exc).__name__,
                finished_at=_utc_now_iso(),
            )
            raise

    def search_restaurants_stream(
        self,
        *,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        budget: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Run discovery in STREAMING mode, yielding SSE-ready events.

        Same run lifecycle/observability as `search_restaurants` (run_started/run_finished/
        error + agent_runs record).

        WHY NOT CrewAI crew-streaming: CrewAI 1.15.5 `Crew(stream=True)` is unreliable with
        the tool-calling search/preference agents on FPT (the streamed tool-call deltas come
        back empty/malformed → "Invalid response from LLM call"). So this path runs the
        search+preference crew NON-streaming (reliable), then streams the explanation answer
        via a SEPARATE direct DeepSeek call (plain-text streaming is proven to work on FPT).
        Net effect: the answer flows in token-by-token (TTFT ~5s) instead of dumping at end.

        Yields:
          - ``answer_delta`` {answer_delta: <text>} per DeepSeek token chunk.
          - ``run_finished`` {<CustomerChatResponse>} — terminal, full answer + results.
          - ``error`` {error_code, message} — on failure.

        Tool/task progress events flow in parallel via the StreamingListener (stream_scope).
        """
        from agents.customer.customer_crew import (
            build_customer_crew,
            explanation_prompt_pieces,
        )

        trace_id = new_id("trace")
        self._repo.create_run(
            AgentRunRecord(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                crew_name=_CREW_NAME,
                intent="restaurant_discovery",
                status="running",
                started_at=_utc_now_iso(),
            )
        )
        self._repo.add_event(
            build_event_record(
                trace_id=trace_id,
                event_type="run_started",
                agent_name="customer_flow",
                task_name="search_restaurants_stream",
                input_payload={
                    "query": query,
                    "cuisine": cuisine,
                    "city": city,
                    "budget": budget,
                    "location": {"lat": lat, "lng": lng} if lat is not None else None,
                },
            )
        )

        has_location = lat is not None and lng is not None
        if has_location and radius_km is None:
            radius_km = 5.0
        inputs = _build_inputs(
            query=query, cuisine=cuisine, city=city, budget=budget,
            lat=lat, lng=lng, radius_km=radius_km,
            user_id=user_id, session_id=session_id,
        )

        try:
            # 1) Search + preference, NON-streaming and CONCURRENT. Run them as two
            #    single-task crews in parallel threads (true parallelism — a single 2-task
            #    async crew can't satisfy CrewAI's "end with at most one async task" rule
            #    without serializing). Each worker runs in its OWN copy of this context so
            #    the PersistingListener (run_scope), tool dedupe (tool_call_scope), and the
            #    SSE progress sink (stream_scope, set by the route) all propagate. CrewAI's
            #    crew-level streaming is unreliable with these tool-calling agents on FPT, so
            #    the explanation is streamed separately below. Construction is inside the try
            #    so a ConfigError/LLM-init failure is persisted (same observability as blocking).
            # Pure-discovery query → skip preference (no signals → it would return empty
            # anyway). Only build+run the preference crew when taste/dietary signals exist.
            has_signals = _query_has_preference_signals(query)
            search_crew = build_customer_crew(has_location=has_location, mode="search")

            def _run_one(crew: Any) -> Any:
                with run_scope(trace_id, self._repo), tool_call_scope():
                    return crew.kickoff(inputs=inputs)

            pref_fut = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                # copy_context() captures stream_scope/run state from this thread; a single
                # Context can't be .run() concurrently, so each worker gets its own copy.
                search_fut = pool.submit(contextvars.copy_context().run, _run_one, search_crew)
                if has_signals:
                    pref_crew = build_customer_crew(mode="preference")
                    pref_fut = pool.submit(contextvars.copy_context().run, _run_one, pref_crew)
                search_output = search_fut.result()
                pref_output = pref_fut.result() if pref_fut is not None else None

            search = _task_pydantic(search_output, "SearchTaskOutput")
            preference = (
                _task_pydantic(pref_output, "PreferenceTaskOutput")
                if pref_output is not None
                else None
            )
            results = [c.model_dump() for c in search.candidates] if search is not None else []
            suggestions = (
                [s.model_dump() for s in preference.suggestions] if preference is not None else []
            )

            # 2) Stream the explanation answer token-by-token via a DIRECT DeepSeek call
            #    (plain-text streaming is reliable on FPT, unlike CrewAI's crew-streaming).
            messages = _build_explanation_messages(
                explanation_prompt_pieces(), inputs, results, suggestions, preference
            )
            answer_parts: list[str] = []
            for delta in _stream_explanation_tokens(messages):
                answer_parts.append(delta)
                yield {"event": "answer_delta", "data": {"answer_delta": delta}}
            if not answer_parts:
                # DeepSeek streamed nothing (rare FPT empty-response). Emit a graceful
                # fallback so the bubble is never blank; run_finished carries the same text.
                fallback = "Hmm, mình chưa nắm rõ lắm — bạn kể thêm xem thèm món gì, ở khu nào nhé?"
                answer_parts.append(fallback)
                yield {"event": "answer_delta", "data": {"answer_delta": fallback}}

            answer = _strip_answer_artifacts("".join(answer_parts))
            response = CustomerChatResponse(
                trace_id=trace_id,
                session_id=session_id,
                intent="restaurant_discovery",
                answer=answer,
                results=results,
                preference_suggestions=suggestions,
            )
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="run_finished",
                    agent_name="customer_flow",
                    task_name="search_restaurants_stream",
                    output_summary={"result_count": len(response.results)},
                )
            )
            self._repo.finish_run(trace_id, status="ok", finished_at=_utc_now_iso())
            yield {"event": "run_finished", "data": response.model_dump()}
        except Exception as exc:  # noqa: BLE001 - yield error event, keep the process alive
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="error",
                    agent_name="customer_flow",
                    task_name="search_restaurants_stream",
                    status="error",
                    error_code=type(exc).__name__,
                    output_summary={"error": str(exc)},
                )
            )
            self._repo.finish_run(
                trace_id,
                status="error",
                error_code=type(exc).__name__,
                finished_at=_utc_now_iso(),
            )
            yield {
                "event": "error",
                "data": {"error_code": type(exc).__name__, "message": str(exc)},
            }


def _build_inputs(
    *,
    query: str | None,
    cuisine: str | None,
    city: str | None,
    budget: str | None,
    lat: float | None,
    lng: float | None,
    radius_km: float | None,
    user_id: str | None,
    session_id: str | None,
) -> dict[str, Any]:
    """Fill every `{var}` referenced by the task YAML; None → "" to avoid literal braces."""
    return {
        "query": query or "",
        "cuisine": cuisine or "",
        "city": city or "",
        "budget": budget or "",
        "lat": lat if lat is not None else "",
        "lng": lng if lng is not None else "",
        "radius_km": radius_km if radius_km is not None else "",
        "user_id": user_id or "",
        "session_id": session_id or "",
    }


def _task_pydantic(crew_output: Any, model_name: str) -> Any | None:
    """Find a task output whose pydantic model matches `model_name` (defensive)."""
    for task_out in getattr(crew_output, "tasks_output", []) or []:
        pyd = getattr(task_out, "pydantic", None)
        if pyd is not None and type(pyd).__name__ == model_name:
            return pyd
    return None


def _to_chat_response(trace_id: str, session_id: str | None, crew_output: Any) -> CustomerChatResponse:
    """Map a CrewAI CrewOutput to the CustomerChatResponse contract (§11.4).

    Reads structured task outputs for search/preference (still output_pydantic). The
    explanation task is now free-text (output_pydantic dropped so its tokens stream
    readably), so its answer is read from the raw task output. Never assumes LLM
    content — only shape."""
    search = _task_pydantic(crew_output, "SearchTaskOutput")
    preference = _task_pydantic(crew_output, "PreferenceTaskOutput")

    results = (
        [c.model_dump() for c in search.candidates] if search is not None else []
    )
    suggestions = (
        [s.model_dump() for s in preference.suggestions] if preference is not None else []
    )
    answer = _explanation_raw_answer(crew_output)

    return CustomerChatResponse(
        trace_id=trace_id,
        session_id=session_id,
        intent="restaurant_discovery",
        answer=answer,
        results=results,
        preference_suggestions=suggestions,
    )


def _explanation_raw_answer(crew_output: Any) -> str:
    """Read the explanation task's free-text answer (raw output of the final task).

    With output_pydantic dropped from explanation_task, the answer is plain text — read
    from the last task's `.raw` (explanation runs last in the sequential graph). Falls
    back to crew_output.raw if task outputs are unavailable. NEVER falls through to the
    CrewOutput object repr (the old ``or crew_output`` branch) — return "" so the FE keeps
    its streamed text instead of showing garbage."""
    tasks_output = getattr(crew_output, "tasks_output", []) or []
    if tasks_output:
        raw = getattr(tasks_output[-1], "raw", None)
        if raw:
            return _strip_answer_artifacts(str(raw))
    fallback = getattr(crew_output, "raw", "")
    return _strip_answer_artifacts(str(fallback or ""))


_LABEL_PREFIXES = ("câu trả lời:", "trả lời:", "answer:", "answer =", "answer -")


def _strip_answer_artifacts(text: str) -> str:
    """Defensive cleanup of the final answer text.

    DeepSeek-V4-Flash carried a strong structural prior (the old ExplanationTaskOutput JSON
    shape), so despite the free-text prompt it may still emit a leading label
    ("Câu trả lời:", "answer:") or a JSON wrapper (``{"answer": ...}``). These would stream
    verbatim and survive run_finished reconciliation, so strip them here. Applied ONLY to
    the terminal answer (not per-token deltas) — a label can span chunks, so per-delta
    stripping would corrupt valid text."""
    import json
    import re

    s = (text or "").strip()
    if not s:
        return ""
    # Unwrap a JSON object like {"answer": "...", ...} → the answer string.
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and isinstance(obj.get("answer"), str):
                return obj["answer"].strip()
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', s, re.DOTALL)
            if m:
                return m.group(1).encode().decode("unicode_escape", "ignore").strip()
    # Strip a leading label prefix.
    low = s.lower()
    for prefix in _LABEL_PREFIXES:
        if low.startswith(prefix):
            return s[len(prefix):].lstrip(" :-").strip()
    return s


def _build_explanation_messages(
    pieces: dict[str, str],
    inputs: dict[str, Any],
    results: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    preference: Any,
) -> list[dict[str, str]]:
    """Build chat messages for the direct streaming explanation call.

    Reuses the explanation agent's persona + instruction from agents.yaml/tasks.yaml
    (single source of truth) and appends a grounded context block (candidates, preference
    signals, weather). The streamed call has NO tool access (unlike the CrewAI explanation
    agent which could call get_merchant_profile), so every fact it may reference is provided
    up front from the search/preference outputs — keeping the answer truthful."""
    instruction = _safe_format(pieces["instruction"], inputs)
    lines = ["", "NGỮ CẢNH (chỉ dùng dữ kiện THẬT dưới đây, KHÔNG bịa tên/rating/địa chỉ):"]
    if results:
        lines.append("Ứng viên quán:")
        for r in results[:5]:
            lines.append(
                f"- {r.get('name')} | cuisine={r.get('cuisine')} | addr={r.get('address')} "
                f"| dist={r.get('distance_km')}km | rating={r.get('avg_rating')} "
                f"| match={r.get('match_score')}"
            )
    else:
        lines.append("Ứng viên quán: (không có quán khớp — trả lời tự nhiên, gợi mở hướng khác)")
    sig_bits: list[str] = []
    for s in suggestions:
        if s.get("field"):
            sig_bits.append(f"{s.get('field')}={s.get('value')} ({s.get('rationale')})")
    weather = getattr(preference, "weather_summary", None) if preference is not None else None
    if weather:
        sig_bits.append(f"thời tiết: {weather}")
    lines.append(
        "Tín hiệu sở thích/bối cảnh: " + ("; ".join(sig_bits) if sig_bits else "(không có)")
    )
    return [
        {"role": "system", "content": pieces["system"]},
        {"role": "user", "content": instruction + "\n".join(lines)},
    ]


def _safe_format(template: str, inputs: dict[str, Any]) -> str:
    """Interpolate {var} placeholders from inputs; unknown placeholders become empty."""
    import re

    safe = {k: ("" if v is None else v) for k, v in inputs.items()}
    return re.sub(
        r"\{([a-zA-Z_]\w*)\}", lambda m: str(safe.get(m.group(1), "")), template
    )


def _stream_explanation_tokens(messages: list[dict[str, str]]) -> Iterator[str]:
    """Stream the explanation answer from DeepSeek via a direct OpenAI-compatible call.

    CrewAI's crew-level streaming breaks with the tool-calling search/preference agents on
    FPT, so the SSE path streams the explanation separately through a plain-text streaming
    call (proven reliable: DeepSeek-V4-Flash streams cleanly). Yields token delta strings."""
    from openai import OpenAI

    from core.settings import get_settings

    s = get_settings()
    if not s.fpt_configured:
        raise RuntimeError(
            "FPT Cloud AI chưa được cấu hình — cần FPT_API_KEY/FPT_BASE_URL để stream answer"
        )
    client = OpenAI(base_url=s.fpt_base_url, api_key=s.fpt_api_key)
    model = s.fpt_model_deepseek or "DeepSeek-V4-Flash"
    stream = client.chat.completions.create(model=model, messages=messages, stream=True)
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# Singleton instance (kept for existing import sites).
customer_flow = CustomerFlow()
