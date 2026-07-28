"""Real-browser UX test for the Customer Agent (Playwright/Chromium).

Drives the live FE (localhost:5173) through >=6 real queries in a real Chromium,
measuring PERCEIVED timing (submit -> first answer char -> done) the way a user
experiences it, plus result-card count, scroll/stream UX notes, and screenshots.

Why not the Playwright MCP: it is registered in config but not exposed to the
session/subagent tool namespace, so we drive Chromium directly via the venv.

Run (env ai_restaurant):
  PYTHONUTF8=1 python scripts/browser_test_customer.py
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/customer/chat"
SHOTS = Path(__file__).resolve().parent.parent.parent / "plans" / "reports" / "browser-shots"
SHOTS.mkdir(parents=True, exist_ok=True)

# (id, query, geolocation or None). Coords mock the browser geolocation the FE sends.
QUERIES = [
    ("Q1-pho-CauGiay", "Tìm quán phở gần Cầu Giấy", (21.036, 105.790)),
    ("Q2-cay-CauGiay", "Gợi ý quán cay ngon cho buổi tối ở Cầu Giấy", (21.036, 105.790)),
    ("Q3-trasua-GiaLam", "Tìm quán trà sữa gần đây", (21.028, 105.948)),
    ("Q4-sushi-MocChau", "Tìm quán sushi Nhật Bản chính gốc ở Mộc Châu", None),
    ("Q5-weather", "Thời tiết Hà Nội hôm nay thế nào?", None),
    ("Q6-nodiacritics", "tim cho an ngon o cau giay gia duoi 50k nha", None),
]


def run_query(context, qid: str, query: str, loc) -> dict:
    """One fresh page per query (clean chat state). Returns perceived timing + captures."""
    page = context.new_page()
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_selector('textarea[aria-label="Tin nhắn"]', timeout=15000)

    ta = page.locator('textarea[aria-label="Tin nhắn"]')
    ta.fill(query)
    t0 = time.perf_counter()
    ta.press("Enter")

    # TTFT: first non-empty char in the (only) agent bubble's text node.
    agent_text = page.locator(".cmsg--agent .cmsg__text").last
    ttft = None
    deadline = time.perf_counter() + 90
    while time.perf_counter() < deadline:
        try:
            if agent_text.count() and agent_text.inner_text(timeout=150).strip():
                ttft = time.perf_counter() - t0
                break
        except Exception:  # noqa: BLE001 - node may not exist yet
            pass

    # Completion: the copy button only renders when streaming stops (!msg.streaming).
    total = None
    try:
        page.locator(".cmsg--agent").last.locator(".cmsg__copy").wait_for(timeout=90000)
        total = time.perf_counter() - t0
    except Exception:  # noqa: BLE001
        total = (time.perf_counter() - t0) if ttft else None

    # Capture answer text + result-card count.
    answer = ""
    cards = 0
    try:
        answer = agent_text.inner_text(timeout=1000).strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        cards = page.locator(".cmsg--agent").last.locator(".cmsg__results .rcard").count()
    except Exception:  # noqa: BLE001
        pass

    # Scroll-smoothness probe: rapid scrollTo then back, measure if it throws / lags.
    scroll_ok = True
    try:
        stream = page.locator(".cchat__stream")
        stream.evaluate("el => { el.scrollTo(0, el.scrollHeight); el.scrollTo(0, 0); }")
    except Exception:  # noqa: BLE001
        scroll_ok = False

    shot = SHOTS / f"{qid}.png"
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:  # noqa: BLE001
        shot = None

    page.close()
    return {
        "id": qid, "query": query, "has_location": loc is not None,
        "ttft_s": round(ttft, 2) if ttft else None,
        "total_s": round(total, 2) if total else None,
        "stream_s": round(total - ttft, 2) if (ttft and total) else None,
        "result_cards": cards, "scroll_ok": scroll_ok,
        "answer_preview": answer[:200], "screenshot": str(shot) if shot else None,
    }


def main() -> None:
    print("=" * 84)
    print("BROWSER UX TEST — real Chromium via Playwright (FE localhost:5173)")
    print("=" * 84)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for qid, query, loc in QUERIES:
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                geolocation={"latitude": loc[0], "longitude": loc[1], "accuracy": 50} if loc else None,
                permissions=["geolocation"] if loc else [],
            )
            print(f"\n→ {qid}: {query!r}" + (f"  @ {loc}" if loc else "  (no location)"))
            try:
                r = run_query(ctx, qid, query, loc)
            except Exception as exc:  # noqa: BLE001
                r = {"id": qid, "query": query, "error": f"{type(exc).__name__}: {exc}"}
            results.append(r)
            if "error" in r:
                print(f"   ERROR: {r['error']}")
                continue
            print(f"   TTFT={r['ttft_s']}s  total={r['total_s']}s  stream={r['stream_s']}s  "
                  f"cards={r['result_cards']}  scroll_ok={r['scroll_ok']}")
            print(f"   ANSWER: {r['answer_preview']}")
            ctx.close()
        browser.close()

    out = SHOTS.parent / "browser-test-results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")
    print("\nPer-query perceived totals:")
    for r in results:
        if "error" not in r:
            print(f"  {r['id']:22s} TTFT={r['ttft_s']}s total={r['total_s']}s cards={r['result_cards']}")


if __name__ == "__main__":
    main()
