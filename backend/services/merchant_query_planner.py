"""Rewrite-first, multi-capability planning for merchant-owner questions."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from models.merchant_orchestration import (
    Capability,
    CapabilityPlan,
    MerchantExecutionContext,
    PlannerResult,
    SearchFilters,
    TokenUsage,
)


class PlannerLLM(Protocol):
    def call(self, messages: list[dict[str, Any]]) -> Any: ...


LLMFactory = Callable[[str], PlannerLLM | None]


def _default_llm_factory(tier: str) -> PlannerLLM | None:
    # Lazy import avoids a module cycle while the existing flow owns LLM setup.
    from flows.merchant_flow import get_configured_llm

    return get_configured_llm(tier)


def _response_text(response: Any) -> str:
    return str(getattr(response, "content", response)).strip()


def _usage_snapshot(llm: PlannerLLM | None) -> TokenUsage:
    if llm is None:
        return TokenUsage()
    getter = getattr(llm, "get_token_usage_summary", None)
    if not callable(getter):
        return TokenUsage()
    usage = getter()
    return TokenUsage(
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _usage_delta(before: TokenUsage, after: TokenUsage) -> TokenUsage:
    return TokenUsage(
        total_tokens=max(0, after.total_tokens - before.total_tokens),
        prompt_tokens=max(0, after.prompt_tokens - before.prompt_tokens),
        completion_tokens=max(
            0,
            after.completion_tokens - before.completion_tokens,
        ),
    )


def _json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Planner response does not contain a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Planner response must be a JSON object")
    return value


def _extract_city(query: str) -> str | None:
    city_aliases = {
        "đà nẵng": "Đà Nẵng",
        "da nang": "Đà Nẵng",
        "hà nội": "Hà Nội",
        "ha noi": "Hà Nội",
        "huế": "Huế",
        "hue": "Huế",
        "hồ chí minh": "TP. HCM",
        "sài gòn": "TP. HCM",
        "tp hcm": "TP. HCM",
        "cần thơ": "Cần Thơ",
        "vũng tàu": "Vũng Tàu",
        "hải phòng": "Hải Phòng",
        "khánh hòa": "Khánh Hoà",
        "khánh hoà": "Khánh Hoà",
        "đồng nai": "Đồng Nai",
    }
    lowered = query.lower()
    for alias, normalized in city_aliases.items():
        if alias in lowered:
            return normalized
    return None


def _extract_cuisine(query: str) -> str | None:
    lowered = query.lower()
    candidates = (
        "sushi",
        "phở",
        "bún bò",
        "bún chả",
        "bún đậu",
        "trà sữa",
        "hải sản",
        "món nhật",
        "món hàn",
        "món việt",
        "đồ chay",
        "quán chay",
        "cơm",
        "lẩu",
        "pizza",
        "burger",
    )
    for candidate in candidates:
        if candidate in lowered:
            return "chay" if candidate in ("đồ chay", "quán chay") else candidate
    return None


def _extract_budget(query: str) -> int | None:
    match = re.search(
        r"(?:dưới|không quá|tối đa|<)\s*([0-9][0-9.,]*)\s*(k|nghìn)?",
        query.lower(),
    )
    if not match:
        return None
    return _parse_price(match.group(1), match.group(2))


def _parse_price(raw: str, suffix: str | None = None) -> int:
    compact = raw.replace(" ", "")
    if suffix in ("k", "nghìn"):
        return int(float(compact.replace(",", ".")) * 1000)
    if re.search(r"[.,]\d{3}(?:[.,]\d{3})*$", compact):
        return int(compact.replace(".", "").replace(",", ""))
    amount = float(compact.replace(",", "."))
    return int(amount * 1000 if amount < 1000 else amount)


def _extract_price_range(query: str) -> tuple[int | None, int | None]:
    match = re.search(
        r"từ\s*([0-9][0-9.,]*)\s*(k|nghìn)?\s*"
        r"(?:đến|tới|-)\s*([0-9][0-9.,]*)\s*(k|nghìn)?",
        query.lower(),
    )
    if not match:
        return None, _extract_budget(query)
    return (
        _parse_price(match.group(1), match.group(2)),
        _parse_price(match.group(3), match.group(4)),
    )


def _extract_min_rating(query: str) -> float | None:
    match = re.search(
        r"(?:rating|đánh giá|điểm)\s*(?:từ|>=|trên|ít nhất)?\s*(\d(?:[.,]\d+)?)",
        query.lower(),
    )
    return float(match.group(1).replace(",", ".")) if match else None


def _extract_district(query: str) -> str | None:
    match = re.search(
        r"\bquận\s+(.+?)(?=\s+(?:có|ở|với|giá|rating)\b|[,?.]|$)",
        query,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _extract_radius(query: str) -> float | None:
    match = re.search(r"(?:bán kính|trong)\s*(\d+(?:[.,]\d+)?)\s*km", query.lower())
    return float(match.group(1).replace(",", ".")) if match else None


def _fallback_plan(query: str) -> CapabilityPlan:
    q = query.lower()
    selected: list[Capability] = []

    search_terms = (
        "tìm quán",
        "tìm các quán",
        "tìm nhà hàng",
        "tìm đối thủ",
        "danh sách quán",
        "quán nào",
        "nhà hàng nào",
        "ở đâu",
        "đối thủ",
        "xung quanh",
        "gần quán",
        "thị trường",
        "khám phá",
        "có quán",
        "có nhà hàng",
        "ở quận",
    )
    cohort_terms = (
        "phân tích nhóm",
        "nhóm đó",
        "nhóm quán",
        "các quán đó",
        "thị trường",
        "mặt bằng chất lượng",
        "phân khúc này",
    )
    benchmark_terms = (
        "so sánh",
        "tốt hơn quán",
        "kém hơn quán",
        "vị thế",
        "đối thủ",
        "đối chiếu",
        "so với cohort",
        "so với thị trường",
        "so với quán tôi",
    )
    owner_review_terms = (
        "review",
        "đánh giá của khách",
        "khách thích",
        "khách ghét",
        "phàn nàn",
        "khiếu nại",
        "chê",
    )
    diagnosis_terms = (
        "tại sao",
        "vì sao",
        "nguyên nhân",
        "điểm yếu",
        "bị chê",
        "điểm thấp",
        "ít đơn",
        "chẩn đoán",
        "yếu",
        "chê ảnh",
        "chê hình",
    )
    recommendation_terms = (
        "gợi ý",
        "cải thiện",
        "khuyến nghị",
        "làm gì",
        "tăng doanh thu",
        "tăng đơn",
        "tối ưu",
        "nên sửa",
    )
    owner_profile_terms = (
        "chỉ số",
        "metrics",
        "vận hành",
        "menu",
        "thực đơn",
        "doanh thu",
        "số đơn",
        "thời gian chuẩn bị",
        "cancel",
        "đánh giá tổng quan",
        "chất lượng hình ảnh",
    )

    search_requested = any(term in q for term in search_terms)
    cohort_requested = any(term in q for term in cohort_terms)
    benchmark_requested = any(term in q for term in benchmark_terms)
    diagnosis_requested = any(term in q for term in diagnosis_terms)
    recommendation_requested = any(term in q for term in recommendation_terms)
    market_context = any(
        term in q
        for term in ("nhóm", "thị trường", "các quán", "đối thủ", "cohort")
    )
    owner_context = any(
        term in q
        for term in (
            "quán tôi",
            "quán của tôi",
            "quán mình",
            "cửa hàng tôi",
            "cửa hàng của tôi",
        )
    ) or ((diagnosis_requested or recommendation_requested) and not market_context)
    image_review_context = (
        ("ảnh" in q or "hình" in q)
        and ("khách" in q or "review" in q)
    )

    if search_requested:
        selected.append(Capability.RESTAURANT_SEARCH)
    if cohort_requested:
        selected.append(Capability.MARKET_COHORT_ANALYSIS)
    profile_requested = any(term in q for term in owner_profile_terms)
    if benchmark_requested and not any(
        term in q
        for term in ("profile", "metrics", "vận hành", "đánh giá tổng quan")
    ):
        profile_requested = False
    if profile_requested:
        selected.append(Capability.OWNER_PROFILE_ANALYSIS)
    if (
        any(term in q for term in owner_review_terms)
        and (owner_context or image_review_context)
    ):
        selected.append(Capability.OWNER_REVIEW_ANALYSIS)
    if diagnosis_requested:
        selected.append(Capability.OWNER_DIAGNOSIS)
    if benchmark_requested:
        selected.append(Capability.OWNER_VS_MARKET_BENCHMARK)
    if recommendation_requested:
        selected.append(Capability.RECOMMENDATION)
    if ("ảnh" in q or "hình" in q) and benchmark_requested:
        selected.append(Capability.IMAGE_COMPARISON)

    if not selected:
        selected = [Capability.GENERAL_CHAT]

    min_menu_price, max_menu_price = _extract_price_range(query)
    radius_km = _extract_radius(query)
    return CapabilityPlan(
        capabilities=selected,
        filters=SearchFilters(
            city=_extract_city(query),
            district=_extract_district(query),
            cuisine=_extract_cuisine(query),
            min_menu_price=min_menu_price,
            max_menu_price=max_menu_price,
            min_rating=_extract_min_rating(query),
            radius_km=radius_km,
            use_owner_location=any(
                term in q for term in ("gần quán", "xung quanh", "bán kính")
            ),
        ),
    )


def fallback_capability_plan(query: str) -> CapabilityPlan:
    """Public deterministic fallback used by compatibility routing and tests."""
    return _fallback_plan(query)


def _rewrite(
    message: str,
    history: list[dict[str, Any]],
    llm: PlannerLLM | None,
) -> str:
    clean = message.strip()
    if not history:
        return clean
    anaphora = (
        "nhóm đó",
        "nhóm này",
        "còn ",
        "vậy ",
        "thì sao",
        "so với quán tôi",
        "làm gì trước",
    )
    if any(term in clean.lower() for term in anaphora):
        last_user = next(
            (
                str(item.get("text", "")).strip()
                for item in reversed(history)
                if item.get("sender") in {"user", "merchant"} and item.get("text")
            ),
            "",
        )
        return f"{last_user}. {clean}" if last_user else clean
    if not llm:
        return clean
    prompt = (
        "Rewrite the latest merchant-owner message into one standalone Vietnamese "
        "query only by resolving references from history. Never add, remove, infer, "
        "or broaden an action, filter, metric, comparison, diagnosis, or "
        "recommendation. If the latest message is already standalone, reproduce it "
        "exactly. Output only the query."
    )
    response = llm.call(
        [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"Conversation history: {json.dumps(history, ensure_ascii=False)}\n"
                    f"Latest message: {clean}"
                ),
            },
        ]
    )
    rewritten = _response_text(response)
    return rewritten if rewritten and not rewritten.startswith("{") else clean


def _merge_deterministic_filters(
    plan: CapabilityPlan,
    rewritten_query: str,
) -> CapabilityPlan:
    """Keep high-confidence literal filters stable across LLM translations."""
    deterministic = _fallback_plan(rewritten_query).filters
    values = plan.filters.model_dump()
    for field in (
        "city",
        "district",
        "cuisine",
        "min_menu_price",
        "max_menu_price",
        "min_rating",
        "radius_km",
    ):
        value = getattr(deterministic, field)
        if value is not None:
            values[field] = value
    if deterministic.use_owner_location:
        values["use_owner_location"] = True
    plan.filters = SearchFilters.model_validate(values)
    return plan


def _planner_prompt(context: MerchantExecutionContext) -> str:
    capability_values = ", ".join(f'"{item.value}"' for item in Capability)
    return (
        "Extract only capabilities explicitly requested or logically required to "
        "perform an explicit request in the standalone merchant-owner query. "
        "Do not invent adjacent analysis, comparison, diagnosis, or recommendation. "
        "Compound questions may contain multiple capabilities. Do not expose "
        "competitor private operational information. "
        f"Owner merchant ID is {context.owner_merchant_id}. "
        f"Allowed capabilities: {capability_values}. "
        "Output ONLY one JSON object with keys: capabilities (array), filters "
        "(object), requested_dimensions (array). Filter keys may include query, "
        "city, district, cuisine, category, price_level, min_menu_price, "
        "max_menu_price, min_rating, radius_km, use_owner_location, limit."
    )


def rewrite_then_plan(
    message: str,
    history: list[dict[str, Any]],
    context: MerchantExecutionContext,
    llm_factory: LLMFactory | None = None,
) -> PlannerResult:
    factory = llm_factory or _default_llm_factory
    llm = factory("small")
    usage_before = _usage_snapshot(llm)

    def current_usage() -> TokenUsage:
        return _usage_delta(usage_before, _usage_snapshot(llm))

    rewritten = _rewrite(message, history, llm)

    if llm is None:
        return PlannerResult(
            rewritten_query=rewritten,
            plan=_fallback_plan(rewritten),
            token_usage=current_usage(),
            used_fallback=True,
        )

    messages = [
        {"role": "system", "content": _planner_prompt(context)},
        {"role": "user", "content": rewritten},
    ]
    for attempt in range(2):
        try:
            response = llm.call(messages)
            plan = CapabilityPlan.model_validate(_json_object(_response_text(response)))
            plan = _merge_deterministic_filters(plan, rewritten)
            return PlannerResult(
                rewritten_query=rewritten,
                plan=plan,
                token_usage=current_usage(),
            )
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            if attempt == 0:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            f"Previous output was invalid: {exc}. Return only a valid "
                            "JSON object matching the requested schema."
                        ),
                    }
                )

    return PlannerResult(
        rewritten_query=rewritten,
        plan=_fallback_plan(rewritten),
        token_usage=current_usage(),
        used_fallback=True,
    )
