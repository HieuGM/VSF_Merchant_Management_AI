"""Xay dung row dicts cho tung bang DB (schema teammate) tu du lieu da chuan bi.
Thuan Python, khong dung DB -> dung duoc cho ca dry-run lan import that.

Nguon:
- data/profiles.jsonl      -> merchants, operational_metrics, merchant_profiles, reviews, delivery_feedbacks
- data/merchants_unique.jsonl -> city_slug + tags (merchant-level)
- data/crawled/{id}.json   -> menu_items + food_images (menu day du co item_id, anh)
"""
import glob
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime.now().replace(microsecond=0)


def _catalog_map():
    m = {}
    with (ROOT / "data/merchants_unique.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            m[r["merchant_id"]] = r
    return m


def _sentiment(score):
    if score is None:
        return "neutral"
    if score >= 7:
        return "positive"
    if score < 5:
        return "negative"
    return "neutral"


def build_from_profiles(cat):
    """Tra ve dict cac list row cho 5 bang lay tu profiles.jsonl."""
    merchants, ops, profiles, reviews, deliveries = [], [], [], [], []
    with (ROOT / "data/profiles.jsonl").open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            mid = p["merchant_id"]
            md = p["metadata"]
            loc = md.get("location", {})
            c = cat.get(mid, {})
            merchants.append({
                "merchant_id": mid, "name": md.get("name") or mid,
                "cuisine": md.get("cuisine") or "N/A",
                "address": loc.get("address"), "lat": loc.get("lat"), "lng": loc.get("lng"),
                "open_hours": md.get("open_hours"),
                "city": loc.get("city") or "N/A",
                "city_slug": c.get("city_slug") or (loc.get("city") or "na").lower().replace(" ", "_").replace(".", ""),
                "source": "shopeefood", "source_url": md.get("source_url"),
                "is_demo_target": 1 if p.get("tier") == "hero" else 0,
            })
            kpi = p.get("attributes", {}).get("operation_kpis", {})
            ops.append({"merchant_id": mid,
                        "avg_prep_time_min": kpi.get("avg_prep_minutes") or 12.0,
                        "peak_hours": kpi.get("peak_hours", [])})
            profiles.append({"merchant_id": mid, "updated_at": NOW,
                             "dimensions_json": {
                                 "overall_score": p.get("overall_score"),
                                 "tier": p.get("tier"),
                                 "price_level": p.get("price_level"),
                                 "dimensions": p.get("dimensions", {}),
                                 "attributes": p.get("attributes", {}),
                                 "ratings": p.get("ratings", {})}})
            # reviews that + synthetic bu
            for i, rv in enumerate(p.get("reviews", [])):
                sc = rv.get("score")
                reviews.append({"review_id": f"{mid}_rv{i}", "merchant_id": mid,
                                "rating": sc, "text": rv.get("text") or "",
                                "sentiment": _sentiment(sc), "source_page": "foody",
                                "total_like": 0, "created_at": NOW})
            for i, rv in enumerate(p.get("synthetic_reviews", [])):
                sc = rv.get("score")
                reviews.append({"review_id": f"{mid}_srv{i}", "merchant_id": mid,
                                "rating": sc, "text": rv.get("text") or "",
                                "sentiment": _sentiment(sc), "source_page": "synthetic",
                                "total_like": 0, "created_at": NOW})
            for i, d in enumerate(p.get("delivery_feedback", [])):
                deliveries.append({"feedback_id": f"{mid}_df{i}", "merchant_id": mid,
                                   "driver_id": f"drv_{mid}_{i}",
                                   "rating": 5 if d.get("on_time") else 3,
                                   "comment": d.get("text") or "", "created_at": NOW})
    return {"merchants": merchants, "operational_metrics": ops,
            "merchant_profiles": profiles, "reviews": reviews,
            "delivery_feedbacks": deliveries}


def build_menu_and_images(cat, valid_ids):
    """menu_items + food_images tu crawled (menu day du). 1 anh dai dien/mon."""
    menu, images = [], []
    for fp in glob.glob(str(ROOT / "data/crawled/*.json")):
        r = json.load(open(fp, encoding="utf-8"))
        mid = r["merchant_id"]
        if mid not in valid_ids:
            continue
        c = cat.get(mid, {})
        seen = set()
        for g in r.get("menu", []):
            for d in g.get("dishes", []):
                did = str(d.get("id") or "")
                item_id = f"{mid}::{did}"
                if not did or item_id in seen:
                    continue
                seen.add(item_id)
                price = (d.get("price") or {}).get("value")
                photos = d.get("photos") or []
                img = photos[-1]["value"] if photos else None
                menu.append({"item_id": item_id, "merchant_id": mid,
                             "name": d.get("name") or "N/A",
                             "price": int(price) if price else 0,
                             "description": d.get("description") or None,
                             "category": g.get("dish_type_name"),
                             "image_url": img,
                             "diet_tags": c.get("diet_tags", []),
                             "ingredient_tags": c.get("ingredient_tags", []),
                             "taste_tags": c.get("taste_tags", [])})
                if img:
                    images.append({"image_id": f"img_{item_id}", "merchant_id": mid,
                                   "item_id": item_id, "url": img,
                                   "dish_image_quality": None})
    return {"menu_items": menu, "food_images": images}
