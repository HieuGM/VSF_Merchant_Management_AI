# Kế Hoạch Tái Cấu Trúc Merchant AI Agent theo chuẩn CrewAI Native & System Design

> **Mục tiêu**: Chuyển đổi Merchant Advisor Agent từ luồng tĩnh sang **Hệ thống Chatbot Đa-Agent chuẩn Native CrewAI 1.15.5**, tuân thủ 100% tài liệu `docs/2026-07-21-merchant-ai-agent-complete-design.md` và mã mẫu `food_intent_search_crew_v1_crewai-project`.

---

## Các Thành Phần Triển Khai (Tasks Breakdown)

### Task 1: Quản lý Session State & Chat History (`backend/services/chat_session_service.py`)
- Quản lý các bảng CSDL `chat_sessions` và `chat_messages`.
- Đọc/ghi lịch sử đối thoại $N$ lượt gần nhất theo `session_id`.
- Cập nhật `context_snapshot_json`, `last_trace_id`, và `token_usage_json`.

### Task 2: Native CrewAI `BaseTool` Wrappers (`backend/tools/merchant/crewai_tools.py`)
- Xây dựng các lớp Tool chuẩn Native CrewAI kế thừa từ `crewai.tools.BaseTool` (khớp file mẫu `custom_tool.py`):
  - `GetMerchantProfileTool(BaseTool)`
  - `GetProfileEvidenceTool(BaseTool)`
  - `DiagnoseMerchantTool(BaseTool)`
  - `RecommendImprovementsTool(BaseTool)`
  - `CompareCompetitorsTool(BaseTool)`
- Đăng ký và kiểm tra ma trận phân quyền `allow_list.py` tại runtime.

### Task 3: Cấu hình CrewAI YAML & Prompting (`backend/agents/merchant/config/`)
- Cập nhật `agents.yaml`: Khai báo 6 vai trò Agents (`merchant_coordinator`, `merchant_profile_analyst`, `diagnosis`, `recommendation`, `competitor`, `evidence_verifier`).
- Cập nhật `tasks.yaml`: Khai báo các nhiệm vụ trích xuất intent, chẩn đoán, khuyến nghị, so sánh đối thủ, kiểm duyệt bằng chứng và tổng hợp câu trả lời chatbot (`synthesis_chat_task`).

### Task 4: Cấu trúc Class `@CrewBase` chuẩn CrewAI (`backend/flows/merchant_flow.py`)
- Xây dựng class `MerchantAdvisorCrew` sử dụng `@CrewBase`, `@agent`, `@task`, `@crew` đúng chuẩn mã mẫu `crew.py`.
- Tích hợp **2-Layer Evidence Verification**:
  - **Layer 1 Guardrail (Deterministic)**: `validate_evidence_guardrail` gắn trên Task chẩn đoán, kích hoạt tự động check & retry của CrewAI.
  - **Layer 2 Semantic Verifier Agent**: Thẩm định tính chính xác ngữ nghĩa bằng chứng.
- Tích hợp **Synthesis Agent**: Dùng LLM tổng hợp dữ liệu thực tế thu được từ Tool thành câu trả lời hội thoại cá nhân hoá cho chủ quán.

### Task 5: API Endpoint & CLI Chatbot Đa Lượt
- Cập nhật `POST /api/v1/agent/merchant/chat` hỗ trợ duy trì Session State và ghi nhận token usage.
- Nâng cấp `scripts/merchant_advisor_cli.py` hỗ trợ chat đa lượt duy trì lịch sử phiên hội thoại.
- Viết bộ unit & contract tests kiểm thử toàn bộ hệ thống.
