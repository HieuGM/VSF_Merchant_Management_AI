"""Preference delta reasoning (Phase 02) — PROPOSE ONLY, never persists (§7.1).

Pure, rule-based logic (KISS): given explicit conversation constraints, optional weather,
and the current profile, return a list of `ProfileDeltaSuggestion` candidates. Persisting
a confirmed change is the job of the `/preferences` route (§11.6) — NOT this service and
NOT the `propose_profile_delta` tool. This module touches no DB session.
"""
from __future__ import annotations

from typing import Any

from core.tracing import new_id
from models.preference import ProfileDeltaSuggestion, UserProfilePublic

# Vietnamese budget signal keywords → budget_level value.
_BUDGET_KEYWORDS: dict[str, str] = {
    "sinh viên": "student",
    "sinh vien": "student",
    "rẻ": "student",
    "bình dân": "student",
    "cao cấp": "premium",
    "sang": "premium",
    "premium": "premium",
}


def _suggestion(field: str, operation: str, value: Any, confidence: float, rationale: str) -> ProfileDeltaSuggestion:
    return ProfileDeltaSuggestion(
        delta_id=new_id("delta"),
        field=field,
        operation=operation,
        value=value,
        confidence=confidence,
        rationale=rationale,
    )


def propose_deltas(
    *,
    constraints: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
    profile: UserProfilePublic | None = None,
) -> list[ProfileDeltaSuggestion]:
    """Return candidate profile changes. Empty list when no strong signal.

    Rules (deliberately simple):
    - Rain (weather.is_rain) → suggest reducing `distance_preference_km` (prefer nearby).
    - Budget keyword in constraints (e.g. "sinh viên") → suggest `budget_level`.
    - Explicit cuisine constraint not already liked → suggest adding to `liked_cuisines`.
    """
    constraints = constraints or {}
    suggestions: list[ProfileDeltaSuggestion] = []

    # --- Weather signal: rain → prefer nearby ---
    if weather and weather.get("is_rain"):
        current_km = profile.distance_preference_km if profile else 5.0
        target_km = min(current_km, 3.0)
        if target_km < current_km:
            suggestions.append(
                _suggestion(
                    "distance_preference_km",
                    "set",
                    target_km,
                    0.6,
                    "Trời đang mưa — ưu tiên quán gần để giao nhanh và tránh chờ lâu.",
                )
            )

    # --- Budget signal from conversation constraints ---
    budget_value = constraints.get("budget")
    if not budget_value:
        # Scan free-text-ish constraint values for budget keywords.
        joined = " ".join(str(v).lower() for v in constraints.values())
        for kw, lvl in _BUDGET_KEYWORDS.items():
            if kw in joined:
                budget_value = lvl
                break
    if budget_value in ("student", "standard", "premium"):
        current_budget = profile.budget_level if profile else None
        if budget_value != current_budget:
            suggestions.append(
                _suggestion(
                    "budget_level",
                    "set",
                    budget_value,
                    0.7,
                    f"Tín hiệu ngân sách '{budget_value}' rút ra từ hội thoại.",
                )
            )

    # --- Cuisine signal: explicit constraint not already in liked list ---
    cuisine = constraints.get("cuisine")
    if cuisine:
        liked = [c.lower() for c in (profile.liked_cuisines if profile else [])]
        if str(cuisine).lower() not in liked:
            suggestions.append(
                _suggestion(
                    "liked_cuisines",
                    "add",
                    cuisine,
                    0.5,
                    f"Người dùng nhắc tới '{cuisine}' — cân nhắc thêm vào món yêu thích.",
                )
            )

    return suggestions
