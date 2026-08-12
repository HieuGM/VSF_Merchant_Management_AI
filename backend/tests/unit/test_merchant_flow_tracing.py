import pytest

from flows.merchant_flow import _require_trace_id


def test_require_trace_id_accepts_w3c_lowercase_hex():
    assert _require_trace_id("a" * 32) == "a" * 32


@pytest.mark.parametrize("value", [None, "", "tr-123", "A" * 32, "g" * 32])
def test_require_trace_id_rejects_non_w3c_values(value):
    with pytest.raises(RuntimeError, match="active Langfuse trace"):
        _require_trace_id(value)
