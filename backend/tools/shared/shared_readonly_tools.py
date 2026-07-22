"""Shared read-only tools — FROZEN Phase 0 surface (red-team C1, design §9.2).

`get_merchant_profile` and `get_trending_dishes` are consumed by BOTH the Customer
crew (Explanation/Recommendation) and the Merchant crew. Shipping them frozen in
Phase 0 means Customer Explanation and Merchant Recommendation don't block waiting on
each other. Phase 1/2 wires real repositories; the SIGNATURE + OUTPUT SHAPE here is the
contract and must not change without the protocol.

Output rule: `overall_score` is stripped from every external surface (§6.4 [C2]).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.errors import NotFoundError
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "merchant_profiles.json"


@lru_cache
def _load_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _strip_internal(profile: dict[str, Any]) -> dict[str, Any]:
    """Remove internal-only aggregate before returning externally (§6.4 [C2])."""
    return {k: v for k, v in profile.items() if k != "overall_score"}


def get_merchant_profile(merchant_id: str) -> dict[str, Any]:
    """Return the public Merchant Profile (no overall_score). Phase 0: fixture-backed."""
    profile = _load_fixture().get(merchant_id)
    if profile is None:
        raise NotFoundError(
            f"Không tìm thấy hồ sơ merchant '{merchant_id}'.",
            details={"merchant_id": merchant_id},
        )
    return _strip_internal(profile)


def get_trending_dishes(merchant_id: str) -> dict[str, Any]:
    """Return trending dishes for a merchant. Phase 0: from profile attributes fixture."""
    profile = _load_fixture().get(merchant_id)
    if profile is None:
        raise NotFoundError(
            f"Không tìm thấy hồ sơ merchant '{merchant_id}'.",
            details={"merchant_id": merchant_id},
        )
    dishes = profile.get("attributes", {}).get("trending_dishes", [])
    return {"merchant_id": merchant_id, "trending_dishes": dishes}


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point (called by registry.auto_discover)."""
    reg.register(
        ToolSpec(
            name="get_merchant_profile",
            description="Fetch a merchant's public 8-dimension profile (no aggregate score).",
            input_schema={"merchant_id": "str"},
            output_schema={"merchant_id": "str", "dimensions": "dict", "attributes": "dict"},
            allowed_agents=agents_allowed_for("get_merchant_profile"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        get_merchant_profile,
    )
    reg.register(
        ToolSpec(
            name="get_trending_dishes",
            description="Fetch trending dishes for a merchant from profile cache/table.",
            input_schema={"merchant_id": "str"},
            output_schema={"merchant_id": "str", "trending_dishes": "list"},
            allowed_agents=agents_allowed_for("get_trending_dishes"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        get_trending_dishes,
    )
