"""Long-term cross-session memory (phase-03).

Distills DURABLE free-text facts from the user's message — things NOT captured by the
structured profile schema (allergies, persistent-diet declarations, specific medical
context) — into ``user_profiles.context_memory["notes"]``. The ``get_user_profile`` tool
already returns ``context_memory`` in its profile dict, so the crew / preference agent
reads these notes with NO new injection path — we only populate the field.

Boundary (important — no overlap):
- ``prior_context`` (chat_messages, phase-01/02) = SHORT-TERM, in-session anaphora.
- ``context_memory`` (user_profiles JSONB, this module) = LONG-TERM, cross-session.

Best-effort end-to-end: ``extract_notes`` is heuristic + high-precision (a small trigger
list, deliberately narrow to avoid noise); ``append_notes`` redacts PII, dedupes
(case-insensitive), and caps FIFO. ``maybe_persist`` never raises (F3) — a memory failure
must never break the chat flow. The structured preference flow (liked/disliked_cuisines,
dietary) is the canonical store for taste prefs; this module only stores facts that have
no structured field (e.g. an allergen, or a declared persistent diet)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from core.constraint_catalog import CATALOG
from core.text_norm import fold_diacritics as _fold

from core.logging import get_logger
from core.pii import redact_pii
from database.connection import SessionLocal
from repositories.user_profile_repository import UserProfileRepository

_LOG = get_logger(__name__)

# High-precision triggers (diacritics-folded). Only DURABLE facts with no structured field.
# Vague likes/dislikes are intentionally excluded — the structured preference flow owns those.
# "benh" (bệnh) is excluded: false-positives on location cues like "gần bệnh viện".
# "da day" is qualified to đau/viêm: the bare form collides with "đã đầy" (I'm full).
_TRIGGERS: tuple[str, ...] = (
    "di ung",           # dị ứng — allergy (health risk)
    "khong an duoc",    # không ăn được — can't eat
    "kieng",            # kiêng — avoid (health/religion)
    "chay truong",      # chay trường — persistent vegetarian
    "tu gio an chay",   # từ giờ ăn chay — declared persistent
    "tieu duong",       # tiểu đường — diabetes (durable medical)
    "dau da day",       # đau dạ dày — stomach ache
    "viem da day",      # viêm dạ dày — gastritis
)

# Transient time markers (folded, word-boundary). A bare 'ăn chay' carrying one is a ONE-OFF
# ('hôm nay ăn chay'), not a durable habit — so it is not persisted (memory.txt Test 1 vs Test 2).
# Scope is DIET ONLY: allergies/medical conditions are durable regardless of a 'hôm nay' mention
# ('hôm nay đau dạ dày' is still a stomach fact), so the guard does not apply to those triggers.
_TRANSIENT_RE = re.compile(r"\b(hom nay|hom qua|ngay mai|lan nay)\b")

# Retraction/recovery markers (folded) — a user withdrawing a prior allergy declaration
# ("quên chuyện dị ứng tôm đi", "bác sĩ nói hết dị ứng", "giờ ăn được bình thường rồi"). Such a
# sentence must NOT be persisted as a new note (it would contradict the original and re-enforce the
# very allergy being retracted — the stale-note bug, memory_test.json 7.2/3.4). Instead the matching
# prior note is REMOVED (see maybe_persist). KEEP IN SYNC with active_constraints_loader._RECOVERY_RE
# (which suppresses the allergen at enforcement when the retraction is in the current message).
_RETRACTION_RE = re.compile(
    r"quen\s*(chuyen|di)|khong con\s*(di ung|bi)|da het|het roi|het\s*di ung|het benh|"
    r"khoi\s*(benh|di ung)|mat di ung|an duoc binh thuong|gio\s*an duoc|bo\s*di ung|"
    r"khong\s*bi.{0,20}nua|bac si.{0,30}(het|khong con|khoi)"
)

# Trailing tokens to strip when extracting the retracted food term (particles/verbs, not the food).
_RETRACT_STOP = {"di", "roi", "nua", "ay", "the", "lam", "nhieu", "va", "ma", "thoi", "nhe"}

# Folded duration markers → approximate validity in DAYS. A note carrying one is a TEMPORARY
# constraint (memory_test.json 6.3: "tuần này ăn kiêng ít dầu mỡ") that auto-expires, unlike a
# permanent allergy/diet. Order matters: more-specific multi-token markers first so "2 ngày" wins
# over a bare "ngày" form. Absent a marker → None → the note is durable (current default).
_DURATIONS: tuple[tuple[str, int], ...] = (
    ("2 ngay", 2), ("hai ngay", 2), ("3 ngay", 3), ("ba ngay", 3),
    ("may ngay", 3), ("vai ngay", 2), ("mot ngay", 1), ("1 ngay", 1), ("trong ngay", 1),
    ("hom nay", 1),
    ("2 tuan", 14), ("hai tuan", 14), ("mot tuan", 7), ("1 tuan", 7), ("tuan nay", 7), ("tuan", 7),
    ("2 thang", 60), ("mot thang", 30), ("1 thang", 30), ("thang nay", 30),
)


def _duration_days(folded: str) -> int | None:
    """Approximate validity (days) when the sentence carries a temporary-duration marker, else None."""
    for marker, days in _DURATIONS:
        if marker in folded:
            return days
    return None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expiry_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# Allergy/avoid triggers (subset of _TRIGGERS). A durable declaration carrying one is a
# food-avoidance fact → also mirrored to the no-cap `allergens` store (Phase 2, distinct from the
# FIFO-capped notes) so a safety-critical allergy is never evicted (memory_test.json 6.1).
_AVOID_TRIGGERS: tuple[str, ...] = ("di ung", "khong an duoc", "kieng")


def _is_permanent_avoid_note(folded: str) -> bool:
    """True for a durable allergy/avoid declaration with NO time bound → belongs in the no-cap
    `allergens` store. A temporary "kiêng" (carries a duration marker) stays in notes (TTL) only."""
    return any(t in folded for t in _AVOID_TRIGGERS) and _duration_days(folded) is None


_MAX_NOTE_LEN = 120
_MAX_NOTES = 8


# `_fold` is imported above from core.text_norm (audit #15). Notes are stored in original
# Vietnamese; folding is for trigger matching only.


def _sentences(text: str) -> list[str]:
    """Split into trimmed sentences on Vietnamese + common terminators."""
    return [s.strip() for s in re.split(r"[\.!\?\n;]+", text) if s.strip()]


def extract_notes(user_text: str | None) -> list[str]:
    """Return durable-fact sentences (ORIGINAL Vietnamese, PII-redacted, length-capped)
    that contain a trigger. Empty when no trigger / empty input. High-precision by design."""
    if not user_text:
        return []
    notes: list[str] = []
    for sent in _sentences(user_text):
        sf = _fold(sent)
        # A retraction ("quên chuyện dị ứng tôm đi", "đã hết dị ứng") is NEVER saved as a note —
        # it would contradict + re-enforce the retracted allergy. maybe_persist removes the prior
        # note instead. (Skipped here so extract_notes alone never produces a contradictory note.)
        if _RETRACTION_RE.search(sf):
            continue
        triggered = any(t in sf for t in _TRIGGERS)
        # Bare 'ăn chay' (not the 'từ giờ'/'trường' forms above) is durable ONLY without a
        # transient time marker — 'tôi ăn chay' (habit) persists, 'hôm nay ăn chay' (one-off) does
        # not. Allergies/medical are durable regardless of 'hôm nay', so they skip this guard.
        if not triggered and "an chay" in sf and not _TRANSIENT_RE.search(sf):
            triggered = True
        if triggered:
            note = redact_pii(sent)
            if len(note) > _MAX_NOTE_LEN:
                note = note[: _MAX_NOTE_LEN - 3].rstrip() + "..."
            if note:
                notes.append(note)
    return notes


def append_notes(user_id: str, notes_with_expiry: list[tuple[str, str | None]]) -> None:
    """Persist notes into ``context_memory["notes"]``: dedupe (case-insensitive) + FIFO cap.

    Each entry is ``(note, expiry_iso|None)``; a set expiry marks a TEMPORARY constraint (6.3) and
    is stored in ``context_memory["note_expiries"]`` keyed by the lowercased note. One tx; upserts
    a minimal row if the user has none. Never raises — wrapped so memory cannot break the flow (F3)."""
    if not notes_with_expiry:
        return
    notes = [n for n, _ in notes_with_expiry]
    expiries = {n.lower(): exp for n, exp in notes_with_expiry if exp}
    db = SessionLocal()
    try:
        UserProfileRepository(db).append_context_notes(user_id, notes, cap=_MAX_NOTES, expiries=expiries)
    except Exception as exc:  # noqa: BLE001 — memory must never break the flow
        _LOG.warning("context_memory append failed (user=%s): %s", user_id, exc)
    finally:
        db.close()


def _retracted_food_terms(text_folded: str) -> list[str]:
    """Food terms a retraction message withdraws (folded): the token(s) right after an allergy
    verb, plus any catalog 'avoid' term present. Used to match + remove the prior note. Returns
    [] when no specific food can be identified (then nothing is removed — conservative, since
    removing the wrong note is worse than leaving a stale one the loader can still suppress)."""
    terms: set[str] = set()
    m = re.search(r"(?:di ung|khong an duoc|ko an duoc|kien)\s+((?:\w+\s+){0,1}\w+)", text_folded)
    if m:
        toks = m.group(1).split()
        while toks and toks[-1] in _RETRACT_STOP:  # strip trailing particles ("đi", "rồi", …)
            toks.pop()
        if toks:
            terms.add(" ".join(toks))
    for _scope, d in CATALOG.items():
        if d.kind != "avoid":
            continue
        for t in d.terms:
            ft = _fold(t)
            if not ft:
                continue
            if " " in ft:
                if ft in text_folded:
                    terms.add(ft)
            elif ft in text_folded.split():
                terms.add(ft)
    return [t for t in terms if len(t) > 1]


def maybe_persist(user_id: str | None, user_text: str | None) -> None:
    """Extract durable facts from the user message + append them. No-op without a user_id
    or when no trigger fires. Best-effort, never raises (F3) — called from _persist_user_turn
    at flow ENTRY, BEFORE the run's try/except, so any exception here would surface as an
    uncaught 500. Three duties, one tx:
      - Retract (7.2/3.4): a withdrawal ("quên dị ứng tôm") removes the matching prior note.
      - Expire (6.3): drop notes whose temporary duration window has elapsed.
      - Append: new durable facts, tagged with an expiry when the sentence is time-bounded
        ("tuần này ăn kiêng" → expires in 7 days) so temporary constraints do not persist forever."""
    if not user_id:
        return
    try:
        folded = _fold(user_text or "")
        notes_with_expiry: list[tuple[str, str | None]] = []
        for n in extract_notes(user_text):
            days = _duration_days(_fold(n))
            notes_with_expiry.append((n, _expiry_iso(days) if days else None))
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            if _RETRACTION_RE.search(folded):
                terms = _retracted_food_terms(folded)
                if terms:
                    repo.remove_notes_matching(user_id, terms)
                    repo.remove_allergens_matching(user_id, terms)  # Phase 2: keep allergens in sync
            repo.prune_expired_notes(user_id)  # TTL hygiene (6.3): drop elapsed temporary notes
            if notes_with_expiry:
                repo.append_context_notes(
                    user_id, [n for n, _ in notes_with_expiry], cap=_MAX_NOTES,
                    expiries={n.lower(): exp for n, exp in notes_with_expiry if exp},
                )
            # Phase 2 (6.1): mirror PERMANENT allergy/avoid facts to the no-cap `allergens` store so
            # they survive FIFO eviction. Temporary kiêng (has duration) stays in notes (TTL) only.
            permanents = [n for n, _ in notes_with_expiry if _is_permanent_avoid_note(_fold(n))]
            if permanents:
                repo.add_allergens(user_id, permanents)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — memory must never break the flow (F3)
        _LOG.warning("context_memory maybe_persist failed (user=%s): %s", user_id, exc)
