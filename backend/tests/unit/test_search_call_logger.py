"""Unit tests for services/search_call_logger.py (Path A / phase-02).

Verifies: writes a parseable JSONL row when enabled; no-op when the flag is off; NEVER raises
on a write failure (GT-neutral guarantee). The log path is monkeypatched to a temp file so the
real logs/search_queries.jsonl is not polluted."""
from __future__ import annotations

import json

from services import search_call_logger as scl


class _FakeSettings:
    def __init__(self, on: bool) -> None:
        self.search_call_logging_enabled = on


def _enable(monkeypatch, on: bool) -> None:
    from core import settings as settings_mod

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(on=on))


def test_logs_jsonl_row_when_enabled(monkeypatch, tmp_path):
    log_file = tmp_path / "search_queries.jsonl"
    monkeypatch.setattr(scl, "_LOG_FILE", log_file)
    _enable(monkeypatch, on=True)

    scl.log_search_call(
        "merchant_search",
        {"query": "phở", "cuisine": None, "city": "Hà Nội", "min_price": None},
        3,
    )

    rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["tool"] == "merchant_search"
    assert row["result_count"] == 3
    assert row["was_empty"] is False
    # empty values dropped from args
    assert "cuisine" not in row["args"] and "min_price" not in row["args"]
    assert row["args"]["query"] == "phở" and row["args"]["city"] == "Hà Nội"
    assert row["hybrid_flag"] is None


def test_marks_empty_results(monkeypatch, tmp_path):
    log_file = tmp_path / "search_queries.jsonl"
    monkeypatch.setattr(scl, "_LOG_FILE", log_file)
    _enable(monkeypatch, on=True)

    scl.log_search_call("nearby_merchant_search", {"query": "sao hỏa"}, 0)

    row = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert row["was_empty"] is True
    assert row["result_count"] == 0


def test_noop_when_flag_off(monkeypatch, tmp_path):
    log_file = tmp_path / "search_queries.jsonl"
    monkeypatch.setattr(scl, "_LOG_FILE", log_file)
    _enable(monkeypatch, on=False)

    scl.log_search_call("merchant_search", {"query": "phở"}, 5)

    assert not log_file.exists()  # nothing written


def test_never_raises_on_write_failure(monkeypatch):
    _enable(monkeypatch, on=True)
    # point at an unwritable path (a file under a missing drive root raises on open)
    monkeypatch.setattr(scl, "_LOG_FILE", __import__("pathlib").Path("Z:/no_such_dir/x.jsonl"))

    # must NOT raise — logging never breaks search
    scl.log_search_call("merchant_search", {"query": "phở"}, 5)
