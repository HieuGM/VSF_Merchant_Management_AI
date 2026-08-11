"""Unit tests for cross-conversation recall (memory-system P2b).

Pure tests: _format_cross_conv_block rendering + recall_cross_conv scoring with a
mocked SessionRepository (no DB). The DB read path lives in the integration suite."""
from __future__ import annotations

from unittest.mock import MagicMock

from flows.customer_flow import _format_cross_conv_block
from services import cross_conv_recall_service as recall_svc

# newest-first (idx 0 = newest), as list_recent_distillates returns.
_FAKE_DISTILLATES = [
    {"intent": "tìm phở bò", "cuisines": ["Món Việt"], "shown": ["m1"]},
    {"intent": "đồ cay thái", "cuisines": ["Món Thái"], "shown": ["m2"]},
    {"intent": "ăn chay", "cuisines": ["Món Việt"], "shown": ["m3"]},
]


def _patch_db(monkeypatch):
    """Patch the lazily-imported SessionLocal + SessionRepository at their source so
    recall_cross_conv picks up the fakes via its `from ... import` inside the fn."""
    from database import connection as conn
    from repositories import session_repository as sr

    class _DB:
        def close(self) -> None:
            pass

    monkeypatch.setattr(conn, "SessionLocal", lambda: _DB())
    fake_repo = MagicMock()
    fake_repo.list_recent_distillates = lambda *a, **k: _FAKE_DISTILLATES
    monkeypatch.setattr(sr, "SessionRepository", lambda db: fake_repo)


# --- _format_cross_conv_block ---
def test_format_block_empty_returns_empty():
    assert _format_cross_conv_block([]) == ""


def test_format_block_renders_entries():
    out = _format_cross_conv_block(
        [{"intent": "tìm phở", "cuisines": ["Món Việt"], "shown": ["m1", "m2"]}]
    )
    assert "LỊCH SỬ TRƯỚC ĐÓ" in out
    assert "tìm phở" in out and "Món Việt" in out and "m1" in out


# --- recall_cross_conv scoring (mocked DB) ---
def test_recall_ranks_by_token_overlap(monkeypatch):
    _patch_db(monkeypatch)
    hits = recall_svc.recall_cross_conv("u1", "phở bò ngon", k=3)
    assert hits, "an overlapping distillate must be recalled"
    assert hits[0]["intent"] == "tìm phở bò"   # only this one shares 'pho' with the query


def test_recall_excludes_no_overlap(monkeypatch):
    _patch_db(monkeypatch)
    assert recall_svc.recall_cross_conv("u1", "sushi nhật", k=3) == []


def test_recall_empty_query_returns_empty():
    assert recall_svc.recall_cross_conv("u1", "", k=3) == []
    assert recall_svc.recall_cross_conv("u1", None, k=3) == []


def test_recall_no_user_returns_empty():
    assert recall_svc.recall_cross_conv("", "phở", k=3) == []


def test_recall_respects_k_limit(monkeypatch):
    _patch_db(monkeypatch)
    # Query "món việt" overlaps TWO distillates (both have 'Món Việt' cuisine) → k=1 keeps 1.
    hits = recall_svc.recall_cross_conv("u1", "món việt", k=1)
    assert len(hits) == 1
