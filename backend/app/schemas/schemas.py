"""Pydantic Schemas - 请求/响应数据模型"""
from datetime import datetime, date
from typing import Optional, Any, Literal
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field
from pydantic import field_validator


class HealthDataSource(str, Enum):
    """健康数据来源枚举"""
    PATIENT_DIRECT = "PATIENT_DIRECT"    # 孕妇端直接录入
    PATIENT_CHAT = "PATIENT_CHAT"        # 对话中NLU识别
    FOLLOWUP = "FOLLOWUP"                # 随访中录入
    NURSE_INPUT = "NURSE_INPUT"          # 护士端录入
    DOCTOR_INPUT = "DOCTOR_INPUT"        # 医生端录入
    AGENT_REPORT = "AGENT_REPORT"        # Agent工具调用
    SEED_DATA = "SEED_DATA"              # 种子数据


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
class ImageItem(BaseModel):
    """单张图片数据"""
    data: str  # base64 编码的图片数据
    format: str = "jpeg"  # 图片格式: jpeg, png, webp, gif


class ChatSendRequest(BaseModel):
    pregnant_id: str
    message: str
    session_id: str = ""
    message_type: str = "TEXT"  # TEXT | AUDIO | IMAGE
    record_id: Optional[str] = None  # 随访记录ID，存在时进入随访Agent模式
    audio_data: Optional[str] = None  # base64 编码的音频数据（message_type=AUDIO 时使用）
    audio_format: str = "webm"  # 音频格式: webm, wav, mp3
    images: Optional[list[ImageItem]] = None  # 多张图片（message_type=IMAGE 时使用）


class ChatStreamRequest(BaseModel):
    """SSE streaming chat request (doctor/nurse AI chat endpoints)"""
    message: str = ""
    pregnant_id: str = ""
    message_type: str = Field(default="TEXT", pattern="^(TEXT|AUDIO|IMAGE)$")
    audio_data: Optional[str] = None
    audio_format: str = Field(default="webm", pattern="^(webm|wav|mp3|ogg|m4a)$")
    session_id: Optional[str] = None


class ChatNLUResult(BaseModel):
    intent: str = ""
    entities: dict[str, Any] = {}


class ChatResponse(BaseModel):
    content: str
    nlu_result: Optional[ChatNLUResult] = None
    session_id: str = ""
    memory_updated: list[str] = []
    audit_log_id: Optional[int] = None  # 关联的审计日志 ID，供前端提交反馈时使用
    source: Optional[str] = None
    followup_progress: Optional[dict] = None  # 随访进度 {answered, total, status}


# === FollowUp ===

# 随访状态机: draft → in_progress → completed → confirmed → archived
# - draft: 护士创建，等待孕妇开始
# - in_progress: 孕妇已开始回答（第一个问题答完）
# - completed: 所有问题回答完毕，系统自动归档
# - confirmed: 护士确认审核
# - archived: 长期存档
FOLLOWUP_STATUS_DRAFT = "draft"
FOLLOWUP_STATUS_IN_PROGRESS = "in_progress"
FOLLOWUP_STATUS_COMPLETED = "completed"
FOLLOWUP_STATUS_CONFIRMED = "confirmed"
FOLLOWUP_STATUS_ARCHIVED = "archived"

# 孕妇端可见的活跃随访状态（主页通知卡片展示条件）
FOLLOWUP_ACTIVE_STATUSES = [FOLLOWUP_STATUS_DRAFT, FOLLOWUP_STATUS_IN_PROGRESS]

# 随访回答结构化数据字段定义
FOLLOWUP_FIELD_SCHEMA = {
    "feeling": {"label": "身体感受", "type": "text", "extractable": False},
    "weight": {"label": "体重", "type": "number", "unit": "kg", "extractable": True, "metric": "weight"},
    "bp": {"label": "血压", "type": "text", "format": "sbp/dbp", "extractable": True, "metrics": ["systolic", "diastolic"]},
    "bp_morning": {"label": "晨血压", "type": "text", "format": "sbp/dbp", "extractable": True, "metrics": ["systolic", "diastolic"]},
    "bp_evening": {"label": "晚血压", "type": "text", "format": "sbp/dbp", "extractable": True, "metrics": ["systolic", "diastolic"]},
    "fetal_movement": {"label": "胎动", "type": "number", "unit": "次/小时", "extractable": True, "metric": "fetal_movement"},
    "blood_sugar_fasting": {"label": "空腹血糖", "type": "number", "unit": "mmol/L", "extractable": True, "metric": "blood_sugar_fasting"},
    "blood_sugar_postprandial": {"label": "餐后血糖", "type": "number", "unit": "mmol/L", "extractable": True, "metric": "blood_sugar_postprandial"},
    "sleep": {"label": "睡眠", "type": "number", "unit": "小时", "extractable": True, "metric": "sleep_hours"},
    "diet": {"label": "饮食", "type": "text", "extractable": False},
    "medication": {"label": "用药", "type": "text", "extractable": False},
    "mood": {"label": "情绪", "type": "text", "extractable": False},
    "stress": {"label": "压力", "type": "text", "extractable": False},
    "support": {"label": "社会支持", "type": "text", "extractable": False},
    "self_harm": {"label": "自伤想法", "type": "text", "extractable": False},
    "nausea": {"label": "恶心呕吐", "type": "text", "extractable": False},
    "bleeding": {"label": "出血", "type": "text", "extractable": False},
    "supplement": {"label": "补充剂", "type": "text", "extractable": False},
    "wound": {"label": "伤口", "type": "text", "extractable": False},
    "edema": {"label": "水肿", "type": "text", "extractable": False},
    "contraction": {"label": "宫缩", "type": "text", "extractable": False},
    "exercise": {"label": "运动", "type": "text", "extractable": False},
    "preparation": {"label": "分娩准备", "type": "text", "extractable": False},
    "signs": {"label": "临产征兆", "type": "text", "extractable": False},
    "appetite": {"label": "食欲", "type": "text", "extractable": False},
}


class FollowUpRecordResponse(BaseModel):
    id: UUID
    pregnant_id: str
    gestational_week: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    self_reported_data: dict = {}
    chief_complaint: Optional[str] = None
    obstetric_exam: dict = {}
    lab_results: dict = {}
    classification: str = "normal"
    health_education: list = []
    guidance_tags: list = []
    referral: Optional[dict] = None
    next_followup_date: Optional[date] = None
    status: str = FOLLOWUP_STATUS_DRAFT
    summary: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None
    ai_snapshot: dict = {}
    record_snapshot: dict = {}
    record_text: Optional[str] = None
    signature_data: dict = {}
    created_at: Optional[datetime] = None
    patient_name: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator(
        "self_reported_data", "obstetric_exam", "lab_results",
        "ai_snapshot", "record_snapshot", "signature_data",
        mode="before",
    )
    @classmethod
    def _none_to_dict(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v

    @field_validator("health_education", "guidance_tags", mode="before")
    @classmethod
    def _none_to_list(cls, v: Any) -> Any:
        if v is None:
            return []
        return v


class FollowUpConfirm(BaseModel):
    status: str = FOLLOWUP_STATUS_CONFIRMED
    reviewer_id: Optional[str] = None        # 审核护士ID
    review_comment: Optional[str] = None      # 审核意见
    ai_snapshot: Optional[dict] = None        # 审核时 AI 分析报告快照


class FollowUpSignatureRequest(BaseModel):
    """签名提交请求"""
    signature_image: str = Field(description="手写签名的 base64 PNG 图片数据")
    signer_name: str = Field(description="签名者姓名")


class FollowUpRecordUpdateRequest(BaseModel):
    """Update a follow-up record (partial update, safe fields only)"""
    summary: Optional[str] = Field(None, max_length=5000)
    classification: Optional[str] = Field(None, max_length=50)
    health_education: Optional[Any] = None
    nurse_notes: Optional[str] = Field(None, max_length=5000)


class FollowUpTrigger(BaseModel):
    pregnant_id: str
    template_id: Optional[str] = "standard"


# === FGR ===
class FgrAssessRequest(BaseModel):
    pregnant_id: str = ""
    gestational_weeks: float = 28.0
    image_type: str = "AC"


class FgrAssessResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    case_id: str
    risk_level: str
    risk_label: str
    fgr_probability: Optional[float] = None
    predicted_label: Optional[str] = None
    model_confidence: Optional[str] = None
    confidence_interval: dict = {}
    explanation: str = ""
    processing_time: int = 0
    hardware: str = "NPU"
    fold_details: Optional[list[dict]] = None


class PatientImageResponse(BaseModel):
    """患者绑定的超声图像信息"""
    pregnant_id: str
    has_image: bool
    image_url: str = ""
    display_name: str = ""


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
    domain: Optional[str] = None
    level: str
    message: str
    details: dict = {}
    status: str
    created_at: Optional[datetime] = None
    patient_name: Optional[str] = None
    gestational_age_days: Optional[int] = None

    model_config = {"from_attributes": True}


class AlertReviewRequest(BaseModel):
    action: str = Field(...,
        pattern="^(confirm|dismiss|escalate|downgrade|supplement|nurse_confirm|nurse_dismiss|nurse_escalate|nurse_appeal)$")
    reason: Optional[str] = None
    target_level: Optional[str] = Field(None,
        pattern="^(ORANGE|YELLOW|GREEN)$")


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
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    signature_data: Optional[dict] = None
    order_snapshot: Optional[dict] = None
    order_text: Optional[str] = None
    modified_by_doctor: Optional[bool] = False
    doctor_notes: Optional[str] = None
    patient_name: Optional[str] = None

    model_config = {"from_attributes": True}


class OrderSignRequest(BaseModel):
    doctor_id: str
    signature_image: Optional[str] = None  # base64 PNG 手写签名
    signer_name: Optional[str] = None  # 签名者姓名


class OrderUpdateRequest(BaseModel):
    """Update an existing medical order (partial update)"""
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    order_type: Optional[str] = Field(None, min_length=1, max_length=100)
    doctor_notes: Optional[str] = Field(None, max_length=2000)


class OrderDocumentResponse(BaseModel):
    order_id: str
    patient_name: str
    snapshot: dict = {}
    text: str = ""
    signature: dict = {}
    has_document: bool = False
class DashboardStats(BaseModel):
    total_pregnant: int = 0
    pending_alerts: int = 0
    today_followups: int = 0
    pending_reviews: int = 0
    high_risk_count: int = 0
    weekly_new_pregnant: int = 0
    pending_orders: int = 0
    fgr_high_risk_count: int = 0


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
    alert_level: str = ""  # LLM 返回的预警级别: RED/ORANGE/YELLOW/NONE


class FollowUpAiReviewResponse(BaseModel):
    """护士审核随访时的 AI 辅助报告"""
    summary: str = Field(description="本次随访要点摘要（100-200字）")
    abnormal_flags: list[str] = Field(default_factory=list, description="异常指标标红列表")
    action_needed: bool = Field(default=False, description="是否需要上报医生")
    recommendation: str = Field(description="审核建议：确认通过/需进一步沟通/紧急上报")
    detail_analysis: str = Field(default="", description="详细分析（100-200字）")


class FollowUpGenerateRequest(BaseModel):
    pregnant_id: str
    template_id: str = "standard"


class FollowUpAnalysisReport(BaseModel):
    """随访完成后的 LLM 结构化分析报告"""
    warm_summary: str = Field(description="温馨总结（30-50字），语气温和自然")
    abnormal_indicators: list[str] = Field(default_factory=list, description="异常指标列表，如['血压较上次升高15mmHg']")
    trend_analysis: str = Field(default="", description="与历史数据对比的趋势分析（50-100字）")
    personalized_advice: str = Field(default="", description="基于回答内容的个性化建议（50-100字）")
    nurse_action_suggestion: str = Field(default="", description="护士行动建议：确认通过/需进一步沟通/紧急上报")


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
    reasoning_chain: list[str] = []  # 逐步推理链
    source: str = "llm"  # "llm" | "template" — 区分数据来源


# === Order Explain ===
class OrderExplainResponse(BaseModel):
    order_id: str
    original_content: str
    plain_language: str = ""
    precautions: str = ""
    source: str = "AI_CARE"


# === Health Trend ===
class TrendDataPoint(BaseModel):
    date: str                          # ISO日期 "2026-04-01"
    gest_week: int                     # 孕周（整数，如 20）
    value: float                       # 数据值


class TrendSeries(BaseModel):
    metric: str                        # 指标代码，如 "systolic"
    name: str                          # 指标中文名，如 "收缩压"
    unit: str                          # 单位，如 "mmHg"
    normal_range: dict = {}            # {"min": 90, "max": 140}
    data: list[TrendDataPoint] = []    # 时序数据点
    trend: str = "insufficient_data"   # rising/falling/stable/insufficient_data
    latest_value: float | None = None
    is_normal: bool | None = None


class HealthTrendResponse(BaseModel):
    pregnant_id: str
    gestational_week: str = ""         # "24+3"
    axis_mode: str = "date"            # date / gestational_week
    series: list[TrendSeries] = []


# === Follow-Up History ===
class FollowUpHistoryRecord(BaseModel):
    id: str
    follow_up_date: str | None = None
    gestational_week: str | None = None
    status: str = "draft"
    summary: str | None = None
    chief_complaint: str | None = None
    self_reported_data: dict = {}
    obstetric_exam: dict = {}
    lab_results: dict = {}
    classification: str = "normal"
    health_education: list[str] = []
    guidance_tags: list = []
    referral: Optional[dict] = None
    next_followup_date: str | None = None
    signature_data: dict = {}

    @field_validator("self_reported_data", "obstetric_exam", "lab_results",
                     "signature_data", mode="before")
    @classmethod
    def _none_to_dict(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("health_education", "guidance_tags", mode="before")
    @classmethod
    def _none_to_list(cls, v: Any) -> Any:
        return v if v is not None else []


class FollowUpHistoryResponse(BaseModel):
    pregnant_id: str
    records: list[FollowUpHistoryRecord] = []


# === 生化指标趋势 ===
class LabTrendItem(BaseModel):
    """单项生化指标趋势"""
    lab_key: str
    name: str
    unit: str
    normal_low: Optional[float] = None
    normal_high: Optional[float] = None
    is_qualitative: bool = False
    data_points: list[dict] = []  # [{date, gest_week, value, raw_value}]
    latest_value: str = ""
    is_normal: Optional[bool] = None


class LabTrendResponse(BaseModel):
    """生化指标趋势响应"""
    pregnant_id: str
    gestational_week: str
    items: list[LabTrendItem] = []


# === 医护协作 ===
class NurseDoctorIssueCreate(BaseModel):
    pregnant_id: str
    issue_type: str = "risk_alert"
    title: str
    description: str
    priority: str = "medium"


class NurseDoctorIssueResponse(BaseModel):
    id: str
    pregnant_id: str
    patient_name: str
    reported_by: str
    issue_type: str
    title: str
    description: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
