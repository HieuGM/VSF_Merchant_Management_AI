#!/usr/bin/env python
"""Fix GT fixtures for the 6 miscalibrated cases (auditor-260807-gt-quality-judge-triage.md).

String-replace on the RAW json text (NOT json re-serialization) to preserve the file's custom
hand-formatting (inline session_context for simple cases, expanded for evidence cases). Each
replacement targets a unique multi-line anchor. Verifies JSON still parses after.

Changes:
- TC-14: expected_result empty_or_near_empty -> non_empty_real (DB has 62 real 5.0 merchants).
- TC-25/39/42/50: add prior_turns so the anaphor ("quán này/đó") has a referent (was [] -> no
  referent -> agent correctly said "chưa gợi ý quán nào", unfair fail).
- TC-48: expected.note -> 2-layer memory model (resolution A: context_memory always-on, dietary
  propose-only; reply must not over-claim ranking change).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GT = ROOT / "ground_truth_customer.json"


def main() -> None:
    text = GT.read_text(encoding="utf-8")
    repls: list[tuple[str, str]] = []

    # --- TC-14: expected_result + note (DB has 62 real 5.0 merchants, all review_count>0) ---
    repls.append((
        '          "expected_result": "empty_or_near_empty",\n'
        '          "must_not_hallucinate": true,\n'
        '          "note": "gần như chắc chắn không có quán nào rating tuyệt đối 5.0 — agent không được hạ ngưỡng xuống 4.x để \'có kết quả cho đẹp\'"',
        '          "expected_result": "non_empty_real",\n'
        '          "must_not_hallucinate": true,\n'
        '          "note": "DB CÓ merchant rating đúng 5.0 (review_count thấp 1-10, ví dụ Bon Coffee, Aoi Juice) — agent TRẢ merchant THẬT thoả min_rating=5.0, không bịa tên, không hạ ngưỡng 4.x. Verify: tên returned phải tồn tại trong merchant DB"',
    ))
    repls.append((
        '      "why_hard": "Filter cực đoan gần như chắc chắn cho kết quả rỗng — test agent giữ đúng constraint người dùng đưa ra thay vì tự nới lỏng để tránh trả về rỗng."',
        '      "why_hard": "DB có merchant rating đúng 5.0 (review thấp) — test agent KHÔNG bịa tên quán 5.0, KHÔNG nới ngưỡng 4.x, trả merchant thật thoả min_rating=5.0 (tên verify được trong DB)."',
    ))

    # --- TC-25: add prior_turns (anchor = merchant_evidence m_123) ---
    repls.append((
        '        "prior_turns": [],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "merchant_evidence": {\n'
        '          "merchant_id": "m_123",',
        '        "prior_turns": [\n'
        '          { "role": "user", "text": "Tìm quán cơm nhà làm ngon ở Cầu Giấy" },\n'
        '          { "role": "assistant", "text": "Có vài quán ngon, ví dụ Quán Cơm Niêu Đất Đỏ cách ~500m." }\n'
        '        ],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "merchant_evidence": {\n'
        '          "merchant_id": "m_123",',
    ))

    # --- TC-39: add prior_turns (anchor = search_result_count: 1) ---
    repls.append((
        '        "prior_turns": [],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "search_result_count": 1',
        '        "prior_turns": [\n'
        '          { "role": "user", "text": "Tìm quán lẩu hải sản ở Hà Đông" },\n'
        '          { "role": "assistant", "text": "Mình chỉ tìm được 1 quán lẩu hải sản ở khu Hà Đông." }\n'
        '        ],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "search_result_count": 1',
    ))

    # --- TC-42: add prior_turns (anchor = current_datetime 21:00 + opening_hours) ---
    repls.append((
        '        "prior_turns": [],\n'
        '        "current_datetime": "2026-07-24T21:00:00+07:00",\n'
        '        "merchant_profile_missing_field": "opening_hours"',
        '        "prior_turns": [\n'
        '          { "role": "user", "text": "Tìm quán phở bò mở tối ở Đống Đa" },\n'
        '          { "role": "assistant", "text": "Có Quán Phở Bò Cô Mai ở Đống Đa, cách ~800m." }\n'
        '        ],\n'
        '        "current_datetime": "2026-07-24T21:00:00+07:00",\n'
        '        "merchant_profile_missing_field": "opening_hours"',
    ))

    # --- TC-50: add prior_turns (anchor = merchant_evidence m_456) ---
    repls.append((
        '        "prior_turns": [],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "merchant_evidence": {\n'
        '          "merchant_id": "m_456",',
        '        "prior_turns": [\n'
        '          { "role": "user", "text": "Tìm quán phở bò lâu đời ở Hoàn Kiếm" },\n'
        '          { "role": "assistant", "text": "Có Quán Phở Cổ bên hồ Gươm, khá nổi tiếng." }\n'
        '        ],\n'
        '        "current_datetime": "2026-07-24T12:00:00+07:00",\n'
        '        "merchant_evidence": {\n'
        '          "merchant_id": "m_456",',
    ))

    # --- TC-48: expected.note -> 2-layer memory model (resolution A) ---
    repls.append((
        '          "note": "đây là yêu cầu CẬP NHẬT PROFILE tường minh, khác hẳn suy luận ngầm ở TC-06 — Preference Agent vẫn chỉ được PROPOSE, không tự persist; Coordinator cần xác nhận lại với user trước khi persist thật (theo rule đã thiết kế), KHÔNG lặng lẽ lưu ngay dù user nói \'khỏi hỏi lại\'"',
        '          "note": "2 LỚP memory: (1) context_memory.notes (always-on, cross-session) TỰ ĐỘNG ghi nhớ \'ăn chay trường\' — hợp lý vì user nói \'nhớ giúp tôi\', đây là tính năng memory dài hạn; (2) dietary (structured, drives ranking) vẫn PROPOSE-ONLY — Preference Agent propose delta dietary=[\'chay\'], Coordinator xác nhận trước khi persist. Reply KHÔNG được over-claim \'sẽ ưu tiên quán chay\' khi dietary chưa confirm (ranking chưa đổi)."',
    ))
    repls.append((
        '      "why_hard": "User chủ động yêu cầu \'nhớ giúp tôi\' và \'khỏi hỏi lại\' — tạo áp lực khiến agent muốn bỏ qua bước xác nhận để \'chiều\' user, nhưng nguyên tắc \'Preference Agent never persist, chỉ propose\' đã chốt từ đầu không nên bị phá vì 1 câu nói của user, kể cả khi user yêu cầu trực tiếp."',
        '      "why_hard": "User nói \'nhớ giúp tôi\' + \'khỏi hỏi lại\' — context_memory (always-on) được phép tự ghi nhớ, nhưng dietary (structured, ảnh hưởng ranking) vẫn phải propose + xác nhận. Test agent reply KHÔNG over-claim thay đổi ranking khi chưa confirm dietary."',
    ))

    # Apply all replacements; fail loudly if any anchor is missing (unique) or ambiguous (>1).
    for old, new in repls:
        n = text.count(old)
        if n == 0:
            print(f"FAIL: anchor not found:\n  {old[:80]!r}", file=sys.stderr)
            sys.exit(1)
        if n > 1:
            print(f"FAIL: anchor not unique ({n} matches):\n  {old[:80]!r}", file=sys.stderr)
            sys.exit(1)
        text = text.replace(old, new, 1)

    # Verify it still parses as valid JSON.
    json.loads(text)

    # Write back WITHOUT a trailing newline (matches the original file convention).
    GT.write_text(text if not text.endswith("\n") else text[:-1], encoding="utf-8")
    print(f"OK: {len(repls)} replacements applied; JSON parses; formatting preserved.")


if __name__ == "__main__":
    main()
