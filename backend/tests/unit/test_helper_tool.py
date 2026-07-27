"""Unit tests for Helper Metadata Catalog Tool."""
from __future__ import annotations

from tools.merchant.helper_tool import (
    get_merchant_metadata_catalog,
    GetMerchantMetadataCatalogTool,
)


def test_get_merchant_metadata_catalog_function():
    res = get_merchant_metadata_catalog()
    assert "available_cuisines" in res
    assert "available_cities" in res
    assert "official_8_dimensions" in res
    assert len(res["official_8_dimensions"]) == 8
    assert "price_competitiveness" in res["official_8_dimensions"]


def test_get_merchant_metadata_catalog_tool_run():
    tool = GetMerchantMetadataCatalogTool()
    output_json = tool._run(topic="dimensions")
    assert "official_8_dimensions" in output_json
    assert "food_quality" in output_json
