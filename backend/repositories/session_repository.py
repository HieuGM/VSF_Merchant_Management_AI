"""Chat session repository (Phase 02) — read session candidate list + distillates.

Candidates are the merchant shortlist already generated in a session, persisted in
`chat_sessions.context_snapshot_json` (Redis stays the hot copy — §6.2). Returning
them lets the crew refine an existing list instead of re-searching.

memory-system P2b: `list_recent_distillates` reads the per-conversation `distillate`
object (written by conversation_distillate_service) for cross-conversation recall.

Contract for a candidate dict (minimal): `{merchant_id, name, cuisine, ...}`.
Missing session / empty snapshot → empty list (never raises)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from database.models import ChatSession
from repositories.chat_message_repository import make_title


def _iso(dt) -> str | None:
    """ISO 8601 string for a ChatSession timestamp, annotated as UTC.

    The columns are TIMESTAMP WITHOUT TIME ZONE and Postgres stores UTC (server tz=UTC), so
    the naive datetime is really UTC. A bare isoformat() has no offset → the browser's
    new Date() treats it as LOCAL time → in UTC+7 a session updated moments ago reads ~7h
    old ("7 giờ trước"). Appending 'Z' makes the FE parse it as UTC. A tz-aware dt passes
    through unchanged (isoformat already carries +00:00)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


class SessionRepository:
    """Read access to session context snapshots + distillates."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_candidates(self, session_id: str) -> list[dict[str, Any]]:
        row = self._db.get(ChatSession, session_id)
        if row is None or not row.context_snapshot_json:
            return []
        snapshot = row.context_snapshot_json
        candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
        if not isinstance(candidates, list):
            return []
        # Keep only dict entries — defensive against malformed snapshots.
        return [c for c in candidates if isinstance(c, dict)]

    def list_recent_distillates(
        self,
        user_id: str,
        limit: int = 20,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recent per-conversation distillates for a user (memory-system P2b recall).

        Returns the `distillate` object from each of the user's chat_sessions that has
        one, newest-first (by updated_at). `exclude_session_id` skips the current
        conversation (its context is already covered by prior_context). Returns [] on
        any failure — never raises."""
        try:
            q = self._db.query(ChatSession).filter(ChatSession.user_id == user_id)
            if exclude_session_id:
                q = q.filter(ChatSession.session_id != exclude_session_id)
            rows = q.order_by(ChatSession.updated_at.desc()).limit(int(limit)).all()
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for r in rows:
            snap = r.context_snapshot_json
            dist = snap.get("distillate") if isinstance(snap, dict) else None
            if isinstance(dist, dict):
                out.append(dist)
        return out

    # --- Conversation history (ChatGPT-style list / reopen / delete / rename) ---

    def list_sessions_for_user(
        self, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """A user's sessions newest-first (updated_at desc): ``{session_id, title,
        updated_at, created_at}``. Titles that are NULL (sessions created before auto-title
        existed) are resolved from each session's FIRST user message via ONE batched query
        (not N+1). Never raises — returns [] on any failure."""
        try:
            rows = (
                self._db.query(ChatSession)
                .filter(ChatSession.user_id == user_id)
                .order_by(ChatSession.updated_at.desc())
                .limit(int(limit))
                .offset(int(offset))
                .all()
            )
        except Exception:
            return []
        if not rows:
            return []
        # Resolve null titles from the first user message per session (single batched query).
        null_ids = [r.session_id for r in rows if not r.title]
        first_msg: dict[str, str] = {}
        if null_ids:
            try:
                res = self._db.execute(
                    sa_text(
                        "SELECT DISTINCT ON (session_id) session_id, text "
                        "FROM chat_messages "
                        "WHERE sender = 'user' AND session_id = ANY(:ids) "
                        "ORDER BY session_id, timestamp ASC"
                    ),
                    {"ids": null_ids},
                )
                for sid, txt in res:
                    derived = make_title(txt)
                    if derived:
                        first_msg[sid] = derived
            except Exception:
                pass  # best-effort — unresolved titles stay None
        return [
            {
                "session_id": r.session_id,
                "title": r.title or first_msg.get(r.session_id),
                "updated_at": _iso(r.updated_at),
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]

    def get_session_meta(self, session_id: str) -> dict[str, Any] | None:
        """``{session_id, title, updated_at, created_at}`` for the session-detail header.
        A NULL title is resolved from the first user message (consistent with the list
        view). None when the session does not exist."""
        row = self._db.get(ChatSession, session_id)
        if row is None:
            return None
        title = row.title
        if not title:
            try:
                r0 = self._db.execute(
                    sa_text(
                        "SELECT text FROM chat_messages WHERE session_id = :s AND sender = 'user' "
                        "ORDER BY timestamp ASC LIMIT 1"
                    ),
                    {"s": session_id},
                ).first()
                if r0:
                    title = make_title(r0[0])
            except Exception:
                pass
        return {
            "session_id": row.session_id,
            "title": title,
            "updated_at": _iso(row.updated_at),
            "created_at": _iso(row.created_at),
        }

    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a session OWNED BY user_id — chat_messages cascade via FK ON DELETE
        CASCADE. Ownership-guarded: returns False when absent or not owned, so a caller
        cannot delete another user's session by guessing an unguessable id. Commits."""
        row = self._db.get(ChatSession, session_id)
        if row is None or row.user_id != user_id:
            return False
        self._db.delete(row)
        self._db.commit()
        return True

    def rename_session(
        self, session_id: str, user_id: str, title: str
    ) -> dict[str, Any] | None:
        """Set the title of a session OWNED BY user_id (ownership-guarded). Caller strips +
        rejects empty titles (→ 400). Returns updated meta, or None when absent/not owned.
        Commits."""
        row = self._db.get(ChatSession, session_id)
        if row is None or row.user_id != user_id:
            return None
        row.title = title
        self._db.commit()
        # expire_on_commit (default True) → reading row.updated_at re-fetches the committed
        # value (including any server onupdate for updated_at).
        return {
            "session_id": row.session_id,
            "title": row.title,
            "updated_at": _iso(row.updated_at),
        }
