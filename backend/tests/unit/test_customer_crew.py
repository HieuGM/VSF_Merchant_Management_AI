"""Customer crew assembly with fake LLM — no network/key (Phase 07 tests 8, 8b).

Sequential process: 3 specialists, no coordinator/manager. Hybrid LLM: gpt-oss-20b
(fast) for search+preference, DeepSeek-V4-Flash (strong) for explanation.
"""
from __future__ import annotations

from crewai import Process

from agents.customer.customer_crew import build_customer_crew
from tools.registry import registry


def _ensure_tools():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def test_crew_builds_without_network(fake_llm_fast, fake_llm_strong):
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    # Sequential process — no manager agent.
    assert crew.process == Process.sequential
    assert crew.manager_agent is None
    assert len(crew.agents) == 3  # 3 specialists, no coordinator
    assert len(crew.tasks) == 3


def test_per_agent_llm_tiers(fake_llm_fast, fake_llm_strong):
    """search + preference use the fast model; explanation uses the strong model."""
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    search = next(a for a in crew.agents if "Tìm kiếm" in a.role)
    preference = next(a for a in crew.agents if "Suy luận" in a.role)
    explanation = next(a for a in crew.agents if "thân thiện" in a.role)
    assert search.llm.model == "openai/gpt-oss-20b"
    assert preference.llm.model == "openai/gpt-oss-20b"
    assert explanation.llm.model == "openai/DeepSeek-V4-Flash"


def test_specialists_do_not_delegate(fake_llm_fast, fake_llm_strong):
    """Sequential specialists never delegate (no coordinator to hand off to)."""
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    assert all(a.allow_delegation is False for a in crew.agents)


def test_agents_only_have_allowlisted_tools(fake_llm_fast, fake_llm_strong):
    _ensure_tools()
    crew = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    reasoning = next(a for a in crew.agents if "Suy luận" in a.role)
    names = {t.name for t in reasoning.tools}
    assert "merchant_search" not in names  # not allow-listed for this agent


def test_search_agent_tools_lock_by_location(fake_llm_fast, fake_llm_strong):
    """Location locks the search agent's tool: nearby-only with coords (geo hard-filter →
    correct city), merchant_search-only without. Prevents the HCM-instead-of-HN leak."""
    _ensure_tools()
    with_loc = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong, has_location=True)
    search_with = next(a for a in with_loc.agents if "Tìm kiếm" in a.role)
    assert {t.name for t in search_with.tools} == {"nearby_merchant_search"}

    no_loc = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong, has_location=False)
    search_without = next(a for a in no_loc.agents if "Tìm kiếm" in a.role)
    assert {t.name for t in search_without.tools} == {"merchant_search"}


def test_mode_controls_crew_shape(fake_llm_fast, fake_llm_strong):
    """mode='full' → 3-task crew (blocking /chat path, search+preference async + explanation
    sync); 'search'/'preference' → 1-task crews the SSE path runs concurrently. Explanation
    is always free-text (output_pydantic dropped) so its tokens can stream readably."""
    _ensure_tools()
    full = build_customer_crew(llm_fast=fake_llm_fast, llm_strong=fake_llm_strong)
    assert len(full.tasks) == 3
    assert full.tasks[-1].output_pydantic is None  # explanation free-text
    assert full.tasks[0].output_pydantic is not None  # search structured
    assert full.tasks[1].output_pydantic is not None  # preference structured

    search_crew = build_customer_crew(
        llm_fast=fake_llm_fast, llm_strong=fake_llm_strong, mode="search"
    )
    assert len(search_crew.tasks) == 1
    assert search_crew.tasks[0].output_pydantic is not None

    pref_crew = build_customer_crew(
        llm_fast=fake_llm_fast, llm_strong=fake_llm_strong, mode="preference"
    )
    assert len(pref_crew.tasks) == 1
    assert pref_crew.tasks[0].output_pydantic is not None


def test_build_explanation_messages_grounds_answer():
    """The streamed explanation has no tool access (unlike the CrewAI explanation agent),
    so its messages must carry the candidate + preference facts to stay truthful."""
    from agents.customer.customer_crew import explanation_prompt_pieces
    from flows.customer_flow import _build_explanation_messages

    pieces = explanation_prompt_pieces()
    inputs = {
        "query": "phở gần đây", "cuisine": "", "city": "", "budget": "",
        "lat": "", "lng": "", "radius_km": "", "user_id": "u1", "session_id": "s1",
    }
    results = [
        {
            "name": "Phở Lệ", "cuisine": "Việt", "address": "Cầu Giấy",
            "distance_km": 1.2, "avg_rating": 4.5, "match_score": 0.9,
        }
    ]
    suggestions = [{"field": "liked_cuisines", "value": "Việt", "rationale": "hỏi lại"}]

    msgs = _build_explanation_messages(pieces, inputs, results, suggestions, preference=None)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    user = msgs[1]["content"]
    assert "phở gần đây" in user  # query interpolated into the instruction
    assert "Phở Lệ" in user  # candidate grounded
    assert "Việt" in user  # preference signal grounded


def test_safe_format_handles_missing_placeholders():
    """Unknown {var}s become empty; known ones interpolate (the explanation instruction
    only references {query}, but _build_inputs passes the full dict)."""
    from flows.customer_flow import _safe_format

    assert _safe_format("Q: {query}", {"query": "phở"}) == "Q: phở"
    # Missing placeholder → format would raise KeyError; _safe_format falls back to replace
    assert _safe_format("Q: {query} / {missing}", {"query": "phở"}) == "Q: phở / "
    assert _safe_format("no vars", {"query": "x"}) == "no vars"


def test_query_has_preference_signals_detects_taste():
    """Pure-discovery queries skip preference; taste/dietary/weather signals trigger it.
    Diacritics-insensitive ('chay' ≡ 'chay')."""
    from flows.customer_flow import _query_has_preference_signals

    # Pure discovery → False (skip preference)
    assert _query_has_preference_signals("phở gần Cầu Giấy") is False
    assert _query_has_preference_signals("quán Nhật ở Hà Nội") is False
    assert _query_has_preference_signals("gợi ý quán ăn trưa") is False
    assert _query_has_preference_signals(None) is False
    assert _query_has_preference_signals("") is False
    # Signals present → True (run preference)
    assert _query_has_preference_signals("quán chay gần đây") is True
    assert _query_has_preference_signals("món ít cay cho người lớn tuổi") is True
    assert _query_has_preference_signals("trời nóng, muốn ăn nhẹ") is True
    # Diacritics-insensitive
    assert _query_has_preference_signals("quan chay gan day") is True


def test_explanation_raw_answer_reads_last_task():
    """With output_pydantic gone, the answer is the final task's raw text; never the
    CrewOutput object repr, and structural artifacts (label/JSON) are stripped."""
    from types import SimpleNamespace

    from flows.customer_flow import _explanation_raw_answer

    crew_output = SimpleNamespace(
        tasks_output=[
            SimpleNamespace(raw="search output"),
            SimpleNamespace(raw="preference output"),
            SimpleNamespace(raw="Hôm nay ăn phở nhé!"),
        ],
        raw="fallback",
    )
    assert _explanation_raw_answer(crew_output) == "Hôm nay ăn phở nhé!"
    # No task outputs → fall back to crew_output.raw
    assert _explanation_raw_answer(SimpleNamespace(tasks_output=[], raw="only raw")) == "only raw"
    # Both empty → "" (never the object repr)
    assert _explanation_raw_answer(SimpleNamespace(tasks_output=[], raw="")) == ""
    assert _explanation_raw_answer(SimpleNamespace(tasks_output=[], raw=None)) == ""
    # Structural artifacts stripped (DeepSeek may emit a label/JSON despite free-text prompt)
    assert (
        _explanation_raw_answer(
            SimpleNamespace(
                tasks_output=[SimpleNamespace(raw="Câu trả lời: Hmm, hôm nay lạnh.")], raw="ok"
            )
        )
        == "Hmm, hôm nay lạnh."
    )
    assert (
        _explanation_raw_answer(
            SimpleNamespace(
                tasks_output=[SimpleNamespace(raw='{"answer": "Chào bạn!", "reasons": []}')],
                raw="ok",
            )
        )
        == "Chào bạn!"
    )
