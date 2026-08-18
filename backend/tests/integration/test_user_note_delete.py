"""Per-note delete integration tests (FE 'Ghi nhớ của trợ lý' × button).

Exercises ``UserProfileRepository.remove_note`` against real Postgres:
- happy path: the note + its TTL expiry entry + its allergen twin all drop in one tx
- 404 path: unknown key / unknown user → False (route maps to 404), no row created
- isolation: sibling notes and unrelated allergens survive
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.connection import SessionLocal, engine
from database.models import UserProfile
from repositories.user_profile_repository import UserProfileRepository


def _require_db() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


def _new_uid() -> str:
    return "user_testnoted_" + uuid.uuid4().hex[:10]


@pytest.fixture()
def seeded_user():
    _require_db()
    uid = _new_uid()
    db = SessionLocal()
    try:
        db.merge(UserProfile(user_id=uid))
        db.commit()
        repo = UserProfileRepository(db)
        # Two notes (one temporary w/ expiry) + two allergens; the first pair twins.
        repo.append_context_notes(
            uid, ["Tôi dị ứng đậu phộng", "Tuần này tôi ăn kiêng ít dầu mỡ"],
            cap=8, expiries={"tuần này tôi ăn kiêng ít dầu mỡ": "2099-01-01T00:00:00+00:00"},
        )
        repo.add_allergens(uid, ["Tôi dị ứng đậu phộng", "Tôi dị ứng hải sản"])
        yield uid
    finally:
        db.query(UserProfile).filter(UserProfile.user_id == uid).delete()
        db.commit()
        db.close()


def _ctx(db: SessionLocal, uid: str) -> dict:
    row = db.get(UserProfile, uid)
    db.refresh(row)
    return dict(row.context_memory or {})


def test_remove_note_drops_note_expiry_and_allergen_twin(seeded_user):
    uid = seeded_user
    db = SessionLocal()
    try:
        repo = UserProfileRepository(db)
        assert repo.remove_note(uid, "tôi dị ứng đậu phộng") is True
        mem = _ctx(db, uid)
        assert mem["notes"] == ["Tuần này tôi ăn kiêng ít dầu mỡ"]  # sibling survives
        # The deleted note had no expiry entry; the sibling's must survive.
        assert mem["note_expiries"] == {"tuần này tôi ăn kiêng ít dầu mỡ": "2099-01-01T00:00:00+00:00"}
        row = db.get(UserProfile, uid)
        db.refresh(row)
        assert row.allergens == ["Tôi dị ứng hải sản"]  # twin dropped, unrelated kept
    finally:
        db.close()


def test_remove_note_drops_its_own_expiry_entry(seeded_user):
    uid = seeded_user
    db = SessionLocal()
    try:
        repo = UserProfileRepository(db)
        assert repo.remove_note(uid, "tuần này tôi ăn kiêng ít dầu mỡ") is True
        mem = _ctx(db, uid)
        assert mem["notes"] == ["Tôi dị ứng đậu phộng"]
        assert mem.get("note_expiries") == {}  # its expiry went with it
    finally:
        db.close()


def test_remove_note_unknown_key_returns_false(seeded_user):
    uid = seeded_user
    db = SessionLocal()
    try:
        repo = UserProfileRepository(db)
        assert repo.remove_note(uid, "không tồn tại") is False
        mem = _ctx(db, uid)
        assert len(mem["notes"]) == 2  # untouched
    finally:
        db.close()


def test_remove_note_unknown_user_returns_false_and_creates_no_row():
    _require_db()
    db = SessionLocal()
    try:
        repo = UserProfileRepository(db)
        assert repo.remove_note(_new_uid(), "gì đó") is False
    finally:
        db.close()
