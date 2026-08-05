"""Customer context tools (Phase 03) — profile, session candidates, delta proposal.

Three registry tools consumed by the Customer Crew (§5.4):
  - get_user_profile        (customer_coordinator, preference_reasoning)
  - get_session_candidates  (customer_coordinator, preference_reasoning)
  - propose_profile_delta   (preference_reasoning)

Each tool is a plain function taking kwargs, opening/closing its own `SessionLocal`.
Agents never receive a DB session. `propose_profile_delta` PROPOSES ONLY — it never
writes `preference_events` / `user_profiles` (§7.1 guardrail).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.errors import NotFoundError
from database.connection import SessionLocal
from repositories.session_repository import SessionRepository
from repositories.user_profile_repository import UserProfileRepository
from services import preference_service
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


# --------------------------------------------------------------------------- #
# args schemas (explicit → LLM gets rich field descriptions)
# --------------------------------------------------------------------------- #
class GetUserProfileArgs(BaseModel):
    user_id: str = Field(..., description="ID người dùng cần lấy hồ sơ sở thích")


class GetSessionCandidatesArgs(BaseModel):
    session_id: str = Field(..., description="ID phiên chat cần lấy danh sách quán ứng viên")


class ProposeDeltaArgs(BaseModel):
    user_id: str = Field(..., description="ID người dùng")
    session_id: str | None = Field(None, description="ID phiên chat (nếu có)")
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Ràng buộc rút từ hội thoại, vd {'cuisine':'chay','budget':'student'}",
    )
    weather: dict[str, Any] | None = Field(
        None, description="Kết quả get_weather_context (nếu có)"
    )


# --------------------------------------------------------------------------- #
# tool functions
# --------------------------------------------------------------------------- #
def get_user_profile(*, user_id: str) -> dict[str, Any]:
    """Read a user's confirmed preference profile (§6.5). Raises NotFoundError if absent."""
    db = SessionLocal()
    try:
        profile = UserProfileRepository(db).get_by_id(user_id)
        if profile is None:
            raise NotFoundError(
                f"Không tìm thấy hồ sơ user '{user_id}'.",
                details={"user_id": user_id},
            )
        return profile.model_dump()
    finally:
        db.close()


def get_session_candidates(*, session_id: str) -> dict[str, Any]:
    """Read the candidate merchant shortlist for a session. Empty when none (no raise)."""
    db = SessionLocal()
    try:
        candidates = SessionRepository(db).get_candidates(session_id)
        return {
            "session_id": session_id,
            "candidates": candidates,
            "total": len(candidates),
        }
    finally:
        db.close()


def propose_profile_delta(
    *,
    user_id: str,
    session_id: str | None = None,
    constraints: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Suggest candidate profile changes (never persisted — §7.1 guardrail).

    Reads the current profile for context, then delegates to the rule-based
    preference_service. Does NOT write preference_events / user_profiles."""
    db = SessionLocal()
    try:
        profile = UserProfileRepository(db).get_by_id(user_id)
    finally:
        db.close()

    suggestions = preference_service.propose_deltas(
        constraints=constraints or {},
        weather=weather,
        profile=profile,
    )
    return {
        "suggestions": [s.model_dump() for s in suggestions],
        "count": len(suggestions),
    }


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point (called by registry.auto_discover)."""
    reg.register(
        ToolSpec(
            name="get_user_profile",
            description=(
                "Lấy hồ sơ sở thích đã xác nhận của người dùng (cuisine thích/ghét, mức chi, "
                "khẩu vị, ăn kiêng, vị trí, khoảng cách ưu tiên) VÀ context_memory — các ghi "
                "nhớ dài hạn cross-session (vd: dị ứng, ăn chay trường, bệnh lý). Dùng "
                "context_memory khi liên quan đến câu hỏi hiện tại."
            ),
            input_schema={"user_id": "str (required)"},
            output_schema={
                "user_id": "str",
                "liked_cuisines": "list",
                "disliked_cuisines": "list",
                "budget_level": "str",
                "distance_preference_km": "float",
            },
            allowed_agents=agents_allowed_for("get_user_profile"),
            cache_policy="profile_snapshot",
            source_kind="real",
            args_schema=GetUserProfileArgs,
        ),
        get_user_profile,
    )

    reg.register(
        ToolSpec(
            name="get_session_candidates",
            description=(
                "Lấy danh sách quán ứng viên đã tạo trong phiên chat hiện tại để tinh chỉnh, "
                "tránh tìm kiếm lại từ đầu."
            ),
            input_schema={"session_id": "str (required)"},
            output_schema={"session_id": "str", "candidates": "list", "total": "int"},
            allowed_agents=agents_allowed_for("get_session_candidates"),
            cache_policy="none",
            source_kind="real",
            args_schema=GetSessionCandidatesArgs,
        ),
        get_session_candidates,
    )

    reg.register(
        ToolSpec(
            name="propose_profile_delta",
            description=(
                "ĐỀ XUẤT (không lưu) thay đổi hồ sơ sở thích dựa trên ràng buộc hội thoại + "
                "thời tiết. Mỗi đề xuất kèm lý do; KHÔNG ghi vào cơ sở dữ liệu."
            ),
            input_schema={
                "user_id": "str (required)",
                "session_id": "str | None",
                "constraints": "dict",
                "weather": "dict | None",
            },
            output_schema={"suggestions": "list", "count": "int"},
            allowed_agents=agents_allowed_for("propose_profile_delta"),
            cache_policy="none",
            has_side_effect=False,
            source_kind="real",
            args_schema=ProposeDeltaArgs,
        ),
        propose_profile_delta,
    )
