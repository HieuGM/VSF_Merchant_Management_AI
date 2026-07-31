from __future__ import annotations

import json
from unittest.mock import MagicMock

from providers.cache.memory_adapter import InMemoryCache
from services.merchant_trace_collector import TraceCollector


def test_city_aliases_canonicalize_to_single_slug():
    from models.merchant_agentic import normalize_city_slugs

    assert normalize_city_slugs("Đà Nẵng") == "da_nang"
    assert normalize_city_slugs("Da Nang") == "da_nang"
    assert normalize_city_slugs("da-nang") == "da_nang"
    assert normalize_city_slugs("da_nang") == "da_nang"


def test_market_search_tool_emits_canonical_city_and_cache_events(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway

    events: list[dict] = []
    semantic_events: list[dict] = []
    context = AgenticRunContext(
        trace_id="tr-gateway",
        session_id="sess-gateway",
        owner_merchant_id="94",
    )
    gateway = RunScopedMerchantToolGateway(
        context=context,
        db=MagicMock(),
        cache=InMemoryCache(),
        emit=events.append,
        trace_collector=TraceCollector("tr-gateway", semantic_events.append),
    )

    import tools.merchant.gateway as gateway_module

    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda **kwargs: {
            "status": "ok",
            "count": 1,
            "merchants": [
                {
                    "merchant_id": "external-1",
                    "name": "Quán công khai",
                    "city_slug": "da_nang",
                    "overall_score": 0.99,
                }
            ],
        },
    )
    tool = next(
        item
        for item in gateway.tools_for("market_search")
        if item.name == "search_merchants"
    )

    collector = gateway._trace_collector
    assert collector is not None
    sdk_args = {"query": "tôm", "city": "Đà Nẵng"}
    resolution = gateway.tool_correlation_bridge.observe_sdk_event(
        "Public Market Search Specialist",
        "search_merchants",
        sdk_args,
        "sdk-market-search",
        is_start=True,
    )
    assert resolution.state == "pending"
    sdk_span = collector.observe_crewai_tool_started(
        "Public Market Search Specialist",
        "search_merchants",
        sdk_args,
        correlation_id="sdk-market-search",
    )

    result = json.loads(tool._run(query="tôm", city="Đà Nẵng"))

    assert result["status"] == "ok"
    assert "overall_score" not in result["merchants"][0]
    started = next(event for event in events if event["event"] == "tool_started")
    finished = next(event for event in events if event["event"] == "tool_finished")
    assert started["args"]["city"] == "da_nang"
    assert started["tool_name"] == "search_merchants"
    assert finished["correlation_id"] == "sdk-market-search"
    assert [event["kind"] for event in semantic_events] == ["started", "finished"]
    assert {event["span_id"] for event in semantic_events} == {sdk_span}
    assert semantic_events[-1]["debug"]["args"]["city"] == "da_nang"
    assert semantic_events[-1]["debug"]["result"]["status"] == "ok"


def test_owner_profile_tool_ignores_model_supplied_merchant_id(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway

    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-owner",
            session_id="sess-owner",
            owner_merchant_id="94",
        ),
        db=MagicMock(),
        cache=InMemoryCache(),
        emit=lambda _event: None,
    )

    import tools.merchant.gateway as gateway_module

    monkeypatch.setattr(
        gateway_module,
        "get_merchant_profile_summary",
        lambda merchant_id, **_kwargs: {"status": "ok", "merchant_id": merchant_id},
    )
    tool = next(
        item
        for item in gateway.tools_for("self_analysis")
        if item.name == "get_owner_profile_summary"
    )

    result = json.loads(tool._run(merchant_id="585"))

    assert result["merchant_id"] == "94"


def test_owner_gateway_tools_hide_and_bind_merchant_id(monkeypatch):
    """The coordinator must not supply identity for an owner-bound operation."""
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    observed: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "get_merchant_operational_metrics",
        lambda merchant_id, **_kwargs: observed.update(merchant_id=merchant_id)
        or {"status": "ok", "merchant_id": merchant_id, "metrics": {}},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-owner-contract",
            session_id="sess-owner-contract",
            owner_merchant_id="94",
        ),
        db=MagicMock(),
        cache=None,
        emit=lambda _event: None,
    )
    tool = next(
        item
        for item in gateway.tools_for("self_analysis")
        if item.name == "get_owner_operational_metrics"
    )

    assert "merchant_id" not in tool.args_schema.model_json_schema().get("properties", {})
    result = json.loads(tool._run())

    assert result["merchant_id"] == "94"
    assert observed["merchant_id"] == "94"


def test_image_comparison_tool_is_owner_bound_and_accepts_search_reference(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    captured: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "compare_merchant_images",
        lambda *, owner_merchant_id, competitor_merchant_ids, limit_per_side, db: captured.update(
            owner_merchant_id=owner_merchant_id,
            competitor_merchant_ids=competitor_merchant_ids,
            limit_per_side=limit_per_side,
            db=db,
        )
        or {"status": "ok", "differences": []},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-image-ref",
            session_id="sess-image-ref",
            owner_merchant_id="94",
        ),
        db=MagicMock(),
        cache=None,
        emit=lambda _event: None,
    )
    gateway._cohort_refs["search_1"] = ["110450", "110451"]
    tool = next(
        item
        for item in gateway.tools_for("self_analysis")
        if item.name == "compare_merchant_images"
    )

    result = json.loads(tool._run(search_ref="search_1", limit_per_side=2))

    assert result["status"] == "ok"
    assert captured["owner_merchant_id"] == "94"
    assert captured["competitor_merchant_ids"] == ["110450", "110451"]
    assert captured["limit_per_side"] == 2


def test_gateway_uses_and_closes_an_isolated_session_for_each_tool(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    tool_session = MagicMock()
    db_factory = MagicMock(return_value=tool_session)
    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda *, db, **kwargs: (
            {"status": "ok", "count": 0, "merchants": []}
            if db is tool_session
            else (_ for _ in ()).throw(AssertionError("shared DB session used"))
        ),
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-isolated-db",
            session_id="sess-isolated-db",
            owner_merchant_id="94",
        ),
        db=MagicMock(),
        db_factory=db_factory,
        cache=None,
        emit=lambda event: None,
    )

    gateway.run_market_search(query="sushi", city="da_nang")

    db_factory.assert_called_once_with()
    tool_session.close.assert_called_once_with()


def test_cohort_aggregation_resolves_search_reference_to_exact_observed_ids(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    captured: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda **_kwargs: {
            "status": "ok",
            "count": 2,
            "merchants": [
                {"merchant_id": "110450", "name": "Quán A"},
                {"merchant_id": "110451", "name": "Quán B"},
            ],
        },
    )
    monkeypatch.setattr(
        gateway_module,
        "aggregate_public_merchant_cohort",
        lambda *, merchant_ids, step_id, db: captured.update(
            merchant_ids=merchant_ids, step_id=step_id, db=db
        )
        or {"status": "ok", "cohort_count": len(merchant_ids)},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-cohort-ref",
            session_id="sess-cohort-ref",
            owner_merchant_id="94",
        ),
        db=MagicMock(),
        cache=None,
        emit=lambda _event: None,
    )

    search_result = json.loads(gateway.run_market_search(query="chay"))
    aggregate_result = json.loads(
        gateway.run_public_cohort_operation(
            "aggregate",
            search_ref=search_result["cohort_ref"],
            step_id="cohort-analysis",
        )
    )

    assert aggregate_result["cohort_count"] == 2
    assert captured["merchant_ids"] == ["110450", "110451"]
    assert captured["step_id"] == "cohort-analysis"
    assert aggregate_result["cohort_members"] == [
        {"merchant_id": "110450", "name": "Quán A"},
        {"merchant_id": "110451", "name": "Quán B"},
    ]


def test_search_gateway_drops_filters_not_grounded_in_owner_request(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    observed: dict = {}
    events: list[dict] = []
    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda **kwargs: observed.update(kwargs)
        or {"status": "ok", "count": 0, "merchants": []},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-grounded-search",
            session_id="sess-grounded-search",
            owner_merchant_id="94",
            user_query="Tìm các quán sushi ở Đà Nẵng.",
        ),
        db=MagicMock(),
        cache=None,
        emit=events.append,
    )

    gateway.run_market_search(
        query="sushi",
        city="Đà Nẵng",
        cuisine="Món Nhật",
        district="Hải Châu",
        diet="chay",
        min_rating=4.0,
        max_menu_price=1_000_000,
        anchor_merchant_id="94",
        radius_km=5.0,
        sort_by="rating",
    )

    assert observed["query"] == "sushi"
    assert observed["city"] == "da_nang"
    assert observed["cuisine"] is None
    assert observed["district"] is None
    assert observed["diet"] is None
    assert observed["min_rating"] is None
    assert observed["max_menu_price"] is None
    assert observed["anchor_merchant_id"] is None
    assert observed["radius_km"] is None
    assert observed["sort_by"] == "relevance"
    normalized = next(event for event in events if event["event"] == "tool_args_normalized")
    assert set(normalized["removed_fields"]) >= {"district", "diet", "radius_km"}


def test_search_gateway_keeps_approved_default_radius_for_nearby_request(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    observed: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda **kwargs: observed.update(kwargs)
        or {"status": "ok", "count": 0, "merchants": []},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-nearby-default",
            session_id="sess-nearby-default",
            owner_merchant_id="94",
            user_query="Tôi cần khảo sát các quán bún cá gần đây",
        ),
        db=MagicMock(),
        cache=None,
        emit=lambda _event: None,
    )

    gateway.run_market_search(
        query="bún cá",
        ingredient="cá",
        anchor_merchant_id="94",
        radius_km=5.0,
        sort_by="distance",
    )

    assert observed["anchor_merchant_id"] == "94"
    assert observed["radius_km"] == 5.0
    assert observed["sort_by"] == "distance"


def test_search_gateway_rejects_negation_as_invented_diet_filter(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    observed: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "search_merchants",
        lambda **kwargs: observed.update(kwargs)
        or {"status": "ok", "count": 0, "merchants": []},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-hours-negation",
            session_id="sess-hours-negation",
            owner_merchant_id="94",
            user_query="Tôi có thể ăn đêm ở đây không từ 2-4h đêm?",
        ),
        db=MagicMock(),
        cache=None,
        emit=lambda _event: None,
    )

    gateway.run_market_search(query="quán đã chọn", diet="không")

    assert observed["diet"] is None


def test_market_search_agent_can_fetch_public_merchant_detail(monkeypatch):
    from models.merchant_agentic import AgenticRunContext
    from tools.merchant.gateway import RunScopedMerchantToolGateway
    import tools.merchant.gateway as gateway_module

    observed: dict = {}
    monkeypatch.setattr(
        gateway_module,
        "get_public_merchant_detail",
        lambda merchant_id, **kwargs: observed.update(
            merchant_id=merchant_id,
            **kwargs,
        )
        or {"status": "ok", "merchant_id": merchant_id, "menu_items": []},
    )
    gateway = RunScopedMerchantToolGateway(
        context=AgenticRunContext(
            trace_id="tr-public-detail",
            session_id="sess-public-detail",
            owner_merchant_id="94",
            user_query="Quán 78532 có menu gì?",
        ),
        db=MagicMock(),
        cache=InMemoryCache(),
        emit=lambda _event: None,
    )

    tool = next(
        item
        for item in gateway.tools_for("market_search")
        if item.name == "get_public_merchant_detail"
    )
    result = json.loads(tool._run(merchant_id="78532"))

    assert result["merchant_id"] == "78532"
    assert observed["merchant_id"] == "78532"
