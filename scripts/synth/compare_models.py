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

OUTDIR = Path("data/synthetic/model_comparison")
# 3 quan mau dai dien: doi thu fast-food / diagnosis / variety
SAMPLES = ["10341", "68814", "126520"]


def main():
    models = available_models()
    if not models:
        print("CHUA co model nao duoc cau hinh trong .env. Xem .env.example.")
        return
    print(f"models configured: {models}")
    print(f"samples: {SAMPLES}\n")
    OUTDIR.mkdir(parents=True, exist_ok=True)

    summary = []
    for mid in SAMPLES:
        for mk in models:
            try:
                data, meta = generate_for(mk, mid)
                (OUTDIR / f"{mid}__{mk}.json").write_text(
                    json.dumps({"meta": meta, "data": data}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                row = {"merchant": mid, "model": mk, "ok": True,
                       "latency_s": meta["latency_s"], "tokens": meta.get("tokens"),
                       **meta["counts"]}
                print(f"[OK] {mid} {mk:14} {meta['latency_s']}s counts={meta['counts']}")
            except Exception as e:
                row = {"merchant": mid, "model": mk, "ok": False, "error": str(e)[:120]}
                print(f"[FAIL] {mid} {mk:14} {str(e)[:100]}")
            summary.append(row)
            time.sleep(1)

    (OUTDIR / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsummary -> {OUTDIR/'_summary.json'}")
    print("Xem cac file {mid}__{model}.json de danh gia chat luong text va chon model.")


if __name__ == "__main__":
    main()
