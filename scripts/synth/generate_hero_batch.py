"""Sinh du lieu text synthetic cho TAT CA hero merchant bang model da chon.
Mac dinh model = fpt-deepseek (thang cuoc so sanh: nhanh nhat, tuan thu luat, chat luong tot).
Resume: bo qua merchant da co file. Output: data/synthetic/text/{merchant_id}.json

Usage: python scripts/synth/generate_hero_batch.py [--model fpt-deepseek]
"""
import argparse
import json
import time
from pathlib import Path

from generate_text_data import generate_for

HERO = Path("data/synthetic/hero_set.json")
OUTDIR = Path("data/synthetic/text")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="fpt-deepseek")
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    hero = json.loads(HERO.read_text(encoding="utf-8"))["merchants"]
    print(f"generating text data for {len(hero)} hero merchants with model={args.model}\n")

    ok = fail = skip = 0
    for i, m in enumerate(hero):
        mid = m["merchant_id"]
        out = OUTDIR / f"{mid}.json"
        if out.exists():
            skip += 1
            continue
        try:
            data, meta = generate_for(args.model, mid)
            out.write_text(json.dumps(
                {"merchant_id": mid, "model": meta["model_id"],
                 "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **data},
                ensure_ascii=False, indent=1), encoding="utf-8")
            ok += 1
            print(f"[{i+1}/{len(hero)}] {mid} {m['name'][:30]:30} "
                  f"{meta['latency_s']}s counts={meta['counts']}")
        except Exception as e:
            fail += 1
            print(f"[{i+1}/{len(hero)}] {mid} ERROR {type(e).__name__}: {str(e)[:100]}")
        time.sleep(1)

    print(f"\ndone. ok={ok} fail={fail} skipped={skip} -> {OUTDIR}")


if __name__ == "__main__":
    main()
