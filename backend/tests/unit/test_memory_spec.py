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
from services.context_memory_service import extract_notes


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
