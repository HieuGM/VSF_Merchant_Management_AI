"""Scope Guard Module for Merchant Advisor AI.

Validates query scope using lightweight NLU Model.
"""
from __future__ import annotations

import json


def validate_query_scope(query: str) -> tuple[bool, str | None]:
    """Validate if user query is within Merchant/Food domain scope using lightweight NLU Model."""
    q = query.strip() if query else ""
    if not q:
        return False, "Câu hỏi không được để trống. Bạn cần hỗ trợ gì về quán ăn của mình?"

    # Truncate query to 200 chars for lightweight NLU classification
    clean_q = q[:200]

    try:
        from flows.merchant_flow import get_configured_llm
        llm = get_configured_llm("small")
        if llm:
            prompt = (
                "Is this query related to food, dining, restaurants, merchant operations, or greetings?\n"
                "In scope: food search, dining, menus, competitors, sales, reviews, metrics, greetings.\n"
                "Out of scope: programming/coding, news, politics, weather, medical, legal.\n"
                "Output ONLY JSON: {\"in_scope\": true} OR {\"in_scope\": false, \"reason\": \"Polite Vietnamese rejection\"}"
            )

            response = llm.call(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": clean_q},
                ]
            )
            raw_text = str(getattr(response, "content", response)).strip()
            if "{" in raw_text and "}" in raw_text:
                json_str = raw_text[raw_text.find("{"):raw_text.rfind("}") + 1]
                data = json.loads(json_str)
                if not data.get("in_scope", True):
                    reason = data.get("reason") or (
                        "Tôi là Merchant Advisor AI, chuyên hỗ trợ vận hành quán ăn và ẩm thực. "
                        "Rất tiếc tôi không thể hỗ trợ chủ đề này."
                    )
                    return False, reason
                return True, None
    except Exception as e:
        print(f"[NLU Scope Guard Warning]: {e}")

    return True, None
