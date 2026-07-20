"""Sinh du lieu TEXT synthetic cho hero merchant bang LLM:
- complaints (khieu nai co category + severity, bam vao dimension yeu)
- delivery_feedback (phan hoi tai xe)
- filled_reviews (bu review neu review that < 8, nhat quan voi rating)

Dung chung cho compare_models.py va batch. Grounded tren du lieu that cua quan.
"""
import json
import re
from pathlib import Path

CRAWLED = Path("data/crawled")
OPS = Path("data/synthetic/operational.jsonl")
_ops_cache = None


def _load_ops():
    global _ops_cache
    if _ops_cache is None:
        _ops_cache = {}
        for line in OPS.open(encoding="utf-8"):
            r = json.loads(line)
            _ops_cache[r["merchant_id"]] = r
    return _ops_cache


def _catalog(mid):
    for line in open("data/merchants_unique.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["merchant_id"] == mid:
            return r
    return {}


def build_context(mid):
    r = json.load(open(CRAWLED / f"{mid}.json", encoding="utf-8"))
    ops = _load_ops().get(mid, {})
    cat = _catalog(mid)
    dishes = [d["name"] for g in r.get("menu", []) for d in g.get("dishes", [])]
    reviews = [rv["text"][:200] for rv in r.get("reviews", [])][:6]
    return {
        "merchant_id": mid,
        "name": r.get("merchant_name"),
        "cuisine": cat.get("cuisine"),
        "city": cat.get("city"),
        "rating": r.get("shopeefood_rating_avg"),
        "real_review_count": len(r.get("reviews", [])),
        "price_level": ops.get("price_level"),
        "top_dishes": dishes[:15],
        "delivery_stats": ops.get("delivery_stats"),
        "operation_kpis": ops.get("operation_kpis"),
        "real_reviews": reviews,
    }


PROMPT = """Bạn là hệ thống sinh dữ liệu mô phỏng cho nền tảng giao đồ ăn (mục đích DEMO nội bộ).
Dựa trên thông tin THẬT của quán dưới đây, hãy sinh dữ liệu vận hành mô phỏng NHẤT QUÁN với dữ liệu thật.

THÔNG TIN QUÁN (JSON):
{context}

YÊU CẦU:
1. complaints: 6-9 khiếu nại thực tế của khách. Mỗi cái gồm category (một trong: giao_hàng_trễ, món_nguội, sai_hoặc_thiếu_món, đóng_gói_kém, thái_độ_phục_vụ, giá_cao, vệ_sinh, chất_lượng_món), text (tiếng Việt tự nhiên, cụ thể, nhắc tên món có thật trong menu khi hợp lý), severity (low/medium/high), date (2026 gần đây).
   - Phân bố khiếu nại phải BÁM tín hiệu yếu: nếu on_time_rate thấp -> nhiều khiếu nại giao trễ; packaging_ok_rate thấp -> khiếu nại đóng gói; v.v.
2. delivery_feedback: 4-6 phản hồi ngắn từ tài xế giao hàng, mỗi cái gồm text, on_time (true/false), issue (null hoặc mô tả ngắn).
3. filled_reviews: nếu real_review_count < 8 thì sinh thêm cho ĐỦ 8 (số cần sinh = 8 - real_review_count), mỗi review gồm text (tiếng Việt, nhắc món thật) và score (thang 10, nhất quán rating thật). Nếu đã đủ thì để mảng rỗng [].

Trả về DUY NHẤT một JSON hợp lệ, không giải thích, không markdown, theo schema:
{{"complaints":[{{"category":"","text":"","severity":"","date":""}}],"delivery_feedback":[{{"text":"","on_time":true,"issue":null}}],"filled_reviews":[{{"text":"","score":0}}]}}"""


def build_messages(mid):
    ctx = build_context(mid)
    # /no_think: giam thinking cho cac model reasoning (Qwen3), model khac bo qua vo hai
    content = "/no_think\n" + PROMPT.format(context=json.dumps(ctx, ensure_ascii=False, indent=1))
    return [{"role": "user", "content": content}], ctx


def parse_json(text):
    """Trich JSON tu output model (co the kem markdown fence / reasoning)."""
    # bo <think>...</think> cua model reasoning
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("khong tim thay JSON trong output")
    return json.loads(m.group(0))


def generate_for(model_key, mid):
    """Sinh du lieu text cho 1 merchant bang 1 model. Tra ve (data, meta)."""
    from llm_client import call
    messages, ctx = build_messages(mid)
    # max_tokens cao de model reasoning (Qwen3) thinking xong van du cho xuat JSON
    text, meta = call(model_key, messages, temperature=0.8, max_tokens=16000)
    data = parse_json(text)
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    meta["counts"] = counts
    return data, meta


if __name__ == "__main__":
    import sys
    mid = sys.argv[1] if len(sys.argv) > 1 else "10341"
    ctx = build_context(mid)
    print(json.dumps(ctx, ensure_ascii=False, indent=1)[:1500])
