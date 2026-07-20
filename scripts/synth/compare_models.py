"""So sanh cac model LLM (NIM qwen, FPT qwen, FPT deepseek) tren vai hero merchant mau.
Chay moi model tren cung input -> luu output canh nhau + bang so sanh (latency, so luong,
tinh hop le JSON) de chon model tot nhat cho batch.

Usage: python scripts/synth/compare_models.py
Yeu cau: cau hinh key trong .env (xem .env.example).
"""
import json
import time
from pathlib import Path

from llm_client import available_models
from generate_text_data import generate_for

OUT = Path("data/synthetic/model_comparison.jsonl")
# 3 quan mau dai dien: doi thu fast-food / diagnosis / variety
SAMPLES = ["10341", "68814", "126520"]


def main():
    models = available_models()
    if not models:
        print("CHUA co model nao duoc cau hinh trong .env. Xem .env.example.")
        return
    print(f"models configured: {models}")
    print(f"samples: {SAMPLES}\n")

    rows = []
    for mid in SAMPLES:
        for mk in models:
            try:
                data, meta = generate_for(mk, mid)
                rows.append({"merchant_id": mid, "model": mk, "ok": True,
                             "meta": meta, "data": data})
                print(f"[OK] {mid} {mk:14} {meta['latency_s']}s counts={meta['counts']}")
            except Exception as e:
                rows.append({"merchant_id": mid, "model": mk, "ok": False, "error": str(e)[:120]})
                print(f"[FAIL] {mid} {mk:14} {str(e)[:100]}")
            time.sleep(1)

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\ncomparison -> {OUT} (mỗi dòng 1 merchant×model; xem 'meta.latency_s' + 'data' để chọn model)")


if __name__ == "__main__":
    main()
