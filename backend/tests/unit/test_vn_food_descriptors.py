"""Unit tests for core/vn_food_descriptors.py (Path A / phase-01) + the _descriptor_hints gate.

Pure-function tests for ``expand_vague_descriptors`` (the dictionary lookup) + gate tests for
``customer_flow._descriptor_hints``: flag OFF (default) → "(không có)" so the prompt line is a
no-op (byte-identical to baseline); flag ON → the hint is populated."""
from __future__ import annotations

import pytest

from core.vn_food_descriptors import expand_vague_descriptors


def test_none_and_empty_return_empty():
    assert expand_vague_descriptors(None) == ""
    assert expand_vague_descriptors("") == ""
    assert expand_vague_descriptors("   ") == ""


def test_no_match_returns_empty():
    # a precise dish query carries no vague descriptor → no hint
    assert expand_vague_descriptors("phở bò") == ""
    assert expand_vague_descriptors("sushi") == ""
    assert expand_vague_descriptors("cơm tấm sài gòn") == ""


def test_single_descriptor_with_diacritics():
    out = expand_vague_descriptors("ăn gì cho đỡ ngán bữa trưa")
    assert "đỡ ngán" in out
    assert "Món Việt" in out


def test_single_descriptor_without_diacritics():
    # toneless typing still matches (folded substring) — "do ngan" ≡ "đỡ ngán"
    out = expand_vague_descriptors("an gi cho do ngan")
    assert "đỡ ngán" in out


def test_multiple_descriptors_joined_with_semicolon():
    out = expand_vague_descriptors("trời lạnh, hơi đói và đỡ ngán")
    assert "trời lạnh" in out
    assert "đỡ ngán" in out
    assert ";" in out  # multiple hits joined


def test_hint_shape_has_query_and_cuisine_fields():
    out = expand_vague_descriptors("trời lạnh")
    assert "query:" in out
    assert "cuisine:" in out
    assert "Món Việt" in out


@pytest.mark.parametrize(
    "query,expected_label",
    [
        ("món thanh đạm", "thanh đạm"),
        ("hôm trời nóng quá", "trời nóng"),
        ("thèm đồ cay", "đồ cay"),
        ("ăn cay đi", "ăn cay"),
        ("đồ ngọt tráng miệng", "tráng miệng"),
        ("món đại bổ", "đại bổ"),
        ("bổ dưỡng chút", "bổ dưỡng"),
        ("chill chill đi", "chill"),
        ("đi nhậu không", "nhậu"),
        ("ăn vặt", "ăn vặt"),
        ("cho no nê", "no nê"),
        ("đậm đà vị", "đậm đà"),
        ("đồ uống", "đồ uống"),
        ("ăn kiêng", "ăn kiêng"),
        ("eat clean", "eat clean"),
        ("giảm cân", "giảm cân"),
        ("nhóm đông người", "nhóm"),
        ("trời mưa", "trời mưa"),
        ("đồ nhẹ", "đồ nhẹ"),
        ("nhẹ nhàng thôi", "nhẹ nhàng"),
    ],
)
def test_descriptor_coverage(query, expected_label):
    assert expected_label in expand_vague_descriptors(query)


# --- gate: _descriptor_hints respects the flag (default OFF = no-op) ---


class _FakeSettings:
    def __init__(self, on: bool) -> None:
        self.coordinator_descriptor_expansion_enabled = on


def test_descriptor_hints_off_by_default(monkeypatch):
    """Flag OFF (default) → '(không có)' → the prompt line is a no-op, byte-identical to baseline."""
    from core import settings as settings_mod

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(on=False))
    from flows.customer_flow import _NO_DESCRIPTOR_HINT, _descriptor_hints

    assert _descriptor_hints("ăn gì cho đỡ ngán") == _NO_DESCRIPTOR_HINT


def test_descriptor_hints_on_expands(monkeypatch):
    """Flag ON + vague query → the hint is populated (non-trivial, not the no-op sentinel)."""
    from core import settings as settings_mod

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(on=True))
    from flows.customer_flow import _NO_DESCRIPTOR_HINT, _descriptor_hints

    out = _descriptor_hints("ăn gì cho đỡ ngán")
    assert out != _NO_DESCRIPTOR_HINT
    assert "đỡ ngán" in out


def test_descriptor_hints_on_but_no_match_is_noop(monkeypatch):
    """Flag ON + a precise dish (no descriptor) → still '(không có)' (no spurious hint)."""
    from core import settings as settings_mod

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(on=True))
    from flows.customer_flow import _NO_DESCRIPTOR_HINT, _descriptor_hints

    assert _descriptor_hints("phở bò") == _NO_DESCRIPTOR_HINT
