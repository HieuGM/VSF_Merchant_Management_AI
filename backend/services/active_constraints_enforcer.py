"""Active-constraints enforcer — the deterministic keep/drop + confirm logic.

Two enforcement depths (defense-in-depth, per the enforcement research):
  - ``hard_filter_l1`` — cuisine/name/taste_tags only. Called inside ``should_hard_filter`` at the
    DB-result loop (``merchant_search_service``), where menu items are NOT yet loaded. Drops a
    merchant whose cuisine/name IS the restriction (e.g. a sushi place for a seafood allergy).
  - ``apply_constraints`` — adds dish-level (top_dishes). Called post-search in ``customer_flow``
    on the final result dicts. Keeps a mixed merchant when ≥1 visible dish is safe (partial-overlap
    per TC-30 posture); drops only when cuisine/name is the restriction OR every dish is.

``query_requests_restriction`` is the REACTIVE→confirm gate (replaces ``_detect_dietary_conflict``):
when the user EXPLICITLY asks for a restricted food, confirm before filtering — health-safety UX.
Proactive enforcement (filter on every turn, incl. 'xin chào') comes from the always-on L1+L2 path,
NOT from this gate. Pure functions, no DB.

All term matching goes through ``constraint_catalog.scope_present`` (collision-safe: whole-token
folded + diacritic-confirm for homophones), so 'Cơm Của Mẹ', 'Nhà hàng Ngọc', 'Bún Sốt Cay' are
NOT dropped for a seafood-allergic user, and 'ăn cơm sốt' does NOT trip the confirm gate."""
from __future__ import annotations

from typing import Any

from core.constraint_catalog import (
    CATALOG, all_dish_names, merchant_cuisine_name, merchant_cuisine_raw,
    merchant_dishes, merchant_dishes_raw, scope_present,
)
from core.text_norm import fold_diacritics
from services.active_constraints_loader import ActiveConstraints, Constraint, _ALLERGY_VERB_RE


def _violates_l1(c: Constraint, raw: str, folded: str) -> bool:
    """L1 (no dishes): True if the merchant violates `c` on cuisine/name/taste_tags alone.

    `raw`/`folded` are the two forms of the SAME cuisine+name+taste_tags haystack."""
    cdef = CATALOG.get(c.scope)
    if cdef is None:
        return False
    present = scope_present(cdef, raw, folded)
    if cdef.kind == "avoid":                       # allergy → drop if allergen present
        return present
    return not present                             # want(chay) → drop if absent


def hard_filter_l1(merchant: Any, cs: ActiveConstraints) -> Constraint | None:
    """DB-result-level hard filter (ORM Merchant; no dishes loaded). Returns the violating
    constraint or None. Used by ``should_hard_filter`` via the constraints ContextVar."""
    if not cs.hard:
        return None
    bits = [getattr(merchant, "cuisine", None), getattr(merchant, "name", None)]
    bits += list(getattr(merchant, "taste_tags", None) or [])
    raw = " ".join(str(b) for b in bits if b).lower()
    folded = fold_diacritics(raw)
    for c in cs.hard:
        if _violates_l1(c, raw, folded):
            return c
    return None


def violates_hard(merchant_dict: dict, cs: ActiveConstraints) -> Constraint | None:
    """Full L1+L2 check on a result DICT (cuisine/name/taste_tags + top_dishes). Returns the
    violating constraint or None. Dish-level: an 'avoid' merchant is dropped only if cuisine/name
    carries the allergen OR every visible dish is the allergen (no safe dish)."""
    if not cs.hard:
        return None
    cn_raw = merchant_cuisine_raw(merchant_dict)
    cn_folded = merchant_cuisine_name(merchant_dict)
    dishes_folded = [d for d in all_dish_names(merchant_dict) if d]
    dishes_raw = _dish_raw_names(merchant_dict)
    for c in cs.hard:
        cdef = CATALOG.get(c.scope)
        if cdef is None:
            continue
        if cdef.kind == "avoid":
            if scope_present(cdef, cn_raw, cn_folded):            # L1: cuisine/name → drop
                return c
            # L2: every visible dish is the allergen (collision-safe per-dish check) → drop
            if dishes_folded and len(dishes_folded) == len(dishes_raw) and all(
                scope_present(cdef, dr, df) for dr, df in zip(dishes_raw, dishes_folded)
            ):
                return c
        else:  # want (chay): drop if no diet signal in cuisine/name/dishes
            full_raw = (cn_raw + " " + merchant_dishes_raw(merchant_dict))
            full_folded = cn_folded + " " + merchant_dishes(merchant_dict)
            if not scope_present(cdef, full_raw, full_folded):
                return c
    return None


def _dish_raw_names(merchant: dict) -> list[str]:
    """RAW (lowercased) individual dish names — paired by index with all_dish_names() for the
    per-dish homophone re-check in the L2 'every dish is the allergen' test."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return [
        (str(d.get("name", "")) if isinstance(d, dict) else str(d)).lower() for d in dishes
    ]


def apply_constraints(results: list[dict], cs: ActiveConstraints) -> list[dict]:
    """Post-search hard filter — drop results violating any hard constraint (L1 + dish-level L2)."""
    if not cs or not cs.hard:
        return results
    return [r for r in results if violates_hard(r, cs) is None]


def query_requests_restriction(query: str | None, cs: ActiveConstraints) -> str | None:
    """Confirm-gate: the user EXPLICITLY requests a food matching a hard AVOID restriction
    (allergy). Returns a confirm-answer, else None. (Replaces ``_detect_dietary_conflict``.)

    Suppresses when the query itself carries an allergy verb ('dị ứng'/'không ăn được'/...) — that
    is a DECLARATION of the restriction, not a request for the food, so confirming would be wrong.
    Matching is collision-safe (scope_present): 'ăn cơm sốt' does NOT fire (sốt ≠ sò as a token)."""
    if not cs.hard:
        return None
    q_raw = (query or "")
    q_folded = fold_diacritics(q_raw)
    if _ALLERGY_VERB_RE.search(q_folded):
        return None  # the query is declaring the restriction, not requesting the food
    for c in cs.hard:
        cdef = CATALOG.get(c.scope)
        if cdef is None or cdef.kind != "avoid":
            continue
        if scope_present(cdef, q_raw.lower(), q_folded):
            label = cdef.label_vi
            return (
                f"Khoan, ở lượt trước bạn có vẻ đang kiêng/dị ứng {label} — mình muốn chắc chắn trước "
                f"khi gợi ý. Bạn vẫn muốn tìm quán {label} nhé, hay mình gợi ý món khác an toàn hơn?"
            )
    return None
