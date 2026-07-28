"""Customer flow (G-02) — CrewAI Crew orchestration + run/event persistence.

Phase 06: replaces the Phase-0b direct tool call with a real `CustomerDiscoveryCrew`
kickoff. The flow owns the run lifecycle (agent_runs + run_started/run_finished events);
the PersistingListener persists tool/task trace events emitted by CrewAI during kickoff.
Every run carries a `trace_id` (§11.4) so events and results correlate.
"""
from __future__ import annotations

import concurrent.futures
import contextvars
import re
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


# --- Out-of-domain classifier (two-tier) ---
# STRONG_OOD: unambiguous NON-food intent (code / prompt-injection / data fabrication).
# Checked FIRST so it OVERRIDES the food whitelist. Without this ordering, "viết code sắp
# xếp mảng" gets whitelisted as in-domain because the food token 'an' (ăn=eat) is a substring
# of 'mảng'/'đoạn', and "bỏ qua toàn bộ hướng dẫn" because 'an' sits in 'toàn'/'hướng'.
_STRONG_OOD_RE = re.compile(
    r"viết.{0,4}code|viet.{0,4}code|đoạn code|doan code|code python|code\s+\w+"
    r"|lập trình|lap trinh|thuật toán|thuat toan|sắp xếp|sap xep"
    r"|bỏ qua.{0,20}hướng dẫn|bo qua.{0,20}huong dan|system prompt|in lại.{0,6}prompt"
    r"|bỏ qua toàn bộ|bo qua toan bo|vô hiệu hóa|vo hieu hoa"
    # Fabrication: 'giả' (fake) AND 'giá' (price) BOTH normalize to 'gia', so a bare 'gia'
    # rule would false-positive on legit "quán ăn giá rẻ". Require a co-occurring fabrication
    # marker (tạo/demo/mock/fake/test/merchant/dữ liệu).
    r"|tao.{0,30}(gia|demo|mock|fake)"
    r"|(merchant|du lieu|du-lieu).{0,6}gia"
    r"|gia (mao|lap)"
    r"|gia.{0,20}(demo|mock|fake)"
)

# Food tokens matched as WHOLE WORDS (\b). Bare substring match is unsafe: the short token
# 'an' (ăn=eat) sits inside 'mảng'/'đoạn'/'toàn'/'hướng', 'com' inside 'combat'/'company',
# 'tra' inside 'translate'/'trade'. Word boundaries (post-_norm_vi the string is ASCII) kill
# those hits. Multi-word entries (ca phe, tra sua) work because \b anchors the token span.
_FOOD_TOKEN_RE = re.compile(
    r"\b(ăn|an|quán|quan|món|mon|nhà hàng|nha hang|phở|pho|bún|bun|cơm|com|chay|cay"
    r"|trà sữa|tra sua|trà|tra|cà phê|ca phe|cafe|đồ ăn|do an|nhậu|nhau|lẩu|lau"
    r"|nướng|nuong|xôi|xoi|mì|mi|bánh|banh|gỏi|goi|sushi|ramen|pizza|burger"
    r"|gà|ga|bò|bo|heo|hải sản|hai san|bia|kem|chè|che|nước|nuoc"
    r"|food|eat|restaurant|drink|beverage|healthy|eat clean|món ngon|mon ngon)\b"
)

# WEAK_OOD: blocks only when NO whole-word food token is present (food wins). Weather
# questions and raw SQL-injection bait. SQL bait that also carries food ("quán ăn'; DROP
# TABLE --") stays in-domain — the tool layer parameterizes queries, so it's not a threat.
_WEAK_OOD_RE = re.compile(
    r"thời tiết|thoi tiet|weather|dự báo|dubao"
    r"|drop table|select\s+\*\s+from|union select"
)

_OUT_OF_DOMAIN_ANSWER = (
    "Mình chỉ hỗ trợ tìm và gợi ý quán ăn thôi nha — câu hỏi này ngoài phạm vi của mình. "
    "Bạn muốn tìm món gì, ở khu vực nào để mình gợi ý nhé?"
)


def _is_out_of_domain(query: str | None) -> bool:
    """True for UNAMBIGUOUS out-of-domain queries.

    Two-tier: STRONG_OOD (code/injection/fabrication) overrides food — a request to "viết
    code" or "in lại system prompt" is refused even if it incidentally mentions food.
    Otherwise any whole-word food token -> in-domain. Weather/SQL-bait block only when no
    food token is present. Keeps 'trời mưa ăn gì', 'quán ăn giá rẻ' in-domain."""
    if not query:
        return False
    q = _norm_vi(query)
    if _STRONG_OOD_RE.search(q):
        return True
    if _FOOD_TOKEN_RE.search(q):
        return False
    return bool(_WEAK_OOD_RE.search(q))


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

        # Out-of-domain guard: refuse weather/code/injection/fake-data/sql-injection BEFORE
        # building crews. No coordinator exists to refuse, so everything otherwise runs
        # search+explanation and the LLM leaks general-knowledge answers.
        if _is_out_of_domain(query):
            response = CustomerChatResponse(
                trace_id=trace_id,
                session_id=session_id,
                intent="out_of_domain",
                answer=_OUT_OF_DOMAIN_ANSWER,
                results=[],
                preference_suggestions=[],
            )
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="run_finished",
                    agent_name="customer_flow",
                    task_name="search_restaurants",
                    output_summary={"out_of_domain": True},
                )
            )
            self._repo.finish_run(trace_id, status="ok", finished_at=_utc_now_iso())
            return response

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
            # Reliability fallback: the search agent non-deterministically drops candidates.
            # If it returned none but we have a location, fetch nearby directly so the user
            # still gets real results (deterministic tool output — never fabricated).
            if not response.results and has_location:
                response.results = _direct_nearby_results(inputs.get("query"), lat, lng)

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

        # Out-of-domain guard: short-circuit BEFORE building crews. Streams the canned refuse
        # answer then a terminal run_finished — the FE never waits on a crew for OOD queries.
        if _is_out_of_domain(query):
            answer = _OUT_OF_DOMAIN_ANSWER
            yield {"event": "answer_delta", "data": {"answer_delta": answer}}
            response = CustomerChatResponse(
                trace_id=trace_id,
                session_id=session_id,
                intent="out_of_domain",
                answer=answer,
                results=[],
                preference_suggestions=[],
            )
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="run_finished",
                    agent_name="customer_flow",
                    task_name="search_restaurants_stream",
                    output_summary={"out_of_domain": True},
                )
            )
            self._repo.finish_run(trace_id, status="ok", finished_at=_utc_now_iso())
            yield {"event": "run_finished", "data": response.model_dump()}
            return

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
            # Reliability fallback: agent non-deterministically drops candidates. If empty
            # and we have a location, fetch nearby directly (deterministic, truthful).
            if not results and has_location:
                results = _direct_nearby_results(inputs.get("query"), lat, lng)
            suggestions = (
                [s.model_dump() for s in preference.suggestions] if preference is not None else []
            )

            # 2) Stream the explanation answer token-by-token via a DIRECT DeepSeek call
            #    (plain-text streaming is reliable on FPT, unlike CrewAI's crew-streaming).
            messages = _build_explanation_messages(
                explanation_prompt_pieces(), inputs, results, suggestions, preference
            )
            answer_parts: list[str] = []
            stream_warnings: list[str] = []  # surfaced via CustomerChatResponse.warnings (FE renders)
            try:
                for delta in _stream_explanation_tokens(messages):
                    answer_parts.append(delta)
                    yield {"event": "answer_delta", "data": {"answer_delta": delta}}
            except Exception as stream_exc:  # noqa: BLE001 - FPT stall/timeout -> graceful fallback, not a broken stream
                # Without this the F3 symptom (stream stall -> broken connection) would be
                # invisible: mark it so monitoring/FE can see the explanation was interrupted.
                stream_warnings.append(f"explanation_stream_interrupted: {type(stream_exc).__name__}")
                fallback = (
                    "Hmm, mình đang gặp chút trục trặc khi tổng hợp câu trả lời — bạn thử lại nhé, "
                    "hoặc kể thêm món/khu vực mình gợi ý cho."
                )
                if not answer_parts:
                    answer_parts.append(fallback)
                    yield {"event": "answer_delta", "data": {"answer_delta": fallback}}
                else:
                    # partial answer already streamed -> append a short close so it reads naturally
                    tail = " (mình vừa bị ngắt kết nối nhỏ, gợi ý trên vẫn dùng được nhé)"
                    answer_parts.append(tail)
                    yield {"event": "answer_delta", "data": {"answer_delta": tail}}
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
                warnings=stream_warnings,
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


# Common Vietnamese dish/cuisine terms (diacritics-stripped). Used by the recovery fallback
# to extract a CLEAN search keyword from the raw message. Order matters: multi-word phrases
# first so 'trà sữa' wins over bare 'trà', 'bánh mì' over 'bánh'. 'an' is last (broadest).
_FOOD_TERMS = (
    "tra sua", "ca phe", "banh mi", "ga ran", "bun dau", "com tam", "do an", "hai san",
    "eat clean", "mon ngon", "pho", "bun", "com", "chay", "cay", "tra", "cafe", "lau",
    "nuong", "xoi", "mi", "banh", "goi", "oc", "sushi", "ramen", "pizza", "burger",
    "ga", "bo", "heo", "nhau", "bia", "kem", "che", "nuoc", "an",
)


def _extract_search_keyword(query: str | None) -> str | None:
    """Best-effort dish/cuisine keyword from a free-text query (diacritics-stripped).

    Returns the first matched _FOOD_TERMS entry, or None when no food term is found (vague
    query like 'ăn gì' / 'chỗ ăn ngon' — caller then falls back to pure-distance nearby)."""
    if not query:
        return None
    q = _norm_vi(query)
    for term in _FOOD_TERMS:
        if term in q:
            return term
    return None


def _direct_nearby_results(
    query: str | None, lat: float, lng: float, limit: int = 6
) -> list[dict[str, Any]]:
    """Distance-based last-resort fallback when the search agent drops its candidates.

    The gpt-oss-20b search agent non-deterministically returns candidates=[] even when the
    tool found matches. We then re-fetch nearby merchants directly — REAL tool results
    (truthful — never fabricated), same shape as SearchTaskOutput candidates.

    Extracts a CLEAN cuisine keyword (NOT the full message). This matters: the full sentence
    as a text filter yields 0 candidates (verified 'Tìm quán ăn chay ở Hà Đông' → 0), and
    query=None returns IRRELEVANT nearest shops for a specific query ('chay' → nearest phở/
    coffee). With a keyword, nearby_search returns RELEVANT same-cuisine shops (correct
    match_score tiers) — or an HONEST empty result when none exist nearby (we do NOT push
    irrelevant shops for a specific ask). Vague queries (no keyword) fall back to pure
    distance (match_score 1.0 = nearby)."""
    from database.connection import SessionLocal
    from repositories.merchant_repository import MerchantRepository
    from services.merchant_search_service import MerchantSearchService

    keyword = _extract_search_keyword(query)
    db = SessionLocal()
    try:
        svc = MerchantSearchService(MerchantRepository(db))
        # keyword -> relevant same-cuisine shops + correct match tiers, or honest empty;
        # None (vague query) -> pure-distance nearest. Never the full message (filters to 0).
        ranked = svc.nearby_search(lat, lng, radius_km=5.0, query=keyword, limit=limit)
        return [
            {
                "merchant_id": r.merchant.merchant_id,
                "name": r.merchant.name,
                "cuisine": r.merchant.cuisine,
                "address": r.merchant.address,
                "city": r.merchant.city,
                "distance_km": round(r.distance_km, 2) if r.distance_km is not None else None,
                "avg_rating": r.avg_rating,
                "match_score": round(r.match_score, 3),
            }
            for r in ranked
        ]
    finally:
        db.close()


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
    # timeout=30 is httpx read-timeout: a stalled FPT stream (no bytes for 30s) raises
    # ReadTimeout instead of hanging ~90s until the proxy closes the chunked connection.
    # Normal chunks arrive every ~10ms so this never fires on the happy path. The SSE
    # heartbeat (route layer) keeps the connection alive meanwhile; this guard aborts a
    # truly hung upstream so the streaming-loop fallback can take over.
    stream = client.chat.completions.create(
        model=model, messages=messages, stream=True, timeout=30.0
    )
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# Singleton instance (kept for existing import sites).
customer_flow = CustomerFlow()
