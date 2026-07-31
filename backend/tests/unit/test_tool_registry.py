"""Tool registry + allow-list enforcement (§9.1, §5.4, red-team C1)."""
from __future__ import annotations

import importlib
import sys

import pytest

from tools.allow_list import SHARED_READONLY_TOOLS
from tools.registry import ToolRegistry, registry as global_registry


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.auto_discover("tools.shared")
    return reg


def test_shared_readonly_tools_registered(registry):
    for name in SHARED_READONLY_TOOLS:
        assert name in registry.names()


def test_get_merchant_profile_strips_overall_score(registry):
    tool = registry.get("get_merchant_profile")
    result = tool.fn("68814")
    assert "overall_score" not in result
    assert set(result["dimensions"].keys()) >= {"food_quality", "price_competitiveness"}


def test_allow_list_enforced(registry):
    # Customer Explanation may call get_merchant_profile; Restaurant Search may not.
    assert registry.is_allowed("customer_explanation", "get_merchant_profile")
    assert not registry.is_allowed("restaurant_search", "get_merchant_profile")


def test_trending_dishes(registry):
    result = registry.get("get_trending_dishes").fn("68814")
    assert result["trending_dishes"] == ["bún bò Huế"]


def test_importing_merchant_package_does_not_register_legacy_tools():
    global_registry._tools.clear()
    sys.modules.pop("tools.merchant", None)

    merchant_package = importlib.import_module("tools.merchant")

    assert global_registry.names() == []
    assert not hasattr(merchant_package, "merchant_tools")
