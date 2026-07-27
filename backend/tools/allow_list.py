"""Agent→tool allow-list — FROZEN DATA ARTIFACT (red-team C1, design §5.4).

This is DATA, not logic: a single frozen table both verticals read but neither edits
freely. The registry enforces it at runtime — a prompt cannot grant a tool absent from
an agent's assignment here. Changes go through the contract-change protocol (plan §[C2]).
"""
from __future__ import annotations

# Agent (role key) -> tools it may call directly (§5.4).
AGENT_TOOL_ALLOW_LIST: dict[str, tuple[str, ...]] = {
    # --- Customer Discovery Crew (Dev A) ---
    "customer_coordinator": ("get_user_profile", "get_session_candidates"),
    "restaurant_search": ("merchant_search", "nearby_merchant_search"),
    "preference_reasoning": (
        "get_user_profile",
        "get_session_candidates",
        "get_weather_context",
        "propose_profile_delta",
    ),
    "customer_explanation": ("get_merchant_profile",),
    # --- Merchant Advisor Crew (Dev B) ---
    "merchant_coordinator": (
        "get_merchant_profile_summary",
        "get_merchant_metadata_catalog",
    ),
    "merchant_profile_analyst": (
        "get_merchant_profile_summary",
        "get_merchant_operational_metrics",
        "get_merchant_complaints",
        "get_menu_and_food_images",
    ),
    "diagnosis": (
        "get_merchant_profile_summary",
        "get_merchant_operational_metrics",
        "get_merchant_complaints",
        "diagnose_merchant",
    ),
    "recommendation": (
        "get_merchant_profile_summary",
        "get_merchant_operational_metrics",
        "search_trending_dishes",
        "recommend_improvements",
    ),
    "competitor": (
        "search_merchants",
        "search_trending_dishes",
        "compare_merchant_benchmark",
    ),
    "evidence_verifier": (
        "get_merchant_profile_summary",
        "get_merchant_complaints",
    ),
    "synthesis_advisor": (),
}

# Tools consumed by BOTH domains — shipped frozen in Phase 0 (C1) so neither vertical
# blocks the other. Registered by tools/shared_readonly_tools.py.
SHARED_READONLY_TOOLS: tuple[str, ...] = ("get_merchant_profile", "get_trending_dishes")


def agents_allowed_for(tool_name: str) -> tuple[str, ...]:
    """Reverse lookup: which agents may call a given tool."""
    return tuple(
        agent for agent, tools in AGENT_TOOL_ALLOW_LIST.items() if tool_name in tools
    )
