"""PII redaction at the conversation-memory boundary (audit phase-01 supplement).

chat_messages is a DURABLE store that gets re-injected into future prompts via
phase-02 prior_context, which amplifies PII exposure compared to the raw
agent_runs.input_payload that already exists today. redact_pii masks Vietnamese
phone numbers + emails BEFORE persistence and BEFORE re-injection.

Masking is one-way token replacement — reversible mapping is out of scope (YAGNI).
"""
from __future__ import annotations

import re

# Vietnamese mobile: leading 0 OR +84 country code, then 9 digits.
# Matches 0912345678 and +84912345678 (audit contract).
_PHONE_RE = re.compile(r"(?:\+84|0)\d{9}")
# Pragmatic email pattern (redaction, not RFC validation).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_PHONE_TOKEN = "[PHONE]"
_EMAIL_TOKEN = "[EMAIL]"


def redact_pii(text: str) -> str:
    """Mask VN phone numbers and emails in free text.

    Non-string input returns "" — callers feed message text which is always str;
    the guard keeps the durable store clean if a None slips through.
    """
    if not isinstance(text, str):
        return ""
    masked = _PHONE_RE.sub(_PHONE_TOKEN, text)
    masked = _EMAIL_RE.sub(_EMAIL_TOKEN, masked)
    return masked
