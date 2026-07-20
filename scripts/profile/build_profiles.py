"""Dung Merchant Profile HOP NHAT cho tat ca merchant -> data/profiles/{id}.json.
Gop: catalog (static) + crawled (menu/rating/reviews) + operational (ops so) +
text synthetic (hero: complaints/delivery/filled_reviews) + vision (hero) +
trending/competitors precomputed. Moi profile TU CHUA DU de agent doc thang.

Usage: python scripts/profile/build_profiles.py
"""
import json
import glob
import statistics
import time
from pathlib import Path

import dimension_scoring as ds

CRAWLED = Path("data/crawled")
CACHE = Path("data/profile_cache")
OUTDIR = Path("data/profiles")


def load_catalog():
    cat = {}
    for line in open("data/merchants_unique.jsonl", encoding="utf-8"):
        r = json.loads(line)
        cat[r["merchant_id"]] = r
    return cat


def load_jsonl_map(path, key="merchant_id"):
    m = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        m[r[key]] = r
    return m


def trim_menu(menu):
    """Giu thong tin dish can cho agent, bo mang photos nang."""
    out = []
    for g in menu:
        for d in g.get("dishes", []):
            price = (d.get("price") or {}).get("value")
            disc = (d.get("discount_price") or {}).get("value")
            out.append({
                "name": d.get("name"),
                "type": g.get("dish_type_name"),
                "price": price,
                "discount_price": disc if disc and disc != price else None,
                "total_like": ds.like_to_int(d.get("total_like")),
                "has_photo": bool(d.get("photos")),
            })
    return out


def build_metadata(cat, crawled):
    oh = cat.get("merchant_open_hours") or {}
    return {
        "name": cat.get("merchant_name") or crawled.get("merchant_name"),
        "cuisine": cat.get("cuisine"),
        "category": cat.get("category"),
        "location": {
            "address": cat.get("merchant_address"),
            "lat": cat.get("merchant_lat"), "lng": cat.get("merchant_lng"),
            "city": cat.get("city"),
        },
        "open_hours": {"open": oh.get("open_time"), "close": oh.get("close_time")},
        "image_url": cat.get("image_url"),
        "source_url": cat.get("source_url"),
        "phones": crawled.get("phones"),
        "taste_tags": cat.get("taste_tags", []),
        "diet_tags": cat.get("diet_tags", []),
    }


def build_dimensions(crawled, ops, text, vision, cat, median_price):
    specs = {
        "food_quality": ds.food_quality(crawled, ops, text),
        "image_quality": ds.image_quality(crawled, vision),
        "delivery_quality": ds.delivery_quality(ops, text),
        "packaging": ds.packaging(ops, text),
        "service": ds.service(crawled, text),
        "waiting_time": ds.waiting_time(ops, cat, text),
        "menu_diversity": ds.menu_diversity(crawled),
        "price_level": ds.price_level(ops, cat, median_price),
    }
    dims = {}
    for name, (score, ev, note) in specs.items():
        dims[name] = {"score": score, "evidence": ev, "basis": note}
    return dims


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cat = load_catalog()
    ops_map = load_jsonl_map("data/synthetic/operational.jsonl")
    hero_ids = {m["merchant_id"] for m in
                json.loads(Path("data/synthetic/hero_set.json").read_text(encoding="utf-8"))["merchants"]}
    trending = json.loads((CACHE / "trending_by_cluster.json").read_text(encoding="utf-8"))
    competitors = json.loads((CACHE / "competitors_by_merchant.json").read_text(encoding="utf-8"))
    prices = [m["price"] for m in cat.values() if m.get("price")]
    median_price = statistics.median(prices)

    n = hero_n = 0
    for fp in glob.glob("data/crawled/*.json"):
        crawled = json.load(open(fp, encoding="utf-8"))
        mid = crawled["merchant_id"]
        c = cat.get(mid, {})
        ops = ops_map.get(mid, {})
        is_hero = mid in hero_ids
        text = {}
        vision = None
        if is_hero:
            tfp = Path(f"data/synthetic/text/{mid}.json")
            if tfp.exists():
                text = json.loads(tfp.read_text(encoding="utf-8"))
            vfp = CACHE / "vision" / f"{mid}.json"
            if vfp.exists():
                vision = json.loads(vfp.read_text(encoding="utf-8"))

        dims = build_dimensions(crawled, ops, text, vision, c, median_price)
        overall = round(sum(d["score"] for d in dims.values()) / len(dims), 3)
        cluster_key = f"{c.get('city')}||{c.get('cuisine')}"

        profile = {
            "merchant_id": mid,
            "tier": "hero" if is_hero else "background",
            "overall_score": overall,
            "metadata": build_metadata(c, crawled),
            "price_level": ops.get("price_level"),
            "dimensions": dims,
            "attributes": {
                "customer_segments": ops.get("customer_segments", []),
                "peak_time": ops.get("operation_kpis", {}).get("peak_hours", []),
                "competitors": competitors.get(mid, []),
                "trending_dishes": trending.get(cluster_key, [])[:8],
                "operation_kpis": ops.get("operation_kpis", {}),
                "delivery_stats": ops.get("delivery_stats", {}),
            },
            "ratings": {
                "shopeefood_avg": crawled.get("shopeefood_rating_avg"),
                "shopeefood_total_review": crawled.get("shopeefood_total_review"),
                "foody_rating": crawled.get("foody_rating"),
                "foody_review_count": crawled.get("foody_review_count"),
            },
            "menu": trim_menu(crawled.get("menu", [])),
            "reviews": crawled.get("reviews", []),
            "synthetic_reviews": text.get("filled_reviews", []),
            "complaints": text.get("complaints", []),
            "delivery_feedback": text.get("delivery_feedback", []),
            "data_sources": {
                "menu_rating": "crawled (shopeefood)",
                "reviews": "crawled (foody)" + (" + synthetic fill" if text.get("filled_reviews") else ""),
                "ops_delivery": "procedural synthetic",
                "complaints_delivery_text": "LLM synthetic (hero)" if is_hero else "n/a",
                "image_quality": "vision LLM" if vision else "heuristic",
            },
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        (OUTDIR / f"{mid}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
        hero_n += is_hero
    print(f"built {n} profiles ({hero_n} hero, {n - hero_n} background) -> {OUTDIR}")


if __name__ == "__main__":
    main()
