"""Unit tests for conversation-history repo methods (ChatGPT-style list/reopen/delete/rename).

`make_title` is PURE (no DB) — always runs. The repo-method tests hit the REAL Postgres:
the JSONB columns + `DISTINCT ON` / `ANY(:ids)` SQL are Postgres-specific so SQLite cannot
stand in, and they verify the actual ownership-guard / cascade / null-title-resolution SQL.
They SKIP when Postgres is unreachable (mirrors the live E2E scripts — not a Docker-free test).

Covers: make_title edge cases; list_sessions_for_user (null-title resolution + explicit-title
preservation); list_turns (no-TTL + results mapping); append_turn auto-title; delete_session +
rename_session ownership guards."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text as sa_text

from database.connection import SessionLocal
from repositories.chat_message_repository import ChatMessageRepository, make_title
from repositories.session_repository import SessionRepository


def _db_up() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(sa_text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return False


needs_db = pytest.mark.skipif(not _db_up(), reason="Postgres unavailable — repo tests need the real DB")


# --- make_title (pure, always runs) ---

def testmake_title_none_and_empty():
    assert make_title(None) is None
    assert make_title("") is None
    assert make_title("   ") is None


def testmake_title_takes_first_six_words():
    # 7 words → first 6 kept, 7th dropped.
    assert make_title("hôm nay mình muốn ăn bún bò") == "hôm nay mình muốn ăn bún"


def testmake_title_caps_long_with_ellipsis():
    # A single token longer than 40 chars → truncated to 37 chars + "…".
    t = make_title("x" * 50)
    assert t is not None and t.endswith("…") and len(t) <= 40


def testmake_title_collapses_whitespace_and_keeps_vietnamese():
    assert make_title("  múôn   ăn\nphở   ") == "múôn ăn phở"


# --- helpers for the DB-backed tests ---

def _seed_user(db, *user_ids):
    """Insert minimal user_profiles rows (PK only — other columns are nullable) so the
    chat_sessions.user_id FK is satisfied."""
    for uid in user_ids:
        db.execute(
            sa_text("INSERT INTO user_profiles (user_id) VALUES (:u) ON CONFLICT (user_id) DO NOTHING"),
            {"u": uid},
        )


def _seed_session(db, session_id, user_id, title=None, user_text="tôi muốn ăn phở bò"):
    """Insert a session row (no title → null-title path) + one user message directly.
    Seeds the parent user_profiles row so the user_id FK holds."""
    _seed_user(db, user_id)
    db.execute(
        sa_text(
            "INSERT INTO chat_sessions (session_id, user_id, title) VALUES (:s, :u, :t) "
            "ON CONFLICT (session_id) DO NOTHING"
        ),
        {"s": session_id, "u": user_id, "t": title},
    )
    db.execute(
        sa_text(
            "INSERT INTO chat_messages (message_id, session_id, sender, text) "
            "VALUES (:m, :s, 'user', :txt)"
        ),
        {"m": f"msg_{session_id}", "s": session_id, "txt": user_text},
    )
    db.commit()


def _wipe(db, *session_ids, users=()):
    """Clean up test rows (messages → sessions → profiles). Rolls back first so the cleanup
    DELETEs run even if a prior statement aborted the transaction mid-test."""
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass
    for sid in session_ids:
        db.execute(sa_text("DELETE FROM chat_messages WHERE session_id = :s"), {"s": sid})
        db.execute(sa_text("DELETE FROM chat_sessions WHERE session_id = :s"), {"s": sid})
    for uid in users:
        db.execute(sa_text("DELETE FROM user_profiles WHERE user_id = :u"), {"u": uid})
    db.commit()


# --- repo methods (real Postgres) ---

@needs_db
def test_list_sessions_resolves_null_title_from_first_user_message():
    uid, sid = f"u_{uuid.uuid4().hex[:8]}", f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, sid)
        _seed_session(db, sid, uid, title=None, user_text="mình thèm bún chả hà nội")
        rows = SessionRepository(db).list_sessions_for_user(uid)
        assert len(rows) == 1
        assert rows[0]["session_id"] == sid
        assert rows[0]["title"] == "mình thèm bún chả hà nội"  # derived from first user message (6 words)
    finally:
        _wipe(db, sid, users=(uid,))
        db.close()


@needs_db
def test_list_sessions_keeps_explicit_title():
    uid = f"u_{uuid.uuid4().hex[:8]}"
    s1, s2 = f"s_{uuid.uuid4().hex[:12]}", f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, s1, s2)
        _seed_session(db, s1, uid, title="Bún đậu mắm tôm")
        _seed_session(db, s2, uid, title="Lẩu Thái cay")
        rows = SessionRepository(db).list_sessions_for_user(uid)
        titles = {r["title"] for r in rows if r["session_id"] in (s1, s2)}
        # Explicit titles are preserved (NOT overwritten by derivation).
        assert titles == {"Bún đậu mắm tôm", "Lẩu Thái cay"}
    finally:
        _wipe(db, s1, s2, users=(uid,))
        db.close()


@needs_db
def test_list_turns_no_ttl_and_maps_results():
    uid, sid = f"u_{uuid.uuid4().hex[:8]}", f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, sid)
        _seed_user(db, uid)
        db.commit()
        repo = ChatMessageRepository(db)
        repo.append_turn(sid, "user", "gợi ý phở giúp mình", user_id=uid)
        repo.append_turn(
            sid, "agent", "Mình gợi ý Phở Thìn.",
            payload={"result_merchant_ids": ["m1"],
                     "results": [{"merchant_id": "m1", "name": "Phở Thìn", "cuisine": "Việt"}]},
            user_id=uid,
        )
        turns = ChatMessageRepository(db).list_turns(sid)
        assert [t["sender"] for t in turns] == ["user", "agent"]
        assert turns[1]["results"] == [{"merchant_id": "m1", "name": "Phở Thìn", "cuisine": "Việt"}]
        assert turns[0]["results"] == []  # user turns carry no results
    finally:
        _wipe(db, sid, users=(uid,))
        db.close()


@needs_db
def test_append_turn_auto_titles_from_first_user_message():
    uid, sid = f"u_{uuid.uuid4().hex[:8]}", f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, sid)
        _seed_user(db, uid)
        db.commit()
        ChatMessageRepository(db).append_turn(sid, "user", "cho mình hỏi quán lẩu hải sản", user_id=uid)
        meta = SessionRepository(db).get_session_meta(sid)
        assert meta is not None
        assert meta["title"] == "cho mình hỏi quán lẩu hải"  # first 6 words
    finally:
        _wipe(db, sid, users=(uid,))
        db.close()


@needs_db
def test_delete_session_ownership_guard_and_cascade():
    uid, other = f"u_{uuid.uuid4().hex[:8]}", f"u_{uuid.uuid4().hex[:8]}"
    sid = f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, sid)
        _seed_session(db, sid, uid, title="mine")
        # Wrong owner cannot delete (ownership guard) — session survives.
        assert SessionRepository(db).delete_session(sid, other) is False
        assert SessionRepository(db).get_session_meta(sid) is not None
        # Correct owner deletes; messages cascade away.
        assert SessionRepository(db).delete_session(sid, uid) is True
        assert SessionRepository(db).get_session_meta(sid) is None
        assert ChatMessageRepository(db).list_turns(sid) == []
    finally:
        _wipe(db, sid, users=(uid, other))
        db.close()


@needs_db
def test_rename_session_ownership_guard():
    uid, other = f"u_{uuid.uuid4().hex[:8]}", f"u_{uuid.uuid4().hex[:8]}"
    sid = f"s_{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        _wipe(db, sid)
        _seed_session(db, sid, uid, title="old")
        # Wrong owner cannot rename.
        assert SessionRepository(db).rename_session(sid, other, "hacked") is None
        # Correct owner renames.
        updated = SessionRepository(db).rename_session(sid, uid, "Bún bò Huế")
        assert updated is not None and updated["title"] == "Bún bò Huế"
    finally:
        _wipe(db, sid, users=(uid, other))
        db.close()
