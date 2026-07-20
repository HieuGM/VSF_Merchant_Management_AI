"""Cham Image Quality cho hero-set bang Vision LLM (nim-qwen ho tro anh).
Moi quan: chon 3 mon pho bien nhat co anh HD -> 1 call vision -> score 0-1 + notes.
Output: data/profile_cache/vision/{merchant_id}.json  (resume: bo qua file da co)

Usage: python scripts/profile/vision_image_score.py
"""
import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

HERO = Path("data/synthetic/hero_set.json")
CRAWLED = Path("data/crawled")
OUT = Path("data/profile_cache/vision.jsonl")

PROMPT = ("Bạn là chuyên gia đánh giá ảnh món ăn trên app giao đồ ăn. "
          "Dưới đây là vài ảnh món của một quán. Đánh giá TỔNG THỂ chất lượng hình ảnh "
          "(ánh sáng, độ nét, bố cục/trình bày, độ hấp dẫn/thèm ăn). "
          "Trả về DUY NHẤT JSON: {\"score\": <0..1>, \"notes\": \"<nhận xét ngắn tiếng Việt>\"}")


def pick_images(crawled, k=3):
    dishes = [d for g in crawled.get("menu", []) for d in g.get("dishes", [])]
    withhd = []
    for d in dishes:
        hd = [p for p in (d.get("photos") or []) if p.get("width", 0) >= 400]
        if hd:
            likes = str(d.get("total_like") or "0").replace("+", "").replace(".", "")
            withhd.append((int(likes) if likes.isdigit() else 0, hd[-1]["value"]))
    withhd.sort(key=lambda x: -x[0])
    return [u for _, u in withhd[:k]]


def score_merchant(client, model, crawled):
    imgs = pick_images(crawled)
    if not imgs:
        return {"score": None, "notes": "no images", "n_images": 0}
    content = [{"type": "text", "text": PROMPT}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in imgs]
    r = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": content}], max_tokens=500)
    text = r.choices[0].message.content or ""
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {"score": None, "notes": text[:200]}
    data["n_images"] = len(imgs)
    return data


def main():
    base, key, model = os.getenv("NIM_BASE_URL"), os.getenv("NIM_API_KEY"), os.getenv("NIM_MODEL")
    if not (base and key and model):
        print("NIM chua cau hinh trong .env")
        return
    client = OpenAI(base_url=base, api_key=key)
    hero = json.loads(HERO.read_text(encoding="utf-8"))["merchants"]

    rows, ok, fail = [], 0, 0
    for i, m in enumerate(hero):
        mid = m["merchant_id"]
        try:
            crawled = json.load(open(CRAWLED / f"{mid}.json", encoding="utf-8"))
            res = score_merchant(client, model, crawled)
            rows.append({"merchant_id": mid, **res})
            ok += 1
            print(f"[{i+1}/{len(hero)}] {mid} {m['name'][:28]:28} score={res.get('score')} imgs={res.get('n_images')}")
        except Exception as e:
            fail += 1
            print(f"[{i+1}/{len(hero)}] {mid} FAIL {str(e)[:90]}")
        time.sleep(1)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\ndone. ok={ok} fail={fail} -> {OUT}")


if __name__ == "__main__":
    main()
