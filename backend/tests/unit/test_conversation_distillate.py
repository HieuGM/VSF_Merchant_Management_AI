"""Unit tests for services/conversation_distillate_service.py (memory-system P2).

Pure tests of the distillate accumulation logic (build_distillate_state) — no DB.
Covers: intent-set-once, cuisines/shown union (order-stable, deduped), turn_count,
PII redaction, empty-results turn. The DB RMW + user_id binding live in the
integration suite (test_customer_memory_wireup.py)."""
from __future__ import annotations

from services.conversation_distillate_service import build_distillate_state


def test_intent_set_once_from_first_turn_last_query_updates():
    d = build_distillate_state(None, "tìm phở cầu giấy", [{"merchant_id": "m1", "cuisine": "Món Việt"}])
    assert d["intent"] == "tìm phở cầu giấy"
    d = build_distillate_state(d, "rẻ hơn nữa", [{"merchant_id": "m2", "cuisine": "Món Việt"}])
    assert d["intent"] == "tìm phở cầu giấy"   # topic frozen at first turn
    assert d["last_query"] == "rẻ hơn nữa"      # most recent query tracked


def test_cuisines_union_order_stable_and_deduped():
    d = build_distillate_state(None, "phở", [{"merchant_id": "m1", "cuisine": "Món Việt"}])
    d = build_distillate_state(d, "bún", [{"merchant_id": "m2", "cuisine": "Món Việt"}])
    d = build_distillate_state(d, "cơm tấm", [{"merchant_id": "m3", "cuisine": "Ăn vặt"}])
    assert d["cuisines"] == ["Món Việt", "Ăn vặt"]   # union, deduped, insertion order


def test_shown_union_deduped():
    d = build_distillate_state(None, "phở", [{"merchant_id": "m1"}, {"merchant_id": "m2"}])
    d = build_distillate_state(d, "lại", [{"merchant_id": "m2"}, {"merchant_id": "m3"}])
    assert d["shown"] == ["m1", "m2", "m3"]   # m2 not duplicated


def test_turn_count_increments_each_turn():
    d = build_distillate_state(None, "a", [{"merchant_id": "m1"}])
    assert d["turn_count"] == 1
    d = build_distillate_state(d, "b", [{"merchant_id": "m2"}])
    assert d["turn_count"] == 2


def test_pii_redacted_in_intent():
    d = build_distillate_state(None, "gọi mình 0912345678 nhé", [{"merchant_id": "m1"}])
    assert "0912345678" not in d["intent"]
    assert "[PHONE]" in d["intent"]


def test_empty_results_still_counts_turn_and_omits_shown():
    d = build_distillate_state(None, "ăn gì ngon", [])
    assert d["turn_count"] == 1
    assert d["intent"] == "ăn gì ngon"
    assert "shown" not in d        # no merchants surfaced → key omitted
    assert "cuisines" not in d


def test_merge_preserves_existing_distillate_keys():
    existing = {"intent": "old", "cuisines": ["X"], "shown": ["m0"], "turn_count": 5}
    d = build_distillate_state(existing, "more", [{"merchant_id": "m1", "cuisine": "Y"}])
    assert d["intent"] == "old"          # not overwritten
    assert d["shown"] == ["m0", "m1"]    # appended
    assert d["cuisines"] == ["X", "Y"]
    assert d["turn_count"] == 6


# --- _persist_turns distillate write is gated by memory_cross_conv_enabled ---
def test_persist_turns_distillate_gated_by_flag(monkeypatch):
    """The flag guard in _persist_turns must keep distillate writes OFF when the flag is
    off (byte-identical baseline) + when user_id is absent. Catches a refactor that drops
    the guard (code-review M2)."""
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from core import settings as settings_mod
    import services.conversation_distillate_service as cds

    # `import flows.customer_flow as cf` binds cf to the SINGLETON instance, NOT the module:
    # flows/__init__.py shadows the submodule attribute via `from flows.customer_flow
    # import customer_flow` (CPython `import a.b as c` = `c = a.b`, an attribute read).
    # Resolve the MODULE from sys.modules so we can patch its module-level functions.
    import flows.customer_flow  # noqa: F401 — ensures the module is loaded
    cf = sys.modules["flows.customer_flow"]

    monkeypatch.setattr(cf, "_append_turns", MagicMock())  # no DB
    fake_update = MagicMock()
    monkeypatch.setattr(cds, "update_distillate", fake_update)  # lazy-imported in _persist_turns

    resp = SimpleNamespace(answer="gợi ý Phở Lệ")
    top3 = [{"merchant_id": "m1", "name": "Phở Lệ", "cuisine": "Món Việt"}]

    # Flag OFF -> never written.
    monkeypatch.setattr(settings_mod, "get_settings", lambda: SimpleNamespace(
        memory_cross_conv_enabled=False))
    cf._persist_turns("s1", "t1", "tìm phở", resp, displayed=top3, user_id="u1")
    assert fake_update.call_count == 0

    # Flag ON + user_id -> written once.
    monkeypatch.setattr(settings_mod, "get_settings", lambda: SimpleNamespace(
        memory_cross_conv_enabled=True))
    cf._persist_turns("s1", "t1", "tìm phở", resp, displayed=top3, user_id="u1")
    assert fake_update.call_count == 1

    # Flag ON but no user_id -> never written (distillate is per-user only).
    fake_update.reset_mock()
    cf._persist_turns("s1", "t1", "tìm phở", resp, displayed=top3, user_id=None)
    assert fake_update.call_count == 0
