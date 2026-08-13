"""Chat message repository — durable conversation turns (design §6.2 chat_messages).

Append-only turn store keyed by session_id.

- append_turn: persists one user/agent turn. NEVER raises — persistence failures
  are logged + swallowed so the flow / SSE stream stay unaffected (phase-01 F3).
  PII is redacted before write (audit phase-01 supplement) and the parent
  ChatSession is get-or-created anonymous-safe so the session_id FK always holds
  (audit B1 — otherwise every INSERT FK-violates and memory silently never persists).
- get_recent_turns: loads the last N turns within a TTL window for anaphora context
  injection (phase-02). TTL uses DB server time, no client-clock param (audit B2).

Repository receives a Session; the caller (flow helper) owns the SessionLocal
lifecycle, consistent with UserProfileRepository / SessionRepository.
"""
from __future__ import annotations

import logging

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from core.pii import redact_pii
from core.tracing import new_id
from database.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


def make_title(text: str | None) -> str | None:
    """Derive a short conversation title from the first user message: first ~6 words,
    capped at ~40 chars, ORIGINAL Vietnamese (not diacritic-folded). None when empty.

    Used as the auto-title when a ChatSession is first created (ChatGPT-style), so the
    history list isn't all "untitled". Editable later via PATCH .../sessions/{id}. This is
    a cheap deterministic truncation — no LLM cost (YAGNI)."""
    if not text:
        return None
    cleaned = " ".join(text.split())  # collapse runs of whitespace/newlines
    if not cleaned:
        return None
    title = " ".join(cleaned.split()[:6])
    if len(title) > 40:
        title = title[:37].rstrip() + "…"
    return title


class ChatMessageRepository:
    """Session-scoped read/write access to conversation turns."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def append_turn(
        self,
        session_id: str | None,
        sender: str,
        text: str,
        trace_id: str | None = None,
        payload: dict | None = None,
        user_id: str | None = None,
    ) -> None:
        """Persist one turn. No-op when session_id is None; never raises (phase-01 F3).

        `user_id` (memory-system P2) binds the parent ChatSession to its user so
        conversations become queryable per-user (prerequisite for cross-conv recall).
        Anonymous-safe when None."""
        if not session_id:
            return
        try:
            # Title is auto-derived from the FIRST user message of a session (the flow
            # persists the user turn at entry before any agent turn), so it is set exactly
            # once when the ChatSession row is created. Agent turns reuse the existing row.
            first_title = text if sender == "user" else None
            self._ensure_session(session_id, user_id=user_id, title=first_title)
            self._db.add(
                ChatMessage(
                    message_id=new_id("msg"),
                    session_id=session_id,
                    sender=sender,
                    text=redact_pii(text or ""),
                    trace_id=trace_id,
                    structured_payload_json=payload,
                )
            )
            self._db.commit()
            # memory-system storage: lazy-on-write purge of stale chat_messages
            # (time-gated + best-effort; runs in its own session). Routing-neutral.
            try:
                from services.chat_message_purge_service import maybe_purge_stale_messages

                maybe_purge_stale_messages()
            except Exception:  # noqa: BLE001 — purge must never break the chat write
                pass
        except Exception as exc:  # noqa: BLE001 — persistence must never break the flow.
            self._db.rollback()
            logger.warning(
                "append_turn failed (session=%s sender=%s): %s", session_id, sender, exc
            )

    def get_recent_turns(
        self,
        session_id: str | None,
        limit: int = 16,
        ttl_hours: int = 72,
    ) -> list[dict]:
        """Last `limit` turns newer than the TTL cutoff, chronological (oldest first).

        Empty list when session_id is missing or nothing matches. Consecutive
        identical (sender, text) pairs are collapsed (retry-dedupe supplement).
        """
        if not session_id:
            return []
        # DB-server-time cutoff (audit B2): make_interval keeps it bound-param safe.
        cutoff = sa_text("now() - make_interval(secs => :secs)").bindparams(
            secs=int(ttl_hours) * 3600
        )
        rows = (
            self._db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .filter(ChatMessage.timestamp > cutoff)
            .order_by(ChatMessage.timestamp.desc())
            .limit(int(limit))
            .all()
        )
        rows.reverse()  # DESC fetch -> chronological
        turns = [
            {
                "sender": r.sender,
                "text": r.text,
                "payload": r.structured_payload_json,
                "ts": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ]
        return self._collapse_duplicates(turns)

    def list_turns(self, session_id: str | None, limit: int = 200) -> list[dict]:
        """Most recent N turns for a session, chronological (oldest first), NO TTL cutoff —
        powers the conversation-history view (reload / reopen a past chat). Fetches newest-N
        then reverses so a long conversation shows its RECENT turns (not the oldest). Agent
        turns carry their stored top-3 merchant results in `structured_payload_json.results`
        (written by _persist_turns) so the FE can re-render the cards. Empty when missing.

        Distinct from get_recent_turns, which applies a 72h anaphora TTL window and is for
        in-flow context injection only — NOT suitable for history (would hide old turns)."""
        if not session_id:
            return []
        rows = (
            self._db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(int(limit))
            .all()
        )
        rows.reverse()  # newest-N fetch → chronological for display
        out: list[dict] = []
        for r in rows:
            payload = r.structured_payload_json
            results = payload.get("results") if isinstance(payload, dict) else []
            out.append(
                {
                    "sender": r.sender,
                    "text": r.text,
                    "ts": r.timestamp.isoformat() if r.timestamp else None,
                    "results": results or [],
                }
            )
        return out

    def _ensure_session(
        self, session_id: str, user_id: str | None = None, title: str | None = None
    ) -> None:
        """B1: get-or-create parent ChatSession before the FK insert.

        memory-system P2: binds `user_id` so conversations are queryable per-user. If the
        row is absent → create WITH user_id (when given) + an auto-title derived from the
        first user message (`title`, via make_title); if it exists with user_id=None and a
        user_id is now provided → backfill (covers a session first seen anonymously). Title
        is only set on CREATE — existing rows keep their (possibly user-edited) title.
        Anonymous-safe when user_id is None (chat_sessions.user_id is nullable / ON DELETE
        SET NULL, so no FK violation when no user_profiles row exists)."""
        existing = self._db.get(ChatSession, session_id)
        if existing is None:
            self._db.add(
                ChatSession(
                    session_id=session_id,
                    user_id=user_id or None,
                    title=make_title(title),
                )
            )
            self._db.flush()  # make the parent PK visible for the child FK.
            return
        if user_id and existing.user_id is None:
            existing.user_id = user_id
            self._db.flush()

    @staticmethod
    def _collapse_duplicates(turns: list[dict]) -> list[dict]:
        """Drop consecutive identical (sender, text) pairs (client-retry dedupe)."""
        out: list[dict] = []
        for turn in turns:
            if (
                out
                and out[-1]["sender"] == turn["sender"]
                and out[-1]["text"] == turn["text"]
            ):
                continue
            out.append(turn)
        return out
