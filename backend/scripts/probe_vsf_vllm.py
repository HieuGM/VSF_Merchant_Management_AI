"""Probe the VSF vLLM gateway (company model) — OAuth2 client_credentials + OpenAI-compatible API.

Standalone discovery tool. Run from a machine WITH network access to the gateway (it is behind
a company firewall — this dev shell got TCP timeout). Discovers:
  1. OAuth2 token (client_credentials grant) -> bearer access_token + expires_in
  2. GET /v1/models -> the model list
  3. (optional) POST /v1/chat/completions -> a tiny Vietnamese smoke test

Reads creds from args OR env (VSF_VLLM_BASE_URL, VSF_VLLM_TOKEN_URL, VSF_VLLM_CLIENT_ID,
VSF_VLLM_CLIENT_SECRET). NOTE: the OAuth TOKEN URL is NOT in the project console snippet —
find it on the same platform/IdP that issued the Client ID (often /oauth2/token, /oauth/token,
or a Keycloak /realms/<tenant>/protocol/openid-connect/token).

Usage:
    python backend/scripts/probe_vsf_vllm.py \\
        --base https://v-llm-core.uat.ntmh.vsf.services/gsm \\
        --token-url https://<idp-host>/<token-path> \\
        --client-id 40360ade-7d41-4128-89ca-366530e9696f \\
        --client-secret <secret> [--chat --model <a-model-id-from-the-list>]
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
    import httpx
except ImportError:  # pragma: no cover - env-dependent
    print("FAIL: the 'httpx' package is not installed in this env.")
    sys.exit(2)


def get_token(token_url: str, client_id: str, client_secret: str, timeout: float = 20.0):
    """OAuth2 client_credentials -> (access_token, expires_in, raw_json).

    Tries form-body client_id/client_secret first (RFC 6749), then HTTP Basic auth (some IdPs
    require it). Raises httpx.HTTPStatusError on failure."""
    form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    r = httpx.post(token_url, data=form, timeout=timeout)
    if r.status_code >= 400:  # retry with Basic auth header
        r = httpx.post(token_url, data={"grant_type": "client_credentials"},
                       auth=(client_id, client_secret), timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return j.get("access_token"), j.get("expires_in"), j


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe the VSF vLLM gateway (OAuth2 + OpenAI API).")
    ap.add_argument("--base", default=os.environ.get("VSF_VLLM_BASE_URL"))
    ap.add_argument("--token-url", default=os.environ.get("VSF_VLLM_TOKEN_URL"))
    ap.add_argument("--client-id", default=os.environ.get("VSF_VLLM_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.environ.get("VSF_VLLM_CLIENT_SECRET"))
    ap.add_argument("--model", default=None, help="model id for the optional chat smoke test")
    ap.add_argument("--chat", action="store_true", help="also send a tiny chat completion")
    args = ap.parse_args()

    need = {"--base / VSF_VLLM_BASE_URL": args.base,
            "--token-url / VSF_VLLM_TOKEN_URL": args.token_url,
            "--client-id / VSF_VLLM_CLIENT_ID": args.client_id,
            "--client-secret / VSF_VLLM_CLIENT_SECRET": args.client_secret}
    missing = [k for k, v in need.items() if not v]
    if missing:
        print("FAIL: missing required creds: " + ", ".join(missing))
        print("\n" + __doc__)
        return 1

    base = args.base.rstrip("/")
    print(f"BASE       = {base}")
    print(f"TOKEN_URL  = {args.token_url}")
    print(f"CLIENT_ID  = {args.client_id}")
    print(f"SECRET     = {args.client_secret[:4]}...{args.client_secret[-3:]} (masked)")

    # 1. token
    try:
        t0 = time.perf_counter()
        tok, exp, raw = get_token(args.token_url, args.client_id, args.client_secret)
        print(f"\n[OK] token in {(time.perf_counter() - t0) * 1000:.0f}ms | expires_in={exp}s | token keys={list(raw.keys())}")
    except Exception as exc:  # noqa: BLE001
        resp = getattr(exc, "response", None)
        print(f"\n[FAIL] token request: {type(exc).__name__}: {str(exc)[:200]}")
        if resp is not None:
            print(f"      status={resp.status_code} body={resp.text[:400]}")
        print("      -> if 404/405, the TOKEN_URL is wrong; check the IdP/platform that issued the Client ID.")
        return 1

    headers = {"Authorization": f"Bearer {tok}"}

    # 2. models
    print("\n=== models ===")
    models: list[str] = []
    for path in ("/v1/models", "/models"):
        url = base + path
        try:
            r = httpx.get(url, headers=headers, timeout=25)
            if r.status_code == 200:
                models = [m.get("id") for m in r.json().get("data", [])]
                print(f"[OK] GET {path} -> {len(models)} models:")
                for m in models[:80]:
                    print(f"     - {m}")
                break
            print(f"[NO] GET {path} -> {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[NO] GET {path} -> {type(exc).__name__}: {str(exc)[:200]}")

    # 3. optional chat smoke test
    if args.chat and (args.model or models):
        model = args.model or models[0]
        url = base + "/v1/chat/completions"
        body = {"model": model, "messages": [{"role": "user", "content": "Bạn là ai? Trả lời đúng 1 câu ngắn."}],
                "max_tokens": 60}
        try:
            t0 = time.perf_counter()
            r = httpx.post(url, headers=headers, json=body, timeout=60)
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code == 200:
                ans = r.json()["choices"][0]["message"]["content"]
                print(f"\n[OK] chat ({model}) {ms:.0f}ms: {ans[:200]}")
            else:
                print(f"\n[NO] chat {r.status_code}: {r.text[:300]}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n[NO] chat: {type(exc).__name__}: {str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
