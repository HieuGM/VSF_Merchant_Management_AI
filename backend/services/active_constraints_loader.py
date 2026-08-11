"""Active-constraints loader — derives a normalized constraint set from the 3 memory layers.

Replaces the scattered, per-restriction readers in ``customer_flow.py``:
  - ``_extract_excluded_foods`` (seafood, allergy-verb-gated)
  - ``_declared_persistent_preference`` + ``_recalled_dietary_filter`` (chay, current-query only)
  - the profile/notes/turn reads that ``_detect_dietary_conflict`` did ad-hoc.

ONE pass over (profile + context_memory notes + recent session turns) → ``ActiveConstraints``
consulted by every output step (DB hard-filter, post-search filter, explanation prompt). Adding a
restriction type = adding a row to ``constraint_catalog.CATALOG``; this loader needs no change.

Constraint provenance (origin/persistence) is preserved so the explanation can say WHY a result
was dropped ("bỏ hải sản vì bạn dị ứng"). Pure functions, no DB — uses already-loaded data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.constraint_catalog import CATALOG
from core.text_norm import fold_diacritics

# Allergy verbs (diacritics-folded). A food term counts as an AVOID restriction only when one of
# these co-occurs — so a plain "tôm hồ" / "quán hải sản" mention (no allergy verb) is NOT treated
# as an exclusion. Mirrors customer_flow._ALLERGY_VERB_RE (now consolidated here).
_ALLERGY_VERB_RE = re.compile(r"di ung|khong an duoc|ko an duoc|kien|bi dau|benh")
# Durable-declaration markers (folded). When present, a diet declaration persists cross-session;
# otherwise it is session-scoped. Mirrors _declared_persistent_preference's durable test.
_DURABLE_RE = re.compile(r"tu gio|tu nay|luon luon|trong tuong lai|truong")
# Diet-break (contradiction) markers — current query explicitly abandons the diet this turn.
_DIET_BREAK_RE = re.compile(r"\b(bo chay|khong an chay( nua)?|tro lai an (man|thit)|an thit|phap le|pha le)\b")

_SESSION_WINDOW = 8  # recent USER turns scanned (covers transient "nay ăn chay" not in notes)


@dataclass(frozen=True)
class Constraint:
    """One active user restriction."""

    type: str          # "allergy" | "diet" | "dislike"
    scope: str         # CATALOG key: "seafood", "chay", ...
    enforce: str       # "hard_filter" | "soft_penalty"
    origin: str        # "profile" | "context_memory" | "session_turn"
    persistence: str   # "durable" | "session"
    rationale: str | None = None


@dataclass(frozen=True)
class ActiveConstraints:
    """The normalized constraint set consulted by every output step."""

    hard: tuple[Constraint, ...] = ()
    soft: tuple[Constraint, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.hard or self.soft)

    def labels(self, which: str = "hard") -> list[str]:
        cs = self.hard if which == "hard" else self.soft
        return [CATALOG[c.scope].label_vi for c in cs if c.scope in CATALOG]


def _avoid_scopes(text: str) -> list[str]:
    """Catalog 'avoid' scopes present in folded `text` (only when an allergy verb co-occurs)."""
    if not text or not _ALLERGY_VERB_RE.search(text):
        return []
    return [s for s, d in CATALOG.items() if d.kind == "avoid" and any(t in text for t in d.terms)]


def _want_scopes(text: str) -> list[tuple[str, bool]]:
    """Catalog 'want' (diet) scopes in folded `text` → (scope, durable)."""
    out: list[tuple[str, bool]] = []
    if not text:
        return out
    durable = bool(_DURABLE_RE.search(text))
    for s, d in CATALOG.items():
        if d.kind == "want" and any(t in text for t in d.terms):
            out.append((s, durable))
    return out


def _from_text(text: str, origin: str, persistence: str) -> list[Constraint]:
    """Extract constraints from one folded text blob with a known origin/persistence."""
    out: list[Constraint] = []
    for scope in _avoid_scopes(text):  # allergy → hard
        out.append(Constraint("allergy", scope, "hard_filter", origin, persistence,
                              f"dị ứng/không ăn được {CATALOG[scope].label_vi}"))
    for scope, _durable in _want_scopes(text):  # diet → hard (want)
        out.append(Constraint("diet", scope, "hard_filter", origin, persistence,
                              f"ăn {CATALOG[scope].label_vi}"))
    return out


def _dedupe(cs: list[Constraint]) -> tuple[Constraint, ...]:
    """Dedup by (type, scope), keeping the most-persistent origin (durable > session)."""
    best: dict[tuple[str, str], Constraint] = {}
    for c in cs:
        key = (c.type, c.scope)
        prev = best.get(key)
        if prev is None or (c.persistence == "durable" and prev.persistence != "durable"):
            best[key] = c
    return tuple(best.values())


def build_active_constraints(
    profile: Any, prior_turns: list[Any] | None, query: str | None
) -> ActiveConstraints:
    """Load the user's active hard + soft constraints from all 3 memory layers.

    Hard: allergies (any origin) + diet declarations (durable note/profile OR recent session turn).
    Soft: structured disliked cuisines (ranking handles the penalty; included so the explanation
    prompt can mention them). Contradiction (current query breaks the diet) drops diet constraints
    for THIS turn so a changed mind isn't over-restricted."""
    q = fold_diacritics(query or "")
    broke_diet = bool(_DIET_BREAK_RE.search(q))

    hard: list[Constraint] = []
    soft: list[Constraint] = []

    # Layer 1 — structured profile.
    if profile is not None:
        dietary = getattr(profile, "dietary", None) or []
        if isinstance(dietary, (list, tuple)):
            for scope, _ in _want_scopes(fold_diacritics(" ".join(str(d) for d in dietary))):
                if not broke_diet:
                    hard.append(Constraint("diet", scope, "hard_filter", "profile", "durable",
                                           f"profile.dietary = {CATALOG[scope].label_vi}"))
        disliked = getattr(profile, "disliked_cuisines", None) or []
        if isinstance(disliked, (list, tuple)):
            for c in disliked:
                soft.append(Constraint("dislike", str(c), "soft_penalty", "profile", "durable",
                                       f"không thích {c}"))

    # Layer 2 — context_memory notes (durable free-text).
    if profile is not None:
        cm = getattr(profile, "context_memory", None)
        notes = (cm.get("notes") or []) if isinstance(cm, dict) else []
        for note in notes:
            for c in _from_text(fold_diacritics(str(note)), "context_memory", "durable"):
                if not (c.type == "diet" and broke_diet):
                    hard.append(c)

    # Layer 3 — recent session USER turns (session-scoped; covers transient 'nay ăn chay').
    for turn in (prior_turns or [])[-_SESSION_WINDOW:]:
        if not isinstance(turn, dict):
            continue
        role = (turn.get("role") or turn.get("sender") or "").lower()
        if "user" not in role:
            continue
        text = fold_diacritics(turn.get("text") or turn.get("content") or "")
        for c in _from_text(text, "session_turn", "session"):
            if not (c.type == "diet" and broke_diet):
                hard.append(c)

    # The CURRENT message is also a declaration source (session) — covers a same-turn declaration
    # like TC-48 'từ giờ nhớ tôi ăn chay trường' (not yet in prior_turns). Diet-break markers in
    # the current query already set broke_diet above, which suppresses diet constraints here.
    for c in _from_text(q, "session_turn", "session"):
        if not (c.type == "diet" and broke_diet):
            hard.append(c)

    return ActiveConstraints(hard=_dedupe(hard), soft=tuple(soft))


def active_constraints_block(cs: ActiveConstraints | None) -> str:
    """Render the 'RÀNG BUỘC NGƯỜI DÙNG' block injected into the explanation prompt (L3)."""
    if cs is None or cs.is_empty:
        return ""
    lines = ["RÀNG BUỘC NGƯỜI DÙNG (TUÂN THỦ NGHIÊM NGẶT — không gợi ý quán vi phạm):"]
    for c in cs.hard:
        label = CATALOG[c.scope].label_vi if c.scope in CATALOG else c.scope
        lines.append(f"- LOẠI TRỪ {label} ({c.rationale or c.type})")
    return "\n".join(lines)
