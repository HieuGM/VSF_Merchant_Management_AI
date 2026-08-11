"""Per-conversation distillate service (memory-system P2).

A lightweight, DETERMINISTIC, LLM-free summary of ONE conversation, accumulated
incrementally on each agent turn and stored under the `distillate` key of
`chat_sessions.context_snapshot_json` — a column that already exists but has NO
production writer (session_repository only READS the sibling `candidates` key, so
this coexists safely; the RMW preserves all sibling keys). No migration needed.

Purpose: cross-conversation recall (P2b) — folded-ILIKE match the current query
against past conversations' intent/cuisines. Distillate shape (accumulated):

    {
      "intent":      <first user query (redacted) — the conversation topic>,
      "last_query":  <most recent user query (redacted)>,
      "cuisines":    [<explored cuisines, union, order-stable>],
      "shown":       [<merchant ids ever surfaced, union, order-stable>],
      "turn_count":  <int>,
      "ts":          <ISO UTC, last update>
    }

All entry points open their own SessionLocal and NEVER raise (phase-01 F3) — a
distillate failure must never break the chat flow.

PII posture: `intent`/`last_query` are run through `redact_pii` (VN phone + email
masked), matching the chat_messages.text posture — NOT a regression. BUT the distillate
is a NEW durable, user-keyed, cross-conversation surface, so before flipping
memory_cross_conv_enabled=true in prod, consider expanding redaction (names/honorifics/
addresses). Tracked as an open question, not a blocker for the flag-OFF default.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DISTILLATE_KEY = "distillate"


def update_distillate(
    session_id: str,
    user_text: str,
    top3: list[dict],
) -> None:
    """Incrementally merge this turn into the conversation's distillate.

    `top3` = the agent's displayed results ([{merchant_id, name, cuisine}, ...]).
    Accumulates `shown` ids + `cuisines` across turns; `intent` is set once (first
    turn = the conversation topic). RMW preserves sibling keys in
    context_snapshot_json. The caller gates this on user_id presence (a distillate is
    only useful for a known user — cross-conv recall is per-user). Never raises (F3)."""
    from database.connection import SessionLocal
    from database.models import ChatSession

    db = SessionLocal()
    try:
        row = db.get(ChatSession, session_id)
        if row is None:
            return  # append_turn creates the parent first; nothing to write to otherwise.
        snapshot = dict(row.context_snapshot_json or {})
        dist = dict(snapshot.get(_DISTILLATE_KEY) or {})

        _merge_turn(dist, user_text, top3)

        snapshot[_DISTILLATE_KEY] = dist
        row.context_snapshot_json = snapshot  # reassign so SQLAlchemy detects the change
        db.commit()
    except Exception as exc:  # noqa: BLE001 — distillate must never break the flow
        db.rollback()
        logger.warning("update_distillate failed (session=%s): %s", session_id, exc)
    finally:
        db.close()


def get_distillate(session_id: str) -> dict | None:
    """Read the distillate for one session (test helper / inspection). None if absent."""
    from database.connection import SessionLocal
    from database.models import ChatSession

    db = SessionLocal()
    try:
        row = db.get(ChatSession, session_id)
        if row is None:
            return None
        snapshot = row.context_snapshot_json or {}
        dist = snapshot.get(_DISTILLATE_KEY) if isinstance(snapshot, dict) else None
        return dict(dist) if isinstance(dist, dict) else None
    finally:
        db.close()


def build_distillate_state(
    existing: dict | None, user_text: str, top3: list[dict]
) -> dict:
    """Pure merge of one turn into a distillate dict (no DB). Exported for unit tests
    so the accumulation logic is testable without Postgres."""
    from core.pii import redact_pii

    dist = dict(existing or {})
    _merge_turn(dist, user_text, top3, redact=redact_pii)
    return dist


# --------------------------------------------------------------------------- #
# internal
# --------------------------------------------------------------------------- #
def _merge_turn(
    dist: dict,
    user_text: str,
    top3: list[dict],
    redact=None,
) -> None:
    """Mutate `dist` in place, merging one turn. `redact` injected so the pure test
    path (build_distillate_state) can pass the real redact_pii without a DB import."""
    if redact is None:
        from core.pii import redact_pii
        redact = redact_pii

    clean_query = redact(user_text or "").strip()

    # intent set ONCE (the conversation topic = first user query).
    if not dist.get("intent") and clean_query:
        dist["intent"] = clean_query
    if clean_query:
        dist["last_query"] = clean_query

    cuisines = list(dist.get("cuisines") or [])
    for r in top3 or []:
        c = r.get("cuisine")
        if c and c not in cuisines:
            cuisines.append(c)
    if cuisines:
        dist["cuisines"] = cuisines

    shown = list(dist.get("shown") or [])
    for r in top3 or []:
        mid = r.get("merchant_id")
        if mid:
            mid = str(mid)
            if mid not in shown:
                shown.append(mid)
    if shown:
        dist["shown"] = shown

    dist["turn_count"] = int(dist.get("turn_count") or 0) + 1
    dist["ts"] = datetime.now(timezone.utc).isoformat()
