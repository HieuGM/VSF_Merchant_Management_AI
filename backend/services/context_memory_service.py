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
import unicodedata

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

_MAX_NOTE_LEN = 120
_MAX_NOTES = 8


def _fold(s: str | None) -> str:
    """Diacritics-fold + lowercase for trigger matching only. (Notes themselves are stored
    in original Vietnamese so the crew reads natural text.)

    Handles ``đ``/``Đ`` → ``d`` explicitly — ``encode('ascii','ignore')`` would DROP ``đ``
    (it is a single non-decomposable char), turning 'tiểu đường' into 'tieu uong' and
    missing the 'tieu duong' trigger. (Same latent bug existed in profile_ranking._fold.)"""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    no_mark = "".join(c for c in nfd if not unicodedata.combining(c))
    return no_mark.replace("đ", "d").replace("Đ", "d").lower()


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
        if any(t in _fold(sent) for t in _TRIGGERS):
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
