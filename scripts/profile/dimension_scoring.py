"""Ham thuan tinh 8 scored dimension (score 0..1 + evidence) cho Merchant Profile.
Input: cac nguon da hop nhat cho 1 merchant. Evidence luon kem so lieu de truy vet.

Nguyen tac: hero (co reviews/complaints/delivery text) -> score giau evidence;
background -> score tu rating + ops procedural. Moi dimension tra (score, evidence[], note).
"""


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def like_to_int(v):
    if not v:
        return 0
    s = str(v).replace("+", "").replace(".", "").strip()
    return int(s) if s.isdigit() else 0


def _rating_norm(crawled):
    """Rating chuan hoa 0..1: uu tien shopeefood (0-5), fallback foody (0-10)."""
    r5 = crawled.get("shopeefood_rating_avg")
    if r5:
        return clamp(r5 / 5.0)
    f10 = crawled.get("foody_rating")
    if f10:
        return clamp(f10 / 10.0)
    return 0.7  # mac dinh trung tinh


def _all_reviews(crawled, text):
    """Gop review that (Foody, score/10) + filled synthetic (score/10)."""
    revs = list(crawled.get("reviews", []))
    revs += text.get("filled_reviews", [])
    return revs


def _sentiment(reviews):
    pos = sum(1 for r in reviews if (r.get("score") or 0) >= 7)
    neg = sum(1 for r in reviews if 0 < (r.get("score") or 0) < 5)
    return pos, neg


def _complaints_by_cat(text):
    d = {}
    for c in text.get("complaints", []):
        d[c.get("category")] = d.get(c.get("category"), 0) + 1
    return d


def food_quality(crawled, ops, text):
    rn = _rating_norm(crawled)
    reviews = _all_reviews(crawled, text)
    pos, neg = _sentiment(reviews)
    dishes = [d for g in crawled.get("menu", []) for d in g.get("dishes", [])]
    likes = sorted((like_to_int(d.get("total_like")) for d in dishes), reverse=True)[:5]
    popularity = clamp((sum(likes) / len(likes) / 500.0) if likes else 0.0)
    cc = _complaints_by_cat(text)
    food_complaints = cc.get("chất_lượng_món", 0) + cc.get("món_nguội", 0)
    if reviews:
        senti = pos / (pos + neg) if (pos + neg) else 0.75
        score = 0.55 * rn + 0.30 * senti + 0.15 * popularity
    else:
        score = 0.85 * rn + 0.15 * popularity
    score = clamp(score - 0.03 * food_complaints)
    ev = [
        {"type": "rating", "value": crawled.get("shopeefood_rating_avg")},
        {"type": "positive_review_count", "value": pos},
        {"type": "negative_review_count", "value": neg},
        {"type": "top_dish_avg_likes", "value": round(sum(likes) / len(likes)) if likes else 0},
        {"type": "food_complaint_count", "value": food_complaints},
    ]
    return round(score, 3), ev, ("hero: reviews+complaints" if reviews else "background: rating proxy")


def image_quality(crawled, vision):
    """vision = dict {score, notes} neu da chay Vision LLM; else None -> heuristic."""
    if vision and vision.get("score") is not None:
        return round(clamp(vision["score"]), 3), [
            {"type": "vision_score", "value": vision["score"]},
            {"type": "vision_notes", "value": vision.get("notes", "")[:200]},
        ], "hero: vision LLM"
    dishes = [d for g in crawled.get("menu", []) for d in g.get("dishes", [])]
    n_photo = sum(1 for d in dishes if d.get("photos"))
    hd = sum(1 for d in dishes if any(p.get("width", 0) >= 750 for p in (d.get("photos") or [])))
    ratio_photo = (n_photo / len(dishes)) if dishes else 0.0
    ratio_hd = (hd / len(dishes)) if dishes else 0.0
    qm = 0.1 if crawled.get("is_quality_merchant") else 0.0
    score = clamp(0.45 * ratio_photo + 0.45 * ratio_hd + qm)
    ev = [
        {"type": "dishes_with_photo", "value": n_photo},
        {"type": "dishes_with_hd_photo", "value": hd},
        {"type": "is_quality_merchant", "value": bool(crawled.get("is_quality_merchant"))},
    ]
    return round(score, 3), ev, "heuristic: photo coverage"


def delivery_quality(ops, text):
    ds = ops.get("delivery_stats", {})
    on_time = ds.get("on_time_rate", 0.85)
    drv = ds.get("driver_rating", 4.3)
    dmin = ds.get("avg_delivery_minutes", 30)
    cc = _complaints_by_cat(text)
    late = cc.get("giao_hàng_trễ", 0)
    score = clamp(0.5 * on_time + 0.3 * (drv / 5.0) + 0.2 * (1 - clamp(dmin / 60.0)) - 0.03 * late)
    ev = [
        {"type": "on_time_rate", "value": on_time},
        {"type": "avg_delivery_minutes", "value": dmin},
        {"type": "driver_rating", "value": drv},
        {"type": "late_complaint_count", "value": late},
    ]
    return round(score, 3), ev, "delivery_stats + complaints"


def packaging(ops, text):
    ok = ops.get("delivery_stats", {}).get("packaging_ok_rate", 0.88)
    cc = _complaints_by_cat(text)
    pk = cc.get("đóng_gói_kém", 0)
    score = clamp(ok - 0.05 * pk)
    ev = [
        {"type": "packaging_ok_rate", "value": ok},
        {"type": "packaging_complaint_count", "value": pk},
    ]
    return round(score, 3), ev, "packaging_ok_rate + complaints"


def service(crawled, text):
    rn = _rating_norm(crawled)
    cc = _complaints_by_cat(text)
    svc = cc.get("thái_độ_phục_vụ", 0)
    score = clamp(rn - 0.06 * svc)
    ev = [
        {"type": "rating", "value": crawled.get("shopeefood_rating_avg")},
        {"type": "service_complaint_count", "value": svc},
    ]
    return round(score, 3), ev, "rating + service complaints"


def waiting_time(ops, catalog, text):
    prep = ops.get("operation_kpis", {}).get("avg_prep_minutes") or catalog.get("avg_prep_minutes") or 15
    cc = _complaints_by_cat(text)
    late = cc.get("giao_hàng_trễ", 0)
    # prep thap -> score cao (5 phut ~1.0, 45 phut ~0.0)
    score = clamp(1 - (prep - 5) / 40.0 - 0.03 * late)
    ev = [
        {"type": "avg_prep_minutes", "value": prep},
        {"type": "late_complaint_count", "value": late},
    ]
    return round(score, 3), ev, "prep time + complaints"


def menu_diversity(crawled):
    groups = crawled.get("menu", [])
    n_dish = sum(len(g.get("dishes", [])) for g in groups)
    n_type = len(groups)
    score = clamp(0.6 * clamp(n_dish / 80.0) + 0.4 * clamp(n_type / 8.0))
    ev = [
        {"type": "dish_count", "value": n_dish},
        {"type": "dish_type_count", "value": n_type},
    ]
    return round(score, 3), ev, "menu size + categories"


def price_level(ops, catalog, median_price):
    price = catalog.get("price")
    label = ops.get("price_level", "trung bình")
    ratio = round(price / median_price, 2) if (price and median_price) else 1.0
    # score = do "phu hop tui tien" (re -> cao); mang tinh positioning
    score = clamp(1.2 - ratio * 0.5)
    ev = [
        {"type": "price", "value": price},
        {"type": "cluster_median_price", "value": median_price},
        {"type": "price_ratio", "value": ratio},
        {"type": "price_level_label", "value": label},
    ]
    return round(score, 3), ev, "price vs cluster median (score=affordability)"
