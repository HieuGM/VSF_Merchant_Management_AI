"""Chat Session Service (Design §6.2, §8.1) — Session State & Message History Management.

Manages durable session state in PostgreSQL and hot copy in Redis.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ChatSession, ChatMessage
from core.cache import CacheKeys, TTL_SESSION_CONTEXT
from core.dependencies import get_cache


class ChatSessionService:
    """Service layer for chat sessions and message history."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._cache = get_cache()

    def get_or_create_session(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        title: str | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> ChatSession:
        """Get existing session or create a new session."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        stmt = select(ChatSession).where(ChatSession.session_id == sid)
        session_obj = self._db.execute(stmt).scalar_one_or_none()

        if session_obj:
            if context_snapshot:
                session_obj.context_snapshot_json = context_snapshot
                session_obj.updated_at = datetime.utcnow()
                self._db.commit()
            return session_obj

        session_obj = ChatSession(
            session_id=sid,
            user_id=user_id,
            title=title or f"Chat Session {sid}",
            context_snapshot_json=context_snapshot or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._db.add(session_obj)
        self._db.commit()
        self._db.refresh(session_obj)

        # Sync hot copy to Redis
        redis_key = CacheKeys.session_context(sid)
        self._cache.set(redis_key, context_snapshot or {}, ttl_seconds=TTL_SESSION_CONTEXT)

        return session_obj

    def append_message(
        self,
        session_id: str,
        sender: str,
        text: str,
        trace_id: str | None = None,
        structured_payload: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Append user or agent chat message to session history."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        msg = ChatMessage(
            message_id=msg_id,
            session_id=session_id,
            sender=sender,
            text=text,
            trace_id=trace_id,
            structured_payload_json=structured_payload or {},
            timestamp=datetime.utcnow(),
        )
        self._db.add(msg)

        # Update session last_trace_id and updated_at
        stmt = select(ChatSession).where(ChatSession.session_id == session_id)
        session_obj = self._db.execute(stmt).scalar_one_or_none()
        if session_obj:
            if trace_id:
                session_obj.last_trace_id = trace_id
            session_obj.updated_at = datetime.utcnow()

        self._db.commit()
        self._db.refresh(msg)
        return msg

    def get_recent_history(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent message history formatted for Agent context injection."""
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.timestamp.asc())
        )
        messages = list(self._db.execute(stmt).scalars().all())
        messages = messages[-limit:]

        return [
            {
                "message_id": m.message_id,
                "sender": m.sender,
                "text": m.text,
                "trace_id": m.trace_id,
                "timestamp": str(m.timestamp),
            }
            for m in messages
        ]

    def update_session_snapshot(
        self, session_id: str, snapshot: dict[str, Any], last_trace_id: str | None = None
    ) -> None:
        """Update durable snapshot in PG and hot copy in Redis."""
        stmt = select(ChatSession).where(ChatSession.session_id == session_id)
        session_obj = self._db.execute(stmt).scalar_one_or_none()

        if session_obj:
            session_obj.context_snapshot_json = snapshot
            if last_trace_id:
                session_obj.last_trace_id = last_trace_id
            session_obj.updated_at = datetime.utcnow()
            self._db.commit()

        redis_key = CacheKeys.session_context(session_id)
        self._cache.set(redis_key, snapshot, ttl_seconds=TTL_SESSION_CONTEXT)
