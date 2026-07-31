"""Narrow deterministic handling for public merchant menu/hour follow-ups."""
from __future__ import annotations

from typing import Any

from models.merchant_agentic import normalize_text


SELECTED_PUBLIC_MERCHANT_KEY = "merchant_agentic.selected_public_merchant"
LAST_PUBLIC_SEARCH_KEY = "merchant_agentic.last_public_search"


def selected_public_merchant_update(
    answer: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist bounded candidates and select one only when the answer names one."""
    public_candidates = [
        {
            key: candidate.get(key)
            for key in ("merchant_id", "name", "cuisine", "address")
            if candidate.get(key) is not None
        }
        for candidate in candidates[:5]
        if candidate.get("merchant_id") and candidate.get("name")
    ]
    update: dict[str, Any] = {LAST_PUBLIC_SEARCH_KEY: public_candidates}
    normalized_answer = normalize_text(answer)
    mentioned = [
        candidate
        for candidate in public_candidates
        if str(candidate["merchant_id"]) in answer
        or normalize_text(str(candidate["name"])) in normalized_answer
    ]
    if len(mentioned) == 1:
        update[SELECTED_PUBLIC_MERCHANT_KEY] = mentioned[0]
    elif len(public_candidates) == 1:
        update[SELECTED_PUBLIC_MERCHANT_KEY] = public_candidates[0]
    return update


def selected_public_merchant(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    selected = snapshot.get(SELECTED_PUBLIC_MERCHANT_KEY)
    if not isinstance(selected, dict):
        return None
    if not selected.get("merchant_id"):
        return None
    return selected

