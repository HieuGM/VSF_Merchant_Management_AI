"""Memory behaviour spec — translates memory.txt (A–G) into deterministic unit checks.

These encode the USER-FACING memory contract, not just the matcher:
  - Test 1 (Persistence): a bare 'Tôi ăn chay' must persist cross-session (durable note), so a
    later session auto-filters WITHOUT re-asking. Transient 'hôm nay ăn chay' must NOT persist.
  - Test 3 (Safety): a durable allergy survives a LONG conversation (past the 8-turn session
    window) — the durable note, not the session window, carries it.
  - Test 7 (Isolation): transient session context ('đi với gia đình') must NOT leak into the
    durable profile.
Scoring dims per the spec: Correctness / Precedence / Isolation."""
from __future__ import annotations

from types import SimpleNamespace as NS

from services.active_constraints_loader import build_active_constraints as build
from services.active_constraints_loader import active_constraints_block as render_block
from services.context_memory_service import extract_notes
from services.context_memory_service import _retracted_food_terms, _fold as fold_cms


def U(t): return {"sender": "user", "text": t}
def A(t): return {"sender": "agent", "text": t}
def prof(notes): return NS(dietary=[], disliked_cuisines=[], context_memory={"notes": notes})


# --- Test 1: Persistence — durable recall of a declared diet ---
def test_t1_bare_an_chay_persists_durable():
    # A bare vegetarian declaration (no 'từ giờ'/'trường') must still persist as a durable fact.
    assert extract_notes("Tôi ăn chay") != []


def test_t1_declared_chay_recalled_cross_session_without_reask():
    # Simulate a durable note persisted from a prior session; a FRESH session (no prior turns)
    # queries generically → the chay hard-filter is active (no re-ask needed).
    cs = build(prof(["Tôi ăn chay"]), [], "Tìm quán ăn trưa gần đây")
    assert any(c.scope == "chay" and c.persistence == "durable" for c in cs.hard)


def test_t1_transient_chay_not_persisted():
    # 'hôm nay ăn chay' is transient → must NOT be written as a durable note (Test 2 spirit:
    # real-time/transient context is not cached as a lasting preference).
    assert extract_notes("Hôm nay tôi ăn chay nhé") == []


# --- Test 3: Safety — allergy survives a long conversation ---
def test_t3_allergy_survives_past_session_window():
    # Durable seafood-allergy note + 50 interleaved turns (25 user/25 agent) → the allergy is
    # STILL enforced for a later 'gợi ý sushi'. The durable note carries it past the 8-turn window.
    turns = []
    for i in range(25):
        turns.append(U(f"cho mình xem quán số {i}"))   # unrelated filler
        turns.append(A(f"đây là quán số {i}"))
    cs = build(prof(["Tôi dị ứng hải sản"]), turns, "Gợi ý quán sushi ngon gần đây")
    assert any(c.scope == "seafood" and c.persistence == "durable" for c in cs.hard)


# --- Test 7: Isolation — transient context does not leak into the durable profile ---
def test_t7_transient_group_context_not_persisted():
    # 'đi ăn với gia đình, chỗ rộng' is transient session context → must NOT become a durable note.
    assert extract_notes("Tôi đang đi ăn với gia đình, cần chỗ rộng") == []


def test_t7_transient_context_does_not_create_hard_constraint():
    # And it must not materialize as any hard constraint in a later fresh session.
    cs = build(prof([]), [], "Tìm chỗ ăn trưa")
    assert cs.is_empty


# --- Generalize: non-catalog allergy surfaced to the explanation LLM as a health note ---
# A declared allergen whose scope is NOT in the catalog (peanut, garlic, organ-meat, …) cannot be
# hard-filtered (no dish-level allergen data). It must instead be surfaced to the explanation LLM
# via ActiveConstraints.health_notes so the LLM warns the user — generalizing without per-allergen
# catalog entries. (memory_test.json case 3.1: peanut allergy, indirect buffet query.)
def test_non_catalog_allergy_surfaced_as_health_note():
    # Peanut is not a catalog scope → no hard constraint, but the sentence is captured for the LLM.
    cs = build(prof(["Tôi dị ứng đậu phộng"]), [], "Gợi ý quán buffet ngon nhất")
    assert not any(c.scope in ("seafood", "chay") for c in cs.hard)
    assert any("đậu phộng" in n for n in cs.health_notes)


def test_health_note_rendered_in_constraints_block():
    # The block injected into the explanation prompt must carry the health warning (any allergen).
    cs = build(prof(["Tôi không ăn được nội tạng"]), [], "Gợi ý lẩu")
    block = render_block(cs)
    assert "nội tạng" in block
    assert "CẢNH BÁO SỨC KHOẺ" in block


def test_catalog_allergy_still_hard_filtered():
    # Seafood IS a catalog scope → enforced as a hard constraint (unchanged behavior).
    cs = build(prof(["Tôi dị ứng hải sản"]), [], "Gợi ý sushi")
    assert any(c.scope == "seafood" for c in cs.hard)


def test_mixed_catalog_and_noncatalog_allergy_surfaced():
    # H1: a note mixing a catalog allergen + a non-catalog one ("… hải sản và đậu phộng") must
    # still surface to the LLM so the non-catalog half (peanut) is warned — not silently dropped
    # just because the catalog handled the seafood half.
    cs = build(prof(["Tôi dị ứng hải sản và đậu phộng"]), [], "Gợi ý buffet")
    assert any(c.scope == "seafood" for c in cs.hard)  # seafood still hard-filtered
    assert any("đậu phộng" in n for n in cs.health_notes)  # peanut surfaced to LLM


def test_broke_diet_does_not_resurface_abandoned_diet_as_warning():
    # H2: when the user abandons a diet this turn ("tôi bỏ chay"), a durable note whose only
    # signal is that diet must NOT be re-surfaced as a health warning. (An allergy-only note is
    # still surfaced even under broke_diet.)
    prof_diet = NS(dietary=[], disliked_cuisines=[], context_memory={"notes": [
        "Bị đau dạ dày nên kiêng đồ chay nhiều dầu",
    ]})
    cs = build(prof_diet, prior_turns=[], query="Tôi bỏ chay rồi")
    assert not cs.health_notes  # the abandoned-diet note is not a health warning


def test_recovery_note_not_surfaced_as_health_warning():
    # A retraction ("đã hết dị ứng tôm") carries an allergy verb but must NOT become an active
    # warning (it retires the allergy — the stale-note case, handled elsewhere).
    cs = build(prof(["Đã hết dị ứng tôm rồi"]), [], "Gợi ý món")
    assert not cs.health_notes


# --- Stale-note fix (7.2/3.4): retracting an allergy removes it; retraction not saved ---
def test_retraction_sentence_not_extracted_as_note():
    # A withdrawal ("quên chuyện dị ứng tôm", "bác sĩ nói hết dị ứng") must never be persisted as a
    # new note — it would contradict the original and re-enforce the retracted allergy.
    assert extract_notes("Quên chuyện tôi dị ứng tôm đi, giờ ăn được bình thường rồi") == []
    assert extract_notes("Bác sĩ nói tôi hết dị ứng tôm rồi, giờ ăn được") == []


def test_retracted_food_terms_identifies_the_allergen():
    # The withdrawn allergen is parsed so maybe_persist can match + remove the prior note.
    assert "tom" in _retracted_food_terms(fold_cms("Quên chuyện tôi dị ứng tôm đi"))
    assert "dau phong" in _retracted_food_terms(fold_cms("Quên dị ứng đậu phộng đi"))


def test_loader_recovery_suppresses_retraction_in_current_message():
    # A retraction in the CURRENT query must not (re)impose the allergen (broadened _RECOVERY_RE),
    # nor surface it as a health warning.
    cs = build(prof([]), [], "Quên chuyện tôi dị ứng tôm đi, giờ mình muốn ăn tôm")
    assert not any(c.scope == "seafood" for c in cs.hard)
    assert not cs.health_notes


# --- TTL (6.3): a temporary constraint ("tuần này ăn kiêng") auto-expires, not permanent ---
from datetime import datetime, timezone, timedelta
from services.context_memory_service import _duration_days


def test_duration_detection_for_temporary_markers():
    assert _duration_days(fold_cms("Tuần này tôi ăn kiêng ít dầu mỡ")) == 7
    assert _duration_days(fold_cms("Tháng này ăn kiêng")) == 30
    assert _duration_days(fold_cms("Hôm nay ăn kiêng")) == 1
    # A permanent declaration has no duration marker.
    assert _duration_days(fold_cms("Tôi dị ứng đậu phộng")) is None


def _prof_with_expiry(notes, expiry_iso):
    return NS(dietary=[], disliked_cuisines=[],
              context_memory={"notes": notes, "note_expiries": {notes[0].lower(): expiry_iso}})


def test_expired_temporary_constraint_not_enforced():
    # A note whose expiry is in the past must NOT enforce (nor surface) — the temporary window closed.
    past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    cs = build(_prof_with_expiry(["Tôi dị ứng tôm"], past), [], "Gợi ý hải sản")
    assert not any(c.scope == "seafood" for c in cs.hard)
    assert not cs.health_notes


def test_valid_temporary_constraint_still_enforced():
    # A note whose expiry is in the future still enforces normally.
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    cs = build(_prof_with_expiry(["Tôi dị ứng tôm"], future), [], "Gợi ý hải sản")
    assert any(c.scope == "seafood" for c in cs.hard)


# --- Phase 2 (6.1): no-cap `allergens` store survives FIFO eviction ---
def test_allergens_surfaced_when_note_evicted():
    # The peanut allergy was FIFO-evicted from notes, but lives in the no-cap `allergens` store →
    # still surfaced to the LLM (the 6.1 no-cap guarantee).
    prof_a = NS(dietary=[], disliked_cuisines=[], allergens=["Tôi dị ứng đậu phộng"], context_memory={})
    cs = build(prof_a, [], "Gợi ý buffet")
    assert any("đậu phộng" in n for n in cs.health_notes)


def test_allergens_catalog_still_hard_filtered():
    # A catalog allergen (seafood) in `allergens` is hard-filtered too, not just warned — so even
    # an evicted-from-notes seafood allergy still removes violating merchants.
    prof_s = NS(dietary=[], disliked_cuisines=[], allergens=["Tôi dị ứng hải sản"], context_memory={})
    cs = build(prof_s, [], "Gợi ý sushi")
    assert any(c.scope == "seafood" for c in cs.hard)
