"""Merchant Advisor CrewAI Flow (Design §4.1, §4.2, §5.3, §6.2) — Spec-Compliant Agentic Chatbot System.

Adheres strictly to CrewAI 1.15.5 @CrewBase convention matching reference project:
/home/minhnv/Downloads/food_intent_search_crew_v1_crewai-project/src/food_intent_search_crew/crew.py

Pipeline Flow:
Query -> Load Session History -> Intent Extraction by LLM -> Planning Agent -> Specialist Agents Execution via BaseTools -> 2-Layer Evidence Verification -> Synthesis LLM Agent -> Update Session State & Token Usage -> Final Response.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Generator
from sqlalchemy.orm import Session


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

from crewai import Agent, Crew, Process, Task, LLM
from crewai.lite_agent_output import LiteAgentOutput
from crewai.project import CrewBase, agent, crew, task
from crewai.tasks.task_output import TaskOutput

from core.settings import get_settings
from database.connection import SessionLocal
from models.profile import SCORED_DIMENSIONS
from services.merchant_profile_service import MerchantProfileService
from services.recommendation_service import RecommendationService
from services.competitor_service import CompetitorService
from services.agent_run_service import AgentRunService
from services.chat_session_service import ChatSessionService
from agents.listeners.crewai_listener import DatabaseRecordingListener, build_event_record
from agents.merchant.scope_guard import validate_query_scope

from tools.merchant.crewai_tools import (
    GetMerchantMetadataCatalogTool,
    SearchMerchantsTool,
    SearchTrendingDishesTool,
    GetMerchantProfileSummaryTool,
    GetMerchantOperationalMetricsTool,
    GetMerchantComplaintsTool,
    GetMenuAndFoodImagesTool,
    CompareMerchantBenchmarkTool,
    DiagnoseMerchantTool,
    RecommendImprovementsTool,
)
from tools.merchant.diagnosis_tool import diagnose_merchant
from models.merchant_orchestration import (
    Capability,
    EvidenceValidationResult,
    ExecutionResult,
    MerchantExecutionContext,
    PlannerResult,
    TokenUsage,
)
from services.evidence_validation_service import EvidenceValidationService
from services.merchant_plan_executor import execute_plan
from services.merchant_query_planner import rewrite_then_plan
from services.merchant_data_policy import MerchantDataPolicy


from pydantic import BaseModel, Field


class CauseItem(BaseModel):
    dimension: str = Field(description="Scored dimension name")
    score: float = Field(ge=0.0, le=1.0, description="Normalized score 0..1")
    evidence_refs: list[str] = Field(description="List of evidence references")


class DiagnosisTaskOutput(BaseModel):
    causes: list[CauseItem] = Field(description="List of root causes (max 5)")


class ActionItem(BaseModel):
    action_title: str
    description: str
    expected_impact: str | None = None
    evidence_refs: list[str]


class RecommendationTaskOutput(BaseModel):
    actions: list[ActionItem]


def get_configured_llm(tier: str = "large") -> LLM | None:
    """Instantiate CrewAI LLM with model tiering ("small" vs "large"), reading API key and base_url from .env."""
    try:
        settings = get_settings()
        api_key = settings.llm_api_key
        if not api_key:
            return None

        if tier == "small":
            model_name = settings.llm_model_small
        else:
            model_name = settings.llm_model_large
        if not model_name:
            raise ValueError(f"LLM model name for tier '{tier}' is not configured in .env.")

        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
            kwargs["provider"] = "openai"
        return LLM(**kwargs)
    except Exception as e:
        print(f"[get_configured_llm Warning]: {e}")
        return None


def validate_evidence_guardrail(
    output: TaskOutput | LiteAgentOutput | str | dict[str, Any],
) -> tuple[bool, Any]:
    """Validate the normalized diagnosis payload passed by CrewAI."""
    try:
        payload = getattr(output, "raw", output)
        if isinstance(payload, str):
            data = json.loads(payload)
        elif isinstance(payload, dict):
            data = payload
        else:
            return False, "Output chẩn đoán phải là một JSON object hoặc JSON string."

        if not isinstance(data, dict):
            return False, "Output chẩn đoán phải là một JSON object."
        if "causes" not in data:
            return False, "Output chẩn đoán thiếu trường bắt buộc 'causes'."

        causes = data["causes"]
        if not isinstance(causes, list):
            return False, "Trường 'causes' phải là một danh sách các nguyên nhân."
        if len(causes) > 5:
            return False, "Trường 'causes' chỉ được chứa tối đa 5 nguyên nhân."

        for cause in causes:
            if not isinstance(cause, dict):
                return False, "Mỗi phần tử trong 'causes' phải là một JSON object."
            dimension = cause.get("dimension")
            if dimension not in SCORED_DIMENSIONS:
                return False, f"Chiều chẩn đoán không hợp lệ: {dimension!r}."
            score = cause.get("score")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 1
            ):
                return False, (
                    f"Điểm của chiều '{dimension}' phải nằm trên thang 0..1."
                )
            refs = cause.get("evidence_refs", [])
            if (
                not isinstance(refs, list)
                or not refs
                or not all(isinstance(ref, str) and ref.strip() for ref in refs)
            ):
                return False, (
                    f"Nguyên nhân cho chiều '{dimension}' thiếu danh sách "
                    "bằng chứng 'evidence_refs'."
                )

        validated_output = (
            output if hasattr(output, "raw") or isinstance(output, (TaskOutput, LiteAgentOutput)) else data
        )
        return True, validated_output
    except Exception as e:
        return False, f"Không thể phân tích output chẩn đoán: {e}"


@CrewBase
class MerchantAdvisorCrew:
    """Merchant Advisor CrewBase class adhering to CrewAI 1.15.5 conventions."""

    agents_config = "../agents/merchant/config/agents.yaml"
    tasks_config = "../agents/merchant/config/tasks.yaml"

    @agent
    def merchant_coordinator(self) -> Agent:
        return Agent(
            config=self.agents_config["merchant_coordinator"],
            tools=[GetMerchantProfileSummaryTool(), GetMerchantMetadataCatalogTool()],
            llm=get_configured_llm("small"),
            allow_delegation=True,
            verbose=True,
        )

    @agent
    def merchant_profile_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["merchant_profile_analyst"],
            tools=[
                GetMerchantProfileSummaryTool(),
                GetMerchantOperationalMetricsTool(),
                GetMerchantComplaintsTool(),
                GetMenuAndFoodImagesTool(),
            ],
            llm=get_configured_llm("large"),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def diagnosis(self) -> Agent:
        return Agent(
            config=self.agents_config["diagnosis"],
            tools=[
                GetMerchantProfileSummaryTool(),
                GetMerchantOperationalMetricsTool(),
                GetMerchantComplaintsTool(),
                DiagnoseMerchantTool(),
            ],
            llm=get_configured_llm("large"),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def recommendation(self) -> Agent:
        return Agent(
            config=self.agents_config["recommendation"],
            tools=[
                GetMerchantProfileSummaryTool(),
                SearchTrendingDishesTool(),
                RecommendImprovementsTool(),
            ],
            llm=get_configured_llm("large"),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def competitor(self) -> Agent:
        return Agent(
            config=self.agents_config["competitor"],
            tools=[
                SearchMerchantsTool(),
                SearchTrendingDishesTool(),
                CompareMerchantBenchmarkTool(),
            ],
            llm=get_configured_llm("large"),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def evidence_verifier(self) -> Agent:
        return Agent(
            config=self.agents_config["evidence_verifier"],
            tools=[GetMerchantProfileSummaryTool(), GetMerchantComplaintsTool()],
            llm=get_configured_llm("small"),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def synthesis_advisor(self) -> Agent:
        return Agent(
            config=self.agents_config["synthesis_advisor"],
            tools=[],  # Pure response synthesis — NO tool calls to prevent wasteful executions
            llm=get_configured_llm("large"),
            allow_delegation=False,
            verbose=True,
        )

    @task
    def intent_planning_task(self) -> Task:
        return Task(
            config=self.tasks_config["intent_planning_task"],
            agent=self.merchant_coordinator(),
        )

    @task
    def analyze_profile_task(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_profile_task"],
            agent=self.merchant_profile_analyst(),
        )

    @task
    def diagnose_merchant_task(self) -> Task:
        return Task(
            config=self.tasks_config["diagnose_merchant_task"],
            agent=self.diagnosis(),
            guardrail=validate_evidence_guardrail,  # Layer 1 Task Guardrail check & retry
            output_pydantic=DiagnosisTaskOutput,
        )

    @task
    def recommend_improvements_task(self) -> Task:
        return Task(
            config=self.tasks_config["recommend_improvements_task"],
            agent=self.recommendation(),
            output_pydantic=RecommendationTaskOutput,
        )

    @task
    def search_market_task(self) -> Task:
        return Task(
            config=self.tasks_config["search_market_task"],
            agent=self.competitor(),
        )

    @task
    def compare_competitors_task(self) -> Task:
        return Task(
            config=self.tasks_config["compare_competitors_task"],
            agent=self.competitor(),
        )

    @task
    def verify_evidence_task(self) -> Task:
        return Task(
            config=self.tasks_config["verify_evidence_task"],
            agent=self.evidence_verifier(),
        )

    @task
    def synthesis_chat_task(self) -> Task:
        return Task(
            config=self.tasks_config["synthesis_chat_task"],
            agent=self.synthesis_advisor(),
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )

    def chat_crew(self) -> Crew:
        """Default multi-agent crew for full operational advisory."""
        return self.build_crew_for_intent("diagnosis")

    def build_crew_for_intent(
        self,
        intent: str,
        step_callback: Any = None,
        task_callback: Any = None,
    ) -> Crew:
        """Dynamically assemble Crew agents and tasks focused strictly on extracted capability intent."""
        kwargs: dict[str, Any] = {"process": Process.sequential, "verbose": True}
        if step_callback:
            kwargs["step_callback"] = step_callback
        if task_callback:
            kwargs["task_callback"] = task_callback

        if intent in ("benchmark", "competitor_analysis"):
            compare_task = self.compare_competitors_task()
            synth_task = self.synthesis_chat_task()
            synth_task.context = [compare_task]
            return Crew(
                agents=[self.competitor(), self.synthesis_advisor()],
                tasks=[compare_task, synth_task],
                **kwargs,
            )
        elif intent in ("weakness_explanation", "diagnosis", "recommendation"):
            profile_task = self.analyze_profile_task()
            diag_task = self.diagnose_merchant_task()
            rec_task = self.recommend_improvements_task()
            verify_task = self.verify_evidence_task()
            synth_task = self.synthesis_chat_task()
            synth_task.context = [profile_task, diag_task, rec_task, verify_task]
            return Crew(
                agents=[
                    self.merchant_profile_analyst(),
                    self.diagnosis(),
                    self.recommendation(),
                    self.evidence_verifier(),
                    self.synthesis_advisor(),
                ],
                tasks=[profile_task, diag_task, rec_task, verify_task, synth_task],
                **kwargs,
            )
        elif intent in ("ops_analysis", "profile_inquiry"):
            profile_task = self.analyze_profile_task()
            synth_task = self.synthesis_chat_task()
            synth_task.context = [profile_task]
            return Crew(
                agents=[self.merchant_profile_analyst(), self.synthesis_advisor()],
                tasks=[profile_task, synth_task],
                **kwargs,
            )
        elif intent == "search":
            search_task = self.search_market_task()
            synth_task = self.synthesis_chat_task()
            synth_task.context = [search_task]
            return Crew(
                agents=[self.competitor(), self.synthesis_advisor()],
                tasks=[search_task, synth_task],
                **kwargs,
            )
        else:  # general_chat / off-topic (NO TOOLS INVOKED)
            return Crew(
                agents=[self.synthesis_advisor()],
                tasks=[self.synthesis_chat_task()],
                **kwargs,
            )



def classify_intent(message: str) -> str:
    """Classify user query into one of 5 capability intents strictly using lightweight NLU Model:
    - search: searching restaurants, dishes, food discovery (e.g. 'bún chả ở đâu ngon nhất Huế')
    - benchmark: competitor comparison, geo-radius comparison
    - weakness_explanation: diagnosis of underperforming metrics, improvement advice, recommendations
    - ops_analysis: operational metrics, complaints, reviews, menu items, prices, store profile/info
    - general_chat: pure greetings, small talk, general questions
    """
    clean_msg = message.strip()[:200] if message else ""
    llm = get_configured_llm("small")
    if llm:
        prompt = (
            "Classify the input into EXACTLY ONE category:\n"
            "- 'search': searching restaurants/dishes/places (e.g., 'bún chả ngon nhất Huế', 'tìm quán cơm')\n"
            "- 'benchmark': competitor comparison in a radius\n"
            "- 'weakness_explanation': score drop diagnosis or improvement advice\n"
            "- 'ops_analysis': prep time, cancel rate, complaints, reviews, menu, store info\n"
            "- 'general_chat': greetings, small talk, general questions\n\n"
            "Output ONLY JSON: {\"intent\": \"category_name\"}"
        )

        try:
            response = llm.call(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": clean_msg},
                ]
            )
            raw_text = str(getattr(response, "content", response)).strip()
            if "{" in raw_text and "}" in raw_text:
                json_str = raw_text[raw_text.find("{"):raw_text.rfind("}") + 1]
                data = json.loads(json_str)
                intent = str(data.get("intent", "")).strip().lower()
                if intent in ("search", "benchmark", "weakness_explanation", "ops_analysis", "general_chat"):
                    return intent
        except Exception as e:
            print(f"[LLM Intent Classifier Error]: {e}")

    from services.merchant_query_planner import fallback_capability_plan
    from models.merchant_orchestration import Capability

    capabilities = set(fallback_capability_plan(clean_msg).capabilities)
    if Capability.OWNER_VS_MARKET_BENCHMARK in capabilities:
        return "benchmark"
    if (
        Capability.OWNER_DIAGNOSIS in capabilities
        or Capability.RECOMMENDATION in capabilities
    ):
        return "weakness_explanation"
    if (
        Capability.OWNER_PROFILE_ANALYSIS in capabilities
        or Capability.OWNER_REVIEW_ANALYSIS in capabilities
    ):
        return "ops_analysis"
    if Capability.RESTAURANT_SEARCH in capabilities:
        return "search"
    return "general_chat"


def rewrite_query(message: str, history_str: str = "") -> str:
    """Rewrite raw user query into a clean, standalone, structured query using NLU LLM.

    Resolves pronouns, ambiguous references (e.g. '?', 'ở đâu', 'quán nào'), and extracts location/dish context.
    """
    clean_msg = message.strip() if message else ""
    if not clean_msg or clean_msg == "?":
        # Handle single question mark or empty query with fallback text
        if history_str and history_str != "[]":
            clean_msg = "Phân tích thêm thông tin dựa trên ngữ cảnh trò chuyện trước đó"
        else:
            return clean_msg

    llm = get_configured_llm("small")
    if not llm:
        return clean_msg

    prompt = (
        "You are an NLU Query Rewriter for a Food & Merchant Advisory System.\n"
        "Rewrite the user's input into a clean, standalone, explicit query in Vietnamese for search and analysis tools.\n"
        "Rules:\n"
        "1. Resolve any pronouns, short references (e.g. '?', 'quán nào', 'ở đâu'), or ambiguous queries using conversation history.\n"
        "2. Make city, cuisine, dish names, and core intent explicit (e.g., 'bún chả ở đâu ngon nhất Huế' -> 'Tìm kiếm danh sách quán bún chả ngon và nổi tiếng tại Huế').\n"
        "3. Output ONLY the rewritten query text. Do NOT add JSON formatting, quotes, or extra explanations."
    )

    try:
        user_prompt = f"User Query: {clean_msg}"
        if history_str and history_str != "[]":
            user_prompt += f"\nConversation History: {history_str}"

        response = llm.call(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        rewritten = str(getattr(response, "content", response)).strip()
        if rewritten and len(rewritten) > 2 and not rewritten.startswith("{"):
            print(f"[NLU Query Rewrite]: '{clean_msg}' -> '{rewritten}'")
            return rewritten
    except Exception as e:
        print(f"[Query Rewrite Error]: {e}")

    return clean_msg


def _deterministic_synthesis(
    query: str,
    capabilities: list[Capability],
    execution: ExecutionResult,
    evidence: EvidenceValidationResult,
) -> str:
    """Render a grounded Vietnamese response when the synthesis LLM is unavailable."""
    sections: list[str] = []
    outputs = execution.outputs

    search = outputs.get("search")
    if search is not None:
        merchants = search.get("merchants", [])
        if merchants:
            lines = []
            for item in merchants[:10]:
                ratings = item.get("ratings") or {}
                rating = ratings.get("shopeefood") or ratings.get("foody")
                price = item.get("menu_price_median")
                metadata = []
                if rating is not None:
                    metadata.append(f"rating {rating}")
                if price is not None:
                    metadata.append(f"giá giữa khoảng {int(price):,}đ")
                if item.get("distance_km") is not None:
                    metadata.append(f"cách {item['distance_km']} km")
                suffix = f" — {', '.join(metadata)}" if metadata else ""
                lines.append(f"- **{item['name']}** ({item.get('cuisine', '')}){suffix}")
            sections.append("### Kết quả tìm kiếm\n" + "\n".join(lines))
        else:
            sections.append(
                "### Kết quả tìm kiếm\nKhông tìm thấy quán phù hợp trong dữ liệu hiện có."
            )

    cohort = outputs.get("cohort")
    if cohort and cohort.get("cohort_count", 0):
        lines = [f"- Quy mô cohort: {cohort['cohort_count']} quán."]
        dimensions = cohort.get("aggregates", {}).get("dimensions", {})
        for dimension, stats in dimensions.items():
            lines.append(
                f"- {dimension}: trung bình {stats['mean']:.3f}, "
                f"trung vị {stats['median']:.3f}."
            )
        themes = cohort.get("aggregates", {}).get("review_themes", {})
        if themes:
            top_themes = ", ".join(
                f"{name} ({count})" for name, count in list(themes.items())[:5]
            )
            lines.append(f"- Chủ đề review công khai nổi bật: {top_themes}.")
        sections.append("### Phân tích nhóm quán\n" + "\n".join(lines))

    profile = outputs.get("owner_profile")
    if profile and profile.get("status") == "ok":
        dimensions = profile.get("dimensions", {})
        ranked = sorted(
            (
                (name, score)
                for name, score in dimensions.items()
                if isinstance(score, (int, float))
            ),
            key=lambda item: item[1],
        )
        lines = [f"- {name}: {score:.3f}" for name, score in ranked]
        sections.append("### Chất lượng quán của bạn\n" + "\n".join(lines))

    reviews = outputs.get("owner_reviews")
    if reviews and reviews.get("total_count", 0):
        sentiments = reviews.get("sentiment_counts", {})
        themes = reviews.get("themes", {})
        sections.append(
            "### Review của quán\n"
            f"- Tổng review phân tích: {reviews['total_count']}.\n"
            f"- Cảm xúc: {sentiments}.\n"
            f"- Chủ đề nổi bật: {themes}."
        )

    diagnosis = outputs.get("diagnosis")
    if diagnosis:
        causes = diagnosis.get("causes", [])
        if causes:
            lines = [
                f"- {cause.get('issue', cause.get('dimension'))} "
                f"(evidence: {', '.join(cause.get('evidence_refs', []))})"
                for cause in causes[:5]
            ]
            sections.append("### Điểm yếu và nguyên nhân\n" + "\n".join(lines))
        elif diagnosis.get("status") == "healthy":
            sections.append(
                "### Điểm yếu và nguyên nhân\n"
                "Không có chiều chất lượng nào dưới ngưỡng chẩn đoán 0.600."
            )

    benchmark = outputs.get("benchmark")
    if benchmark and benchmark.get("dimensions"):
        lines = []
        for dimension, item in benchmark["dimensions"].items():
            direction = "cao hơn" if item["delta"] > 0 else "thấp hơn"
            lines.append(
                f"- {dimension}: quán {item['owner_value']:.3f}, "
                f"cohort {item['cohort_mean']:.3f} — {direction} "
                f"{abs(item['delta']):.3f}."
            )
        sections.append(
            "### So sánh quán với cohort công khai\n" + "\n".join(lines)
        )

    image_comparison = outputs.get("image_comparison")
    if image_comparison:
        owner = image_comparison.get("owner_summary", {})
        public = image_comparison.get("public_cohort_summary", {})
        gaps = image_comparison.get("gaps", {})
        lines = [
            f"- Hình ảnh quán: {owner.get('image_count', 0)} ảnh, "
            f"chất lượng trung bình {owner.get('quality_mean')}, "
            f"độ mờ trung bình {owner.get('blur_mean')}.",
            f"- Nhóm công khai: {public.get('image_count', 0)} ảnh từ "
            f"{public.get('merchant_count', 0)} quán, chất lượng trung bình "
            f"{public.get('quality_mean')}, độ mờ trung bình "
            f"{public.get('blur_mean')}.",
            f"- Khác biệt chất lượng: {gaps.get('quality_delta')}; "
            f"khác biệt độ mờ: {gaps.get('blur_delta')}.",
        ]
        lines.extend(
            f"- {difference}"
            for difference in image_comparison.get("differences", [])
        )
        public_samples = image_comparison.get("public_samples", [])
        if public_samples:
            lines.append(
                "- Ảnh công khai tham chiếu: "
                + ", ".join(
                    f"{sample.get('merchant_name')} / {sample.get('item_name')}"
                    for sample in public_samples
                )
                + "."
            )
        sections.append("### So sánh hình ảnh món ăn\n" + "\n".join(lines))

    recommendation = outputs.get("recommendation")
    if recommendation is not None:
        actions = recommendation.get("actions", [])
        if actions:
            lines = [
                f"- **{action['action_title']}**: {action['description']}"
                for action in actions
            ]
            body = "\n".join(lines)
        else:
            body = (
                "Chưa đủ evidence để đề xuất hành động cụ thể; cần bổ sung dữ "
                "liệu hoặc kiểm tra lại các tín hiệu chẩn đoán."
            )
        sections.append("### Hành động đề xuất\n" + body)

    if evidence.rejected:
        sections.append(
            f"_Đã loại {len(evidence.rejected)} nhận định không vượt qua kiểm tra "
            "evidence/policy._"
        )

    if not sections:
        return (
            "Xin chào! Tôi có thể giúp tìm và phân tích thị trường quán ăn, "
            "đánh giá quán của bạn, giải thích điểm yếu, so sánh cohort công khai "
            "và đề xuất cải thiện."
        )
    return "\n\n".join(sections)


def _synthesize_with_usage(
    merchant_id: str,
    query: str,
    history_str: str,
    execution: ExecutionResult,
    evidence: EvidenceValidationResult,
    settings: Any,
) -> tuple[str, TokenUsage]:
    if not settings.llm_configured:
        return (
            _deterministic_synthesis(
                query,
                [],
                execution,
                evidence,
            ),
            TokenUsage(),
        )

    verified_context = {
        "tool_outputs": execution.outputs,
        "verified_claims": [
            claim.model_dump() for claim in evidence.valid_claims
        ],
        "rejected_claim_count": len(evidence.rejected),
    }
    task = Task(
        description=(
            "Trả lời trực tiếp câu hỏi merchant owner bằng tiếng Việt.\n"
            "User query: {query}\n"
            "Conversation history: {chat_history}\n"
            "Verified structured context: {execution_context}\n"
            "Chỉ dùng dữ liệu trong verified context. Không tiết lộ KPI vận hành "
            "riêng, complaint hoặc diagnosis của đối thủ. Nếu dữ liệu thiếu, nói "
            "rõ giới hạn. Với câu compound, trả lời đủ từng phần."
        ),
        expected_output=(
            "Câu trả lời tiếng Việt có cấu trúc, grounded, ngắn gọn và đủ các "
            "phần user yêu cầu."
        ),
        agent=MerchantAdvisorCrew().synthesis_advisor(),
    )
    crew = Crew(
        agents=[task.agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )
    result = crew.kickoff(
        inputs={
            "merchant_id": merchant_id,
            "query": query,
            "chat_history": history_str,
            "execution_context": json.dumps(
                verified_context,
                ensure_ascii=False,
                default=str,
            ),
        }
    )
    usage = getattr(result, "token_usage", None)
    return (
        str(result.raw if hasattr(result, "raw") else result),
        TokenUsage(
            total_tokens=getattr(usage, "total_tokens", 0),
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
        ),
    )


class MerchantFlowDispatcher:
    """High-level flow runner connecting services, CrewAI execution, session state, and trace persistence."""

    def run_diagnosis(
        self, merchant_id: str, db: Session | None = None
    ) -> dict[str, Any]:
        """Execute deterministic diagnosis and recommendation workflow with trace logging."""
        session = db or SessionLocal()
        trace_id = f"tr-{uuid.uuid4().hex[:12]}"
        run_svc = AgentRunService(session)

        run_svc.start_run(
            trace_id=trace_id,
            crew_name="merchant_advisor_crew",
            intent="diagnose_merchant",
        )

        try:
            profile_svc = MerchantProfileService(session)
            rec_svc = RecommendationService(session)
            comp_svc = CompetitorService(session)

            profile = profile_svc.get_profile_view(merchant_id)
            diag = diagnose_merchant(merchant_id, db=session)
            recommendations = rec_svc.generate_recommendations(merchant_id)
            competitors = comp_svc.analyze_competitors(merchant_id)

            # Record event via listener
            listener = DatabaseRecordingListener(session)
            evt = build_event_record(
                trace_id=trace_id,
                event_type="run_started",
                agent_name="merchant_advisor_coordinator",
                task_name="diagnose_and_recommend",
                output_summary={
                    "merchant_id": merchant_id,
                    "causes_count": len(diag.get("causes", [])),
                },
                duration_ms=150,
                status="ok",
            )
            listener.handle(evt)

            run_svc.finish_run(trace_id=trace_id, status="completed")

            return {
                "trace_id": trace_id,
                "merchant_id": merchant_id,
                "status": recommendations.get("status", "ok"),
                "profile": profile,
                "diagnosis": diag,
                "recommendations": recommendations.get("actions", []),
                "competitors": competitors.get("competitors", []),
            }
        except Exception as e:
            run_svc.finish_run(trace_id=trace_id, status="failed", error_code=str(e))
            raise e
        finally:
            if db is None:
                session.close()

    def chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
        step_callback: Any = None,
        task_callback: Any = None,
        event_callback: Any = None,
    ) -> dict[str, Any]:
        """Execute one rewrite-first, multi-capability, policy-aware chat run."""
        del step_callback, task_callback  # Backward-compatible parameters.
        started_clock = time.perf_counter()
        session = db or SessionLocal()
        settings = get_settings()
        trace_id = f"tr-{uuid.uuid4().hex[:12]}"
        session_svc = ChatSessionService(session)
        run_svc = AgentRunService(session)
        run_started = False

        try:
            session_obj = session_svc.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                context_snapshot={"merchant_id": merchant_id},
            )
            sid = session_obj.session_id
            history = session_svc.get_compact_history(
                session_id=sid,
                max_turns=3,
            )
            session_svc.append_message(
                session_id=sid,
                sender="user",
                text=message,
                trace_id=trace_id,
            )

            is_in_scope, reject_reason = validate_query_scope(message)
            if not is_in_scope:
                run_svc.start_run(
                    trace_id=trace_id,
                    session_id=sid,
                    user_id=user_id,
                    crew_name="merchant_advisor_crew",
                    intent="out_of_scope",
                )
                run_started = True
                reply = reject_reason or (
                    "Câu hỏi nằm ngoài phạm vi hỗ trợ của Merchant Advisor AI."
                )
                token_dict = TokenUsage().model_dump()
                run_svc.finish_run(
                    trace_id=trace_id,
                    status="completed",
                    token_usage_json=token_dict,
                )
                session_svc.append_message(
                    session_id=sid,
                    sender="agent",
                    text=reply,
                    trace_id=trace_id,
                    structured_payload={"token_usage": token_dict},
                )
                return {
                    "trace_id": trace_id,
                    "session_id": sid,
                    "merchant_id": merchant_id,
                    "intent": "out_of_scope",
                    "capabilities": [],
                    "rewritten_query": message.strip(),
                    "reply": reply,
                    "token_usage": token_dict,
                    "trace_summary": [],
                    "duration_ms": round(
                        (time.perf_counter() - started_clock) * 1000
                    ),
                    "merchants": [],
                }

            query_policy = MerchantDataPolicy(merchant_id).query_decision(message)
            if not query_policy.allowed:
                run_svc.start_run(
                    trace_id=trace_id,
                    session_id=sid,
                    user_id=user_id,
                    crew_name="merchant_advisor_crew",
                    intent="policy_denied",
                )
                run_started = True
                policy_payload = {
                    "agent_name": "merchant_data_policy",
                    "status": "denied",
                    "scope": query_policy.scope,
                    "private_fields": query_policy.private_fields,
                    "decision": "deny_competitor_private",
                    "timestamp": _utc_now_iso(),
                }
                run_svc.record_event(
                    trace_id=trace_id,
                    event_type="policy_decision",
                    agent_name="merchant_data_policy",
                    task_name="query_policy_gate",
                    output_summary_json={
                        key: value
                        for key, value in policy_payload.items()
                        if key != "timestamp"
                    },
                    status="denied",
                )
                if event_callback is not None:
                    event_callback("policy_decision", policy_payload)
                reply = query_policy.reason or (
                    "Không thể cung cấp dữ liệu riêng tư của merchant khác."
                )
                token_dict = TokenUsage().model_dump()
                run_svc.finish_run(
                    trace_id=trace_id,
                    status="completed",
                    token_usage_json=token_dict,
                )
                session_svc.append_message(
                    session_id=sid,
                    sender="agent",
                    text=reply,
                    trace_id=trace_id,
                    structured_payload={
                        "token_usage": token_dict,
                        "policy_scope": query_policy.scope,
                    },
                )
                return {
                    "trace_id": trace_id,
                    "session_id": sid,
                    "merchant_id": merchant_id,
                    "intent": "policy_denied",
                    "capabilities": [],
                    "rewritten_query": message.strip(),
                    "reply": reply,
                    "token_usage": token_dict,
                    "trace_summary": [
                        {
                            "event": "policy_decision",
                            "agent_name": "merchant_data_policy",
                            "status": "denied",
                            "scope": query_policy.scope,
                        }
                    ],
                    "duration_ms": round(
                        (time.perf_counter() - started_clock) * 1000
                    ),
                    "merchants": [],
                    "competitors": [],
                    "structured_outputs": {},
                    "evidence_status": "not_required",
                }

            context = MerchantExecutionContext(
                trace_id=trace_id,
                session_id=sid,
                user_id=user_id,
                owner_merchant_id=merchant_id,
            )
            planner: PlannerResult = rewrite_then_plan(
                message,
                history=history,
                context=context,
            )
            capabilities = [
                capability.value for capability in planner.plan.capabilities
            ]
            intent = ",".join(capabilities)
            run_svc.start_run(
                trace_id=trace_id,
                session_id=sid,
                user_id=user_id,
                crew_name="merchant_advisor_crew",
                intent=intent,
            )
            run_started = True

            def _persistable_payload(
                event_type: str,
                payload: dict[str, Any],
            ) -> dict[str, Any]:
                if event_type != "tool_result":
                    return {
                        key: value
                        for key, value in payload.items()
                        if key not in {"timestamp"}
                    }
                result = payload.get("result")
                summary: dict[str, Any] = {
                    "step_id": payload.get("step_id"),
                    "status": payload.get("status"),
                }
                if isinstance(result, dict):
                    for key in (
                        "count",
                        "cohort_count",
                        "status",
                    ):
                        if key in result:
                            summary[key] = result[key]
                    if isinstance(result.get("dimensions"), dict):
                        summary["dimensions"] = list(result["dimensions"])
                return summary

            def emit(event_type: str, payload: dict[str, Any]) -> None:
                enriched = {**payload, "timestamp": _utc_now_iso()}
                run_svc.record_event(
                    trace_id=trace_id,
                    event_type=event_type,
                    agent_name=payload.get("agent_name"),
                    task_name=payload.get("step_id") or payload.get("task"),
                    tool_name=payload.get("tool_name"),
                    output_summary_json=_persistable_payload(
                        event_type,
                        payload,
                    ),
                    duration_ms=payload.get("duration_ms"),
                    status=payload.get("status", "ok"),
                    error_code=payload.get("error_code"),
                )
                if event_callback is not None:
                    event_callback(event_type, enriched)

            emit(
                "plan",
                {
                    "agent_name": "merchant_planner",
                    "task": "rewrite_and_plan",
                    "rewritten_query": planner.rewritten_query,
                    "capabilities": capabilities,
                    "filters": planner.plan.filters.model_dump(exclude_none=True),
                    "used_fallback": planner.used_fallback,
                },
            )
            execution = execute_plan(
                planner.plan,
                context=context,
                db=session,
                event_callback=emit,
            )
            if execution.claims:
                evidence = EvidenceValidationService(session).validate_claims(
                    execution.claims,
                    context=context,
                    aggregate_snapshots=execution.aggregate_snapshots,
                )
            else:
                evidence = EvidenceValidationResult(status="not_required")
            emit(
                "evidence_validation",
                {
                    "agent_name": "evidence_resolver",
                    "task": "resolve_and_filter_evidence",
                    "status": evidence.status,
                    "valid_claims": len(evidence.valid_claims),
                    "rejected_claims": len(evidence.rejected),
                    "rejection_reasons": [
                        item.reason for item in evidence.rejected
                    ],
                },
            )

            history_str = json.dumps(history, ensure_ascii=False)
            try:
                reply, synthesis_usage = _synthesize_with_usage(
                    merchant_id,
                    planner.rewritten_query,
                    history_str,
                    execution,
                    evidence,
                    settings,
                )
            except Exception as synthesis_error:
                emit(
                    "agent_retry",
                    {
                        "agent_name": "synthesis_advisor",
                        "task": "deterministic_synthesis_fallback",
                        "detail": str(synthesis_error),
                    },
                )
                reply = _deterministic_synthesis(
                    planner.rewritten_query,
                    planner.plan.capabilities,
                    execution,
                    evidence,
                )
                synthesis_usage = TokenUsage()

            total_usage = planner.token_usage + synthesis_usage
            token_dict = total_usage.model_dump()
            duration_ms = round(
                (time.perf_counter() - started_clock) * 1000
            )
            trace_summary = [
                {
                    "event": "plan",
                    "agent_name": "merchant_planner",
                    "capabilities": capabilities,
                },
                *execution.trace_steps,
                {
                    "event": "evidence_validation",
                    "agent_name": "evidence_resolver",
                    "status": evidence.status,
                    "valid_claims": len(evidence.valid_claims),
                    "rejected_claims": len(evidence.rejected),
                },
            ]
            run_svc.finish_run(
                trace_id=trace_id,
                status="completed",
                token_usage_json=token_dict,
            )
            session_svc.append_message(
                session_id=sid,
                sender="agent",
                text=reply,
                trace_id=trace_id,
                structured_payload={
                    "token_usage": token_dict,
                    "capabilities": capabilities,
                    "rewritten_query": planner.rewritten_query,
                    "duration_ms": duration_ms,
                },
            )
            return {
                "trace_id": trace_id,
                "session_id": sid,
                "merchant_id": merchant_id,
                "intent": intent,
                "capabilities": capabilities,
                "rewritten_query": planner.rewritten_query,
                "reply": reply,
                "token_usage": token_dict,
                "trace_summary": trace_summary,
                "duration_ms": duration_ms,
                "merchants": execution.merchants,
                "competitors": execution.merchants,
                "structured_outputs": execution.outputs,
                "evidence_status": evidence.status,
            }
        except Exception as error:
            if run_started:
                try:
                    run_svc.finish_run(
                        trace_id=trace_id,
                        status="failed",
                        error_code=str(error),
                    )
                except Exception:
                    pass
            raise
        finally:
            if db is None:
                session.close()

    def chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        """Stream events from the same single chat run used for the final answer."""
        del db  # Worker owns a thread-local SQLAlchemy session.
        import queue
        import threading

        event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        result_box: dict[str, Any] = {}

        def event_cb(event_type: str, payload: dict[str, Any]) -> None:
            event_queue.put((event_type, payload))

        def worker() -> None:
            worker_session = SessionLocal()
            try:
                result_box["res"] = self.chat(
                    merchant_id=merchant_id,
                    message=message,
                    session_id=session_id,
                    user_id=user_id,
                    db=worker_session,
                    event_callback=event_cb,
                )
            except Exception as error:
                result_box["err"] = error
            finally:
                worker_session.close()
                event_queue.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        start_time = time.time()
        timeout_seconds = 300

        while True:
            try:
                event = event_queue.get(timeout=0.2)
                if event is None:
                    break
                event_type, payload = event
                yield (
                    f"event: {event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                )
            except queue.Empty:
                if time.time() - start_time > timeout_seconds:
                    result_box["err"] = RuntimeError(
                        "Hệ thống xử lý quá thời gian chờ 300 giây."
                    )
                    break
                if not thread.is_alive() and event_queue.empty():
                    break

        thread.join(timeout=1.0)
        if "res" in result_box:
            result = result_box["res"]
            reply = result.get("reply", "")
            for index in range(0, len(reply), 24):
                yield (
                    "event: token_chunk\n"
                    f"data: {json.dumps({'text': reply[index:index + 24]}, ensure_ascii=False)}\n\n"
                )
            finish = {
                "trace_id": result.get("trace_id", ""),
                "status": "COMPLETED",
                "capabilities": result.get("capabilities", []),
                "rewritten_query": result.get("rewritten_query", message),
                "token_usage": result.get("token_usage", {}),
                "duration_ms": result.get("duration_ms"),
                "merchants": result.get("merchants", []),
                "competitors": result.get("merchants", []),
                "evidence_status": result.get("evidence_status"),
            }
            yield (
                "event: execution_finish\n"
                f"data: {json.dumps(finish, ensure_ascii=False, default=str)}\n\n"
            )
        else:
            error_text = str(result_box.get("err", "Unknown execution error"))
            yield (
                "event: agent_error\n"
                f"data: {json.dumps({'agent_name': 'MerchantFlow', 'detail': error_text, 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"
            )
            yield (
                "event: execution_finish\n"
                f"data: {json.dumps({'status': 'FAILED', 'error': error_text}, ensure_ascii=False)}\n\n"
            )

    def _legacy_chat(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
        step_callback: Any = None,
        task_callback: Any = None,
    ) -> dict[str, Any]:
        """Process chat query from merchant owner using Spec-Compliant Agentic Pipeline."""
        session = db or SessionLocal()
        settings = get_settings()
        trace_id = f"tr-{uuid.uuid4().hex[:12]}"

        session_svc = ChatSessionService(session)
        run_svc = AgentRunService(session)

        # 1. Session State Initialization
        session_obj = session_svc.get_or_create_session(
            session_id=session_id,
            user_id=user_id,
            context_snapshot={"merchant_id": merchant_id},
        )
        sid = session_obj.session_id

        # 2. Append User Prompt to Chat History
        session_svc.append_message(
            session_id=sid,
            sender="user",
            text=message,
            trace_id=trace_id,
        )

        # 3. Scope Guard Check (Early Out-of-Scope Rejection)
        is_in_scope, reject_reason = validate_query_scope(message)
        if not is_in_scope:
            reply = reject_reason or "Câu hỏi nằm ngoài phạm vi hỗ trợ của Merchant Advisor AI."
            session_svc.append_message(
                session_id=sid,
                sender="agent",
                text=reply,
                trace_id=trace_id,
            )
            return {
                "trace_id": trace_id,
                "session_id": sid,
                "merchant_id": merchant_id,
                "intent": "out_of_scope",
                "reply": reply,
                "token_usage": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0},
            }

        # 4. Retrieve Compact Conversation History (max 3 turns)
        history = session_svc.get_compact_history(session_id=sid, max_turns=3)
        history_str = json.dumps(history, ensure_ascii=False)

        # 5. NLU Intent Classification & Query Rewrite Layer
        intent = classify_intent(message)
        rewritten_query = rewrite_query(message, history_str)

        run_svc.start_run(
            trace_id=trace_id,
            session_id=sid,
            user_id=user_id,
            crew_name="merchant_advisor_crew",
            intent=intent,
        )

        try:
            reply: str = ""
            recommendations: list[Any] = []

            # 6. If LLM configured, execute Native CrewAI Agentic Chatbot Engine with Rewritten Query
            if settings.llm_configured:
                try:
                    crew_instance = MerchantAdvisorCrew().build_crew_for_intent(
                        intent,
                        step_callback=step_callback,
                        task_callback=task_callback,
                    )
                    kickoff_res = crew_instance.kickoff(
                        inputs={
                            "merchant_id": merchant_id,
                            "query": rewritten_query,
                            "chat_history": history_str,
                        }
                    )

                    reply = str(kickoff_res.raw if hasattr(kickoff_res, "raw") else kickoff_res)
                    token_usage = getattr(kickoff_res, "token_usage", {})
                    token_dict = {
                        "total_tokens": getattr(token_usage, "total_tokens", 0),
                        "prompt_tokens": getattr(token_usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(token_usage, "completion_tokens", 0),
                    }
                    run_svc.finish_run(trace_id=trace_id, status="completed", token_usage_json=token_dict)

                    session_svc.append_message(
                        session_id=sid,
                        sender="agent",
                        text=reply,
                        trace_id=trace_id,
                        structured_payload={"token_usage": token_dict},
                    )

                    return {
                        "trace_id": trace_id,
                        "session_id": sid,
                        "merchant_id": merchant_id,
                        "intent": intent,
                        "reply": reply,
                        "token_usage": token_dict,
                    }
                except Exception as llm_err:
                    print(f"[LLM Agent Error]: {llm_err}")
                    run_svc.finish_run(trace_id=trace_id, status="failed", error_code=str(llm_err))
                    raise RuntimeError(f"Lỗi thực thi LLM Model: {llm_err}") from llm_err

            # 5. Smart Offline Fallback with Real Data Resolution
            if intent == "general_chat":
                reply = (
                    f"Xin chào! Tôi là Merchant Advisor AI đại diện cho quán '{merchant_id}'. "
                    f"Tôi có thể hỗ trợ bạn:\n"
                    f"  1. Chẩn đoán điểm yếu chỉ số 8 chiều & sinh khuyến nghị cải thiện.\n"
                    f"  2. So sánh vị thế với các đối thủ cạnh tranh xung quanh quán.\n"
                    f"  3. Kiểm tra bằng chứng đánh giá khách hàng (Review & Metric refs).\n"
                    f"Bạn cần hỗ trợ phân tích thông tin gì?"
                )
                recommendations = []
            elif intent == "competitor_analysis":
                comp_svc = CompetitorService(session)
                comp_res = comp_svc.analyze_competitors(merchant_id, radius_km=5.0)
                comps = comp_res.get("competitors", [])

                if comps:
                    lines = [f"- {c['name']} (ID: {c['merchant_id']}): Cách {c['distance_km']}km | Loại hình: {c['cuisine']}" for c in comps]
                    reply = (
                        f"Dưới đây là danh sách các đối thủ cạnh tranh xung quanh quán '{merchant_id}' trong bán kính 5.0km:\n"
                        + "\n".join(lines)
                    )
                else:
                    reply = f"Không tìm thấy đối thủ cạnh tranh nào trong bán kính 5.0km xung quanh quán '{merchant_id}'."
                recommendations = []
            else:
                diag_res = self.run_diagnosis(merchant_id, db=session)
                recommendations = diag_res.get("recommendations", [])

                if recommendations:
                    action_summary = "\n".join(
                        [f"- {a['action_title']}: {a['description']} (Chứng cứ: {a['evidence_refs']})" for a in recommendations]
                    )
                    reply = (
                        f"Dựa trên phân tích 8 chiều cho quán '{merchant_id}', hệ thống chẩn đoán các vấn đề chính "
                        f"và khuyến nghị giải pháp như sau:\n{action_summary}"
                    )
                else:
                    reply = f"Hồ sơ quán '{merchant_id}' hoạt động ổn định, không có chiều chỉ số dưới ngưỡng 0.600."

            run_svc.finish_run(trace_id=trace_id, status="completed")

            session_svc.append_message(
                session_id=sid,
                sender="agent",
                text=reply,
                trace_id=trace_id,
            )

            return {
                "trace_id": trace_id,
                "session_id": sid,
                "merchant_id": merchant_id,
                "intent": intent,
                "reply": reply,
                "recommendations": recommendations,
            }
        except Exception as e:
            run_svc.finish_run(trace_id=trace_id, status="failed", error_code=str(e))
            raise e
        finally:
            if db is None:
                session.close()

    def _legacy_chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        """Stream chat execution events in real-time as Server-Sent Events (SSE)."""
        import queue
        import threading

        event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        # 1. Scope Guard Check
        is_in_scope, reject_reason = validate_query_scope(message)
        if not is_in_scope:
            reply = reject_reason or "Câu hỏi nằm ngoài phạm vi hỗ trợ của Merchant Advisor AI."
            yield f"event: agent_start\ndata: {json.dumps({'agent_name': 'ScopeGuard', 'task': 'Scope Validation', 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"
            yield f"event: token_chunk\ndata: {json.dumps({'text': reply}, ensure_ascii=False)}\n\n"
            yield f"event: execution_finish\ndata: {json.dumps({'trace_id': f'tr-{uuid.uuid4().hex[:12]}', 'status': 'COMPLETED'}, ensure_ascii=False)}\n\n"
            return

        # 2. Intent Classification
        intent = classify_intent(message)
        yield f"event: agent_start\ndata: {json.dumps({'agent_name': 'MerchantAdvisorCoordinator', 'task': f'Phân loại query intent: {intent}', 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"

        # 3. NLU Query Rewrite Check
        history_str = ""
        if session_id and db:
            session_svc = ChatSessionService(db)
            history_list = session_svc.get_compact_history(session_id=session_id, max_turns=3)
            history_str = json.dumps(history_list, ensure_ascii=False) if history_list else ""
        rewritten = rewrite_query(message, history_str)
        if rewritten != message.strip():
            yield f"event: agent_start\ndata: {json.dumps({'agent_name': 'QueryRewriter', 'task': f'Viết lại query: {rewritten}', 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"

        def step_cb(step: Any):
            tool_name = getattr(step, "tool", None) or getattr(step, "name", None)
            tool_input = getattr(step, "tool_input", None) or getattr(step, "args", None)
            tool_result = getattr(step, "result", None) or getattr(step, "output", None)

            if tool_name:
                event_queue.put((
                    "tool_call",
                    {
                        "tool_name": str(tool_name),
                        "args": str(tool_input) if tool_input else "",
                        "timestamp": _utc_now_iso(),
                    }
                ))
            if tool_result is not None:
                # Extract structured merchant list: handle both dict objects and JSON strings.
                # Different tools use different keys:
                #   compare_merchant_benchmark → 'competitors'
                #   search_merchants           → 'merchants'
                merchants_list: list[Any] = []
                try:
                    # Case 1: tool_result is already a dict (CrewAI passes raw dict)
                    if isinstance(tool_result, dict):
                        parsed = tool_result
                    else:
                        # Case 2: tool_result is a JSON string
                        parsed = json.loads(str(tool_result))

                    if isinstance(parsed, dict):
                        # Try 'competitors' first (compare_merchant_benchmark),
                        # then fall back to 'merchants' (search_merchants)
                        raw_list = (
                            parsed.get("competitors")
                            or parsed.get("merchants")
                            or []
                        )
                        if isinstance(raw_list, list):
                            for c in raw_list:
                                if not c.get("name"):
                                    continue
                                # Normalise rating: benchmark uses 'scores', search uses 'ratings'
                                rating = None
                                if c.get("scores"):
                                    rating = next(iter(c["scores"].values()), None)
                                elif isinstance(c.get("ratings"), dict):
                                    r = c["ratings"]
                                    rating = r.get("shopeefood") or r.get("foody")
                                elif isinstance(c.get("rating"), (int, float)):
                                    rating = c["rating"]
                                merchants_list.append({
                                    "merchant_id": str(c.get("merchant_id", "")),
                                    "name": c.get("name", ""),
                                    "cuisine": c.get("cuisine", parsed.get("cuisine", "")),
                                    "distance_km": c.get("distance_km"),
                                    "address": c.get("address"),
                                    "rating": rating,
                                })
                except (json.JSONDecodeError, AttributeError, TypeError):
                    pass

                result_str = str(tool_result)

                result_detail = (
                    f"Đã tìm thấy {len(merchants_list)} quán phù hợp."
                    if merchants_list
                    else result_str[:300]
                )
                event_queue.put((
                    "tool_result",
                    {
                        "tool_name": str(tool_name or "Tool"),
                        "result": result_detail,
                        "competitors": merchants_list,  # frontend reads this field
                        "timestamp": _utc_now_iso(),
                    }
                ))

        def task_cb(task_output: Any):
            desc = getattr(task_output, "description", None) or "Executing task"
            role = getattr(task_output, "agent", None) or "SpecialistAgent"
            event_queue.put((
                "agent_start",
                {
                    "agent_name": str(role),
                    "task": str(desc)[:100],
                    "timestamp": _utc_now_iso(),
                }
            ))

        result_box: dict[str, Any] = {}

        def worker():
            worker_session = SessionLocal()
            try:
                res = self.chat(
                    merchant_id=merchant_id,
                    message=message,
                    session_id=session_id,
                    user_id=user_id,
                    db=worker_session,
                    step_callback=step_cb,
                    task_callback=task_cb,
                )
                result_box["res"] = res
            except Exception as ex:
                result_box["err"] = ex
            finally:
                worker_session.close()
                event_queue.put(None)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        import time
        start_time = time.time()
        timeout_seconds = 300

        # Stream events from queue in real-time
        while True:
            try:
                evt = event_queue.get(timeout=0.2)
                if evt is None:
                    break
                event_type, data_dict = evt
                yield f"event: {event_type}\ndata: {json.dumps(data_dict, ensure_ascii=False)}\n\n"
            except queue.Empty:
                if time.time() - start_time > timeout_seconds:
                    result_box["err"] = RuntimeError("Hệ thống xử lý quá thời gian chờ (Timeout > 120s). Vui lòng kiểm tra kết nối LLM Server.")
                    break
                if not t.is_alive() and event_queue.empty():
                    break

        t.join(timeout=1.0)

        if "res" in result_box:
            res = result_box["res"]
            reply_text = res.get("reply", "")

            # Gather all competitors seen during tool_result events for execution_finish
            # (the frontend will name-match these against reply_text)
            all_competitors: list[Any] = res.get("competitors", [])

            # Stream response chunks in real-time
            chunk_size = 15
            for i in range(0, len(reply_text), chunk_size):
                chunk = reply_text[i:i + chunk_size]
                yield f"event: token_chunk\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

            yield f"event: execution_finish\ndata: {json.dumps({'trace_id': res.get('trace_id', ''), 'token_usage': res.get('token_usage', {}), 'competitors': all_competitors, 'status': 'COMPLETED'}, ensure_ascii=False)}\n\n"
        elif "err" in result_box:
            err_msg = str(result_box["err"])
            yield f"event: agent_error\ndata: {json.dumps({'agent_name': 'LLMEngine', 'detail': err_msg, 'timestamp': _utc_now_iso()}, ensure_ascii=False)}\n\n"
            yield f"event: execution_finish\ndata: {json.dumps({'status': 'FAILED', 'error': err_msg}, ensure_ascii=False)}\n\n"


# Process-wide singleton instance
merchant_flow = MerchantFlowDispatcher()
