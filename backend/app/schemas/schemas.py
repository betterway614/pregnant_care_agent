"""Pydantic Schemas - 请求/响应数据模型"""
from datetime import datetime, date
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field


# === Pregnant ===
class PregnantBase(BaseModel):
    pregnant_id: str
    display_name: str
    nickname: Optional[str] = None
    phone: Optional[str] = None
    hospital_id: Optional[str] = None
    gestational_age_days: Optional[int] = None
    lmp_date: Optional[date] = None
    edd: Optional[date] = None
    risk_tags: list[str] = []
    avatar_url: Optional[str] = None


class PregnantResponse(PregnantBase):
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PregnantUpdateRequest(BaseModel):
    nickname: Optional[str] = None
    phone: Optional[str] = None
    hospital_id: Optional[str] = None
    display_name: Optional[str] = None


class PregnantHomeData(BaseModel):
    pregnant: PregnantResponse
    gestational_week: str = ""
    gestational_day: int = 0
    baby_info: dict = {}
    today_tasks: list[dict] = []
    upcoming_checks: list[dict] = []
    recommendations: dict = {}
    health_summary: dict = {}


# === HealthData ===
class HealthDataPointCreate(BaseModel):
    pregnant_id: str
    metric_code: str
    value: float
    unit: str = ""
    source: str = "PATIENT_REPORT"


class HealthDataPointResponse(BaseModel):
    id: UUID
    pregnant_id: str
    metric_code: str
    value: float
    unit: str
    recorded_at: datetime
    source: str

    model_config = {"from_attributes": True}


# === Schedule ===
class ScheduleNodeCreate(BaseModel):
    pregnant_id: str
    gest_week: int
    scheduled_date: date
    item: str
    node_type: str = "routine"


class ScheduleNodeResponse(BaseModel):
    id: UUID
    pregnant_id: str
    gest_week: int
    scheduled_date: date
    item: str
    node_type: str
    status: str
    is_published: int

    model_config = {"from_attributes": True}


class ScheduleNodeUpdate(BaseModel):
    scheduled_date: Optional[date] = None
    item: Optional[str] = None
    node_type: Optional[str] = None


# === Chat ===
class ChatSendRequest(BaseModel):
    pregnant_id: str
    message: str
    session_id: str = ""
    message_type: str = "TEXT"
    record_id: Optional[str] = None  # 随访记录ID，存在时进入随访Agent模式


class ChatNLUResult(BaseModel):
    intent: str = ""
    entities: dict[str, Any] = {}


class ChatResponse(BaseModel):
    content: str
    nlu_result: Optional[ChatNLUResult] = None
    session_id: str = ""
    memory_updated: list[str] = []
    source: Optional[str] = None
    followup_progress: Optional[dict] = None  # 随访进度 {answered, total, status}


# === FollowUp ===
class FollowUpRecordResponse(BaseModel):
    id: UUID
    pregnant_id: str
    gestational_week: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    self_reported_data: dict = {}
    chief_complaint: Optional[str] = None
    health_education: list = []
    status: str = "draft"
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_name: Optional[str] = None

    model_config = {"from_attributes": True}


class FollowUpConfirm(BaseModel):
    status: str = "confirmed"


class FollowUpTrigger(BaseModel):
    pregnant_id: str
    template_id: Optional[str] = "standard"


# === FGR ===
class FgrAssessRequest(BaseModel):
    pregnant_id: str
    gestational_weeks: float
    image_type: str = "AC"
    image_base64: Optional[str] = None


class FgrAssessResponse(BaseModel):
    case_id: str
    risk_level: str
    risk_label: str
    confidence_interval: dict = {}
    explanation: str = ""
    processing_time: int = 0
    hardware: str = "NPU"


class FgrTrendPoint(BaseModel):
    gestational_weeks: float
    risk_score: float
    confidence_lower: float
    confidence_upper: float
    assessed_at: str


# === Alert ===
class AlertResponse(BaseModel):
    id: UUID
    pregnant_id: str
    trigger_source: str
    rule_id: Optional[str] = None
    level: str
    message: str
    details: dict = {}
    status: str
    created_at: Optional[datetime] = None
    patient_name: Optional[str] = None
    gestational_age_days: Optional[int] = None

    model_config = {"from_attributes": True}


class AlertReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(confirm|dismiss|escalate)$")
    reason: Optional[str] = None


# === Order ===
class OrderGenerateRequest(BaseModel):
    pregnant_id: str
    alert_id: Optional[str] = None
    risk_level: str
    gestational_weeks: float


class OrderResponse(BaseModel):
    id: UUID
    pregnant_id: str
    alert_id: Optional[UUID] = None
    content: str
    order_type: str
    source: str
    status: str
    created_at: Optional[datetime] = None
    patient_name: Optional[str] = None

    model_config = {"from_attributes": True}


class OrderSignRequest(BaseModel):
    doctor_id: str


# === Dashboard ===
class DashboardStats(BaseModel):
    total_pregnant: int = 0
    pending_alerts: int = 0
    today_followups: int = 0
    pending_reviews: int = 0
    high_risk_count: int = 0
    weekly_new_pregnant: int = 0


class HardwareMonitor(BaseModel):
    gpu_utilization: float = 0
    gpu_memory_used: float = 0
    npu_utilization: float = 0
    cpu_utilization: float = 0
    memory_used: float = 0
    memory_total: float = 128
    inference_latency_ms: float = 0
    power_watts: float = 0


# === Recommend ===
class RecommendRequest(BaseModel):
    pregnant_id: str


class RecommendResponse(BaseModel):
    pregnant_id: str
    gestational_week: str
    weekly_tips: str = ""
    diet_advice: str = ""
    exercise_advice: str = ""
    warning_signs: str = ""
    baby_development: str = ""
    source: str = "AI_CARE"


# === 随访排期推荐 ===
class FollowupScheduleRecommendation(BaseModel):
    recommended_date: str                    # ISO日期 "2026-05-15" 或 "immediate"
    gestational_week: str                    # 该日期的孕周 "29+0"
    template_id: str                         # standard / fgr_high_risk / post_discharge
    reason: str                              # 推荐原因（中文）
    priority: str                            # high / medium / low
    is_overdue: bool = False
    suggested_actions: list[str] = []


class FollowupScheduleContext(BaseModel):
    days_since_last_followup: int | None = None
    last_followup_date: str | None = None
    last_followup_status: str | None = None
    health_data_frequency: str = "inactive"  # active / moderate / inactive
    health_data_count_14d: int = 0
    active_alert_count: int = 0
    has_critical_alerts: bool = False
    risk_tags: list[str] = []


class FollowupScheduleResponse(BaseModel):
    pregnant_id: str
    current_gestational_week: str
    recommendations: list[FollowupScheduleRecommendation] = []
    context_summary: FollowupScheduleContext = FollowupScheduleContext()


# === Nurse AI ===
class NurseAnalyzeRequest(BaseModel):
    pregnant_id: str


class NurseAnalyzeResponse(BaseModel):
    pregnant_id: str
    patient_name: str
    summary: str = ""
    risk_assessment: str = ""
    nursing_suggestions: str = ""
    followup_focus: list[str] = []
    followup_schedule: FollowupScheduleResponse | None = None


class FollowUpGenerateRequest(BaseModel):
    pregnant_id: str
    template_id: str = "standard"


class FollowUpGenerateResponse(BaseModel):
    pregnant_id: str
    opening_message: str = ""
    questions: list[dict] = []
    closing_message: str = ""


# === Doctor AI ===
class DoctorAnalyzeRequest(BaseModel):
    pregnant_id: str = ""
    query: str = ""


class DoctorAnalyzeResponse(BaseModel):
    pregnant_id: str
    analysis: str = ""
    evidence_references: list[str] = []
    suggested_orders: str = ""
    risk_summary: str = ""
    differential_diagnosis: list[dict] = []  # [{condition, confidence, reasoning}]
    reasoning_chain: list[str] = []  # 逐步推理链


# === Order Explain ===
class OrderExplainResponse(BaseModel):
    order_id: str
    original_content: str
    plain_language: str = ""
    precautions: str = ""
    source: str = "AI_CARE"
