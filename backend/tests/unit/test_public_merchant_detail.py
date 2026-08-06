from datetime import time

from database.models import Merchant, MenuItem
from providers.cache.memory_adapter import InMemoryCache
from tools.merchant.public_detail_tool import get_public_merchant_detail


def test_public_merchant_detail_returns_hours_and_available_menu(db_session):
    merchant = Merchant(
        merchant_id="public-detail-1",
        name="Bún Cá Public",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp_hcm",
        opens_at=time(6, 0),
        closes_at=time(23, 59),
        timezone="Asia/Ho_Chi_Minh",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.add_all(
        [
            MenuItem(
                item_id="public-detail-menu-1",
                merchant_id=merchant.merchant_id,
                name="Bún chả cá",
                price=55_000,
                is_available=True,
            ),
            MenuItem(
                item_id="public-detail-menu-hidden",
                merchant_id=merchant.merchant_id,
                name="Món ngừng bán",
                price=10_000,
                is_available=False,
            ),
        ]
    )
    db_session.commit()

    result = get_public_merchant_detail(
        merchant.merchant_id,
        db=db_session,
        cache=InMemoryCache(),
    )

    assert result["opens_at"] == "06:00:00"
    assert result["closes_at"] == "23:59:00"
    assert result["timezone"] == "Asia/Ho_Chi_Minh"
    assert result["menu_items"] == [
        {
            "name": "Bún chả cá",
            "price": 55_000,
            "discount_price": None,
            "category": None,
        }
    ]


def test_public_merchant_detail_reuses_id_scoped_cache(db_session):
    merchant = Merchant(
        merchant_id="public-detail-cache",
        name="Xôi Cache",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp_hcm",
        is_active=True,
    )
    db_session.add(merchant)
    db_session.commit()
    cache = InMemoryCache()
    events: list[dict] = []

    get_public_merchant_detail(
        merchant.merchant_id,
        db=db_session,
        cache=cache,
        cache_event_callback=events.append,
    )
    get_public_merchant_detail(
        merchant.merchant_id,
        db=db_session,
        cache=cache,
        cache_event_callback=events.append,
    )

    assert [event["status"] for event in events] == ["miss", "store", "hit"]
