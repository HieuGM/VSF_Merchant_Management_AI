"""Kich ban 'quan yeu' co chu dich cho hero-set (phuc vu demo Diagnosis/Recommendation/Competitor).
Moi kich ban lam yeu 1 dimension KHAC NHAU. Dung chung boi:
- generate_operational.py : ep so lieu ops/delivery xau (cho dimension ops-driven).
- generate_text_data.py   : ep complaints/reviews tap trung dung diem yeu (cho dimension rating-anchored).

Gan merchant -> scenario o SCENARIO_ASSIGN (ben duoi), dung chung boi ca 3 script.
"""

# Merchant -> scenario (moi quan lam yeu 1 dimension KHAC nhau) -> phuc vu demo.
# 10344 nam trong cum doi thu fast-food HCM (UC-03).
SCENARIO_ASSIGN = {
    "10344": "weak_delivery",    # Popeyes Tùng Thiện Vương (competitor cluster)
    "68814": "weak_service",     # Dì Bảy - Bún Mắm
    "100810": "weak_packaging",  # 3 Râu
    "13909": "weak_food",        # Cơm Tấm & Hot Pot BBQ (Hải Phòng)
    "233150": "slow_prep",       # Sushi Lounge (Vũng Tàu)
}

SCENARIOS = {
    "weak_delivery": {
        "label": "giao hàng chậm và thường xuyên trễ giờ",
        # override ops (dimension delivery_quality + waiting_time se giam)
        "ops": {"on_time_rate": 0.58, "driver_rating": 3.4,
                "avg_delivery_add": 28, "cancel_rate": 0.16},
        "complaint_focus": "ÍT NHẤT 5 khiếu nại loại 'giao_hàng_trễ', kèm vài 'món_nguội' (đồ tới nguội do giao lâu)",
        "neg_reviews": 1,
    },
    "weak_service": {
        "label": "thái độ phục vụ kém, nhân viên cáu gắt",
        "ops": {},  # rating-anchored -> giam qua complaints
        "complaint_focus": "ÍT NHẤT 5 khiếu nại loại 'thái_độ_phục_vụ', kèm vài 'vệ_sinh'",
        "neg_reviews": 2,
    },
    "weak_packaging": {
        "label": "đóng gói ẩu, hộp bẹp/đổ, rò rỉ nước sốt",
        "ops": {"packaging_ok_rate": 0.55},
        "complaint_focus": "ÍT NHẤT 5 khiếu nại loại 'đóng_gói_kém'",
        "neg_reviews": 1,
    },
    "weak_food": {
        "label": "chất lượng món giảm sút rõ rệt gần đây",
        "ops": {},  # rating-anchored -> giam qua complaints + review diem thap
        "complaint_focus": "ÍT NHẤT 5 khiếu nại loại 'chất_lượng_món' và 'món_nguội'",
        "neg_reviews": 3,
    },
    "slow_prep": {
        "label": "thời gian chuẩn bị/chờ món quá lâu",
        "ops": {"avg_prep_minutes": 34, "avg_delivery_add": 15},
        "complaint_focus": "ÍT NHẤT 4 khiếu nại về CHỜ LÂU (loại 'giao_hàng_trễ', nhấn mạnh bếp làm chậm)",
        "neg_reviews": 1,
    },
}


def apply_ops_override(rec, scenario):
    """Ep so lieu ops xau vao 1 operational record (mutate tai cho)."""
    spec = SCENARIOS.get(scenario)
    if not spec:
        return rec
    o = spec["ops"]
    ds = rec["delivery_stats"]
    kpi = rec["operation_kpis"]
    if "on_time_rate" in o:
        ds["on_time_rate"] = o["on_time_rate"]
    if "driver_rating" in o:
        ds["driver_rating"] = o["driver_rating"]
    if "packaging_ok_rate" in o:
        ds["packaging_ok_rate"] = o["packaging_ok_rate"]
    if "avg_prep_minutes" in o:
        kpi["avg_prep_minutes"] = o["avg_prep_minutes"]
    if "avg_delivery_add" in o:
        ds["avg_delivery_minutes"] = ds["avg_delivery_minutes"] + o["avg_delivery_add"]
    if "cancel_rate" in o:
        kpi["cancel_rate"] = o["cancel_rate"]
    rec["scenario"] = scenario
    return rec


def prompt_directive(scenario):
    """Sinh doan chi thi BAT BUOC nhoi vao prompt LLM cho quan co kich ban yeu.
    Tra ve "" neu merchant khong duoc gan kich ban (prompt giu nguyen phan bo tu nhien)."""
    spec = SCENARIOS.get(scenario)
    if not spec:
        return ""
    return (
        "\n\nKỊCH BẢN BẮT BUỘC (điểm yếu chủ đích của quán này để DEMO chẩn đoán):\n"
        f"- Điểm yếu: {spec['label']}.\n"
        f"- Khiếu nại: {spec['complaint_focus']}. Các khiếu nại còn lại có thể đa dạng nhẹ.\n"
        f"- filled_reviews: bảo đảm có ÍT NHẤT {spec['neg_reviews']} review điểm THẤP (score 3-5/10) "
        "phản ánh đúng điểm yếu trên; nếu real_review_count >= 8 thì vẫn thêm đủ số review tiêu cực này vào filled_reviews.\n"
    )
