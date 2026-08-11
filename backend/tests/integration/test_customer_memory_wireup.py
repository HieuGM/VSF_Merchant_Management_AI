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
def test_prior_context_no_prior_note_on_first_turn():
    from flows.customer_flow import _NO_PRIOR_NOTE, _build_inputs, _format_prior_context

    # Empty prior → explicit NO-PRIOR note (not "") so the model can't confabulate a prior turn
    # ("lần trước mình gợi ý…" on a first-turn query). Formerly "" (F4); changed to kill the
    # fabricated-prior class — see _NO_PRIOR_NOTE in customer_flow.py.
    assert _format_prior_context([]) == _NO_PRIOR_NOTE
    assert _format_prior_context(None) == _NO_PRIOR_NOTE
    inputs = _build_inputs(
        query="phở", cuisine="", city="", budget="", lat=None, lng=None, radius_km=None,
        user_id="u", session_id="s", prior_turns=[], weather_override=None)
    assert inputs["prior_context"] == _NO_PRIOR_NOTE


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


# --------------------------------------------------------------------------- #
# phase-03: context_memory long-term distillation (extract -> persist -> read back).
# --------------------------------------------------------------------------- #
def test_context_memory_distills_allergy_and_reads_back():
    _require_db()
    from services.context_memory_service import maybe_persist

    uid = _new_uid()
    try:
        # maybe_persist takes RAW user text (exactly as _persist_user_turn calls it in the flow).
        maybe_persist(uid, "Mình dị ứng đậu phộng đấy. Hôm nay muốn ăn phở.")
        db = SessionLocal()
        try:
            from repositories.user_profile_repository import UserProfileRepository

            mem = UserProfileRepository(db).get_by_id(uid).context_memory
        finally:
            db.close()
        # allergy sentence distilled into a note; read back via the get_user_profile path.
        notes = mem.get("notes") or []
        assert any("dị ứng" in n.lower() for n in notes)
    finally:
        _cleanup_user(uid)


def test_context_memory_dedupe_on_repeat():
    _require_db()
    from services.context_memory_service import maybe_persist

    uid = _new_uid()
    try:
        maybe_persist(uid, "Dị ứng đậu phộng")
        maybe_persist(uid, "dị ứng đậu phộng")  # same fact, different case -> deduped
        db = SessionLocal()
        try:
            from repositories.user_profile_repository import UserProfileRepository

            mem = UserProfileRepository(db).get_by_id(uid).context_memory
        finally:
            db.close()
        notes = mem.get("notes") or []
        assert sum(1 for n in notes if "dị ứng" in n.lower()) == 1, "dedupe: no duplicate note"
    finally:
        _cleanup_user(uid)


# --------------------------------------------------------------------------- #
# phase-01 carryover (L3): apply_fields repo-level (the PATCH path) — mirrors the
# apply_delta tests above + adds the atomic validate-all-before-write guarantee.
# --------------------------------------------------------------------------- #
def _assert_apply_fields_exists():
    from repositories.user_profile_repository import UserProfileRepository
    assert hasattr(UserProfileRepository, "apply_fields"), (
        "contract: UserProfileRepository.apply_fields must exist (phase-01 PATCH path)")


def test_apply_fields_multi_field_patch():
    _require_db()
    _assert_apply_fields_exists()
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            profile = repo.apply_fields(
                {"liked_cuisines": ["Việt", "Nhật"], "budget_level": "student"},
                user_id=uid,
            )
            assert profile.liked_cuisines == ["Việt", "Nhật"]
            assert profile.budget_level == "student"
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


def test_apply_fields_bad_enum_rejected_400():
    _require_db()
    _assert_apply_fields_exists()
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            with pytest.raises(Exception):
                repo.apply_fields({"budget_level": "not-a-real-budget"}, user_id=uid)
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


def test_apply_fields_scalar_on_list_rejected_400():
    _require_db()
    _assert_apply_fields_exists()
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            # 'set' on a list[str] field requires a list — a scalar must be rejected (B5).
            with pytest.raises(Exception):
                repo.apply_fields({"liked_cuisines": "Việt-scalar-not-list"}, user_id=uid)
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


def test_apply_fields_upsert_first_write():
    _require_db()
    _assert_apply_fields_exists()
    from database.models import UserProfile
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    # NOTE: deliberately NO _seed_user — apply_fields must upsert a minimal row (R3).
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            assert db.get(UserProfile, uid) is None, "precondition: user has no row"
            profile = repo.apply_fields({"dietary": ["chay"]}, user_id=uid)
            assert profile.dietary == ["chay"]
            assert db.get(UserProfile, uid) is not None, "upsert created the row"
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


def test_apply_fields_atomic_bad_field_aborts():
    """A bad field in a multi-field patch must abort the WHOLE patch — no partial mutation
    (validate-all-before-write). liked_cuisines is valid but budget_level is not → the patch
    raises AND liked_cuisines is NOT applied."""
    _require_db()
    _assert_apply_fields_exists()
    from repositories.user_profile_repository import UserProfileRepository
    uid = _new_uid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            with pytest.raises(Exception):
                repo.apply_fields(
                    {"liked_cuisines": ["Việt"], "budget_level": "bad-budget"},
                    user_id=uid,
                )
            after = repo.get_by_id(uid)
            assert "Việt" not in (after.liked_cuisines or []), (
                "atomic: a bad field must abort the whole patch (no partial write)"
            )
        finally:
            db.close()
    finally:
        _cleanup_user(uid)


# --------------------------------------------------------------------------- #
# memory-system P2a: user_id binding + per-conversation distillate (RMW).
# --------------------------------------------------------------------------- #
def test_session_binds_user_id_on_create():
    _require_db()
    uid = _new_uid()
    sid = _new_sid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            ChatMessageRepository(db).append_turn(sid, "user", "tìm phở", user_id=uid)
            parent = db.get(ChatSession, sid)
        finally:
            db.close()
        assert parent is not None, "parent session auto-created"
        assert parent.user_id == uid, "P2: session must bind the caller's user_id on create"
    finally:
        _cleanup_session(sid)
        _cleanup_user(uid)


def test_session_backfills_user_id_when_first_seen_anon():
    _require_db()
    uid = _new_uid()
    sid = _new_sid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            ChatMessageRepository(db).append_turn(sid, "user", "tìm phở")  # anon first
            assert db.get(ChatSession, sid).user_id is None
            ChatMessageRepository(db).append_turn(sid, "agent", "gợi ý", user_id=uid)
            db.commit()
            assert db.get(ChatSession, sid).user_id == uid, (
                "P2: backfill user_id when an existing anon session later sees a user_id")
        finally:
            db.close()
    finally:
        _cleanup_session(sid)
        _cleanup_user(uid)


def test_distillate_accumulates_and_preserves_sibling_keys():
    _require_db()
    from services.conversation_distillate_service import get_distillate, update_distillate

    uid = _new_uid()
    sid = _new_sid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            ChatMessageRepository(db).append_turn(sid, "user", "tìm phở", user_id=uid)
            # Simulate a pre-existing sibling key (candidates is read by session_repository).
            row = db.get(ChatSession, sid)
            row.context_snapshot_json = {"candidates": [{"x": 1}]}
            db.commit()
        finally:
            db.close()

        update_distillate(sid, "tìm phở cầu giấy",
                          [{"merchant_id": "m1", "cuisine": "Món Việt"}])
        update_distillate(sid, "rẻ hơn nữa",
                          [{"merchant_id": "m2", "cuisine": "Món Việt"}])

        dist = get_distillate(sid)
        assert dist is not None
        assert dist["intent"] == "tìm phở cầu giấy"   # frozen at first turn
        assert dist["last_query"] == "rẻ hơn nữa"
        assert dist["shown"] == ["m1", "m2"]           # accumulated, deduped
        assert dist["cuisines"] == ["Món Việt"]
        assert dist["turn_count"] == 2

        db = SessionLocal()
        try:
            snap = db.get(ChatSession, sid).context_snapshot_json or {}
        finally:
            db.close()
        assert snap.get("candidates") == [{"x": 1}], "RMW must preserve sibling keys"
        assert "distillate" in snap
    finally:
        _cleanup_session(sid)
        _cleanup_user(uid)


# --------------------------------------------------------------------------- #
# memory-system storage: lazy-on-write purge of stale chat_messages.
# --------------------------------------------------------------------------- #
def test_purge_deletes_stale_rows():
    _require_db()
    from services.chat_message_purge_service import purge_now

    sid = _new_sid()
    db = SessionLocal()
    try:
        repo = ChatMessageRepository(db)
        repo.append_turn(sid, "user", "cũ")
        repo.append_turn(sid, "agent", "gợi ý cũ")
        # Backdate both rows to 48h ago — beyond a 1-day retention window.
        db.query(ChatMessage).filter(ChatMessage.session_id == sid).update(
            {ChatMessage.timestamp: text("now() - interval '48 hours'")},
            synchronize_session=False,
        )
        db.commit()
        assert db.query(ChatMessage).filter(ChatMessage.session_id == sid).count() == 2

        deleted = purge_now(max_age_days=1)  # 1-day retention → the 48h rows are purged
        db.expire_all()
        assert deleted >= 2, "purge must delete the backdated rows"
        assert db.query(ChatMessage).filter(ChatMessage.session_id == sid).count() == 0
    finally:
        db.close()
        _cleanup_session(sid)


def test_purge_keeps_rows_within_retention():
    _require_db()
    from services.chat_message_purge_service import purge_now

    sid = _new_sid()
    db = SessionLocal()
    try:
        ChatMessageRepository(db).append_turn(sid, "user", "giữ")  # fresh (now)
        db.commit()
        purge_now(max_age_days=90)  # 90-day retention → a fresh row survives
        db.expire_all()
        assert db.query(ChatMessage).filter(ChatMessage.session_id == sid).count() == 1
    finally:
        db.close()
        _cleanup_session(sid)


# --------------------------------------------------------------------------- #
# memory-system P2b: list_recent_distillates exclude_session_id (code-review M4).
# --------------------------------------------------------------------------- #
def test_list_recent_distillates_excludes_current_session():
    _require_db()
    from repositories.session_repository import SessionRepository
    from services.conversation_distillate_service import update_distillate

    uid = _new_uid()
    sid1, sid2 = _new_sid(), _new_sid()
    _seed_user(uid)
    try:
        db = SessionLocal()
        try:
            for sid in (sid1, sid2):
                ChatMessageRepository(db).append_turn(sid, "user", "tìm phở", user_id=uid)
            db.commit()
        finally:
            db.close()
        update_distillate(sid1, "tìm phở", [{"merchant_id": "m1", "cuisine": "Món Việt"}])
        update_distillate(sid2, "tìm bún", [{"merchant_id": "m2", "cuisine": "Món Việt"}])

        db = SessionLocal()
        try:
            all_d = SessionRepository(db).list_recent_distillates(uid, limit=20)
            excl = SessionRepository(db).list_recent_distillates(
                uid, limit=20, exclude_session_id=sid1
            )
        finally:
            db.close()
        assert len(all_d) == 2, "both conversations have a distillate for this user"
        assert len(excl) == 1, "exclude_session_id drops the current conversation"
        intents_excl = {d.get("intent") for d in excl}
        assert "tìm phở" not in intents_excl   # sid1 (the excluded one) gone
        assert "tìm bún" in intents_excl        # sid2 kept
    finally:
        _cleanup_session(sid1)
        _cleanup_session(sid2)
        _cleanup_user(uid)
