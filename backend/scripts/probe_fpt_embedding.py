"""Probe whether FPT_API_KEY authorizes the FPT embeddings endpoint (Path A / phase-03).

Standalone — reads FPT_API_KEY + FPT_BASE_URL from os.environ ONLY (does NOT import
core.settings, does NOT read .env — the user manages keys). FPT Cloud AI is OpenAI-compatible
(``OpenAI(base_url=FPT_BASE_URL, api_key=FPT_API_KEY)``), so embeddings live at
``{FPT_BASE_URL}/embeddings``. The embedding model id is undocumented in public docs, so this
probes a candidate list and reports status + dimensions + a vector head + latency for each.

Exit 0 if any model works (authorized + returns vectors), 1 if none / unauthorized.

Usage:
    python backend/scripts/probe_fpt_embedding.py
    python backend/scripts/probe_fpt_embedding.py --model bge-m3 --input "phở bò,bún chả"
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - env-dependent
    print("FAIL: the 'openai' package is not installed in this env.")
    sys.exit(2)

DEFAULT_INPUT = ["phở bò", "bún chả"]
# Candidate FPT embedding model ids (public docs don't list them). First that returns 200 wins.
CANDIDATE_MODELS = [
    "Qwen3-Embedding-8B",
    "bge-m3",
    "text-embedding-3-small",
    "text-embedding-3-large",
    "FPT-VN-Embedding",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe the FPT embeddings endpoint.")
    ap.add_argument("--model", default=None, help="test one model id (skip the candidate sweep)")
    ap.add_argument("--input", default=None, help="comma-separated sample texts")
    args = ap.parse_args()

    api_key = os.environ.get("FPT_API_KEY")
    base_url = os.environ.get("FPT_BASE_URL")
    if not api_key or not base_url:
        print("FAIL: FPT_API_KEY and FPT_BASE_URL must be set in the environment.")
        print("      (this script reads os.environ only — it does NOT read .env)")
        return 1

    print(f"FPT_BASE_URL = {base_url}")
    print(f"FPT_API_KEY  = {api_key[:6]}...{api_key[-3:]}  (masked)")
    inputs = [s.strip() for s in args.input.split(",")] if args.input else DEFAULT_INPUT
    models = [args.model] if args.model else CANDIDATE_MODELS

    client = OpenAI(base_url=base_url, api_key=api_key)
    any_ok = False
    for m in models:
        try:
            t0 = time.perf_counter()
            resp = client.embeddings.create(model=m, input=inputs)
            ms = (time.perf_counter() - t0) * 1000
            vecs = [d.embedding for d in resp.data]
            dim = len(vecs[0]) if vecs else 0
            head = [round(x, 4) for x in vecs[0][:5]] if vecs else []
            print(f"\n[OK] model={m}  dim={dim}  latency={ms:.0f}ms  n={len(vecs)}")
            print(f"     vec[0][:5] = {head}")
            any_ok = True
        except Exception as exc:  # noqa: BLE001 — report every failure, don't abort the sweep
            msg = str(exc).replace("\n", " ")[:160]
            print(f"\n[NO] model={m}  -> {type(exc).__name__}: {msg}")

    verdict = "at least one embedding model works." if any_ok else "no model succeeded (unauthorized or wrong id)."
    print("\nRESULT: " + verdict)
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
