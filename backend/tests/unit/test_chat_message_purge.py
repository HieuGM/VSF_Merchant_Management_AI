"""Unit tests for the purge time-gate (memory-system storage, code-review M3).

Verifies maybe_purge_stale_messages: runs on first eligible tick, is time-gated
afterward, respects the enabled flag, and floors min_interval at 60s even when 0.
_purge + time.monotonic + get_settings are mocked — no DB."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from services import chat_message_purge_service as cps


def _setup(monkeypatch, enabled=True, min_interval_hours=1):
    """Reset the gate + patch _purge / time.monotonic / get_settings. Returns
    (purge_mock, mutable_clock_list)."""
    from core import settings as settings_mod

    monkeypatch.setattr(cps, "_last_purge_ts", 0.0)
    purge_mock = MagicMock(return_value=7)
    monkeypatch.setattr(cps, "_purge", purge_mock)
    clock = [100000.0]
    monkeypatch.setattr(cps.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        settings_mod, "get_settings",
        lambda: SimpleNamespace(
            memory_purge_enabled=enabled,
            memory_purge_min_interval_hours=min_interval_hours,
            memory_purge_max_age_days=90,
        ),
    )
    return purge_mock, clock


def test_first_eligible_tick_runs_purge(monkeypatch):
    purge_mock, _ = _setup(monkeypatch)
    assert cps.maybe_purge_stale_messages() == 7
    assert purge_mock.call_count == 1


def test_within_interval_is_gated(monkeypatch):
    purge_mock, clock = _setup(monkeypatch)
    cps.maybe_purge_stale_messages()           # runs (first)
    clock[0] += 100                            # 100s later (< 1h floor) -> gated
    assert cps.maybe_purge_stale_messages() == 0
    assert purge_mock.call_count == 1


def test_after_interval_runs_again(monkeypatch):
    purge_mock, clock = _setup(monkeypatch)
    cps.maybe_purge_stale_messages()
    clock[0] += 4000                           # >1h later -> runs again
    assert cps.maybe_purge_stale_messages() == 7
    assert purge_mock.call_count == 2


def test_disabled_flag_never_purges(monkeypatch):
    purge_mock, _ = _setup(monkeypatch, enabled=False)
    assert cps.maybe_purge_stale_messages() == 0
    assert purge_mock.call_count == 0


def test_min_interval_zero_floors_to_60s(monkeypatch):
    """A 0h setting must NOT purge every append_turn — floored at 60s."""
    purge_mock, clock = _setup(monkeypatch, min_interval_hours=0)
    cps.maybe_purge_stale_messages()           # runs (first; last_ts=0)
    clock[0] += 30                             # 30s later (< 60s floor) -> gated
    assert cps.maybe_purge_stale_messages() == 0
    assert purge_mock.call_count == 1
    clock[0] += 31                             # 61s total -> past floor -> runs
    assert cps.maybe_purge_stale_messages() == 7
    assert purge_mock.call_count == 2
