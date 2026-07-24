"""Xay dung row dicts cho tung bang DB tu du lieu da chuan bi.
Thuan Python, khong dung DB -> dung duoc cho ca dry-run lan import that.

Aligned with docs/2026-07-23-merchant-relational-schema-design.md:
- data/profiles.jsonl      -> merchants, operational_metrics, merchant_profiles,
                              merchant_ratings, merchant_dimension_calculations,
                              merchant_dimension_evidence, merchant_complaints,
                              reviews, delivery_feedbacks
- data/merchants_unique.jsonl -> city_slug + tags (merchant-level)
- data/crawled/{id}.json   -> menu_items + food_images
"""
import glob
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime.now().replace(microsecond=0)

# JSON dimension key -> relational dimension name
_DIM_KEY_MAP = {
    "food_quality": "food_quality",
    "image_quality": "image_quality",
    "delivery_quality": "delivery_quality",
    "packaging": "packaging",
    "service": "service",
    "waiting_time": "waiting_time",
    "menu_diversity": "menu_diversity",
    "price_level": "price_competitiveness",  # key rename per schema design §6.3
}

# data_sources key -> source_kind mapping
_SOURCE_KIND_MAP = {
    "crawled (shopeefood)": "real",
    "crawled (foody)": "real",
    "procedural synthetic": "synthetic",
    "LLM synthetic (hero)": "synthetic",
    "LLM synthetic": "synthetic",
    "vision LLM": "heuristic",
    "heuristic": "heuristic",
    "heuristic: photo coverage": "heuristic",
    "n/a": "synthetic",
}


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


def _resolve_source_kind(raw):
    """Map raw data_sources value to canonical source_kind."""
    if raw is None:
        return "synthetic"
    return _SOURCE_KIND_MAP.get(raw, "synthetic")


def _dim_source_kind(dim_key, data_sources):
    """Determine source_kind for a specific dimension based on data_sources."""
    # Map dimension -> likely data_sources key
    ds_map = {
        "food_quality": "menu_rating",
        "image_quality": "image_quality",
        "delivery_quality": "ops_delivery",
        "packaging": "ops_delivery",
        "service": "reviews",
        "waiting_time": "ops_delivery",
        "menu_diversity": "menu_rating",
        "price_level": "menu_rating",
        "price_competitiveness": "menu_rating",
    }
    ds_key = ds_map.get(dim_key, "menu_rating")
    return _resolve_source_kind(data_sources.get(ds_key))


def build_from_profiles(cat):
    """Return dict of row-lists for all relational merchant-domain tables."""
    merchants = []
    ops = []
    profiles = []
    ratings_list = []
    calculations = []
    evidence_list = []
    complaints = []
    reviews = []
    deliveries = []

    with (ROOT / "data/profiles.jsonl").open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            mid = p["merchant_id"]
            md = p["metadata"]
            loc = md.get("location", {})
            c = cat.get(mid, {})
            data_sources = p.get("data_sources", {})

            # -- merchants --
            open_hours = md.get("open_hours") or {}
            opens_at = open_hours.get("open") or None
            closes_at = open_hours.get("close") or None
            merchants.append({
                "merchant_id": mid,
                "name": md.get("name") or mid,
                "cuisine": md.get("cuisine") or "N/A",
                "category": None,
                "address": loc.get("address"),
                "city": loc.get("city") or "N/A",
                "city_slug": c.get("city_slug") or (loc.get("city") or "na").lower().replace(" ", "_").replace(".", ""),
                "lat": loc.get("lat"),
                "lng": loc.get("lng"),
                "opens_at": opens_at,
                "closes_at": closes_at,
                "taste_tags": c.get("taste_tags", []),
                "diet_tags": c.get("diet_tags", []),
                "ingredient_tags": c.get("ingredient_tags", []),
                "customer_segments": p.get("attributes", {}).get("customer_segments", []),
                "source": "shopeefood",
                "source_url": md.get("source_url"),
                "is_active": True,
                "is_demo_target": p.get("tier") == "hero",
            })

            # -- operational_metrics --
            kpi = p.get("attributes", {}).get("operation_kpis", {})
            delivery_stats = p.get("attributes", {}).get("delivery_stats", {})
            ops.append({
                "merchant_id": mid,
                "avg_prep_time_min": kpi.get("avg_prep_minutes"),
                "cancel_rate": kpi.get("cancel_rate"),
                "acceptance_rate": kpi.get("acceptance_rate"),
                "estimated_daily_orders": kpi.get("estimated_daily_orders"),
                "peak_hours": kpi.get("peak_hours", []),
                "avg_delivery_time_min": delivery_stats.get("avg_delivery_minutes"),
                "on_time_rate": delivery_stats.get("on_time_rate"),
                "driver_rating": delivery_stats.get("driver_rating"),
                "packaging_ok_rate": delivery_stats.get("packaging_ok_rate"),
                "source_kind": _resolve_source_kind(data_sources.get("ops_delivery")),
            })

            # -- merchant_profiles (relational — no dimensions_json) --
            dims = p.get("dimensions", {})
            profiles.append({
                "merchant_id": mid,
                "tier": p.get("tier") or "background",
                "price_level": p.get("price_level") or "trung bình",
                "food_quality_score": dims.get("food_quality", {}).get("score", 0.5),
                "image_quality_score": dims.get("image_quality", {}).get("score", 0.5),
                "delivery_quality_score": dims.get("delivery_quality", {}).get("score", 0.5),
                "packaging_score": dims.get("packaging", {}).get("score", 0.5),
                "service_score": dims.get("service", {}).get("score", 0.5),
                "waiting_time_score": dims.get("waiting_time", {}).get("score", 0.5),
                "menu_diversity_score": dims.get("menu_diversity", {}).get("score", 0.5),
                "price_competitiveness_score": dims.get("price_level", {}).get("score", 0.5),
                # overall_score_internal is GENERATED — do NOT include
                "scoring_version": "v1",
                "scored_at": NOW,
            })

            # -- merchant_ratings --
            rat = p.get("ratings", {})
            if rat:
                ratings_list.append({
                    "merchant_id": mid,
                    "shopeefood_rating": rat.get("shopeefood_avg"),
                    "shopeefood_review_count": rat.get("shopeefood_total_review"),
                    "foody_rating": rat.get("foody_rating"),
                    "foody_review_count": rat.get("foody_review_count"),
                })

            # -- merchant_dimension_calculations (8 rows per merchant) --
            for dim_key, dim_data in dims.items():
                rel_dim = _DIM_KEY_MAP.get(dim_key, dim_key)
                calculations.append({
                    "merchant_id": mid,
                    "dimension": rel_dim,
                    "basis": dim_data.get("basis", "unknown"),
                    "source_kind": _dim_source_kind(dim_key, data_sources),
                    "scoring_version": "v1",
                    "calculated_at": NOW,
                })

            # -- merchant_dimension_evidence (N rows per dimension) --
            for dim_key, dim_data in dims.items():
                rel_dim = _DIM_KEY_MAP.get(dim_key, dim_key)
                sk = _dim_source_kind(dim_key, data_sources)
                for ev in dim_data.get("evidence", []):
                    ev_type = ev.get("type", "unknown")
                    ev_val = ev.get("value")
                    evidence_list.append({
                        "evidence_id": f"ev:{mid}:{rel_dim}:{ev_type}",
                        "merchant_id": mid,
                        "dimension": rel_dim,
                        "evidence_type": ev_type,
                        "value_numeric": ev_val if isinstance(ev_val, (int, float)) else None,
                        "value_text": ev_val if isinstance(ev_val, str) else None,
                        "value_boolean": ev_val if isinstance(ev_val, bool) else None,
                        "unit": None,
                        "reference_type": None,
                        "reference_ids": [],
                        "source_kind": sk,
                        "observed_at": None,
                    })

            # -- merchant_complaints --
            for i, comp in enumerate(p.get("complaints", [])):
                date_str = comp.get("date")
                complaints.append({
                    "complaint_id": f"cmp:{mid}:{i}",
                    "merchant_id": mid,
                    "category": comp["category"],
                    "severity": comp.get("severity", "medium"),
                    "text": comp["text"],
                    "occurred_on": date_str if date_str else None,
                    "review_id": None,
                    "source_kind": _resolve_source_kind(
                        data_sources.get("complaints_delivery_text")),
                })

            # -- reviews (real + synthetic) --
            for i, rv in enumerate(p.get("reviews", [])):
                sc = rv.get("score")
                reviews.append({
                    "review_id": f"{mid}_rv{i}", "merchant_id": mid,
                    "rating": sc, "text": rv.get("text") or "",
                    "sentiment": _sentiment(sc), "source_page": "foody",
                    "source_kind": "real",
                    "total_like": 0, "created_at": NOW,
                })
            for i, rv in enumerate(p.get("synthetic_reviews", [])):
                sc = rv.get("score")
                reviews.append({
                    "review_id": f"{mid}_srv{i}", "merchant_id": mid,
                    "rating": sc, "text": rv.get("text") or "",
                    "sentiment": _sentiment(sc), "source_page": "synthetic",
                    "source_kind": "synthetic",
                    "total_like": 0, "created_at": NOW,
                })

            # -- delivery_feedbacks --
            for i, d in enumerate(p.get("delivery_feedback", [])):
                deliveries.append({
                    "feedback_id": f"{mid}_df{i}", "merchant_id": mid,
                    "driver_id": f"drv_{mid}_{i}",
                    "rating": 5 if d.get("on_time") else 3,
                    "comment": d.get("text") or "",
                    "on_time": d.get("on_time"),
                    "issue": d.get("issue"),
                    "source_kind": "synthetic",
                    "created_at": NOW,
                })

    return {
        "merchants": merchants,
        "operational_metrics": ops,
        "merchant_profiles": profiles,
        "merchant_ratings": ratings_list,
        "merchant_dimension_calculations": calculations,
        "merchant_dimension_evidence": evidence_list,
        "merchant_complaints": complaints,
        "reviews": reviews,
        "delivery_feedbacks": deliveries,
    }


def build_menu_and_images(cat, valid_ids):
    """menu_items + food_images tu crawled (menu day du). 1 anh dai dien/mon."""
    menu, images = [], []
    for fp in glob.glob(str(ROOT / "data/crawled/*.json")):
        r = json.load(open(fp, encoding="utf-8"))
        mid = r["merchant_id"]
        if mid not in valid_ids:
            continue
        seen = set()
        for g in r.get("menu", []):
            for d in g.get("dishes", []):
                did = str(d.get("id") or "")
                item_id = f"{mid}::{did}"
                if not did or item_id in seen:
                    continue
                seen.add(item_id)
                price_obj = d.get("price") or {}
                price = price_obj.get("value")
                discount = price_obj.get("discount_price")
                photos = d.get("photos") or []
                img = photos[-1]["value"] if photos else None
                total_like = d.get("total_like", 0) or 0
                menu.append({
                    "item_id": item_id, "merchant_id": mid,
                    "name": d.get("name") or "N/A",
                    "price": int(price) if price else 0,
                    "discount_price": int(discount) if discount else None,
                    "description": d.get("description") or None,
                    "category": g.get("dish_type_name"),
                    "image_url": img,
                    "total_like": total_like,
                    "has_photo": img is not None,
                    "is_available": True,
                })
                if img:
                    images.append({
                        "image_id": f"img_{item_id}", "merchant_id": mid,
                        "item_id": item_id, "url": img,
                        "dish_image_quality": None,
                    })
    return {"menu_items": menu, "food_images": images}
