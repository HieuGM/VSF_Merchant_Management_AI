import re

from flows.merchant_flow import MerchantFlowDispatcher


def test_stream_emits_only_answer_and_terminal_events(monkeypatch):
    dispatcher = MerchantFlowDispatcher()
    monkeypatch.setattr(
        dispatcher,
        "chat",
        lambda **_: {
            "reply": "Xin chao",
            "trace_id": "a" * 32,
            "status": "completed",
            "merchants": [],
            "competitors": [],
            "evidence_status": "grounded",
        },
    )

    stream = "".join(dispatcher.chat_stream("94", "hello"))

    assert set(re.findall(r"^event: (.+)$", stream, re.MULTILINE)) == {
        "token_chunk",
        "execution_finish",
    }
    assert "trace_span" not in stream
    assert "sql_query" not in stream
    assert "cache" not in stream
