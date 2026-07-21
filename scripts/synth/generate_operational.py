"""Sinh du lieu SO (procedural, khong LLM) cho tat ca merchant crawl duoc:
operation_kpis, delivery_stats, customer_segments, price_level, peak_hours.

Xac dinh (deterministic): seed = merchant_id -> tai lap duoc, khong random moi lan.
Tin hieu dau vao: category, price, taste_tags, avg_prep_minutes (catalog) + rating that (crawled).
Output: data/synthetic/operational.jsonl (1 dong/merchant).
"""
import json
import random
import statistics
from pathlib import Path

from scenarios import SCENARIO_ASSIGN, apply_ops_override

UNIQUE = Path("data/merchants_unique.jsonl")
CRAWLED = Path("data/crawled")
OUT = Path("data/synthetic/operational.jsonl")


def load_catalog():
    rows = {}
    with UNIQUE.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if str(r.get("merchant_id", "")).isdigit():
                rows[r["merchant_id"]] = r
    return rows


def real_rating(mid):
    """Lay rating that tu file crawled (thang 5). None neu khong co."""
    fp = CRAWLED / f"{mid}.json"
    if not fp.exists():
        return None, 0
    r = json.loads(fp.read_text(encoding="utf-8"))
    menu_size = sum(len(g.get("dishes", [])) for g in r.get("menu", []))
    return r.get("shopeefood_rating_avg"), menu_size


def peak_hours(category):
    c = (category or "").lower()
    if any(k in c for k in ["café", "cafe", "dessert", "trà sữa", "trà", "kem"]):
        return ["14:00-16:00", "19:00-21:30"]
    if any(k in c for k in ["nhậu", "bia", "ốc", "lẩu", "nướng"]):
        return ["18:00-22:30"]
    return ["11:00-13:00", "18:00-20:00"]


def customer_segments(price, category, taste_tags):
    segs = []
    if price is None:
        price = 44000
    if price < 30000:
        segs += ["sinh viên", "nhân viên văn phòng ngân sách thấp"]
    elif price < 70000:
        segs += ["dân văn phòng", "gia đình"]
    else:
        segs += ["gia đình", "nhóm bạn/hẹn hò"]
    tags = " ".join(taste_tags or []).lower()
    if any(k in tags for k in ["healthy", "ít béo", "eat clean", "tốt cho sức khỏe"]):
        segs.append("khách quan tâm sức khỏe")
    c = (category or "").lower()
    if any(k in c for k in ["nhậu", "bia", "ốc", "lẩu"]):
        segs.append("nhóm nhậu")
    return list(dict.fromkeys(segs))  # dedupe giu thu tu


def price_level(price, median):
    if price is None:
        return "trung bình"
    ratio = price / median if median else 1.0
    if ratio < 0.8:
        return "rẻ"
    if ratio <= 1.25:
        return "trung bình"
    return "cao cấp"


def gen_one(m, rating, menu_size, median_price):
    rng = random.Random(int(m["merchant_id"]))
    price = m.get("price")
    prep = m.get("avg_prep_minutes") or rng.randint(8, 20)
    # rating that (thang 5); neu thieu, gia dinh trung binh
    r5 = rating if rating else 4.3
    quality = max(0.0, min(1.0, (r5 - 3.0) / 2.0))  # 0..1 tu rating

    cancel_rate = round(max(0.005, 0.10 - quality * 0.08 + rng.uniform(-0.01, 0.02)), 3)
    acceptance_rate = round(min(0.99, 0.85 + quality * 0.12 + rng.uniform(-0.03, 0.03)), 3)
    on_time_rate = round(min(0.99, 0.80 + quality * 0.15 + rng.uniform(-0.04, 0.03)), 3)
    driver_rating = round(min(5.0, 4.0 + quality * 0.8 + rng.uniform(-0.15, 0.15)), 2)
    packaging_ok = round(min(0.99, 0.82 + quality * 0.14 + rng.uniform(-0.04, 0.04)), 3)
    avg_delivery = int(prep + rng.randint(8, 22))
    # so don/ngay: quan tot + menu lon -> nhieu don hon
    base_orders = 20 + menu_size // 3
    daily_orders = int(base_orders * (0.6 + quality) * rng.uniform(0.7, 1.3))

    return {
        "merchant_id": m["merchant_id"],
        "operation_kpis": {
            "avg_prep_minutes": prep,
            "cancel_rate": cancel_rate,
            "acceptance_rate": acceptance_rate,
            "estimated_daily_orders": daily_orders,
            "peak_hours": peak_hours(m.get("category")),
        },
        "delivery_stats": {
            "avg_delivery_minutes": avg_delivery,
            "on_time_rate": on_time_rate,
            "driver_rating": driver_rating,
            "packaging_ok_rate": packaging_ok,
        },
        "customer_segments": customer_segments(price, m.get("category"), m.get("taste_tags")),
        "price_level": price_level(price, median_price),
        "based_on_real_rating": rating is not None,
        "note": "procedural synthetic (deterministic seed=merchant_id)",
    }


def main():
    catalog = load_catalog()
    prices = [m["price"] for m in catalog.values() if m.get("price")]
    median_price = statistics.median(prices)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    n = with_rating = scen = 0
    with OUT.open("w", encoding="utf-8") as f:
        for mid, m in catalog.items():
            rating, menu_size = real_rating(mid)
            if rating is not None:
                with_rating += 1
            rec = gen_one(m, rating, menu_size, median_price)
            # ep so lieu ops xau cho quan co kich ban yeu (dimension ops-driven)
            if mid in SCENARIO_ASSIGN:
                rec = apply_ops_override(rec, SCENARIO_ASSIGN[mid])
                scen += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"generated operational synthetic for {n} merchants "
          f"({with_rating} keyed to real rating, {scen} scenario-overridden) -> {OUT}")


if __name__ == "__main__":
    main()
