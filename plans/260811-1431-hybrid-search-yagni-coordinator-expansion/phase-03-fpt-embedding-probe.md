# Phase 03 — FPT Embedding API Probe Script (D3)

## Context Links

- Active plan: `plans/260811-1431-hybrid-search-yagni-coordinator-expansion/plan.md`
- Existing FPT client usage (chat): `backend/flows/customer_flow.py:1833-1895` (`_stream_explanation_tokens` — `OpenAI(base_url=s.fpt_base_url, api_key=s.fpt_api_key)`); `backend/scripts/judge_gt_quality.py:82,119` (same pattern)
- Settings (FPT config): `backend/core/settings.py:49-61` (`fpt_api_key`, `fpt_base_url`, `fpt_model_deepseek`, `fpt_model_qwen`, `fpt_model_fast`)
- Constraint reminder: "DO NOT read or write `.env`. D3 reads FPT_API_KEY from env only."

## Overview

Priority: P3. Status: pending. Effort: 2h.

Standalone script `backend/scripts/probe_fpt_embedding.py` — probe whether `FPT_API_KEY` authorizes the FPT `/embeddings` endpoint. POST a tiny Vietnamese food sample ("phở bò", "bún chả"). Report HTTP status, authorized?, dimensions, sample vector head, latency. Degrade gracefully (401/404/timeout → clear message). Parallel prep — does NOT block D1/D2 and does NOT commit to building the vector leg.

## Key Insights

1. **FPT is OpenAI-compatible** (per `settings.py:50` comment: "FPT Cloud AI (OpenAI-compatible; DeepSeek/Qwen)"). So the embeddings endpoint likely follows OpenAI's `/v1/embeddings` shape: `POST {base}/embeddings` with `{"model": "...", "input": "..."}` → `{"data": [{"embedding": [...]}], "usage": {...}}`.
2. **Exact base URL**: `FPT_BASE_URL` env var. The chat client uses it raw (`OpenAI(base_url=s.fpt_base_url, ...)`); for embeddings we POST to `<fpt_base_url>/embeddings`. If `fpt_base_url` already ends in `/v1`, that gives `/v1/embeddings` (canonical OpenAI). If not, we try both.
3. **Model name unknown**: FPT may or may not expose an embedding model under the same key. The script tries, in order: `FPT_EMBED_MODEL` env override → `fpt_model_qwen` → a known FPT embedding model id (research needed — likely `Qwen3-Embedding-8B` or similar; the script should make this configurable). 404 on model → clear "model not found" message.
4. **No backend wiring**: standalone script, no import of `core.settings` (to avoid env-file read — strict "env-only" reading). Read `os.environ.get("FPT_API_KEY")` / `FPT_BASE_URL` directly.
5. **Why this matters**: keeps the embedding option alive cheaply. If the probe succeeds (dimensions/latency reasonable), the vector leg has a viable embedder without a procurement cycle. If it fails (401/404), we know FPT chat keys don't authorize embeddings — kill signal for the FPT-embedding variant of the vector leg.

## Requirements

### Functional
- FR1: Read `FPT_API_KEY` and `FPT_BASE_URL` from `os.environ` ONLY (not `.env`, not `core.settings`).
- FR2: POST a 2-item VN food sample `["phở bò", "bún chả"]` to `{FPT_BASE_URL}/embeddings`.
- FR3: Report on stdout: HTTP status, authorized (Y/N), model used, vector dimensions, sample vector head (first 5 floats), latency ms.
- FR4: Degrade gracefully:
  - 401 → "FPT_API_KEY not authorized for /embeddings (chat-only key?)"
  - 404 (model or endpoint) → "Endpoint/model not found; tried: <list>"
  - Timeout (10s) → "Timeout — endpoint may not exist or be unreachable"
  - Connection error → "Connection failed: <reason>"
- FR5: Exit code 0 on success, 1 on any failure variant (CI-friendly).

### Non-functional
- NFR1: <150 LOC, stdlib + `openai` (already a dep) + `requests` (already a dep per `eval_ground_truth.py`).
- NFR2: No side effects (no file writes, no DB, no backend import).
- NFR3: Timeout 10s (this is a probe, not a hot path).

## Architecture

```
probe_fpt_embedding.py (standalone)
    │
    ├─ read os.environ: FPT_API_KEY, FPT_BASE_URL, FPT_EMBED_MODEL (optional)
    ├─ construct OpenAI client (base_url, api_key)
    ├─ for model in candidate list:
    │     try:
    │         resp = client.embeddings.create(model=model, input=["phở bò", "bún chả"])
    │         print success report + break
    │     except APIStatusError as e:
    │         if 401: print auth-failed + exit 1
    │         if 404: continue to next candidate
    │     except (Timeout, ConnectionError): print connectivity-failed + exit 1
    ├─ (all candidates exhausted) → print "no embedding model found" + exit 1
```

## Related Code Files

### Create
- `backend/scripts/probe_fpt_embedding.py` (NEW, <150 LOC).

### Modify / Delete
- None. This is purely additive.

## Implementation Steps

1. **Create `backend/scripts/probe_fpt_embedding.py`** with the structure above. Snippet:
   ```python
   """Probe whether FPT_API_KEY authorizes the FPT /embeddings endpoint.
   
   Reads FPT_API_KEY, FPT_BASE_URL, FPT_EMBED_MODEL (optional) from os.environ ONLY.
   Does NOT import core.settings, NOT read .env, NOT touch DB.
   Exit 0 on success, 1 on any failure.
   
   Usage (env ai_restaurant):
     FPT_API_KEY=... FPT_BASE_URL=https://... PYTHONPATH=backend \
         C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe scripts/probe_fpt_embedding.py
   """
   from __future__ import annotations
   import os, sys, time
   from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
   
   SAMPLE = ["phở bò", "bún chả"]
   DEFAULT_TIMEOUT_S = 10.0
   
   def main() -> int:
       key = os.environ.get("FPT_API_KEY")
       base = os.environ.get("FPT_BASE_URL")
       if not key or not base:
           print("MISSING: FPT_API_KEY and FPT_BASE_URL must be set in env.")
           return 1
       client = OpenAI(base_url=base, api_key=key, timeout=DEFAULT_TIMEOUT_S)
       candidates = []
       if m := os.environ.get("FPT_EMBED_MODEL"):
           candidates.append(m)
       candidates.extend(["Qwen3-Embedding-8B", "bge-m3", "text-embedding-3-small"])  # research before finalizing
       tried = []
       for model in candidates:
           tried.append(model)
           t0 = time.perf_counter()
           try:
               resp = client.embeddings.create(model=model, input=SAMPLE)
           except APIStatusError as e:
               if e.status_code == 401:
                   print(f"401 UNAUTHORIZED — FPT_API_KEY not authorized for /embeddings (chat-only key?).")
                   return 1
               if e.status_code == 404:
                   continue
               print(f"API error {e.status_code}: {e.message}")
               return 1
           except (APITimeoutError,):
               print(f"TIMEOUT after {DEFAULT_TIMEOUT_S}s — endpoint unreachable or missing.")
               return 1
           except APIConnectionError as e:
               print(f"CONNECTION FAILED: {e}")
               return 1
           lat_ms = (time.perf_counter() - t0) * 1000
           vec = resp.data[0].embedding
           dims = len(vec)
           print(f"OK — model={model}, dims={dims}, latency={lat_ms:.0f}ms")
           print(f"  sample input: {SAMPLE[0]!r}")
           print(f"  vec[0:5]: {vec[:5]}")
           print(f"  vec[0] norm^2 (sanity): {sum(x*x for x in vec[:10]):.4f}")
           return 0
       print(f"NO EMBEDDING MODEL FOUND — tried: {tried}")
       return 1
   
   if __name__ == "__main__":
       sys.exit(main())
   ```
2. **Research FPT embedding model id** before finalizing candidate list (one-time `WebFetch` against FPT Cloud AI docs / `mkp-api.fptcloud.com` — possibly via the `researcher` agent). The candidate list in step 1 is a placeholder.
3. **Manual smoke test**: run with the actual env. Capture stdout into `plans/reports/fpt-embedding-probe-result.txt` (operator decision — NOT auto-written by the script to keep it side-effect-free).
4. **No unit test** (script is I/O-only; mocking the OpenAI client tests nothing useful). Verify by running.

## Todo List

- [ ] Research FPT embedding endpoint URL + model name (one WebFetch or `researcher` agent task)
- [ ] Write `backend/scripts/probe_fpt_embedding.py`
- [ ] Manual smoke run; record result in `plans/reports/fpt-embedding-probe-result.txt`
- [ ] Document findings (authorized? dims? latency?) in the report file

## Request Shape (canonical)

```http
POST {FPT_BASE_URL}/embeddings
Authorization: Bearer {FPT_API_KEY}
Content-Type: application/json

{
  "model": "Qwen3-Embedding-8B",   // candidate — actual model TBD via research
  "input": ["phở bò", "bún chả"]
}
```

Expected response (OpenAI-compatible):
```json
{
  "data": [{"embedding": [0.01, -0.03, ...], "index": 0}, ...],
  "model": "...",
  "usage": {"prompt_tokens": 8, "total_tokens": 8}
}
```

## Success Criteria

- Script runs, exits 0 with a clear `OK — model=..., dims=..., latency=...ms` line, OR exits 1 with one of the clear failure messages.
- Result recorded in `plans/reports/fpt-embedding-probe-result.txt`.
- Decision recorded: FPT embeddings are (a) viable / (b) not viable for the deferred vector leg.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FPT chat key doesn't authorize embeddings (most likely outcome) | H | L (still useful signal) | The 401 path IS the deliverable in that case — clear message + the vector leg moves to a different embedder (NVIDIA NIM, local BGE, etc.) |
| Wrong embedding model id → all candidates 404 | M | L | Research before finalizing; document tried list in failure message |
| FPT base URL doesn't expose `/embeddings` (404 endpoint) | M | L | The script treats endpoint-404 same as model-404 — falls through to "not found" + the verdict is "FPT base doesn't serve embeddings" |
| Script accidentally imports `core.settings` and reads `.env` | L | M (constraint violation) | Code review; explicit `import os` only; no `from core.` imports |

## Security Considerations

- **Key in env only**: no `core.settings` import → no `.env` read. Constraint honored.
- **No key in output**: the script never echoes the key; only status/latency/dims.
- **No PII**: sample strings are generic dish names.
- **No side effects**: no file writes, no DB, no API mutations (GET-equivalent — embeddings are stateless).

## Next Steps

- Result feeds the deferred vector-leg decision. If viable (dims 768/1024/1536, latency <300ms, key authorized) → embedding remains an option for the future vector leg. If not → vector leg (if ever built) uses a different embedder.
- Does NOT block D1/D2/D4 — ship in parallel.

## Open Questions

1. **FPT embedding model id**: research needed (FPT Cloud AI marketplace docs). Candidate list in the script is a placeholder — finalize via `researcher` agent or direct WebFetch to FPT docs.
2. **Endpoint path**: `/embeddings` vs `/v1/embeddings` — depends on whether `FPT_BASE_URL` includes `/v1`. The OpenAI client appends `/embeddings` to `base_url`; verify the exact form FPT expects.
3. **Throughput/cost**: a single probe says nothing about batch latency or quota limits — those need a follow-up load probe IF the vector leg is pursued. Out of scope here.
