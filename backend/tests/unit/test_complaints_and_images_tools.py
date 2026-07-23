"""Unit tests for Complaints and Menu/Food Images tools."""
from __future__ import annotations

import uuid
from datetime import date

from database.models import Merchant, MenuItem, FoodImage, MerchantComplaint
from tools.merchant.complaints_tool import get_merchant_complaints, GetMerchantComplaintsTool
from tools.merchant.menu_image_tool import get_menu_and_food_images, GetMenuAndFoodImagesTool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_merchant(session, mid: str) -> Merchant:
    m = Merchant(
        merchant_id=mid,
        name=f"Quán Test {mid}",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
    )
    session.add(m)
    session.flush()
    return m


def _make_complaint(session, merchant_id: str, category: str, severity: str, text: str) -> None:
    c = MerchantComplaint(
        complaint_id=str(uuid.uuid4()),
        merchant_id=merchant_id,
        category=category,
        severity=severity,
        text=text,
        occurred_on=date(2025, 7, 1),
        source_kind="development_fixture",
    )
    session.add(c)


def _make_menu_item(session, merchant_id: str, item_id: str, has_photo: bool = True) -> MenuItem:
    item = MenuItem(
        item_id=item_id,
        merchant_id=merchant_id,
        name=f"Món {item_id}",
        price=45000,
        category="Món chính",
        has_photo=has_photo,
        total_like=10,
        is_available=True,
    )
    session.add(item)
    session.flush()
    return item


def _make_food_image(session, merchant_id: str, item_id: str, quality: float) -> None:
    img = FoodImage(
        image_id=str(uuid.uuid4()),
        merchant_id=merchant_id,
        item_id=item_id,
        url=f"https://cdn.example.com/{item_id}.jpg",
        dish_image_quality=quality,
        blur_score=0.1,
    )
    session.add(img)


# ── Complaint Tests ───────────────────────────────────────────────────────────

def test_get_merchant_complaints_aggregation(db_session):
    _make_merchant(db_session, "m_complaints_01")
    _make_complaint(db_session, "m_complaints_01", "giao_hàng_trễ", "high", "Giao hàng chậm lắm!")
    _make_complaint(db_session, "m_complaints_01", "giao_hàng_trễ", "medium", "Đợi mãi không thấy.")
    _make_complaint(db_session, "m_complaints_01", "chất_lượng_món", "low", "Món hơi nhạt.")
    db_session.commit()

    res = get_merchant_complaints("m_complaints_01", db=db_session)
    assert res["status"] == "ok"
    assert res["total_count"] == 3
    assert "giao_hàng_trễ" in res["by_category"]
    assert res["by_category"]["giao_hàng_trễ"]["count"] == 2
    assert res["by_category"]["giao_hàng_trễ"]["severity_counts"]["high"] == 1
    assert len(res["by_category"]["giao_hàng_trễ"]["samples"]) >= 1
    assert "chất_lượng_món" in res["by_category"]


def test_get_merchant_complaints_filter_by_severity(db_session):
    _make_merchant(db_session, "m_complaints_02")
    _make_complaint(db_session, "m_complaints_02", "đóng_gói_kém", "high", "Hộp bị vỡ nát.")
    _make_complaint(db_session, "m_complaints_02", "đóng_gói_kém", "low", "Hộp hơi xấu.")
    db_session.commit()

    res = get_merchant_complaints("m_complaints_02", severity="high", db=db_session)
    assert res["total_count"] == 1
    assert res["by_category"]["đóng_gói_kém"]["severity_counts"]["high"] == 1


def test_get_merchant_complaints_not_found(db_session):
    res = get_merchant_complaints("m_not_exist_abc", db=db_session)
    assert res["status"] == "ok"
    assert res["total_count"] == 0


def test_get_merchant_complaints_tool_class(db_session, monkeypatch):
    _make_merchant(db_session, "m_complaints_tool_01")
    _make_complaint(db_session, "m_complaints_tool_01", "vệ_sinh", "medium", "Quán bẩn quá.")
    db_session.commit()

    import tools.merchant.complaints_tool as mod
    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)

    tool = GetMerchantComplaintsTool()
    output = tool._run(merchant_id="m_complaints_tool_01")
    assert "m_complaints_tool_01" in output
    assert "vệ_sinh" in output


# ── Menu & Image Tests ────────────────────────────────────────────────────────

def test_get_menu_and_food_images_basic(db_session):
    _make_merchant(db_session, "m_menu_01")
    item = _make_menu_item(db_session, "m_menu_01", "item_menu_01")
    _make_food_image(db_session, "m_menu_01", "item_menu_01", quality=0.85)
    db_session.commit()

    res = get_menu_and_food_images("m_menu_01", db=db_session)
    assert res["status"] == "ok"
    assert res["count"] == 1
    item_result = res["items"][0]
    assert item_result["item_id"] == "item_menu_01"
    assert len(item_result["images"]) == 1
    assert "url" in item_result["images"][0]
    assert item_result["images"][0]["dish_image_quality"] == 0.85
    # Confirm no pixel/binary data
    assert "pixels" not in item_result["images"][0]


def test_get_menu_and_food_images_quality_filter(db_session):
    _make_merchant(db_session, "m_menu_02")
    item = _make_menu_item(db_session, "m_menu_02", "item_menu_02a")
    _make_food_image(db_session, "m_menu_02", "item_menu_02a", quality=0.30)  # Low quality
    item2 = _make_menu_item(db_session, "m_menu_02", "item_menu_02b")
    _make_food_image(db_session, "m_menu_02", "item_menu_02b", quality=0.90)  # High quality
    db_session.commit()

    res = get_menu_and_food_images("m_menu_02", min_image_quality=0.80, db=db_session)
    assert res["status"] == "ok"
    # item_menu_02b has high quality image, item_menu_02a does not
    items_with_images = [i for i in res["items"] if len(i["images"]) > 0]
    for item in items_with_images:
        for img in item["images"]:
            assert img["dish_image_quality"] >= 0.80


def test_get_menu_and_food_images_tool_class(db_session, monkeypatch):
    _make_merchant(db_session, "m_menu_tool_01")
    _make_menu_item(db_session, "m_menu_tool_01", "item_tool_01")
    db_session.commit()

    import tools.merchant.menu_image_tool as mod
    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)

    tool = GetMenuAndFoodImagesTool()
    output = tool._run(merchant_id="m_menu_tool_01")
    assert "m_menu_tool_01" in output
    assert "item_tool_01" in output
