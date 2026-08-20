"""Active-constraints loader — derives a normalized constraint set from the 3 memory layers.

ONE pass over (profile + context_memory notes + recent session turns + current message) →
``ActiveConstraints`` consulted by every output step (DB hard-filter, post-search filter,
explanation prompt). Adding a restriction type = adding a row to ``constraint_catalog.CATALOG``;
this loader needs no change.

Constraint provenance (origin/persistence) is preserved so the explanation can say WHY a result
was dropped ("bỏ hải sản vì bạn dị ứng"). Pure functions, no DB — uses already-loaded data.

Correctness guards (each closes a real recall failure found by audit):
  - ASK vs DECLARE: a question ('quán này có món chay không?') is NOT a vegetarian declaration →
    ``_QUESTION_RE`` suppresses diet scopes on interrogations.
  - NEGATION/RECOVERY: 'không ăn chay' / 'không còn dị ứng hải sản nữa' must NOT (re)impose the
    restriction → ``_WANT_NEGATION_RE`` + ``_RECOVERY_RE`` suppress.
  - DIET-BREAK scope: 'tôi bỏ chay rồi' in a PRIOR user turn retires the diet for this turn too,
    not only when the break is in the current query.
  - SESSION WINDOW: the 8-turn window counts USER turns (agent turns no longer halve it).
  - DURABLE marker: 'từ giờ ...' in a session/current turn now actually marks the constraint
    durable (the flag was previously discarded)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.constraint_catalog import CATALOG, expand_child_scopes, normalize_abbreviations, scope_present
from core.text_norm import fold_diacritics

# Allergy verbs (diacritics-folded). A food term counts as an AVOID restriction only when one of
# these co-occurs — so a plain "tôm hồ" / "quán hải sản" mention (no allergy verb) is NOT treated
# as an exclusion. 'không ăn X' (bare, no 'được') + 'không uống (được) X' cover the natural
# dairy/organ declarations ("tôi không uống được sữa", "tôi không ăn nội tạng").
_ALLERGY_VERB_RE = re.compile(
    r"di ung|khong (an|uong)( duoc)?|ko (an|uong)( duoc)?|kien|bi dau|benh"
)
# Durable-declaration markers (folded). When present, a diet declaration persists cross-session;
# otherwise it is session-scoped.
_DURABLE_RE = re.compile(r"tu gio|tu nay|luon luon|trong tuong lai|truong")
# Diet-break (contradiction) markers — a user turn explicitly abandons the diet this turn.
_DIET_BREAK_RE = re.compile(r"\b(bo chay|khong an chay( nua)?|tro lai an (man|thit)|an thit|phap le|pha le)\b")
# Interrogation markers (folded) — asking about a diet is NOT declaring it.
_QUESTION_RE = re.compile(r"\?|khong\s*(\?|$)|\bco\b.{0,30}\bkhong\b|duoc khong|the nao|co phai|la gi")
# Negation of a diet declaration (folded) — 'không ăn chay' must not impose vegetarian.
_WANT_NEGATION_RE = re.compile(r"khong\s+(an\s+|thich\s+|muon\s+)?chay|khong\s+chay")
# Allergy recovery / retraction (folded) — a user withdrawing a prior allergy must NOT (re)impose
# it. Covers "không còn/đã hết dị ứng" AND natural retractions ("quên chuyện dị ứng tôm đi", "giờ
# ăn được bình thường rồi", "bác sĩ nói hết"). KEEP IN SYNC with context_memory_service._RETRACTION_RE
# (which prevents the retraction being saved + removes the prior note at extraction time).
_RECOVERY_RE = re.compile(
    r"khong con|da het|het roi|het benh|khoi\s*benh|mat di ung|khong\s*bi.{0,20}nua"
    r"|quen\s*(chuyen|di)|het\s*di ung|khoi\s*di ung|an duoc binh thuong|gio\s*an duoc"
    r"|bo\s*di ung|bac si.{0,30}(het|khong con|khoi)"
)

# Third-party dining (folded) — the CURRENT turn asks on behalf of SOMEONE ELSE ("đi ăn hộ bạn",
# "bạn tôi thích đồ Hàn", "mẹ tôi thèm chè"). The eater is not the user, so their tastes differ:
# DIET (chay) constraints must NOT filter this turn's results — the user is not the one eating.
# ALLERGIES are KEPT (safety posture: ordering for someone else still passes through the user's
# own allergen awareness; dropping a seafood-allergy here would be indefensible). Suppression is
# TURN-SCOPED (regex on the current query only) — the durable note itself is untouched.
# POSITION RULE (eval 3.2): 'gia dinh'/'nguoi than' alone is CONTEXT, not delegation — a bare
# family mention ("gia dinh hom nay la thu Hai, goi y do an trua cho toi" — the USER eats) must
# NOT suspend the diet. They only count when an explicit FOR-SOMEONE construction co-occurs
# (hộ/cho/thay/cty... + recipient), which the alternations below already spell out.
_THIRD_PARTY_RE = re.compile(
    r"an ho|ho ban|ban (toi|to|minh|cua toi)|ban ay|nguoi khac"
    r"|cho (me|bo|chong|vo|ong|ba|con|em|anh|chi) "
    r"|ban cua (toi|to|minh)|ket ban|dong nghiep"
    r"|(gia dinh|nguoi than).{0,25}(an gi|thich|thom|muon an|goi y cho)"
)
# Contrast/caveat markers (folded) — END the post-verb allergy zone. 'dị ứng tôm NHƯNG vẫn
# thích hải sản': the allergen is 'tôm'; the liking tail after 'nhưng' is not an allergen list.
_CONTRAST_RE = re.compile(r"nhung|nhung ma|con (thich|muon)|van (thich|me|an)|ma van|nhe ra|doi lai")

_SESSION_WINDOW = 8  # floor: recent USER turns scanned (covers transient "nay ăn chay" not in notes)


def _session_window() -> int:
    """Constraint-scan window — tracks the within-conversation recall window
    (memory_window_turns) so a constraint declared in ANY recalled turn is seen.
    Floored at _SESSION_WINDOW; settings failure falls back to the floor."""
    try:
        from core.settings import get_settings
        return max(_SESSION_WINDOW, int(get_settings().memory_window_turns))
    except Exception:  # noqa: BLE001
        return _SESSION_WINDOW


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
    """The normalized constraint set consulted by every output step.

    ``health_notes`` carries durable allergy/avoid sentences whose scope is NOT in the catalog
    (e.g. peanut, garlic, organ-meat) — they cannot be hard-filtered deterministically (no
    dish-level allergen data), so they are surfaced to the explanation LLM, which warns the user
    via world-knowledge. This is the GENERALIZE path: any allergen the user declares is proactively
    flagged without per-allergen catalog entries."""

    hard: tuple[Constraint, ...] = ()
    soft: tuple[Constraint, ...] = ()
    health_notes: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.hard or self.soft or self.health_notes)

    def labels(self, which: str = "hard") -> list[str]:
        cs = self.hard if which == "hard" else self.soft
        return [CATALOG[c.scope].label_vi for c in cs if c.scope in CATALOG]


def _avoid_scopes(text_raw: str, text_folded: str) -> list[str]:
    """Catalog 'avoid' scopes present (only when an allergy verb co-occurs; recovery suppresses).

    POSITION-AWARE (eval 2.2): the allergen term must appear AFTER the first allergy verb and
    BEFORE any contrast/liking tail. Vietnamese declarative order puts the allergen directly
    behind the verb ('tôi bị dị ứng tôm'); a stated liking may sit before ('tôi thích hải sản
    ... nhưng tôi dị ứng tôm') or after ('tôi dị ứng tôm nhưng vẫn thích hải sản'). Both
    surrounding liking clauses must stay neutral — only the clause adjacent to the verb counts.
    The allergy zone therefore ends at the first CONTRAST/CAVEAT marker (nhưng/nhỉ/mà...)."""
    if not text_folded:
        return []
    m = _ALLERGY_VERB_RE.search(text_folded)
    if not m:
        return []
    if _RECOVERY_RE.search(text_folded):
        return []  # user recovered from the allergy — do not impose
    zone_folded = text_folded[m.end():]             # everything after the verb …
    cut = _CONTRAST_RE.search(zone_folded)          # … up to the first contrast/liking tail
    if cut:
        zone_folded = zone_folded[: cut.start()]
    # RAW slice aligned to the TAIL (folding never lengthens text, so the last N chars of the
    # raw text correspond to the folded tail — diacritics are only stripped/combined, never added).
    n_raw = len(text_raw or "")
    zone_raw = (text_raw or "")[max(0, n_raw - len(zone_folded)):] if zone_folded else ""
    return [s for s, d in CATALOG.items()
            if d.kind == "avoid" and scope_present(d, zone_raw, zone_folded)]


def _want_scopes(text_raw: str, text_folded: str) -> list[tuple[str, bool]]:
    """Catalog 'want' (diet) scopes → (scope, durable). Question/negation suppresses."""
    out: list[tuple[str, bool]] = []
    if not text_folded:
        return out
    if _QUESTION_RE.search(text_folded) or _WANT_NEGATION_RE.search(text_folded):
        return out  # asking about / negating the diet → not a declaration
    durable = bool(_DURABLE_RE.search(text_folded))
    for s, d in CATALOG.items():
        if d.kind == "want" and scope_present(d, text_raw, text_folded):
            out.append((s, durable))
    return out


def _from_text(text_raw: str, origin: str, persistence: str) -> list[Constraint]:
    """Extract constraints from one text blob (raw + its fold) with a known origin/persistence."""
    text_raw = normalize_abbreviations(text_raw)  # 'dị ứng HS' → 'dị ứng hải sản' (eval 8.3)
    text_folded = fold_diacritics(text_raw)
    out: list[Constraint] = []
    # Parent→children (seafood ⊃ shrimp): a general declaration enforces the narrower scope too.
    avoid_scopes = expand_child_scopes(_avoid_scopes(text_raw, text_folded))
    for scope in avoid_scopes:  # allergy → hard
        out.append(Constraint("allergy", scope, "hard_filter", origin, persistence,
                              f"dị ứng/không ăn được {CATALOG[scope].label_vi}"))
    for scope, durable in _want_scopes(text_raw, text_folded):  # diet → hard (want)
        # Honor an in-text durable marker ('từ giờ ...'): promote to durable regardless of layer.
        pers = "durable" if durable else persistence
        out.append(Constraint("diet", scope, "hard_filter", origin, pers,
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


def _broke_diet(query_folded: str, prior_user_texts: list[str]) -> bool:
    """True if the diet is abandoned in the CURRENT query OR a recent prior USER turn."""
    if _DIET_BREAK_RE.search(query_folded or ""):
        return True
    return any(_DIET_BREAK_RE.search(fold_diacritics(t)) for t in prior_user_texts)


def _expired_note_keys(expiries: Any) -> set[str]:
    """Lowercased note keys whose ISO expiry is in the past (6.3 TTL). Defense-in-depth:
    ``maybe_persist`` prunes elapsed notes at write time; this ALSO skips them at read time so a
    stale temporary constraint can never enforce even if pruning hasn't run (e.g. a direct tool
    call). Malformed expiry values are ignored (never drop a note on a parse error)."""
    if not expiries or not isinstance(expiries, dict):
        return set()
    now = datetime.now(timezone.utc)
    out: set[str] = set()
    for k, v in expiries.items():
        try:
            if datetime.fromisoformat(str(v)) < now:
                out.add(str(k).lower())
        except (ValueError, TypeError):
            continue
    return out


def _process_declaration(
    text: str, origin: str, broke_diet: bool, hard: list, health_notes: list,
    *, suppress_diet: bool = False,
) -> None:
    """Enforce catalog constraints from one durable sentence AND surface it as a health warning
    when it carries an active allergy the catalog can't fully cover. Shared by the notes loop
    (Layer 2) and the no-cap ``allergens`` loop (Phase 2) so both paths enforce + warn identically
    — a permanent allergy thus survives even when its note twin was FIFO-evicted (6.1).
    ``suppress_diet`` (third-party turn) skips ONLY diet constraints — allergies still enforce."""
    note_str = normalize_abbreviations(str(text))  # abbreviations (HS→hải sản) before matching
    folded_note = fold_diacritics(note_str)
    produced = _from_text(note_str, origin, "durable")
    for c in produced:
        if not (c.type == "diet" and (broke_diet or suppress_diet)):
            hard.append(c)
    only_abandoned_diet = bool(produced) and all(c.type == "diet" for c in produced) and broke_diet
    if (_ALLERGY_VERB_RE.search(folded_note)
            and not _RECOVERY_RE.search(folded_note)
            and not only_abandoned_diet):
        clean = note_str.strip()
        if clean and clean not in health_notes:
            health_notes.append(clean)


def build_active_constraints(
    profile: Any, prior_turns: list[Any] | None, query: str | None
) -> ActiveConstraints:
    """Load the user's active hard + soft constraints from all 3 memory layers.

    Hard: allergies (any origin) + diet declarations (durable note/profile OR recent session turn).
    Soft: structured disliked cuisines (ranking handles the penalty; included so the explanation
    prompt can mention them). Contradiction (current query OR a prior user turn breaks the diet)
    drops diet constraints for THIS turn so a changed mind isn't over-restricted. Third-party
    dining ("đi ăn hộ bạn") likewise suspends DIET constraints for this turn (allergies kept)."""
    q_folded = fold_diacritics(query or "")
    third_party = bool(_THIRD_PARTY_RE.search(q_folded))

    # Prior USER turns — filtered BEFORE the window slice so agent turns don't halve the window.
    user_texts: list[str] = []
    for turn in (prior_turns or []):
        if not isinstance(turn, dict):
            continue
        role = (turn.get("role") or turn.get("sender") or "").lower()
        if "user" in role:
            user_texts.append(turn.get("text") or turn.get("content") or "")
    recent_user_texts = user_texts[-_session_window():]
    broke_diet = _broke_diet(q_folded, recent_user_texts)

    hard: list[Constraint] = []
    soft: list[Constraint] = []
    # Allergy/avoid sentences whose scope is NOT in the catalog — surfaced to the LLM (see
    # ActiveConstraints.health_notes). Cannot be hard-filtered without dish-level allergen data.
    health_notes: list[str] = []

    # Layer 1 — structured profile.
    if profile is not None:
        dietary = getattr(profile, "dietary", None) or []
        if isinstance(dietary, (list, tuple)):
            joined = " ".join(str(d) for d in dietary)
            for scope, _d in _want_scopes(joined, fold_diacritics(joined)):
                if not broke_diet and not third_party:
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
        expired = _expired_note_keys(cm.get("note_expiries") if isinstance(cm, dict) else None)
        for note in notes:
            if str(note).lower() in expired:
                continue  # TTL (6.3): temporary constraint elapsed — neither enforce nor warn
            _process_declaration(note, "context_memory", broke_diet, hard, health_notes,
                                 suppress_diet=third_party)
        # Phase 2 (6.1): the no-cap `allergens` store — same enforcement + surfacing as notes, so a
        # permanent allergy survives even when its note twin was FIFO-evicted. (No expiry skip here:
        # allergens holds PERMANENT facts only; temporary "kiêng" lives in notes with a TTL.)
        for allergen in (getattr(profile, "allergens", None) or []):
            entry = str(allergen).strip()
            # UI-added allergens (Preference Center) are bare nouns ("đậu phộng") — no allergy
            # verb, but catalog scope + health-note surfacing both key on the verb. Wrap a
            # verb-less entry as "dị ứng {noun}" so a hand-added allergen hard-filters (catalog
            # scopes, e.g. "hải sản") and warns (non-catalog allergens) exactly like a
            # chat-declared sentence. Full sentences already carry the verb → untouched.
            if entry and not _ALLERGY_VERB_RE.search(fold_diacritics(entry)):
                entry = f"dị ứng {entry}"
            _process_declaration(entry, "profile", broke_diet, hard, health_notes,
                                 suppress_diet=third_party)

    # Layer 3 — recent session USER turns (session-scoped; covers transient 'nay ăn chay').
    for text in recent_user_texts:
        for c in _from_text(text, "session_turn", "session"):
            if not (c.type == "diet" and (broke_diet or third_party)):
                hard.append(c)

    # The CURRENT message is also a declaration source (session) — covers a same-turn declaration
    # like TC-48 'từ giờ nhớ tôi ăn chay trường' (not yet in prior_turns). Diet-break markers in
    # the current query already set broke_diet above, which suppresses diet constraints here.
    # (A same-turn diet declaration with a third-party marker is contradictory — third-party
    # suspension wins for THIS turn; the declaration still persists via context_memory.)
    for c in _from_text(query or "", "session_turn", "session"):
        if not (c.type == "diet" and (broke_diet or third_party)):
            hard.append(c)

    return ActiveConstraints(
        hard=_dedupe(hard), soft=tuple(soft), health_notes=tuple(health_notes[:6])
    )


def active_constraints_block(cs: ActiveConstraints | None) -> str:
    """Render the user-restriction block injected into the explanation prompt (L3).

    Two conditional sections:
      (1) hard catalog constraints → 'RÀNG BUỘC NGƯỜI DÙNG / LOẠI TRỪ': the deterministic filter
          already dropped violators; this tells the LLM so it doesn't recommend one in prose.
      (2) ``health_notes`` → 'CẢNH BÁO SỨC KHOẺ': allergy/avoid sentences OUTSIDE the catalog
          (peanut, garlic, …). The LLM must proactively warn + steer clear using world-knowledge —
          this is the GENERALIZE path (no per-allergen catalog entry needed)."""
    if cs is None or cs.is_empty:
        return ""
    lines: list[str] = []
    if cs.hard:
        lines.append("RÀNG BUỘC NGƯỜI DÙNG (TUÂN THỦ NGHIÊM NGẶT — không gợi ý quán vi phạm):")
        for c in cs.hard:
            label = CATALOG[c.scope].label_vi if c.scope in CATALOG else c.scope
            lines.append(f"- LOẠI TRỪ {label} ({c.rationale or c.type})")
    if cs.health_notes:
        lines.append(
            "CẢNH BÁO SỨC KHOẺ — của CHÍNH NGƯỜI DÙNG đang chat với bạn (dị ứng/không ăn được; "
            "KHÔNG phải bạn bè/người thứ 3 họ có thể nhắc tới trong lượt này). CHỦ ĐỘNG nhắc + "
            "tránh món có nguy cơ, KHÔNG chờ user nhắc lại; nếu không chắc món có chứa chất đó "
            "thì VẪN cảnh báo rõ. Khi nhắc, gọi chủ thể là BẠN (người dùng), đừng gán cho người khác:"
        )
        for n in cs.health_notes:
            lines.append(f'- Chính người dùng từng nói về bản thân họ: "{n}"')
    return "\n".join(lines)
