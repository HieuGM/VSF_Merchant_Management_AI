"""Crawler chinh: bo sung du lieu thieu cho tung merchant trong merchants_unique.jsonl.
- ShopeeFood (Playwright, bat response thu dong): get_detail (rating that, restaurant_id,
  brand, sdt) + get_delivery_dishes (menu day du: mon/gia/anh).
- Foody (HTTP thuong, cung slug): reviews text + rating tong quan.
Ghi tung merchant ra data/crawled/{merchant_id}.json. Resume: bo qua file da co.

Usage: python scripts/crawl/crawl_merchants.py [--limit N] [--start N] [--delay 1.5]
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

from foody_review_parser import parse_foody_html
from playwright.sync_api import sync_playwright

SRC = Path("data/merchants_unique.jsonl")
OUTDIR = Path("data/crawled")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_merchants():
    with SRC.open(encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def slug_path(source_url):
    # https://shopeefood.vn/ho-chi-minh/vitamin-bar-i -> ho-chi-minh/vitamin-bar-i
    return source_url.split("shopeefood.vn/")[-1].strip("/")


def fetch_foody_reviews(path):
    url = f"https://www.foody.vn/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                    "Accept-Language": "vi-VN,vi;q=0.9"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return parse_foody_html(raw)
    except Exception as e:
        return {"error": str(e), "reviews": []}


def crawl_shopeefood(page, source_url, max_wait_ms=12000):
    """Nav vao trang, bat detail + dishes; dung ngay khi co du 2 response
    (khong cho networkidle -> nhanh hon nhieu)."""
    caught = {}

    def on_response(resp):
        u = resp.url
        if resp.status != 200:
            return
        if "get_detail" in u and "detail" not in caught:
            try: caught["detail"] = resp.json()
            except Exception: pass
        elif "get_delivery_dishes" in u and "dishes" not in caught:
            try: caught["dishes"] = resp.json()
            except Exception: pass

    page.on("response", on_response)
    try:
        page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
        # poll cho den khi co du detail+dishes hoac het gio
        waited = 0
        while ("detail" not in caught or "dishes" not in caught) and waited < max_wait_ms:
            page.wait_for_timeout(250)
            waited += 250
    except Exception as e:
        caught["_nav_error"] = str(e)
    page.remove_listener("response", on_response)
    return caught


def build_record(m, sf, foody):
    detail = ((sf.get("detail") or {}).get("reply") or {}).get("delivery_detail") or {}
    dishes = ((sf.get("dishes") or {}).get("reply") or {}).get("menu_infos") or []
    rating = detail.get("rating") or {}
    return {
        "merchant_id": m.get("merchant_id"),
        "merchant_name": m.get("merchant_name"),
        "source_url": m.get("source_url"),
        "restaurant_id": detail.get("restaurant_id"),
        "brand_id": detail.get("brand_id"),
        "is_quality_merchant": detail.get("is_quality_merchant"),
        "phones": detail.get("phones"),
        "shopeefood_rating_avg": rating.get("avg"),
        "shopeefood_total_review": rating.get("total_review"),
        "total_order": detail.get("total_order"),
        "menu": dishes,
        "foody_rating": foody.get("foody_rating"),
        "foody_review_count": foody.get("foody_review_count"),
        "reviews": foody.get("reviews", []),
        "crawl_errors": {k: v for k, v in {
            "nav": sf.get("_nav_error"), "foody": foody.get("error")}.items() if v},
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    merchants = load_merchants()
    # chi crawl quan co merchant_id dang so (goi API duoc)
    merchants = [m for m in merchants if str(m.get("merchant_id", "")).isdigit()]
    batch = merchants[args.start:args.start + args.limit]
    print(f"crawling {len(batch)} merchants (start={args.start}, delay={args.delay}s)")

    ok = fail = skip = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(user_agent=UA, locale="vi-VN")
        page = ctx.new_page()
        for i, m in enumerate(batch):
            mid = m["merchant_id"]
            out = OUTDIR / f"{mid}.json"
            if out.exists():
                skip += 1
                continue
            try:
                sf = crawl_shopeefood(page, m["source_url"])
                foody = fetch_foody_reviews(slug_path(m["source_url"]))
                rec = build_record(m, sf, foody)
                out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                n_menu = sum(len(g.get("dishes", [])) for g in rec["menu"])
                status = "OK" if (n_menu or rec["reviews"]) else "EMPTY"
                if status == "OK": ok += 1
                else: fail += 1
                print(f"[{i+1}/{len(batch)}] {mid} {status} "
                      f"rating={rec['shopeefood_rating_avg']} dishes={n_menu} "
                      f"reviews={len(rec['reviews'])}")
            except Exception as e:
                fail += 1
                print(f"[{i+1}/{len(batch)}] {mid} ERROR {type(e).__name__}: {e}")
            time.sleep(args.delay)
        browser.close()
    print(f"\ndone. ok={ok} empty={fail} skipped={skip}")


if __name__ == "__main__":
    main()
