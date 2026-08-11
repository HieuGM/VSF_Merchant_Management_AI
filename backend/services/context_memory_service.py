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


def append_notes(user_id: str, notes: list[str]) -> None:
    """Persist notes into ``context_memory["notes"]``: dedupe (case-insensitive) + FIFO cap.

    One tx; upserts a minimal row if the user has none. Never raises — wrapped so memory
    cannot break the flow (F3)."""
    if not notes:
        return
    db = SessionLocal()
    try:
        UserProfileRepository(db).append_context_notes(user_id, notes, cap=_MAX_NOTES)
    except Exception as exc:  # noqa: BLE001 — memory must never break the flow
        _LOG.warning("context_memory append failed (user=%s): %s", user_id, exc)
    finally:
        db.close()


def maybe_persist(user_id: str | None, user_text: str | None) -> None:
    """Extract durable facts from the user message + append them. No-op without a user_id
    or when no trigger fires. Best-effort, never raises (F3) — called from _persist_user_turn
    at flow ENTRY, BEFORE the run's try/except, so any exception here would surface as an
    uncaught 500. Wrapping extract_notes too (append_notes is already wrapped)."""
    if not user_id:
        return
    try:
        notes = extract_notes(user_text)
        if notes:
            append_notes(user_id, notes)
    except Exception as exc:  # noqa: BLE001 — memory must never break the flow (F3)
        _LOG.warning("context_memory maybe_persist failed (user=%s): %s", user_id, exc)
