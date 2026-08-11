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
NOT from this gate. Pure functions, no DB."""
from __future__ import annotations

from typing import Any

from core.constraint_catalog import CATALOG, all_dish_names, merchant_cuisine_name, merchant_dishes
from core.text_norm import fold_diacritics
from services.active_constraints_loader import ActiveConstraints, Constraint, _ALLERGY_VERB_RE


def _violates_l1(cuisine_name_folded: str, c: Constraint) -> bool:
    """L1 (no dishes): True if the merchant violates `c` on cuisine/name/taste_tags alone."""
    cdef = CATALOG.get(c.scope)
    if cdef is None:
        return False
    if cdef.kind == "avoid":                       # allergy → drop if allergen present
        return any(t in cuisine_name_folded for t in cdef.terms)
    return not any(t in cuisine_name_folded for t in cdef.terms)   # want(chay) → drop if absent


def hard_filter_l1(merchant: Any, cs: ActiveConstraints) -> Constraint | None:
    """DB-result-level hard filter (ORM Merchant; no dishes loaded). Returns the violating
    constraint or None. Used by ``should_hard_filter`` via the constraints ContextVar."""
    if not cs.hard:
        return None
    bits = [getattr(merchant, "cuisine", None), getattr(merchant, "name", None)]
    bits += list(getattr(merchant, "taste_tags", None) or [])
    cn = fold_diacritics(" ".join(str(b) for b in bits if b))
    for c in cs.hard:
        if _violates_l1(cn, c):
            return c
    return None


def violates_hard(merchant_dict: dict, cs: ActiveConstraints) -> Constraint | None:
    """Full L1+L2 check on a result DICT (cuisine/name/taste_tags + top_dishes). Returns the
    violating constraint or None. Dish-level: an 'avoid' merchant is dropped only if cuisine/name
    carries the allergen OR every visible dish is the allergen (no safe dish)."""
    if not cs.hard:
        return None
    cn = merchant_cuisine_name(merchant_dict)
    dishes = all_dish_names(merchant_dict)
    for c in cs.hard:
        cdef = CATALOG.get(c.scope)
        if cdef is None:
            continue
        if cdef.kind == "avoid":
            if any(t in cn for t in cdef.terms):          # L1: cuisine/name → drop
                return c
            if dishes and all(any(t in dn for t in cdef.terms) for dn in dishes):
                return c                                  # L2: every dish is the allergen → drop
        else:  # want (chay): drop if no diet signal in cuisine/name/dishes
            full = cn + " " + merchant_dishes(merchant_dict)
            if not any(t in full for t in cdef.terms):
                return c
    return None


def apply_constraints(results: list[dict], cs: ActiveConstraints) -> list[dict]:
    """Post-search hard filter — drop results violating any hard constraint (L1 + dish-level L2)."""
    if not cs or not cs.hard:
        return results
    return [r for r in results if violates_hard(r, cs) is None]


def query_requests_restriction(query: str | None, cs: ActiveConstraints) -> str | None:
    """Confirm-gate: the user EXPLICITLY requests a food matching a hard AVOID restriction
    (allergy). Returns a confirm-answer, else None. (Replaces ``_detect_dietary_conflict``.)

    Suppresses when the query itself carries an allergy verb ('dị ứng'/'không ăn được'/...) — that
    is a DECLARATION of the restriction, not a request for the food, so confirming would be wrong
    (the user is telling us the allergy, not asking for the allergen)."""
    if not cs.hard:
        return None
    q = fold_diacritics(query or "")
    if _ALLERGY_VERB_RE.search(q):
        return None  # the query is declaring the restriction, not requesting the food
    for c in cs.hard:
        cdef = CATALOG.get(c.scope)
        if cdef is None or cdef.kind != "avoid":
            continue
        if any(t in q for t in cdef.terms):
            label = cdef.label_vi
            return (
                f"Khoan, ở lượt trước bạn có vẻ đang kiêng/dị ứng {label} — mình muốn chắc chắn trước "
                f"khi gợi ý. Bạn vẫn muốn tìm quán {label} nhé, hay mình gợi ý món khác an toàn hơn?"
            )
    return None
