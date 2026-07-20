"""Precompute 2 attribute cho Merchant Profile:
- trending_dishes: theo (city, cuisine) — mon pho bien nhat (theo total_like tich luy tu menu that).
- competitors: theo merchant — cac quan cung cuisine, gan nhat (haversine tren lat/lng).

Output:
- data/profile_cache/trending_by_cluster.json  (key "city||cuisine" -> [dish,...])
- data/profile_cache/competitors_by_merchant.json (merchant_id -> [ {id,name,dist_km}, ... ])
"""
import json
import glob
import math
from collections import defaultdict
from pathlib import Path

CRAWLED = Path("data/crawled")
UNIQUE = Path("data/merchants_unique.jsonl")
OUTDIR = Path("data/profile_cache")


def load_catalog():
    cat = {}
    for line in UNIQUE.open(encoding="utf-8"):
        r = json.loads(line)
        if str(r.get("merchant_id", "")).isdigit():
            cat[r["merchant_id"]] = r
    return cat


def to_int_like(v):
    """total_like dang '500+' / '4' / None -> int."""
    if not v:
        return 0
    s = str(v).replace("+", "").replace(".", "").strip()
    return int(s) if s.isdigit() else 0


def build_trending(cat):
    # gom dish theo (city, cuisine): ten -> tong like + so quan ban
    cluster = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # name -> [likes, n_merchants]
    for fp in glob.glob("data/crawled/*.json"):
        r = json.load(open(fp, encoding="utf-8"))
        mid = r["merchant_id"]
        c = cat.get(mid)
        if not c:
            continue
        key = f"{c.get('city')}||{c.get('cuisine')}"
        for g in r.get("menu", []):
            for d in g.get("dishes", []):
                name = (d.get("name") or "").strip()
                if len(name) < 2:
                    continue
                cluster[key][name][0] += to_int_like(d.get("total_like"))
                cluster[key][name][1] += 1
    trending = {}
    for key, dishes in cluster.items():
        ranked = sorted(dishes.items(), key=lambda x: (-x[1][0], -x[1][1]))
        trending[key] = [{"dish": n, "total_likes": v[0], "sold_by_n_merchants": v[1]}
                         for n, v in ranked[:10]]
    return trending


def haversine(la1, lo1, la2, lo2):
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def build_competitors(cat):
    # nhom theo (city, cuisine) roi tim gan nhat trong nhom
    groups = defaultdict(list)
    for mid, c in cat.items():
        la, lo = c.get("merchant_lat"), c.get("merchant_lng")
        if la and lo:
            groups[(c.get("city"), c.get("cuisine"))].append((mid, c.get("merchant_name"), la, lo))
    comp = {}
    for members in groups.values():
        for mid, name, la, lo in members:
            dists = []
            for mid2, name2, la2, lo2 in members:
                if mid2 == mid:
                    continue
                d = haversine(la, lo, la2, lo2)
                if d <= 8.0:  # cung khu vuc <=8km
                    dists.append({"id": mid2, "name": name2, "dist_km": round(d, 2)})
            dists.sort(key=lambda x: x["dist_km"])
            comp[mid] = dists[:5]
    return comp


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cat = load_catalog()
    trending = build_trending(cat)
    comp = build_competitors(cat)
    (OUTDIR / "trending_by_cluster.json").write_text(
        json.dumps(trending, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUTDIR / "competitors_by_merchant.json").write_text(
        json.dumps(comp, ensure_ascii=False), encoding="utf-8")
    with_comp = sum(1 for v in comp.values() if v)
    print(f"trending clusters: {len(trending)}")
    print(f"competitors: {len(comp)} merchants ({with_comp} co >=1 competitor)")


if __name__ == "__main__":
    main()
