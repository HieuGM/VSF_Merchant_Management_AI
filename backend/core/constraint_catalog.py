"""Constraint catalog — the single source of truth for user dietary/allergen restrictions.

Replaces the scattered lexicons that drove per-case filters:
  - ``customer_flow._EXCLUDED_FOODS`` (seafood-only)
  - ``customer_flow._ALLERGY_VERB_RE`` (allergy-verb detection)
  - the chay-only logic in ``_declared_persistent_preference`` / ``_recalled_dietary_filter``

A restriction SCOPE (e.g. "seafood", "chay") is defined ONCE here with its folded synonyms +
enforcement kind. Adding a new restriction type = adding one ``ConstraintDef`` row, NOT a new
regex/filter. The loader derives ``Constraint``s from this catalog; the enforcer consults the
catalog's ``terms`` + ``kind`` to decide keep/drop.

Kinds:
  - ``avoid`` (allergy): drop a merchant if the allergen APPEARS (cuisine/name → always; dishes →
    only if EVERY visible dish is the allergen, so a mixed restaurant with ≥1 safe dish survives).
  - ``want``  (diet, e.g. chay): drop a merchant if the diet signal is ABSENT everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.text_norm import fold_diacritics


@dataclass(frozen=True)
class ConstraintDef:
    """Static definition of one restriction scope."""

    scope: str                   # canonical id, e.g. "seafood", "chay"
    label_vi: str                # Vietnamese label for the explanation prompt
    terms: tuple[str, ...]       # folded synonyms matched against a merchant haystack
    kind: str                    # "avoid" (allergy) | "want" (diet)


# Seafood-allergen terms (shellfish + sushi-grade fish carriers). Bare "ca" (fish) is intentionally
# excluded — too broad (would drop every restaurant with a fish dish); shellfish/sushi are the
# medically high-risk carriers a seafood-allergic user must avoid.
_SEAFOOD_TERMS: tuple[str, ...] = (
    "hai san", "tom", "cua", "ghe", "muc", "ngao", "ngheu", "oc", "so",  # shellfish (from _EXCLUDED_FOODS)
    "tom hum", "ghẹ",                                                    # lobster
    "sushi", "sashimi",                                                  # sushi-grade (high seafood cross-risk)
)
_CHAY_TERMS: tuple[str, ...] = ("chay", "vegetarian")

# The catalog. Extensible — new restriction = new row.
CATALOG: dict[str, ConstraintDef] = {
    "seafood": ConstraintDef("seafood", "hải sản", tuple(fold_diacritics(t) for t in _SEAFOOD_TERMS), "avoid"),
    "chay": ConstraintDef("chay", "đồ chay", tuple(fold_diacritics(t) for t in _CHAY_TERMS), "want"),
}


def merchant_cuisine_name(merchant: dict) -> str:
    """Folded L1 haystack: cuisine + name + taste_tags (no dishes). Used by the DB-result filter
    (should_hard_filter), where menu items are not yet loaded."""
    bits = [merchant.get("cuisine"), merchant.get("name")]
    bits += list(merchant.get("taste_tags") or [])
    return fold_diacritics(" ".join(str(b) for b in bits if b))


def merchant_dishes(merchant: dict) -> str:
    """Folded dish-name haystack (top_dishes / top_menu_items). Empty when not loaded."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return fold_diacritics(" ".join(str(d.get("name", "")) if isinstance(d, dict) else str(d) for d in dishes))


def all_dish_names(merchant: dict) -> list[str]:
    """Folded individual dish names (for the 'every dish is the allergen' partial-overlap test)."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return [fold_diacritics(str(d.get("name", "")) if isinstance(d, dict) else str(d)) for d in dishes]
