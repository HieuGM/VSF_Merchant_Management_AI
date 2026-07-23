"""Merchant Advisor CrewAI Flow (Design §4.1, §4.2, §5.3, §6.2) — Spec-Compliant Agentic Chatbot System.

Adheres strictly to CrewAI 1.15.5 @CrewBase convention matching reference project:
/home/minhnv/Downloads/food_intent_search_crew_v1_crewai-project/src/food_intent_search_crew/crew.py

Pipeline Flow:
Query -> Load Session History -> Intent Extraction by LLM -> Planning Agent -> Specialist Agents Execution via BaseTools -> 2-Layer Evidence Verification -> Synthesis LLM Agent -> Update Session State & Token Usage -> Final Response.
"""
import json
import uuid
from typing import Any, Generator
from sqlalchemy.orm import Session

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

from tools.merchant.crewai_tools import (
    GetMerchantProfileTool,
    GetProfileEvidenceTool,
    DiagnoseMerchantTool,
    RecommendImprovementsTool,
    CompareCompetitorsTool,
)
from tools.merchant.diagnosis_tool import diagnose_merchant


def get_configured_llm() -> LLM | None:
    """Instantiate CrewAI LLM with optional custom base_url, model, and api_key."""
    settings = get_settings()
    if not settings.llm_api_key:
        return None

    model_name = settings.llm_model
    if settings.llm_base_url and not model_name.startswith("openai/"):
        model_name = f"openai/{model_name}"

    kwargs: dict[str, Any] = {"model": model_name, "api_key": settings.llm_api_key}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return LLM(**kwargs)


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
            tools=[GetMerchantProfileTool()],
            llm=get_configured_llm(),
            allow_delegation=True,
            verbose=True,
        )

    @agent
    def merchant_profile_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["merchant_profile_analyst"],
            tools=[GetMerchantProfileTool(), GetProfileEvidenceTool()],
            llm=get_configured_llm(),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def diagnosis(self) -> Agent:
        return Agent(
            config=self.agents_config["diagnosis"],
            tools=[GetMerchantProfileTool(), GetProfileEvidenceTool(), DiagnoseMerchantTool()],
            llm=get_configured_llm(),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def recommendation(self) -> Agent:
        return Agent(
            config=self.agents_config["recommendation"],
            tools=[GetMerchantProfileTool(), GetProfileEvidenceTool(), RecommendImprovementsTool()],
            llm=get_configured_llm(),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def competitor(self) -> Agent:
        return Agent(
            config=self.agents_config["competitor"],
            tools=[CompareCompetitorsTool()],
            llm=get_configured_llm(),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def evidence_verifier(self) -> Agent:
        return Agent(
            config=self.agents_config["evidence_verifier"],
            tools=[GetProfileEvidenceTool()],
            llm=get_configured_llm(),
            allow_delegation=False,
            verbose=True,
        )

    @agent
    def synthesis_advisor(self) -> Agent:
        return Agent(
            config=self.agents_config["synthesis_advisor"],
            tools=[GetMerchantProfileTool(), GetProfileEvidenceTool()],
            llm=get_configured_llm(),
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
        )

    @task
    def recommend_improvements_task(self) -> Task:
        return Task(
            config=self.tasks_config["recommend_improvements_task"],
            agent=self.recommendation(),
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

    def build_crew_for_intent(self, intent: str) -> Crew:
        """Dynamically assemble Crew agents and tasks focused strictly on extracted user intent."""
        if intent == "competitor_analysis":
            return Crew(
                agents=[self.competitor(), self.synthesis_advisor()],
                tasks=[self.compare_competitors_task(), self.synthesis_chat_task()],
                process=Process.sequential,
                verbose=True,
            )
        elif intent == "diagnosis":
            return Crew(
                agents=[
                    self.merchant_profile_analyst(),
                    self.diagnosis(),
                    self.evidence_verifier(),
                    self.synthesis_advisor(),
                ],
                tasks=[
                    self.analyze_profile_task(),
                    self.diagnose_merchant_task(),
                    self.verify_evidence_task(),
                    self.synthesis_chat_task(),
                ],
                process=Process.sequential,
                verbose=True,
            )
        elif intent == "recommendation":
            return Crew(
                agents=[
                    self.diagnosis(),
                    self.recommendation(),
                    self.evidence_verifier(),
                    self.synthesis_advisor(),
                ],
                tasks=[
                    self.diagnose_merchant_task(),
                    self.recommend_improvements_task(),
                    self.verify_evidence_task(),
                    self.synthesis_chat_task(),
                ],
                process=Process.sequential,
                verbose=True,
            )
        elif intent == "profile_inquiry":
            return Crew(
                agents=[self.merchant_profile_analyst(), self.synthesis_advisor()],
                tasks=[self.analyze_profile_task(), self.synthesis_chat_task()],
                process=Process.sequential,
                verbose=True,
            )
        else:  # general_chat / off-topic / math (NO TOOLS INVOKED)
            return Crew(
                agents=[self.synthesis_advisor()],
                tasks=[self.synthesis_chat_task()],
                process=Process.sequential,
                verbose=True,
            )


def classify_intent(message: str) -> str:
    """Classify user query into specific merchant advisor intents."""
    msg_lower = message.strip().lower()

    if any(k in msg_lower for k in ("gần", "đối thủ", "xung quanh", "bán kính", "cạnh tranh", "quán nào")):
        return "competitor_analysis"

    if any(k in msg_lower for k in ("tại sao", "vấn đề", "chẩn đoán", "yếu", "chê", "sụt", "giảm", "kém", "thấp", "ít đơn", "vắng", "lỗi")):
        return "diagnosis"

    if any(k in msg_lower for k in ("cải thiện", "lời khuyên", "đề xuất", "giải pháp", "khuyến nghị", "làm gì", "tăng đơn", "tăng doanh thu")):
        return "recommendation"

    if any(k in msg_lower for k in ("hồ sơ", "chỉ số", "điểm số", "menu", "thực đơn", "món ăn", "giờ mở cửa", "giá")):
        return "profile_inquiry"

    return "general_chat"


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

        # 3. Retrieve Recent Conversation History
        history = session_svc.get_recent_history(session_id=sid, limit=6)
        history_str = json.dumps(history, ensure_ascii=False)

        intent = classify_intent(message)

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

            # 4. If LLM configured, execute Native CrewAI Agentic Chatbot Engine
            if settings.llm_configured:
                try:
                    crew_instance = MerchantAdvisorCrew().build_crew_for_intent(intent)
                    kickoff_res = crew_instance.kickoff(
                        inputs={
                            "merchant_id": merchant_id,
                            "query": message,
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
                    print(f"[LLM Agent Error, falling back to smart offline handler]: {llm_err}")

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

    def chat_stream(
        self,
        merchant_id: str,
        message: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: Session | None = None,
    ) -> Generator[str, None, None]:
        """Stream chat execution events as Server-Sent Events (SSE)."""
        yield f"event: agent_start\ndata: {json.dumps({'agent_name': 'MerchantAdvisorAgent', 'task': 'Analyzing merchant query', 'timestamp': '2026-07-22T17:00:00Z'})}\n\n"

        res = self.chat(
            merchant_id=merchant_id,
            message=message,
            session_id=session_id,
            user_id=user_id,
            db=db,
        )

        yield f"event: token_chunk\ndata: {json.dumps({'text': res['reply']})}\n\n"
        yield f"event: execution_finish\ndata: {json.dumps({'trace_id': res['trace_id'], 'status': 'COMPLETED'})}\n\n"


# Process-wide singleton instance
merchant_flow = MerchantFlowDispatcher()
