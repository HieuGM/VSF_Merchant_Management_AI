"""Customer memory wire-up integration tests (phase-05 wiring validation).

Asserts WIRING, not free-text answer equality (R1: deterministic + flake-free):
- FK prereq (B1): a fresh session_id with NO seed chat_sessions row still persists
  chat_messages (get-or-create anonymous parent) and reads back chronologically.
- prior_context (phase-02): empty on turn-1; non-empty + carries prior merchant names +
  the exclude rule when history exists.
- TTL (B2): a turn older than ttl_hours is excluded from get_recent_turns.
- weather short-circuit (B3): weather_override={"is_rain":True} deterministically merges a
  rain delta via propose_deltas AND yields a non-empty weather_hint.
- exclude_merchant_ids (B4): MerchantSearchService drops excluded ids BEFORE ranking.
- confirm/reject/idempotency (phase-04): confirm applies + audits; repeat unchanged;
  reject audits only; field-not-in-whitelist -> 400; scalar-on-list -> 400.

The confirm path imports `preference_confirm_service` / `ConfirmDeltaRequest` LAZILY so the
memory/weather/exclude tests still run even before the phase-04 service exists. NOTE:
``tests/conftest.py`` imports ``app.main`` which imports ``routes.user_routes`` which imports
``ConfirmDeltaRequest`` — until the data layer delivers that model + service, the whole
backend suite aborts at conftest collection. Run this file in isolation with
``pytest --noconftest`` to see the wiring results below the blocked collection."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.pii import redact_pii
from database.connection import SessionLocal, engine
from database.models import ChatMessage, ChatSession, PreferenceEvent, UserProfile
from models.customer_tasks import MerchantCandidate, PreferenceTaskOutput, SearchTaskOutput
from repositories.chat_message_repository import ChatMessageRepository
from repositories.preference_event_repository import PreferenceEventRepository
from services.merchant_search_service import MerchantSearchService
from repositories.merchant_repository import MerchantRepository


def _require_db() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


def _new_sid() -> str:
    return "sess_test_" + uuid.uuid4().hex


def _new_uid() -> str:
    return "user_test_" + uuid.uuid4().hex


def _cleanup_session(sid: str) -> None:
    db = SessionLocal()
    try:
        db.query(ChatMessage).filter(ChatMessage.session_id == sid).delete()
        db.query(ChatSession).filter(ChatSession.session_id == sid).delete()
        db.commit()
    finally:
        db.close()


def _cleanup_user(uid: str) -> None:
    db = SessionLocal()
    try:
        db.query(PreferenceEvent).filter(PreferenceEvent.user_id == uid).delete()
        db.query(UserProfile).filter(UserProfile.user_id == uid).delete()
        db.commit()
    finally:
        db.close()


def _profile_snapshot(uid: str):
    """Read-only profile snapshot (repo is read-only except apply_delta)."""
    from repositories.user_profile_repository import UserProfileRepository
    db = SessionLocal()
    try:
        return UserProfileRepository(db).get_by_id(uid)
    finally:
        db.close()


def _assert_apply_delta_exists():
    """Existence guard used OUTSIDE ``pytest.raises`` so a missing apply_delta FAILS the
    test instead of being silently caught as "raised Exception" (false pass)."""
    from repositories.user_profile_repository import UserProfileRepository
    assert hasattr(UserProfileRepository, "apply_delta"), (
        "contract: UserProfileRepository.apply_delta must exist (phase-04 B5/B6)")


class _MockCrew:
    """CrewAI-shaped stand-in (no LLM/network) — see test_customer_flow_crew.py."""

    def __init__(self, answer: str, candidates: list[MerchantCandidate]) -> None:
        self._answer = answer
        self._candidates = candidates

    def kickoff(self, inputs=None):
        search = SearchTaskOutput(candidates=self._candidates, count=len(self._candidates))
        preference = PreferenceTaskOutput(suggestions=[], reasoning="không đủ tín hiệu")
        return SimpleNamespace(
            raw="ok",
            tasks_output=[
                SimpleNamespace(pydantic=search),
                SimpleNamespace(pydantic=preference),
                SimpleNamespace(raw=self._answer),
            ],
        )


# --------------------------------------------------------------------------- #
# B1: FK prerequisite — get-or-create anonymous ChatSession, persist, read back.
# --------------------------------------------------------------------------- #
def test_fk_prereq_repo_creates_anonymous_parent_then_persists():
    _require_db()
    sid = _new_sid()
    try:
        db = SessionLocal()
        try:
            # NO seed chat_sessions row — append_turn must get-or-create the parent (B1).
            ChatMessageRepository(db).append_turn(sid, "user", "tìm phở")
            ChatMessageRepository(db).append_turn(sid, "agent", "gợi ý Phở Lệ", trace_id="t1")
            parent = db.get(ChatSession, sid)
            msgs = db.query(ChatMessage).filter(ChatMessage.session_id == sid).all()
        finally:
            db.close()
        assert parent is not None, "B1: parent chat_sessions row must be auto-created"
        assert parent.user_id is None, "anonymous-safe: user_id=None when no UserProfile"
        assert len(msgs) == 2
        turns = ChatMessageRepository(SessionLocal()).get_recent_turns(sid, limit=10)
        # Chronological: user before agent.
        assert [t["sender"] for t in turns] == ["user", "agent"]
        assert turns[0]["text"] == "tìm phở"
    finally:
        _cleanup_session(sid)


def test_fk_prereq_flow_persists_across_two_calls():
    _require_db()
    from flows.customer_flow import customer_flow

    sid = _new_sid()
    try:
        # Two flow calls on a fresh session_id (NO seed parent). Inject mock crews so no
        # LLM/network runs. Different queries keep the turns distinguishable on read-back.
        customer_flow.search_restaurants(
            query="tìm phở gần đây", session_id=sid, crew=_MockCrew(
                "Quán Phở Lệ hợp lý.", [MerchantCandidate(merchant_id="m_t1", name="Phở Lệ", match_score=0.9)]))
        customer_flow.search_restaurants(
            query="quán rẻ hơn nữa", session_id=sid, crew=_MockCrew(
                "Quán Phở Rẻ.", [MerchantCandidate(merchant_id="m_t2", name="Phở Rẻ", match_score=0.8)]))

        db = SessionLocal()
        try:
            parent = db.get(ChatSession, sid)
            rows = db.query(ChatMessage).filter(ChatMessage.session_id == sid).all()
        finally:
            db.close()
        assert parent is not None, "B1: flow path must also get-or-create the parent"
        assert len(rows) >= 2, "chat_messages rows must appear after flow calls"

        turns = ChatMessageRepository(SessionLocal()).get_recent_turns(sid, limit=20)
        # Chronological order invariant (ts non-decreasing).
        assert turns, "get_recent_turns must return the persisted turns"
        assert [t["ts"] for t in turns] == sorted(t["ts"] for t in turns), "not chronological"
        # First query appears before second query in the timeline.
        texts = [t["text"] for t in turns]
        assert texts.index("tìm phở gần đây") < texts.index("quán rẻ hơn nữa")
    finally:
        _cleanup_session(sid)


def test_append_turn_none_session_is_noop():
    _require_db()
    # session_id None MUST no-op and never raise (phase-01 F3).
    db = SessionLocal()
    try:
        ChatMessageRepository(db).append_turn(None, "user", "no session")
        db.commit()
    finally:
        db.close()


def test_append_turn_redacts_pii_before_write():
    _require_db()
    sid = _new_sid()
    try:
        db = SessionLocal()
        try:
            ChatMessageRepository(db).append_turn(
                sid, "user", "gọi 0912345678 hoặc email e@x.com nhé")
            row = db.query(ChatMessage).filter(ChatMessage.session_id == sid).one()
        finally:
            db.close()
        assert "0912345678" not in row.text
        assert "e@x.com" not in row.text
        assert "[PHONE]" in row.text and "[EMAIL]" in row.text
    finally:
        _cleanup_session(sid)


# --------------------------------------------------------------------------- #
# B2: TTL filter — DB-server-time cutoff excludes stale turns.
# --------------------------------------------------------------------------- #
def test_get_recent_turns_ttl_excludes_stale():
    _require_db()
    sid = _new_sid()
    db = SessionLocal()
    try:
        ChatMessageRepository(db).append_turn(sid, "user", "mới")
        # Backdate one row to 48h ago — beyond the default 24h TTL.
        db.query(ChatMessage).filter(ChatMessage.session_id == sid).update(
            {ChatMessage.timestamp: text("now() - interval '48 hours'")}, synchronize_session=False
        )
        db.commit()
        turns = ChatMessageRepository(db).get_recent_turns(sid, limit=10, ttl_hours=24)
        assert turns == [], "stale turn (>ttl_hours) must be excluded (B2)"
        # A large TTL still returns it — proves the cutoff is the filter, not absence.
        turns_old = ChatMessageRepository(db).get_recent_turns(sid, limit=10, ttl_hours=72)
        assert len(turns_old) == 1 and turns_old[0]["text"] == "mới"
    finally:
        db.close()
        _cleanup_session(sid)


# --------------------------------------------------------------------------- #
# phase-02: prior_context (anaphora block) + B4 exclude forwarding.
# --------------------------------------------------------------------------- #
def test_prior_context_empty_on_first_turn():
    from flows.customer_flow import _build_inputs, _format_prior_context

    assert _format_prior_context([]) == ""
    assert _format_prior_context(None) == ""
    inputs = _build_inputs(
        query="phở", cuisine="", city="", budget="", lat=None, lng=None, radius_km=None,
        user_id="u", session_id="s", prior_turns=[], weather_override=None)
    assert inputs["prior_context"] == "", "turn-1 must be literally unchanged (F4)"


def test_prior_context_nonempty_and_carries_merchant_names():
    from flows.customer_flow import _build_inputs

    prior = [
        {"sender": "user", "text": "tím phở", "payload": {"query": "tím phở"}, "ts": "t0"},
        {"sender": "agent", "text": "ok", "payload": {
            "result_merchant_ids": ["m_1"],
            "results": [{"merchant_id": "m_1", "name": "Phở Lệ", "cuisine": "phở"}],
        }, "ts": "t1"},
    ]
    inputs = _build_inputs(
        query="quán đầu tiên", cuisine="", city="", budget="", lat=None, lng=None,
        radius_km=None, user_id="u", session_id="s", prior_turns=prior, weather_override=None)
    ctx = inputs["prior_context"]
    assert ctx, "prior_context must be non-empty when history exists"
    assert "Phở Lệ" in ctx and "m_1" in ctx, "prior merchant names + ids must be carried"
    # B4: exclude rule + ids forwarded into the block (consumed by merchant_search).
    assert "exclude_merchant_ids" in ctx and "m_1" in ctx


def test_prior_context_exclude_ids_collected_from_multiple_turns():
    from flows.customer_flow import _collect_exclude_ids

    turns = [
        {"payload": {"result_merchant_ids": ["m_a", "m_b"]}},
        {"payload": {"result_merchant_ids": ["m_b", "m_c"]}},  # m_b deduped
        {"payload": {}},
    ]
    assert _collect_exclude_ids(turns) == ["m_a", "m_b", "m_c"]


# --------------------------------------------------------------------------- #
# B3: weather server-side short-circuit — deterministic rain delta + hint.
# --------------------------------------------------------------------------- #
def test_weather_override_merges_rain_delta_and_hint():
    from flows.customer_flow import _format_weather_hint, _merge_weather_suggestions

    merged = _merge_weather_suggestions(
        [], {"is_rain": True}, {"cuisine": "phở", "budget": None, "city": None}, None)
    field_ops = {(s["field"], s["operation"]) for s in merged}
    assert ("distance_preference_km", "set") in field_ops, (
        "B3: rain must deterministically propose a nearby distance delta")
    rain_delta = next(s for s in merged if s["field"] == "distance_preference_km")
    assert float(rain_delta["value"]) <= 3.0
    # weather_hint non-empty so the preference prompt can use the override.
    assert _format_weather_hint({"is_rain": True}) != ""
    # Regression: no override -> no rain delta merged, empty hint.
    assert _merge_weather_suggestions([], None, {}, None) == []
    assert _format_weather_hint(None) == ""


# --------------------------------------------------------------------------- #
# B4: exclude_merchant_ids is a subtractive pre-ranking tool/service arg (TC-30).
# --------------------------------------------------------------------------- #
def test_exclude_merchant_ids_drops_before_ranking():
    _require_db()
    db = SessionLocal()
    try:
        svc = MerchantSearchService(MerchantRepository(db))
        baseline = svc.search(query="phở", limit=10)
        if not baseline:
            pytest.skip("no merchants in test DB to exercise exclude filter")
        keep_id = baseline[0].merchant.merchant_id
        drop_id = baseline[-1].merchant.merchant_id
        excluded = svc.search(query="phở", limit=10, exclude_merchant_ids=[drop_id])
        ids = {r.merchant.merchant_id for r in excluded}
        assert drop_id not in ids, "excluded id must not survive the pre-ranking filter"
        assert keep_id in ids or drop_id == keep_id, "non-excluded results preserved"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# phase-04: confirm / reject / idempotency (imports the service LAZILY — the data
# layer must deliver preference_confirm_service + apply_delta + ConfirmDeltaRequest).
# --------------------------------------------------------------------------- #
def _confirm_service():
    from services.preference_confirm_service import preference_confirm_service
    return preference_confirm_service


def _confirm_body(**kw):
    from models.agent import ConfirmDeltaRequest
    return ConfirmDeltaRequest(**kw)


def _seed_user(uid: str) -> None:
    db = SessionLocal()
    try:
        if db.get(UserProfile, uid) is None:
            db.add(UserProfile(
                user_id=uid, liked_cuisines=[], disliked_cuisines=[], spice_tolerance="mild",
                dietary=[], budget_level="standard", distance_preference_km=5.0, context_memory={}))
            db.commit()
    finally:
        db.close()


def test_confirm_applies_delta_and_audits_event():
    _require_db()
    svc = _confirm_service()  # FAILS until preference_confirm_service exists (contract).
    uid = _new_uid()
    delta_id = "delta_" + uuid.uuid4().hex
    try:
        _seed_user(uid)
        profile = svc.confirm(uid, delta_id, _confirm_body(
            user_id=uid, field="liked_cuisines", operation="add", value="phở"))
        assert "phở" in profile.liked_cuisines
        db = SessionLocal()
        try:
            ev = db.query(PreferenceEvent).filter(
                PreferenceEvent.user_id == uid, PreferenceEvent.status == "confirmed").all()
        finally:
            db.close()
        assert ev, "confirm must append a preference_events(confirmed) row"
        assert any(delta_id in (e.evidence_refs_json or []) for e in ev)
    finally:
        _cleanup_user(uid)


def test_confirm_idempotent_on_repeat_delta_id():
    _require_db()
    svc = _confirm_service()
    uid = _new_uid()
    delta_id = "delta_" + uuid.uuid4().hex
    try:
        _seed_user(uid)
        first = svc.confirm(uid, delta_id, _confirm_body(
            user_id=uid, field="liked_cuisines", operation="add", value="phở"))
        second = svc.confirm(uid, delta_id, _confirm_body(
            user_id=uid, field="liked_cuisines", operation="add", value="phở"))
        assert first.liked_cuisines == second.liked_cuisines, "repeat must not double-apply"
        db = SessionLocal()
        try:
            n = db.query(PreferenceEvent).filter(
                PreferenceEvent.user_id == uid, PreferenceEvent.status == "confirmed").count()
        finally:
            db.close()
        assert n == 1, "idempotent: exactly one confirmed event per delta_id"
    finally:
        _cleanup_user(uid)


def test_reject_audits_event_only_no_profile_mutation():
    _require_db()
    svc = _confirm_service()
    uid = _new_uid()
    delta_id = "delta_" + uuid.uuid4().hex
    try:
        _seed_user(uid)
        before = list(_profile_snapshot(uid).liked_cuisines)
        svc.reject(uid, delta_id, _confirm_body(
            user_id=uid, field="liked_cuisines", operation="add", value="sushi"))
        after = _profile_snapshot(uid)
        assert after.liked_cuisines == before, "reject must NOT mutate user_profiles"
        db = SessionLocal()
        try:
            n = db.query(PreferenceEvent).filter(
                PreferenceEvent.user_id == uid, PreferenceEvent.status == "rejected").count()
        finally:
            db.close()
        assert n == 1, "reject must append exactly one preference_events(rejected) row"
    finally:
        _cleanup_user(uid)


def test_confirm_field_not_in_whitelist_rejected_400():
    _require_db()
    _assert_apply_delta_exists()  # outside raises: missing method => FAIL, not false-pass
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            # Whitelist bounds WHAT can be mutated — user_id/PK must be unwritable (B5/route 400).
            with pytest.raises(Exception):
                repo.apply_delta("user_id", "set", "attacker")
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


def test_confirm_scalar_on_list_field_rejected_400():
    _require_db()
    _assert_apply_delta_exists()
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            # apply_delta must reject a scalar value on a list[str] field (B5 type guard).
            with pytest.raises(Exception):
                repo.apply_delta("dietary", "set", "chay-string-not-list")
        finally:
            db.close()
    finally:
        _cleanup_user(uid)
