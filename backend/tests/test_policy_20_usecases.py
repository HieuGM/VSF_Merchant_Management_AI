"""20 Comprehensive Policy RAG Use Case Integration Tests.

Validates that PolicyRagService retrieves authoritative evidence for 20 core merchant policy scenarios.
"""
from __future__ import annotations

import pytest
from database.connection import SessionLocal
from services.policy_rag_service import PolicyRagService


POLICY_20_USECASES = [
    # 1. VSATTP & Dị vật
    {
        "id": "UC01",
        "query": "Quy định xử lý vi phạm vệ sinh an toàn thực phẩm hoặc món ăn có dị vật?",
        "expected_keywords": ["vệ sinh", "dị vật", "an toàn thực phẩm", "cảnh báo"],
    },
    # 2. Giao sai / thiếu món
    {
        "id": "UC02",
        "query": "Chế tài xử lý đối với việc giao sai món, thiếu món cho khách hàng?",
        "expected_keywords": ["sai món", "thiếu món", "bồi hoàn", "cảnh báo"],
    },
    # 3. Thời gian chuẩn bị món
    {
        "id": "UC03",
        "query": "Quy định thời gian tối đa để nhà hàng chuẩn bị món cho tài xế?",
        "expected_keywords": ["chuẩn bị", "30 phút", "tài xế", "chờ"],
    },
    # 4. Tự ý hủy đơn
    {
        "id": "UC04",
        "query": "Quy định xử lý khi nhà hàng tự ý hủy đơn hàng với lý do không hợp lý?",
        "expected_keywords": ["hủy", "đơn hàng", "lý do", "cảnh báo"],
    },
    # 5. Sai giờ hoạt động
    {
        "id": "UC05",
        "query": "Quy định xử lý khi gian hàng sai giờ hoạt động đã đăng ký?",
        "expected_keywords": ["giờ hoạt động", "đăng ký", "đóng cửa"],
    },
    # 6. Gian lận / Đơn ảo
    {
        "id": "UC06",
        "query": "Chế tài xử lý đối với hành vi tạo đơn hàng ảo hoặc gian lận khuyến mại?",
        "expected_keywords": ["gian lận", "đơn hàng ảo", "chấm dứt hợp tác", "nghiêm trọng"],
    },
    # 7. Bán hàng cấm
    {
        "id": "UC07",
        "query": "Chế tài xử lý khi gian hàng kinh doanh hoặc đăng tải mặt hàng thuộc danh mục cấm?",
        "expected_keywords": ["cấm", "pháp luật", "danh mục", "hình ảnh"],
    },
    # 8. Phân biệt đối xử
    {
        "id": "UC08",
        "query": "Quy định xử lý khi nhà hàng phân biệt đối xử với tài xế Green SM?",
        "expected_keywords": ["phân biệt đối xử", "tài xế", "từ chối"],
    },
    # 9. Bảo mật thông tin
    {
        "id": "UC09",
        "query": "Quy định về tôn trọng quyền riêng tư và bảo mật thông tin khách hàng?",
        "expected_keywords": ["bảo mật", "thông tin", "quyền riêng tư", "khách hàng"],
    },
    # 10. Kỳ đối soát doanh thu
    {
        "id": "UC10",
        "query": "Thời gian tính kỳ đối soát doanh thu hàng tháng là từ ngày nào đến ngày nào?",
        "expected_keywords": ["đối soát", "ngày 23", "ngày 22", "kỳ"],
    },
    # 11. Hóa đơn VAT
    {
        "id": "UC11",
        "query": "Hướng dẫn yêu cầu xuất hóa đơn giá trị gia tăng VAT cho các đơn hàng?",
        "expected_keywords": ["hóa đơn", "VAT", "giá trị gia tăng", "thương nhân"],
    },
    # 12. Khấu trừ chi phí bồi hoàn
    {
        "id": "UC12",
        "query": "Quy định khấu trừ giá trị đơn hàng hoặc voucher bồi hoàn cho khách hàng?",
        "expected_keywords": ["khấu trừ", "bồi hoàn", "ví", "khuyến mại"],
    },
    # 13. Phản hồi khiếu nại
    {
        "id": "UC13",
        "query": "Thời hạn nhà hàng phải phản hồi khiếu nại từ khách hàng hoặc nền tảng?",
        "expected_keywords": ["phản hồi", "khiếu nại", "24 giờ", "thời gian"],
    },
    # 14. Tái đào tạo bắt buộc
    {
        "id": "UC14",
        "query": "Trường hợp nào nhà hàng phải tham gia chương trình tái đào tạo bắt buộc?",
        "expected_keywords": ["tái đào tạo", "bắt buộc", "gian hàng", "mở lại"],
    },
    # 15. Hư hỏng thiết bị
    {
        "id": "UC15",
        "query": "Quy định xử lý khi nhà hàng làm hư hỏng thiết bị hoạt động của Green SM?",
        "expected_keywords": ["thiết bị", "hư hỏng", "bảo quản", "chi phí"],
    },
    # 16. Hiển thị thực đơn menu
    {
        "id": "UC16",
        "query": "Quy định về thiết lập thông tin thực đơn menu mô tả hình ảnh trên ứng dụng?",
        "expected_keywords": ["thực đơn", "mô tả", "hình ảnh", "hiển thị"],
    },
    # 17. Ảnh hưởng sức khỏe khách hàng
    {
        "id": "UC17",
        "query": "Chế tài khi vi phạm an toàn thực phẩm gây ảnh hưởng sức khỏe khách hàng cần can thiệp y tế?",
        "expected_keywords": ["sức khỏe", "can thiệp y tế", "y tế", "tạm đóng"],
    },
    # 18. Tái thiết lập vi phạm 30 ngày
    {
        "id": "UC18",
        "query": "Quy định về thời gian tái thiết lập số lần vi phạm Nhóm 2-6 sau 30 ngày?",
        "expected_keywords": ["30 ngày", "tái thiết lập", "vi phạm", "số lần"],
    },
    # 19. Nghĩa vụ tài chính
    {
        "id": "UC19",
        "query": "Quy định về thực hiện nghĩa vụ tài chính với Nhà nước và Green SM?",
        "expected_keywords": ["nghĩa vụ tài chính", "tài chính", "nghĩa vụ"],
    },
    # 20. Tự ý chỉnh sửa đơn hàng
    {
        "id": "UC20",
        "query": "Chế tài khi nhà hàng tự ý chỉnh sửa đơn hàng mà không được sự đồng ý của khách hàng?",
        "expected_keywords": ["chỉnh sửa", "đơn hàng", "đồng ý", "khách hàng"],
    },
]


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def rag_service(db_session):
    return PolicyRagService(db_session)


@pytest.mark.parametrize("uc", POLICY_20_USECASES, ids=[u["id"] for u in POLICY_20_USECASES])
def test_policy_usecase(rag_service, uc):
    res = rag_service.search(uc["query"], top_k=5)
    assert res["count"] > 0, f"Usecase {uc['id']} failed: query '{uc['query']}' returned 0 results"

    matched_texts = " ".join([r["text"].lower() for r in res["results"]])
    matched_paths = " ".join([" ".join(r["section_path"]).lower() for r in res["results"]])
    full_haystack = matched_texts + " " + matched_paths

    found_kw = [kw for kw in uc["expected_keywords"] if kw.lower() in full_haystack]
    assert len(found_kw) >= 1, (
        f"Usecase {uc['id']} failed: query '{uc['query']}' matched no expected keywords {uc['expected_keywords']}. "
        f"Top result text snippet: {res['results'][0]['text'][:200]}"
    )
