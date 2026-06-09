"""SQLAlchemy 数据模型定义"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Date, Boolean,
    Text, ForeignKey, JSON, TypeDecorator, Index
)
from ..database import Base
from ..utils.timezone import beijing_now


class _UUID(TypeDecorator):
    """跨数据库UUID类型：SQLite用String，PostgreSQL用原生UUID"""
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


UUIDColumn = _UUID
GUID = _UUID  # 别名，保持兼容


class Pregnant(Base):
    """孕妇（匿名哈希ID）"""
    __tablename__ = "pregnant"

    pregnant_id = Column(String(64), primary_key=True, comment="匿名哈希ID")
    display_name = Column(String(32), nullable=False, comment="展示名称")
    nickname = Column(String(32), nullable=True, comment="昵称")
    phone = Column(String(20), nullable=True, comment="手机号(脱敏)")
    hospital_id = Column(String(32), nullable=True, comment="医院ID卡号")
    gestational_age_days = Column(Integer, nullable=True, comment="孕周天数")
    height_cm = Column(Float, nullable=True, comment="身高(cm)")
    pre_pregnancy_weight_kg = Column(Float, nullable=True, comment="孕前体重(kg)")
    lmp_date = Column(Date, nullable=True, comment="末次月经")
    edd = Column(Date, nullable=True, comment="预产期")
    risk_tags = Column(JSON, default=list, comment="风险标签列表")
    avatar_url = Column(String(256), nullable=True, comment="头像URL")
    created_at = Column(DateTime, default=beijing_now)


class HealthDataPoint(Base):
    """健康数据点"""
    __tablename__ = "health_data_points"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    metric_code = Column(String(32), nullable=False, comment="指标代码: weight/systolic/diastolic/fetal_movement/...")
    value = Column(Float, nullable=False)
    unit = Column(String(16), nullable=False)
    recorded_at = Column(DateTime, default=beijing_now)
    source = Column(String(32), default="PATIENT_REPORT", comment="数据来源")

    __table_args__ = (
        Index('idx_health_pregnant_metric_date', 'pregnant_id', 'metric_code', 'recorded_at'),
    )


class ScheduleNode(Base):
    """排期节点"""
    __tablename__ = "schedule_nodes"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    gest_week = Column(Integer, nullable=False, comment="孕周")
    scheduled_date = Column(Date, nullable=False, comment="计划日期")
    item = Column(String(128), nullable=False, comment="检查项目")
    node_type = Column(String(32), default="routine", comment="节点类型: routine/fgr_high_risk/custom")
    status = Column(String(16), default="pending", comment="状态: pending/published/completed")
    is_published = Column(Integer, default=0, comment="是否已发布")


class FollowUpRecord(Base):
    """随访记录 — 参照国家基本公共卫生服务规范(2024版)第2~5次产前随访记录表

    状态机: draft → in_progress → completed → confirmed → archived
    结构: SOAP (S=自报数据+主诉, O=产科检查+化验, A=评估分类, P=指导+转诊+下次随访)
    """
    __tablename__ = "follow_up_records"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    gestational_week = Column(String(16), comment="孕周")
    follow_up_date = Column(DateTime, default=beijing_now)
    # S: 主观 — 孕妇自报数据 + 主诉
    self_reported_data = Column(JSON, default=dict, comment="自报数据")
    chief_complaint = Column(Text, nullable=True, comment="主诉")
    # O: 客观 — 产科检查 + 化验结果
    obstetric_exam = Column(JSON, default=dict, comment="产科检查：fundal_height/cm, abdominal_circumference/cm, fetal_position, fetal_heart_rate/bpm")
    lab_results = Column(JSON, default=dict, comment="化验结果：hemoglobin/g·L⁻¹, urine_protein, other")
    # A: 评估 — 分类 + 摘要
    classification = Column(String(32), default="normal", comment="分类: normal/abnormal/critical")
    summary = Column(Text, nullable=True, comment="随访摘要")
    # P: 计划 — 指导 + 转诊 + 下次随访
    health_education = Column(JSON, default=list, comment="健康教育内容")
    guidance_tags = Column(JSON, default=list, comment="指导分类标签：营养/运动/心理/生活/监护/母乳/分娩准备")
    referral = Column(JSON, nullable=True, comment="转诊记录：has_referral, reason, institution, department")
    next_followup_date = Column(Date, nullable=True, comment="下次随访日期")
    # 状态 + 审核追溯
    status = Column(String(16), default="draft", comment="draft/in_progress/completed/confirmed/archived")
    reviewed_by = Column(String(64), nullable=True, comment="审核人（护士ID）")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    review_comment = Column(Text, nullable=True, comment="审核意见")
    ai_snapshot = Column(JSON, default=dict, comment="审核时AI分析报告快照（不可变）")
    # 归档文档
    record_snapshot = Column(JSON, default=dict, comment="确认时冻结的全量字段快照（不可变）")
    record_text = Column(Text, nullable=True, comment="格式化纯文本记录（用于检索、导出、打印）")
    signature_data = Column(JSON, default=dict, comment="签名数据：{image: base64, signer, signed_at}")
    created_at = Column(DateTime, default=beijing_now)

    __table_args__ = (
        Index('idx_followup_pregnant_status', 'pregnant_id', 'status'),
    )


class FgrAssessment(Base):
    """FGR评估记录"""
    __tablename__ = "fgr_assessments"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    case_id = Column(String(64), nullable=False, comment="病例编号")
    image_hash = Column(String(128), nullable=True, comment="脱敏B超图片哈希")
    image_type = Column(String(32), nullable=True, comment="切面类型: HC/AC/FL/UA_Doppler")
    gestational_weeks = Column(Float, nullable=False)
    risk_level = Column(String(16), nullable=False, comment="low/medium/high/critical")
    confidence_lower = Column(Float, nullable=True)
    confidence_upper = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    assessed_at = Column(DateTime, default=beijing_now)
    fgr_probability = Column(Float, nullable=True, comment="集成FGR概率(0-1)")
    predicted_label = Column(String(8), nullable=True, comment="FGR/NOR")
    model_confidence = Column(String(8), nullable=True, comment="High/Medium/Low")


class Alert(Base):
    """预警记录"""
    __tablename__ = "alerts"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    trigger_source = Column(String(32), default="RULE_ENGINE", comment="RULE_ENGINE/FGR_ALGORITHM/MANUAL")
    rule_id = Column(String(32), nullable=True)
    domain = Column(String(32), nullable=True, comment="vital/fetal/mental")
    level = Column(String(16), default="YELLOW", comment="RED/ORANGE/YELLOW")
    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict, comment="触发详情/历史时间线")
    status = Column(String(16), default="PENDING", comment="PENDING/CONFIRMED/DISMISSED/AUTO_DISMISSED")
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=beijing_now)

    __table_args__ = (
        Index('idx_alert_pregnant_status', 'pregnant_id', 'status', 'created_at'),
    )


class FetalMovementSession(Base):
    """胎动计数会话"""
    __tablename__ = "fetal_movement_sessions"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    start_time = Column(DateTime, nullable=False, comment="开始计数时间")
    end_time = Column(DateTime, nullable=True, comment="结束计数时间")
    duration_minutes = Column(Integer, nullable=True, comment="持续分钟数")
    total_count = Column(Integer, default=0, comment="总胎动次数")
    kick_times = Column(JSON, default=list, comment="每次胎动时刻列表")
    notes = Column(Text, nullable=True, comment="备注")


class MedicalOrder(Base):
    """医嘱记录"""
    __tablename__ = "medical_orders"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    alert_id = Column(UUIDColumn(as_uuid=True), ForeignKey("alerts.id"), nullable=True)
    content = Column(Text, nullable=False, comment="医嘱内容")
    order_type = Column(String(32), default="standard", comment="standard/custom")
    source = Column(String(32), default="AI_RECOMMENDED", comment="AI_RECOMMENDED/DOCTOR_WRITTEN")
    status = Column(String(16), default="draft", comment="draft/signed/executed")
    created_by = Column(String(64), nullable=True, comment="医生ID")
    signed_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True, comment="孕妇确认阅读时间")
    created_at = Column(DateTime, default=beijing_now)
    # 医嘱签署增强字段
    signature_data = Column(JSON, default=dict, comment="手写签名 {image, signer_name, signed_at}")
    order_snapshot = Column(JSON, default=dict, comment="签署时订单快照")
    order_text = Column(Text, nullable=True, comment="纯文本文档（打印/导出）")
    modified_by_doctor = Column(Boolean, default=False, comment="医生是否已修改内容")
    doctor_notes = Column(Text, nullable=True, comment="医生修改备注")

    __table_args__ = (
        Index('idx_order_pregnant_status', 'pregnant_id', 'status'),
    )


class Feedback(Base):
    """AI 回复反馈（支持孕妇/护士/医生三端）"""
    __tablename__ = "feedback"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), nullable=True, comment="关联孕妇ID（护士/医生反馈时可选）")
    feedback_role = Column(String(16), nullable=False, default="pregnant", index=True, comment="反馈来源角色: pregnant|nurse|doctor")
    user_id = Column(String(64), nullable=True, index=True, comment="反馈用户ID（护士/医生的用户ID）")
    message_id = Column(String(64), nullable=False, comment="前端消息ID")
    rating = Column(String(16), nullable=False, comment="thumbs_up/thumbs_down")
    comment = Column(Text, nullable=True, comment="可选评论")
    session_id = Column(String(64), nullable=True)
    audit_log_id = Column(Integer, nullable=True, index=True, comment="关联的审计日志ID（agent_audit_logs.id）")
    created_at = Column(DateTime, default=beijing_now)


class MentalHealthScreening(Base):
    """心理健康筛查（EPDS量表）"""
    __tablename__ = "mental_health_screenings"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    screening_type = Column(String(32), default="EPDS", comment="EPDS/PHQ9/GAD7")
    answers = Column(JSON, nullable=False, comment="10题答案，0-3分")
    total_score = Column(Integer, nullable=False, comment="总分0-30")
    risk_level = Column(String(16), nullable=False, comment="low/moderate/high/severe")
    created_at = Column(DateTime, default=beijing_now)


class ConversationMessage(Base):
    """对话消息持久化"""
    __tablename__ = "conversation_messages"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=False, comment="会话ID")
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    role = Column(String(16), nullable=False, comment="system/user/assistant")
    content = Column(Text, nullable=False, comment="消息内容")
    extra_data = Column(JSON, default=dict, comment="附加元数据：nlu_result等")
    created_at = Column(DateTime, default=beijing_now)


class DailyHealthSummary(Base):
    """每日健康摘要（用于快速查询某天整体健康状况）"""
    __tablename__ = "daily_health_summaries"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    date = Column(Date, nullable=False, comment="日期")
    weight = Column(Float, nullable=True, comment="体重 kg")
    systolic = Column(Float, nullable=True, comment="收缩压 mmHg")
    diastolic = Column(Float, nullable=True, comment="舒张压 mmHg")
    fetal_movement_avg = Column(Float, nullable=True, comment="胎动平均 次/小时")
    blood_sugar_fasting = Column(Float, nullable=True, comment="空腹血糖 mmol/L")
    blood_sugar_postprandial = Column(Float, nullable=True, comment="餐后血糖 mmol/L")
    mood_score = Column(Float, nullable=True, comment="情绪评分 1-3")
    data_source = Column(String(32), nullable=True, comment="主要数据来源")
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)

    __table_args__ = (
        Index('idx_daily_summary_pregnant_date', 'pregnant_id', 'date', unique=True),
    )


class AiAnalysisResult(Base):
    """AI 分析结果记录"""
    __tablename__ = "ai_analysis_results"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    analysis_type = Column(String(32), nullable=False, comment="分析类型: general/followup_summary/risk_assessment")
    result_data = Column(JSON, nullable=False, comment="分析结果数据")
    created_at = Column(DateTime, default=beijing_now)


class NurseDoctorIssue(Base):
    """医护协作问题记录"""
    __tablename__ = "nurse_doctor_issues"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    reported_by = Column(String(64), nullable=False, comment="上报护士ID")
    issue_type = Column(String(32), default="risk_alert", comment="risk_alert/abnormal_data/patient_complaint")
    title = Column(String(128), nullable=False, comment="问题标题")
    description = Column(Text, nullable=False, comment="问题描述")
    priority = Column(String(16), default="medium", comment="low/medium/high/urgent")
    status = Column(String(16), default="pending", comment="pending/acknowledged/processing/resolved")
    assigned_to = Column(String(64), nullable=True, comment="处理医生ID")
    resolution = Column(Text, nullable=True, comment="处理结果")
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=beijing_now)
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)


class AgentAuditLog(Base):
    """Agent 审计日志 — 每次 arun 一条记录"""
    __tablename__ = "agent_audit_logs"

    # 使用 Integer 自增主键（非 UUID）：审计日志为追加写入高频表，Integer 索引更紧凑、查询性能更好
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True, comment="对话会话ID")
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    # 审计日志有意不使用 ForeignKey：松耦合设计，确保父记录删除时审计日志不丢失
    agent_role = Column(String(16), nullable=False, index=True, comment="pregnant|nurse|doctor")
    agent_variant = Column(String(32), nullable=False, comment="chat|record|qa|emergency|complex|main")
    intent_classification = Column(String(32), nullable=True, comment="NLU识别的意图")
    routed_agent = Column(String(32), nullable=False, comment="最终路由的Agent变体")
    input_tokens = Column(Integer, default=0, comment="输入token数")
    output_tokens = Column(Integer, default=0, comment="输出token数")
    total_tokens = Column(Integer, default=0, comment="总token数")
    tool_calls_json = Column(JSON, nullable=True, comment="工具调用链（兼容旧格式）")
    tool_call_count = Column(Integer, default=0, comment="工具调用总次数")
    tool_error_count = Column(Integer, default=0, comment="工具调用失败次数")
    feedback_rating = Column(String(16), nullable=True, comment="用户反馈: thumbs_up/thumbs_down（冗余字段，便于聚合查询）")
    feedback_comment = Column(Text, nullable=True, comment="用户反馈评论（冗余字段）")
    model_id = Column(String(64), nullable=False, comment="模型ID")
    provider = Column(String(32), nullable=False, comment="模型提供商")
    total_latency_ms = Column(Integer, default=0, comment="总耗时ms")
    llm_latency_ms = Column(Integer, nullable=True, comment="LLM耗时ms")
    guardrail_triggered = Column(Boolean, default=False, comment="安全护栏触发")
    response_preview = Column(String(200), nullable=True, comment="回复预览(前200字)")
    created_at = Column(DateTime, default=beijing_now, index=True, comment="创建时间")


class ToolCallDetail(Base):
    """工具调用详情 — 每次 tool call 一条记录（AgentAuditLog 的子表）"""
    __tablename__ = "tool_call_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_log_id = Column(Integer, nullable=False, index=True, comment="关联的审计日志ID（agent_audit_logs.id）")
    tool_name = Column(String(64), nullable=False, index=True, comment="工具名称")
    tool_args_json = Column(JSON, nullable=True, comment="工具入参（脱敏后）")
    success = Column(Boolean, default=True, comment="调用是否成功")
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")
    latency_ms = Column(Integer, nullable=True, comment="单次工具调用耗时ms")
    result_preview = Column(String(200), nullable=True, comment="工具返回值预览（前200字）")
    call_order = Column(Integer, default=0, comment="在同一轮Agent run中的调用顺序（从1开始）")
    created_at = Column(DateTime, default=beijing_now, comment="创建时间")

    __table_args__ = (
        Index('idx_tool_call_audit', 'audit_log_id', 'call_order'),
    )
