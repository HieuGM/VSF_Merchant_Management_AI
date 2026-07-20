"""Kiem tra ky toan bo Merchant Profile -> bao cao pass/fail chi tiet.
Kiem: truong bat buoc, range score, evidence, referential integrity (competitor id ton tai),
hero co du complaints/delivery/vision, phat hien anomaly. In summary + ghi validation_report.json
"""
import json
from pathlib import Path

PROFILES = Path("data/profiles.jsonl")
DIMS = ["food_quality", "image_quality", "delivery_quality", "packaging",
        "service", "waiting_time", "menu_diversity", "price_level"]


def main():
    profiles = {}
    with PROFILES.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            profiles[p["merchant_id"]] = p
    ids = set(profiles)
    issues = []

    def flag(mid, kind, detail):
        issues.append({"merchant_id": mid, "kind": kind, "detail": detail})

    tier_c = {"hero": 0, "background": 0}
    empty_menu = no_meta_geo = no_reviews = 0
    dim_basis = {}
    comp_broken = trending_empty = 0
    vision_hero = 0

    for mid, p in profiles.items():
        tier_c[p.get("tier", "background")] += 1
        md = p.get("metadata", {})
        loc = md.get("location", {})
        # truong bat buoc metadata
        if not md.get("name"):
            flag(mid, "missing", "metadata.name")
        if not (loc.get("lat") and loc.get("lng")):
            no_meta_geo += 1
        if not md.get("source_url"):
            flag(mid, "missing", "source_url")
        # dimensions
        dims = p.get("dimensions", {})
        for dn in DIMS:
            d = dims.get(dn)
            if not d:
                flag(mid, "missing_dimension", dn)
                continue
            s = d.get("score")
            if s is None or not (0.0 <= s <= 1.0):
                flag(mid, "score_out_of_range", f"{dn}={s}")
            if not d.get("evidence"):
                flag(mid, "no_evidence", dn)
            dim_basis.setdefault(dn, {}).setdefault(d.get("basis", "?"), 0)
            dim_basis[dn][d.get("basis", "?")] += 1
        # overall
        ov = p.get("overall_score")
        if ov is None or not (0.0 <= ov <= 1.0):
            flag(mid, "overall_bad", str(ov))
        # menu / reviews
        if not p.get("menu"):
            empty_menu += 1
        if not p.get("reviews") and not p.get("synthetic_reviews"):
            no_reviews += 1
        # attributes referential integrity
        for comp in p.get("attributes", {}).get("competitors", []):
            if comp.get("id") not in ids:
                comp_broken += 1
        if not p.get("attributes", {}).get("trending_dishes"):
            trending_empty += 1
        # hero-specific
        if p.get("tier") == "hero":
            if not p.get("complaints"):
                flag(mid, "hero_no_complaints", mid)
            if not p.get("delivery_feedback"):
                flag(mid, "hero_no_delivery_feedback", mid)
            if p["dimensions"]["image_quality"]["basis"].startswith("hero: vision"):
                vision_hero += 1

    # in bao cao
    print(f"=== PROFILE VALIDATION ===")
    print(f"total profiles: {len(profiles)} | hero: {tier_c['hero']} background: {tier_c['background']}")
    print(f"empty menu: {empty_menu} | no reviews (real+synth): {no_reviews} | missing geo: {no_meta_geo}")
    print(f"competitor broken refs: {comp_broken} | trending empty: {trending_empty}")
    print(f"hero with vision image score: {vision_hero}/{tier_c['hero']}")
    print(f"\nissues (blocking-ish): {len(issues)}")
    from collections import Counter
    kinds = Counter(i["kind"] for i in issues)
    for k, n in kinds.most_common():
        print(f"  {k}: {n}")
    print("\ndimension scoring basis coverage:")
    for dn in DIMS:
        print(f"  {dn}: {dict(dim_basis.get(dn, {}))}")

    report = {"total": len(profiles), "tiers": tier_c, "empty_menu": empty_menu,
              "no_reviews": no_reviews, "missing_geo": no_meta_geo,
              "competitor_broken_refs": comp_broken, "trending_empty": trending_empty,
              "vision_hero": vision_hero, "issue_counts": dict(kinds),
              "issues_sample": issues[:30]}
    Path("data/profiles_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    verdict = "PASS" if not [i for i in issues if i["kind"] not in ("missing", "hero_no_complaints")] else "REVIEW"
    print(f"\nVERDICT: {verdict} (chi tiet -> data/profiles_validation_report.json)")


if __name__ == "__main__":
    main()
