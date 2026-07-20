"""Chon hero-set (~18 merchant) de sinh du lieu text sau (complaints, review-bu).
Tieu chi:
- Cum doi thu (competitor cluster): fast-food HCM cung phan khuc -> phuc vu UC-03.
- Nhom diagnosis: HCM Mon Viet, trai rating, co review that -> UC-01/02.
- Nhom da dang: moi thanh pho khac 1-2 quan -> Customer Agent search variety.
Chi chon quan co review that >=5 & menu >=10 (du lam nen). Output: data/synthetic/hero_set.json
"""
import json
import glob
from pathlib import Path

CRAWLED = Path("data/crawled")
OUT = Path("data/synthetic/hero_set.json")


def load():
    cat = {}
    for line in open("data/merchants_unique.jsonl", encoding="utf-8"):
        r = json.loads(line)
        cat[r["merchant_id"]] = r
    cands = {}
    for fp in glob.glob("data/crawled/*.json"):
        r = json.load(open(fp, encoding="utf-8"))
        mid = r["merchant_id"]
        nrev = len(r.get("reviews", []))
        d = sum(len(g.get("dishes", [])) for g in r.get("menu", []))
        if nrev >= 5 and d >= 10 and mid in cat:
            c = cat[mid]
            cands[mid] = {
                "merchant_id": mid, "name": r.get("merchant_name"),
                "city": c.get("city"), "cuisine": c.get("cuisine"),
                "category": c.get("category"), "rating": r.get("shopeefood_rating_avg"),
                "reviews": nrev, "dishes": d,
            }
    return cands


def pick(cands):
    chosen, reasons = [], {}

    def add(mid, why):
        if mid in cands and mid not in chosen:
            chosen.append(mid)
            reasons[mid] = why

    # 1) Cum doi thu fast-food HCM (UC-03 Competitor Analysis)
    ff = [m for m in cands.values()
          if m["city"] == "TP. HCM"
          and any(k in m["name"].lower() for k in ["popeyes", "burger king", "mcdonald", "lotteria", "kfc", "gà rán"])]
    for m in sorted(ff, key=lambda x: -x["reviews"])[:5]:
        add(m["merchant_id"], "competitor-cluster: fast-food HCM (UC-03)")

    # 2) Diagnosis HCM Mon Viet, trai rating (UC-01/02)
    mv = sorted([m for m in cands.values()
                 if m["city"] == "TP. HCM" and (m["cuisine"] or "").startswith("Món Việt")],
                key=lambda x: (x["rating"] or 0))
    for m in (mv[:2] + mv[-3:]):  # 2 thap nhat + 3 cao nhat
        add(m["merchant_id"], "diagnosis/recommendation: HCM Món Việt rating-spread (UC-01/02)")

    # 3) Da dang theo thanh pho khac (Customer Agent search/preference)
    seen_city = {"TP. HCM"}
    for m in sorted(cands.values(), key=lambda x: -x["reviews"]):
        city = m["city"]
        if city not in seen_city:
            add(m["merchant_id"], f"variety: {city} (UC-04/05)")
            seen_city.add(city)
        if len(chosen) >= 18:
            break

    return chosen, reasons


def main():
    cands = load()
    chosen, reasons = pick(cands)
    out = {"count": len(chosen), "merchants": [
        {**cands[mid], "why": reasons[mid]} for mid in chosen]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"selected {len(chosen)} hero merchants -> {OUT}\n")
    for mid in chosen:
        m = cands[mid]
        print(f"  {mid} | {m['name'][:34]:34} | {m['city']:9} | r={m['rating']} "
              f"rev={m['reviews']} dish={m['dishes']} | {reasons[mid]}")


if __name__ == "__main__":
    main()
