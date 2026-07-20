"""OpenAI-compatible LLM client, provider-agnostic (NVIDIA NIM, FPT Cloud, OpenAI).
Doc cau hinh tu .env. Moi 'model_key' -> (base_url, api_key, model_id).
Dung chung cho ca so sanh model lan sinh du lieu hang loat.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Dang ky model: friendly key -> env vars. Them/sua o day khi doi provider.
REGISTRY = {
    "nim-qwen": {
        "base_url": os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key_env": "NIM_API_KEY",
        "model_env": "NIM_MODEL",
    },
    "fpt-qwen": {
        "base_url": os.getenv("FPT_BASE_URL", ""),
        "api_key_env": "FPT_API_KEY",
        "model_env": "FPT_MODEL_QWEN",
    },
    "fpt-deepseek": {
        "base_url": os.getenv("FPT_BASE_URL", ""),
        "api_key_env": "FPT_API_KEY",
        "model_env": "FPT_MODEL_DEEPSEEK",
    },
}


def available_models():
    """Cac model_key co du config (base_url + key + model id)."""
    ok = []
    for key, cfg in REGISTRY.items():
        if cfg["base_url"] and os.getenv(cfg["api_key_env"]) and os.getenv(cfg["model_env"]):
            ok.append(key)
    return ok


def _client(cfg):
    return OpenAI(base_url=cfg["base_url"], api_key=os.getenv(cfg["api_key_env"]))


def call(model_key, messages, temperature=0.8, max_tokens=4096, **kw):
    """Goi 1 model. Tra ve (text, meta). Raise neu thieu config."""
    cfg = REGISTRY.get(model_key)
    if not cfg:
        raise ValueError(f"unknown model_key: {model_key}")
    model_id = os.getenv(cfg["model_env"])
    if not (cfg["base_url"] and os.getenv(cfg["api_key_env"]) and model_id):
        raise RuntimeError(f"{model_key} chua cau hinh du trong .env "
                           f"({cfg['api_key_env']}, {cfg['model_env']}, base_url)")
    client = _client(cfg)
    import time
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id, messages=messages,
        temperature=temperature, max_tokens=max_tokens, **kw)
    dt = time.time() - t0
    text = resp.choices[0].message.content
    meta = {"model_key": model_key, "model_id": model_id,
            "latency_s": round(dt, 2),
            "tokens": getattr(resp, "usage", None) and resp.usage.total_tokens}
    return text, meta


if __name__ == "__main__":
    print("available models (configured in .env):", available_models())
    print("all registered keys:", list(REGISTRY.keys()))
