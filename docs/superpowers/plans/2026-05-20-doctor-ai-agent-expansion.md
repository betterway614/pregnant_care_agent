# 医生端智能体功能扩展实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展医护双端AI智能体，实现意图识别→任务分解→工具调用的自主决策能力，以及医护协同闭环

**Architecture:**
- 双端智能体均采用 **意图识别 → 任务分解 → 工具调用** 架构
- 护士端（小护）：护理执行层，工具集偏向数据采集、随访管理、问题上报
- 医生端（Dr.智）：临床决策层，工具集偏向数据分析、医嘱制定、报告生成
- 通过WebSocket实现实时推送，医护协同闭环

**Tech Stack:** Vue 3 + FastAPI + SQLAlchemy + Agno Agent + SSE + WebSocket

---

## 智能体架构设计

### 核心流程
```
用户输入
    ↓
意图识别（NLU）
    ↓
任务分解（Planner）
    ↓
工具调用（Tool Execution）
    ↓
结果整合（Response）
```

### 功能边界（避免重合）

| 维度 | 小护（护士端） | Dr.智（医生端） |
|------|----------------|-----------------|
| **定位** | 护理执行层 | 临床决策层 |
| **意图识别** | 护理类意图（随访、数据采集、健康教育） | 临床类意图（诊断、医嘱、报告） |
| **工具集** | 数据查询、随访管理、预警创建、问题上报 | 数据分析、医嘱生成、报告生成、问题处理 |
| **输出风格** | 简洁、可操作、面向执行 | 专业、严谨、面向决策 |

---

## 文件结构

### 后端文件
| 文件 | 职责 | 操作 |
|------|------|------|
| `backend/app/core/agno_tools.py` | 工具集合 | 修改：新增护士端和医生端专用工具 |
| `backend/app/core/agno_medical_agents.py` | Agent工厂 | 修改：增强Agent的工具调用能力 |
| `backend/app/core/intent_classifier.py` | 意图分类器 | 新建：统一的意图识别模块 |
| `backend/app/models/models.py` | 数据库模型 | 修改：新增NurseDoctorIssue表 |
| `backend/app/routers/doctor_ai.py` | 医生AI路由 | 修改：新增报告生成、问题处理接口 |
| `backend/app/routers/nurse_ai.py` | 护士AI路由 | 修改：新增问题上报接口 |
| `backend/app/core/prompts.py` | 提示词管理 | 修改：新增意图识别和任务分解提示词 |
| `backend/app/schemas/schemas.py` | Pydantic模型 | 修改：新增相关Schema |

### 前端文件
| 文件 | 职责 | 操作 |
|------|------|------|
| `frontend/src/views/doctor/DoctorAIFab.vue` | 医生悬浮球 | 修改：新增"报告"Tab |
| `frontend/src/views/doctor/DoctorAIChat.vue` | 医生对话 | 保持不变 |
| `frontend/src/views/doctor/DoctorReport.vue` | 报告组件 | 新建 |
| `frontend/src/views/nurse/NurseAIFab.vue` | 护士悬浮球 | 修改：新增"上报"按钮 |
| `frontend/src/api/endpoints.ts` | API接口 | 修改：新增相关接口 |

---

## Task 1: 实现统一意图分类器

**Files:**
- Create: `backend/app/core/intent_classifier.py`

- [ ] **Step 1: 创建意图分类器模块**

```python
"""统一意图分类器 - 为护士端和医生端提供意图识别能力

意图分类：
- 护士端意图：查询数据、创建随访、生成报告、上报问题、健康教育
- 医生端意图：分析数据、生成医嘱、查看报告、处理问题、鉴别诊断
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class NurseIntent(str, Enum):
    """护士端意图"""
    QUERY_DATA = "query_data"              # 查询孕妇数据
    CREATE_FOLLOWUP = "create_followup"    # 创建随访记录
    GENERATE_EDUCATION = "generate_education"  # 生成健康教育
    REPORT_ISSUE = "report_issue"          # 上报问题给医生
    VIEW_SCHEDULE = "view_schedule"        # 查看随访排期
    ANALYZE_RISK = "analyze_risk"          # 分析风险
    GENERAL_CHAT = "general_chat"          # 一般对话


class DoctorIntent(str, Enum):
    """医生端意图"""
    ANALYZE_PATIENT = "analyze_patient"    # 分析孕妇数据
    GENERATE_ORDER = "generate_order"      # 生成医嘱
    GENERATE_REPORT = "generate_report"    # 生成报告
    HANDLE_ISSUE = "handle_issue"          # 处理问题
    DIFFERENTIAL_DX = "differential_dx"    # 鉴别诊断
    QUERY_GUIDELINE = "query_guideline"    # 查询指南
    GENERAL_CHAT = "general_chat"          # 一般对话


class IntentResult(BaseModel):
    """意图识别结果"""
    intent: str
    confidence: float
    entities: dict = {}
    requires_patient: bool = False  # 是否需要指定孕妇


# 意图关键词映射
NURSE_INTENT_KEYWORDS = {
    NurseIntent.QUERY_DATA: ["查看", "查询", "数据", "记录", "情况", "怎么样"],
    NurseIntent.CREATE_FOLLOWUP: ["随访", "随访记录", "创建随访", "生成随访"],
    NurseIntent.GENERATE_EDUCATION: ["教育", "宣教", "健康教育", "指导"],
    NurseIntent.REPORT_ISSUE: ["上报", "报告给医生", "通知医生", "问题"],
    NurseIntent.VIEW_SCHEDULE: ["排期", "计划", "安排", "什么时候"],
    NurseIntent.ANALYZE_RISK: ["风险", "分析", "评估", "危险"],
}

DOCTOR_INTENT_KEYWORDS = {
    DoctorIntent.ANALYZE_PATIENT: ["分析", "评估", "诊断", "情况"],
    DoctorIntent.GENERATE_ORDER: ["医嘱", "开药", "处方", "治疗"],
    DoctorIntent.GENERATE_REPORT: ["报告", "总结", "病历", "小结"],
    DoctorIntent.HANDLE_ISSUE: ["处理", "问题", "上报", "护士"],
    DoctorIntent.DIFFERENTIAL_DX: ["鉴别", "鉴别诊断", "鉴别诊断"],
    DoctorIntent.QUERY_GUIDELINE: ["指南", "规范", "标准", "参考"],
}


def classify_nurse_intent(text: str) -> IntentResult:
    """分类护士端意图"""
    text_lower = text.lower()

    for intent, keywords in NURSE_INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return IntentResult(
                    intent=intent.value,
                    confidence=0.8,
                    requires_patient=intent != NurseIntent.GENERAL_CHAT,
                )

    return IntentResult(
        intent=NurseIntent.GENERAL_CHAT.value,
        confidence=0.6,
        requires_patient=False,
    )


def classify_doctor_intent(text: str) -> IntentResult:
    """分类医生端意图"""
    text_lower = text.lower()

    for intent, keywords in DOCTOR_INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return IntentResult(
                    intent=intent.value,
                    confidence=0.8,
                    requires_patient=intent != DoctorIntent.GENERAL_CHAT,
                )

    return IntentResult(
        intent=DoctorIntent.GENERAL_CHAT.value,
        confidence=0.6,
        requires_patient=False,
    )
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/core/intent_classifier.py
git commit -m "feat: add unified intent classifier for nurse and doctor agents"
```

---

## Task 2: 扩展护士端工具集

**Files:**
- Modify: `backend/app/core/agno_tools.py`

- [ ] **Step 1: 添加护士端专用工具**

```python
# 在 agno_tools.py 末尾添加

# ==================== 护士端专用工具 ====================


@tool
def agno_query_patient_data(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """查询孕妇完整数据，包括基本信息、健康数据、预警、随访记录。
    当护士需要了解孕妇整体情况时使用此工具。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    from ..database import SessionLocal
    from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord
    from sqlalchemy import desc

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
        if not pregnant:
            return {"error": "孕妇不存在"}

        # 基本信息
        gest_days = pregnant.gestational_age_days or 0
        result = {
            "basic_info": {
                "name": pregnant.display_name,
                "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
                "risk_tags": pregnant.risk_tags or [],
            }
        }

        # 最近健康数据
        recent_data = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pid
        ).order_by(desc(HealthDataPoint.recorded_at)).limit(10).all()
        result["recent_health_data"] = [
            {"metric": d.metric_code, "value": d.value, "unit": d.unit, "time": d.recorded_at.isoformat()}
            for d in recent_data
        ]

        # 活跃预警
        active_alerts = db.query(Alert).filter(
            Alert.pregnant_id == pid, Alert.status == "PENDING"
        ).all()
        result["active_alerts"] = [
            {"level": a.level, "message": a.message, "time": a.created_at.isoformat()}
            for a in active_alerts
        ]

        # 最近随访
        recent_followups = db.query(FollowUpRecord).filter(
            FollowUpRecord.pregnant_id == pid
        ).order_by(desc(FollowUpRecord.created_at)).limit(3).all()
        result["recent_followups"] = [
            {"status": f.status, "complaint": f.chief_complaint, "time": f.created_at.isoformat()}
            for f in recent_followups
        ]

        return result
    finally:
        db.close()


@tool
def agno_create_followup_record(
    pregnant_id: str = "",
    chief_complaint: str = "",
    summary: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """创建随访记录草稿。
    当护士需要记录随访内容时使用此工具。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    from ..database import SessionLocal
    from ..models import Pregnant, FollowUpRecord

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
        if not pregnant:
            return {"error": "孕妇不存在"}

        gest_days = pregnant.gestational_age_days or 0
        record = FollowUpRecord(
            pregnant_id=pid,
            gestational_week=str(gest_days // 7),
            chief_complaint=chief_complaint,
            summary=summary,
            status="draft",
        )
        db.add(record)
        db.commit()

        return {"success": True, "record_id": str(record.id), "message": "随访记录已创建（草稿）"}
    finally:
        db.close()


@tool
def agno_report_issue_to_doctor(
    pregnant_id: str = "",
    title: str = "",
    description: str = "",
    priority: str = "medium",
    run_context: RunContext | None = None,
) -> dict:
    """上报问题给医生。
    当护士发现异常情况需要医生处理时使用此工具。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    from ..database import SessionLocal
    from ..models import NurseDoctorIssue

    db = SessionLocal()
    try:
        issue = NurseDoctorIssue(
            pregnant_id=pid,
            reported_by="nurse_ai",
            issue_type="risk_alert",
            title=title,
            description=description,
            priority=priority,
            status="pending",
        )
        db.add(issue)
        db.commit()

        return {"success": True, "issue_id": str(issue.id), "message": "问题已上报给医生"}
    finally:
        db.close()
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/core/agno_tools.py
git commit -m "feat: add nurse-specific tools for data query, followup, and issue reporting"
```

---

## Task 3: 扩展医生端工具集

**Files:**
- Modify: `backend/app/core/agno_tools.py`

- [ ] **Step 1: 添加医生端专用工具**

```python
# 在 agno_tools.py 末尾添加

# ==================== 医生端专用工具 ====================


@tool
def agno_analyze_patient_comprehensive(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """综合分析孕妇数据，包括健康指标趋势、风险评估、医嘱评价。
    当医生需要全面了解孕妇情况时使用此工具。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    from ..database import SessionLocal
    from ..models import Pregnant, HealthDataPoint, Alert, FgrAssessment, MedicalOrder
    from sqlalchemy import desc

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
        if not pregnant:
            return {"error": "孕妇不存在"}

        gest_days = pregnant.gestational_age_days or 0
        result = {
            "patient_info": {
                "name": pregnant.display_name,
                "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
                "risk_tags": pregnant.risk_tags or [],
            }
        }

        # 健康数据趋势
        metrics = ["weight", "systolic", "diastolic", "fetal_movement", "blood_sugar"]
        trends = {}
        for metric in metrics:
            points = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == pid,
                HealthDataPoint.metric_code == metric,
            ).order_by(desc(HealthDataPoint.recorded_at)).limit(5).all()
            if points:
                trends[metric] = [
                    {"value": p.value, "unit": p.unit, "time": p.recorded_at.isoformat()}
                    for p in points
                ]
        result["health_trends"] = trends

        # 预警历史
        alerts = db.query(Alert).filter(
            Alert.pregnant_id == pid
        ).order_by(desc(Alert.created_at)).limit(5).all()
        result["alerts"] = [
            {"level": a.level, "message": a.message, "status": a.status, "time": a.created_at.isoformat()}
            for a in alerts
        ]

        # FGR评估
        fgr = db.query(FgrAssessment).filter(
            FgrAssessment.pregnant_id == pid
        ).order_by(desc(FgrAssessment.assessed_at)).first()
        if fgr:
            result["fgr_assessment"] = {
                "risk_level": fgr.risk_level,
                "gestational_weeks": fgr.gestational_weeks,
                "explanation": fgr.explanation,
            }

        # 现有医嘱
        orders = db.query(MedicalOrder).filter(
            MedicalOrder.pregnant_id == pid
        ).order_by(desc(MedicalOrder.created_at)).limit(3).all()
        result["recent_orders"] = [
            {"content": o.content, "status": o.status, "time": o.created_at.isoformat()}
            for o in orders
        ]

        return result
    finally:
        db.close()


@tool
def agno_generate_medical_order(
    pregnant_id: str = "",
    content: str = "",
    order_type: str = "standard",
    run_context: RunContext | None = None,
) -> dict:
    """生成医嘱草稿。
    当医生需要开具医嘱时使用此工具。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    from ..database import SessionLocal
    from ..models import MedicalOrder

    db = SessionLocal()
    try:
        order = MedicalOrder(
            pregnant_id=pid,
            content=content,
            order_type=order_type,
            source="AI_RECOMMENDED",
            status="draft",
        )
        db.add(order)
        db.commit()

        return {"success": True, "order_id": str(order.id), "message": "医嘱草稿已生成"}
    finally:
        db.close()


@tool
def agno_handle_issue(
    issue_id: str = "",
    resolution: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """处理护士上报的问题。
    当医生需要处理问题时使用此工具。"""
    from uuid import UUID
    from ..database import SessionLocal
    from ..models import NurseDoctorIssue
    from datetime import datetime

    db = SessionLocal()
    try:
        issue = db.query(NurseDoctorIssue).filter(NurseDoctorIssue.id == UUID(issue_id)).first()
        if not issue:
            return {"error": "问题不存在"}

        issue.status = "resolved"
        issue.resolution = resolution
        issue.resolved_at = datetime.utcnow()
        db.commit()

        return {"success": True, "message": "问题已处理"}
    finally:
        db.close()


@tool
def agno_query_clinical_guideline(topic: str = "") -> dict:
    """查询临床指南和规范。
    当医生需要查阅相关指南时使用此工具。"""
    guidelines = {
        "fgr": "ACOG Practice Bulletin No. 204: Fetal Growth Restriction (2021)",
        "gdm": "ACOG Practice Bulletin No. 190: Gestational Diabetes Mellitus (2023)",
        "hypertension": "ACOG Practice Bulletin No. 222: Gestational Hypertension and Preeclampsia (2023)",
        "prenatal": "中华医学会妇产科学分会. 孕前和孕期保健指南(2022)",
    }

    topic_lower = topic.lower()
    matched = []
    for key, guideline in guidelines.items():
        if key in topic_lower:
            matched.append(guideline)

    if not matched:
        matched = list(guidelines.values())[:3]

    return {"topic": topic, "guidelines": matched}
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/core/agno_tools.py
git commit -m "feat: add doctor-specific tools for analysis, orders, and issue handling"
```

---

## Task 4: 增强Agent的意图识别和任务分解能力

**Files:**
- Modify: `backend/app/core/agno_medical_agents.py`

- [ ] **Step 1: 更新Agent工厂函数**

```python
"""护士/医生 AI 专用 Agent — 意图识别 + 任务分解 + 工具调用

使用 Agno output_schema 替代手动 _parse_llm_json() 正则解析，
提供类型安全的结构化输出。

Phase 5 升级：为护士/医生 Agent 配备完整的意图识别和任务分解能力，
让它们能根据用户意图自主选择工具并完成任务。
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from agno.agent import Agent
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .agno_tools import (
    # 通用工具
    agno_get_patient_context,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
    agno_search_knowledge,
    # 护士端工具
    agno_query_patient_data,
    agno_create_followup_record,
    agno_report_issue_to_doctor,
    # 医生端工具
    agno_analyze_patient_comprehensive,
    agno_generate_medical_order,
    agno_handle_issue,
    agno_query_clinical_guideline,
)
from .intent_classifier import (
    classify_nurse_intent,
    classify_doctor_intent,
    NurseIntent,
    DoctorIntent,
)


# ==================== Structured Output Schemas ====================


class NurseAnalysisOutput(BaseModel):
    """护士分析结果 — 结构化输出"""
    summary: str = Field(description="综合概述（100-200字），概括孕妇当前整体状况")
    risk_assessment: str = Field(description="风险评估（100-200字），分析当前主要风险因素")
    nursing_suggestions: str = Field(description="护理建议（150-300字），具体的护理措施和健康教育要点")
    followup_focus: list[str] = Field(description="随访重点（3-5个项目），列出随访时需要特别关注的内容")


class DoctorAnalysisOutput(BaseModel):
    """医生分析结果 — 结构化输出"""
    analysis: str = Field(description="综合分析（300-500字），涵盖孕妇基本情况、关键健康指标趋势、风险评估、现有医嘱评价")
    evidence_references: list[str] = Field(description="证据引用（3-5条），引用相关临床指南")
    suggested_orders: str = Field(description="建议医嘱（100-300字），具体的下一步处理建议")
    risk_summary: str = Field(description="风险摘要（50-100字），一句话总结当前核心风险和建议")
    differential_diagnosis: list[dict] = Field(default_factory=list, description="鉴别诊断考虑")
    reasoning_chain: list[str] = Field(default_factory=list, description="推理链，展示逐步推理过程")


class FollowUpGenerateOutput(BaseModel):
    """随访对话脚本生成结果"""
    opening_message: str = Field(description="亲切的开场白（30-50字）")
    questions: list[dict] = Field(description="随访问题列表（4-6个问题），每项含question和purpose")
    closing_message: str = Field(description="温暖的结束语（30-50字）")


class TaskPlanOutput(BaseModel):
    """任务分解结果"""
    intent: str = Field(description="识别的意图")
    steps: list[str] = Field(description="任务执行步骤")
    tools_to_use: list[str] = Field(description="需要使用的工具列表")
    requires_patient: bool = Field(description="是否需要指定孕妇")


# ==================== Agent 工厂 ====================


def create_nurse_agent() -> Agent:
    """创建护士 AI Agent — 意图识别 + 任务分解 + 工具调用

    配备完整工具集，让小护能根据用户意图自主完成任务。
    """
    return Agent(
        name="小护",
        model=get_agno_model(role="nurse"),
        instructions=[
            "你是'小护'，一位专业、高效的产科护理AI助手。",
            "",
            "【核心能力】",
            "1. 意图识别：理解护士的请求属于哪类任务",
            "2. 任务分解：将复杂任务拆解为可执行的步骤",
            "3. 工具调用：自主选择合适的工具完成任务",
            "",
            "【可用工具】",
            "- agno_query_patient_data: 查询孕妇完整数据",
            "- agno_create_followup_record: 创建随访记录",
            "- agno_report_issue_to_doctor: 上报问题给医生",
            "- agno_analyze_health_trends: 分析健康数据趋势",
            "- agno_evaluate_vital_rules: 评估生命体征规则",
            "- agno_search_knowledge: 搜索医学知识",
            "",
            "【工作流程】",
            "1. 理解用户意图",
            "2. 如需数据，先调用查询工具获取",
            "3. 根据意图执行相应操作",
            "4. 返回结构化结果",
            "",
            "【重要规则】",
            "- 绝不出具诊断结论，复杂情况建议咨询医生",
            "- 回答要简洁、专业、可操作",
        ],
        tools=[
            agno_query_patient_data,
            agno_create_followup_record,
            agno_report_issue_to_doctor,
            agno_analyze_health_trends,
            agno_evaluate_vital_rules,
            agno_search_knowledge,
        ],
        output_schema=NurseAnalysisOutput,
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=8,
    )


def create_doctor_agent() -> Agent:
    """创建医生 AI Agent — 意图识别 + 任务分解 + 工具调用

    配备完整工具集，让智医能根据用户意图自主完成任务。
    """
    return Agent(
        name="智医",
        model=get_agno_model(role="doctor"),
        instructions=[
            "你是'Dr.智'，一位资深的产科AI临床助手。",
            "",
            "【核心能力】",
            "1. 意图识别：理解医生的请求属于哪类任务",
            "2. 任务分解：将复杂任务拆解为可执行的步骤",
            "3. 工具调用：自主选择合适的工具完成任务",
            "",
            "【可用工具】",
            "- agno_analyze_patient_comprehensive: 综合分析孕妇数据",
            "- agno_generate_medical_order: 生成医嘱草稿",
            "- agno_handle_issue: 处理护士上报的问题",
            "- agno_query_clinical_guideline: 查询临床指南",
            "- agno_analyze_health_trends: 分析健康数据趋势",
            "- agno_evaluate_vital_rules: 评估生命体征规则",
            "- agno_search_knowledge: 搜索医学知识",
            "",
            "【工作流程】",
            "1. 理解用户意图",
            "2. 如需数据，先调用查询工具获取",
            "3. 根据意图执行相应操作",
            "4. 返回结构化结果",
            "",
            "【重要规则】",
            "- 所有医学建议需标注证据来源",
            "- 提供分析参考，最终决策由医生做出",
            "- 回答要专业、严谨、有循证依据",
        ],
        tools=[
            agno_analyze_patient_comprehensive,
            agno_generate_medical_order,
            agno_handle_issue,
            agno_query_clinical_guideline,
            agno_analyze_health_trends,
            agno_evaluate_vital_rules,
            agno_search_knowledge,
        ],
        output_schema=DoctorAnalysisOutput,
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=8,
    )


def create_followup_generate_agent() -> Agent:
    """创建随访脚本生成 Agent — Structured Output"""
    return Agent(
        name="小安-随访生成",
        model=get_agno_model(role="pregnant"),
        instructions=[
            "你是一位经验丰富的产科随访护士，擅长与孕妇进行有效的电话/微信随访沟通。",
            "请严格按结构化格式返回结果。",
        ],
        output_schema=FollowUpGenerateOutput,
        markdown=True,
    )


def create_task_planner_agent(role: str = "nurse") -> Agent:
    """创建任务规划 Agent — 意图识别 + 任务分解"""
    intent_class = "护士" if role == "nurse" else "医生"

    return Agent(
        name=f"{intent_class}任务规划器",
        model=get_agno_model(role=role),
        instructions=[
            f"你是一位{intent_class}AI助手的任务规划器。",
            "你的职责是：",
            "1. 理解用户的意图",
            "2. 将复杂任务分解为可执行的步骤",
            "3. 确定需要使用的工具",
            "",
            "请根据用户输入，返回结构化的任务计划。",
        ],
        output_schema=TaskPlanOutput,
        markdown=False,
    )
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/core/agno_medical_agents.py
git commit -m "feat: enhance agents with intent recognition and task decomposition"
```

---

## Task 5: 更新流式对话接口支持工具调用

**Files:**
- Modify: `backend/app/routers/nurse_ai.py`
- Modify: `backend/app/routers/doctor_ai.py`

- [ ] **Step 1: 更新护士端流式对话接口**

```python
# 在 nurse_ai.py 的 nurse_chat_stream 函数中更新

@router.post("/chat/stream")
async def nurse_chat_stream(req: dict):
    """护士 AI 持续对话（SSE 流式）— 支持意图识别和工具调用"""
    message = req.get("message", "")
    pregnant_id = req.get("pregnant_id", "")

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # 意图识别
    from ..core.intent_classifier import classify_nurse_intent
    intent_result = classify_nurse_intent(message)

    # 构建护士 AI 上下文
    db = SessionLocal()
    patient_summary = ""
    try:
        if pregnant_id:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
            if pregnant:
                gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0
                risk_text = "、".join(pregnant.risk_tags) if pregnant.risk_tags else "无"
                patient_summary = f"当前查看的孕妇: {pregnant.display_name}, 孕{gw}周, 风险: {risk_text}"
    finally:
        db.close()

    # 使用Agno Agent处理（如果启用）
    if settings.agno_enabled:
        from ..core.agno_medical_agents import create_nurse_agent
        agent = create_nurse_agent()

        async def event_generator():
            try:
                # 先发送意图识别结果
                yield {"event": "thinking", "data": f"识别意图: {intent_result.intent}"}

                # 调用Agent处理
                response = await agent.arun(
                    input=message,
                    user_id=pregnant_id or "anonymous",
                )
                content = response.content or ""

                # 流式返回结果
                for i in range(0, len(content), 50):
                    yield {"event": "chunk", "data": content[i:i+50]}
                    await asyncio.sleep(0.02)

            except Exception as e:
                yield {"event": "error", "data": str(e)}

            yield {"event": "done", "data": json.dumps({"source": "NURSE_AI", "intent": intent_result.intent})}

        return EventSourceResponse(event_generator())

    # 降级到普通LLM处理
    system_prompt = get_nurse_chat_system_prompt(patient_summary)

    async def event_generator():
        try:
            client = get_llm_client()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            async for chunk in client.chat_stream(messages, max_tokens=1024):
                yield {"event": "chunk", "data": chunk}
        except Exception:
            from ..core.llm_client import MockLLMClient
            mock = MockLLMClient()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            async for chunk in mock.chat_stream(messages):
                yield {"event": "chunk", "data": chunk}

        yield {"event": "done", "data": json.dumps({"source": "NURSE_AI", "intent": intent_result.intent})}

    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: 更新医生端流式对话接口**

```python
# 在 doctor_ai.py 的 doctor_chat_stream 函数中更新

@router.post("/chat/stream")
async def doctor_chat_stream(req: dict):
    """医生 AI 持续对话（SSE 流式）— 支持意图识别和工具调用"""
    message = req.get("message", "")
    pregnant_id = req.get("pregnant_id", "")

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # 意图识别
    from ..core.intent_classifier import classify_doctor_intent
    intent_result = classify_doctor_intent(message)

    # 构建医生 AI 上下文
    db = SessionLocal()
    patient_summary = ""
    try:
        if pregnant_id:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
            if pregnant:
                gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0
                risk_text = "、".join(pregnant.risk_tags) if pregnant.risk_tags else "无"
                patient_summary = f"当前查看的孕妇: {pregnant.display_name}, 孕{gw}周, 风险: {risk_text}"
    finally:
        db.close()

    # 使用Agno Agent处理（如果启用）
    if settings.agno_enabled:
        from ..core.agno_medical_agents import create_doctor_agent
        agent = create_doctor_agent()

        async def event_generator():
            try:
                # 先发送意图识别结果
                yield {"event": "thinking", "data": f"识别意图: {intent_result.intent}"}

                # 调用Agent处理
                response = await agent.arun(
                    input=message,
                    user_id=pregnant_id or "anonymous",
                )
                content = response.content or ""

                # 流式返回结果
                for i in range(0, len(content), 50):
                    yield {"event": "chunk", "data": content[i:i+50]}
                    await asyncio.sleep(0.02)

            except Exception as e:
                yield {"event": "error", "data": str(e)}

            yield {"event": "done", "data": json.dumps({"source": "DOCTOR_AI", "intent": intent_result.intent})}

        return EventSourceResponse(event_generator())

    # 降级到普通LLM处理
    system_prompt = get_doctor_chat_system_prompt(patient_summary)

    async def event_generator():
        try:
            client = get_llm_client()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            async for chunk in client.chat_stream(messages, max_tokens=1024):
                yield {"event": "chunk", "data": chunk}
        except Exception:
            from ..core.llm_client import MockLLMClient
            mock = MockLLMClient()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            async for chunk in mock.chat_stream(messages):
                yield {"event": "chunk", "data": chunk}

        yield {"event": "done", "data": json.dumps({"source": "DOCTOR_AI", "intent": intent_result.intent})}

    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: 提交代码**

```bash
git add backend/app/routers/nurse_ai.py backend/app/routers/doctor_ai.py
git commit -m "feat: update chat stream endpoints with intent recognition and tool calling"
```

---

## Task 6: 新增医护协作数据模型

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/schemas/schemas.py`

- [ ] **Step 1: 添加NurseDoctorIssue模型**

```python
# 在 models.py 的 MedicalOrder 类后面添加

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: 添加对应的Pydantic Schema**

```python
# 在 schemas.py 中添加

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

    class Config:
        from_attributes = True
```

- [ ] **Step 3: 运行数据库迁移**

```bash
cd e:/githubproject/medical_agent1
python -c "from backend.app.database import engine; from backend.app.models import Base; Base.metadata.create_all(bind=engine)"
```

- [ ] **Step 4: 提交代码**

```bash
git add backend/app/models/models.py backend/app/schemas/schemas.py
git commit -m "feat: add NurseDoctorIssue model for nurse-doctor collaboration"
```

---

## Task 7: 实现护士端问题上报API

**Files:**
- Modify: `backend/app/routers/nurse_ai.py`

- [ ] **Step 1: 添加问题上报接口**

```python
# 在 nurse_ai.py 中添加

@router.post("/issues/report")
async def report_issue(req: NurseDoctorIssueCreate):
    """护士上报问题给医生"""
    db = SessionLocal()
    try:
        # 获取孕妇信息
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        # 创建问题记录
        issue = NurseDoctorIssue(
            pregnant_id=req.pregnant_id,
            reported_by="current-nurse",  # 实际应从token获取
            issue_type=req.issue_type,
            title=req.title,
            description=req.description,
            priority=req.priority,
            status="pending",
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        # 通过WebSocket推送给医生端
        issue_data = {
            "id": str(issue.id),
            "pregnant_id": req.pregnant_id,
            "patient_name": pregnant.display_name,
            "issue_type": req.issue_type,
            "title": req.title,
            "description": req.description,
            "priority": req.priority,
            "status": "pending",
            "created_at": issue.created_at.isoformat(),
        }

        from ..core.websocket_manager import ws_manager
        await ws_manager.broadcast_issue(issue_data)

        return {"success": True, "issue_id": str(issue.id), "message": "问题已上报"}
    finally:
        db.close()


@router.get("/issues")
async def list_issues(status: str = "pending"):
    """获取护士上报的问题列表"""
    db = SessionLocal()
    try:
        issues = db.query(NurseDoctorIssue).filter(
            NurseDoctorIssue.status == status
        ).order_by(NurseDoctorIssue.created_at.desc()).limit(20).all()

        result = []
        for issue in issues:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == issue.pregnant_id).first()
            result.append({
                "id": str(issue.id),
                "pregnant_id": issue.pregnant_id,
                "patient_name": pregnant.display_name if pregnant else "未知",
                "reported_by": issue.reported_by,
                "issue_type": issue.issue_type,
                "title": issue.title,
                "description": issue.description,
                "priority": issue.priority,
                "status": issue.status,
                "created_at": issue.created_at.isoformat(),
            })

        return result
    finally:
        db.close()
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/routers/nurse_ai.py
git commit -m "feat: add nurse issue reporting API endpoints"
```

---

## Task 8: 实现医生端问题处理API

**Files:**
- Modify: `backend/app/routers/doctor_ai.py`

- [ ] **Step 1: 添加问题处理接口**

```python
# 在 doctor_ai.py 中添加

@router.get("/issues")
async def list_issues(status: str = "pending"):
    """获取待处理的问题列表"""
    db = SessionLocal()
    try:
        issues = db.query(NurseDoctorIssue).filter(
            NurseDoctorIssue.status == status
        ).order_by(
            NurseDoctorIssue.priority.desc(),
            NurseDoctorIssue.created_at.desc()
        ).limit(20).all()

        result = []
        for issue in issues:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == issue.pregnant_id).first()
            result.append({
                "id": str(issue.id),
                "pregnant_id": issue.pregnant_id,
                "patient_name": pregnant.display_name if pregnant else "未知",
                "reported_by": issue.reported_by,
                "issue_type": issue.issue_type,
                "title": issue.title,
                "description": issue.description,
                "priority": issue.priority,
                "status": issue.status,
                "created_at": issue.created_at.isoformat(),
            })

        return result
    finally:
        db.close()


@router.put("/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: str, resolution: str):
    """处理问题"""
    from uuid import UUID
    db = SessionLocal()
    try:
        issue = db.query(NurseDoctorIssue).filter(NurseDoctorIssue.id == UUID(issue_id)).first()
        if not issue:
            raise HTTPException(404, "问题不存在")

        issue.status = "resolved"
        issue.resolution = resolution
        issue.resolved_at = datetime.utcnow()
        issue.assigned_to = "current-doctor"  # 实际应从token获取
        db.commit()

        return {"success": True, "message": "问题已处理"}
    finally:
        db.close()
```

- [ ] **Step 2: 提交代码**

```bash
git add backend/app/routers/doctor_ai.py
git commit -m "feat: add doctor issue handling API endpoints"
```

---

## Task 9: 实现孕期报告生成API

**Files:**
- Modify: `backend/app/routers/doctor_ai.py`
- Modify: `backend/app/core/prompts.py`

- [ ] **Step 1: 添加报告生成提示词**

```python
# 在 prompts.py 中添加

def get_report_generation_prompt(patient_summary: str, health_data: str, alerts: str) -> str:
    """孕期报告生成提示词"""
    return f"""请根据以下信息生成一份结构化的孕期健康报告：

{patient_summary}

【健康数据趋势】
{health_data}

【预警记录】
{alerts}

请生成包含以下部分的报告：

1. **基本情况摘要**（50-100字）
   - 孕周、风险标签、管理时长

2. **关键指标分析**（100-200字）
   - 血压趋势
   - 血糖情况
   - 体重变化
   - 胎动情况

3. **风险评估**（100-150字）
   - 当前主要风险因素
   - 需要关注的问题

4. **医嘱执行情况**（50-100字）
   - 现有医嘱评价
   - 是否需要调整

5. **建议**（100-150字）
   - 下一步处理建议
   - 随访计划

请使用Markdown格式输出，结构清晰，便于阅读。"""
```

- [ ] **Step 2: 添加报告生成接口**

```python
# 在 doctor_ai.py 中添加

@router.post("/report/{pregnant_id}")
async def generate_report(pregnant_id: str):
    """生成孕期健康报告"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7

        # 收集数据
        patient_summary = f"""孕妇：{pregnant.display_name}
孕周：{gest_week}周+{gest_day}天
风险标签：{', '.join(pregnant.risk_tags) if pregnant.risk_tags else '无'}
管理时间：{pregnant.created_at.strftime('%Y-%m-%d') if pregnant.created_at else '未知'}"""

        # 健康数据
        from ..services.patient_context_service import get_recent_health_data
        health_points = get_recent_health_data(db, pregnant_id, limit=20, days=30)
        health_lines = []
        for point in health_points[:10]:
            health_lines.append(f"- {point['metric']}: {point['value']}{point['unit']} ({point['recorded_at'][:10]})")
        health_data = "\n".join(health_lines) if health_lines else "暂无健康数据"

        # 预警记录
        alerts = db.query(Alert).filter(
            Alert.pregnant_id == pregnant_id
        ).order_by(Alert.created_at.desc()).limit(5).all()
        alert_lines = []
        for alert in alerts:
            alert_lines.append(f"- [{alert.level}] {alert.message} ({alert.created_at.strftime('%Y-%m-%d')})")
        alerts_text = "\n".join(alert_lines) if alert_lines else "暂无预警记录"

        # 生成报告
        prompt = get_report_generation_prompt(patient_summary, health_data, alerts_text)

        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            client = get_agno_client()
            messages = [
                {"role": "system", "content": "你是一位资深的产科医生，擅长撰写孕期健康报告。请用专业、严谨的语言生成报告。"},
                {"role": "user", "content": prompt},
            ]
            report_content = ""
            async for chunk in client.chat_stream(messages):
                report_content += chunk
        else:
            client = get_llm_client()
            messages = [
                {"role": "system", "content": "你是一位资深的产科医生，擅长撰写孕期健康报告。请用专业、严谨的语言生成报告。"},
                {"role": "user", "content": prompt},
            ]
            report_content = await client.chat(messages)

        return {
            "pregnant_id": pregnant_id,
            "patient_name": pregnant.display_name,
            "report": report_content,
            "generated_at": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()
```

- [ ] **Step 3: 提交代码**

```bash
git add backend/app/routers/doctor_ai.py backend/app/core/prompts.py
git commit -m "feat: add pregnancy report generation API"
```

---

## Task 10: 前端 - 修改护士端悬浮球增加上报功能

**Files:**
- Modify: `frontend/src/views/nurse/NurseAIFab.vue`
- Modify: `frontend/src/api/endpoints.ts`

- [ ] **Step 1: 添加API接口**

```typescript
// 在 endpoints.ts 中添加

// 医护协作
export const collaborationApi = {
  reportIssue: (data: { pregnant_id: string; issue_type: string; title: string; description: string; priority: string }) =>
    client.post('/nurse/issues/report', data),
  listIssues: (status: string = 'pending') =>
    client.get('/doctor/issues', { params: { status } }),
  resolveIssue: (issueId: string, resolution: string) =>
    client.put(`/doctor/issues/${issueId}/resolve`, { resolution }),
}
```

- [ ] **Step 2: 修改NurseAIFab增加上报功能**

```vue
<!-- 在 NurseAIFab.vue 的 el-tabs 中添加新Tab -->

<el-tab-pane label="上报" name="report">
  <div class="report-tab">
    <el-form :model="reportForm" label-position="top">
      <el-form-item label="问题类型">
        <el-select v-model="reportForm.issue_type" placeholder="选择问题类型">
          <el-option label="风险预警" value="risk_alert" />
          <el-option label="异常数据" value="abnormal_data" />
          <el-option label="患者投诉" value="patient_complaint" />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级">
        <el-radio-group v-model="reportForm.priority">
          <el-radio-button label="low">低</el-radio-button>
          <el-radio-button label="medium">中</el-radio-button>
          <el-radio-button label="high">高</el-radio-button>
          <el-radio-button label="urgent">紧急</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="问题标题">
        <el-input v-model="reportForm.title" placeholder="简要描述问题" />
      </el-form-item>
      <el-form-item label="详细描述">
        <el-input v-model="reportForm.description" type="textarea" :rows="3" placeholder="详细描述问题情况" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submitReport" :loading="reportLoading">
          上报给医生
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</el-tab-pane>
```

- [ ] **Step 3: 添加上报逻辑**

```typescript
// 在 NurseAIFab.vue 的 script 中添加

const reportForm = ref({
  issue_type: 'risk_alert',
  priority: 'medium',
  title: '',
  description: '',
})
const reportLoading = ref(false)

async function submitReport() {
  if (!reportForm.value.title || !reportForm.value.description) {
    ElMessage.warning('请填写问题标题和描述')
    return
  }

  reportLoading.value = true
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    await collaborationApi.reportIssue({
      pregnant_id: pregnantId,
      ...reportForm.value,
    })
    ElMessage.success('问题已上报给医生')
    reportForm.value = {
      issue_type: 'risk_alert',
      priority: 'medium',
      title: '',
      description: '',
    }
  } catch (error) {
    ElMessage.error('上报失败，请重试')
  } finally {
    reportLoading.value = false
  }
}
```

- [ ] **Step 4: 提交代码**

```bash
git add frontend/src/views/nurse/NurseAIFab.vue frontend/src/api/endpoints.ts
git commit -m "feat: add issue reporting to nurse AI panel"
```

---

## Task 11: 前端 - 修改医生端悬浮球增加报告和问题处理功能

**Files:**
- Modify: `frontend/src/views/doctor/DoctorAIFab.vue`
- Create: `frontend/src/views/doctor/DoctorReport.vue`

- [ ] **Step 1: 创建报告组件 DoctorReport.vue**

```vue
<template>
  <div class="doctor-report">
    <div class="report-header">
      <el-select
        v-model="selectedPatient"
        filterable
        placeholder="选择孕妇生成报告"
        style="width: 100%"
        clearable
      >
        <el-option
          v-for="p in pregnantList"
          :key="p.pregnant_id"
          :label="`${p.display_name} (孕${Math.floor((p.gestational_age_days||0)/7)}周)`"
          :value="p.pregnant_id"
        />
      </el-select>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!selectedPatient"
        @click="generateReport"
      >
        <el-icon><Document /></el-icon> 生成报告
      </el-button>
    </div>

    <div v-if="report" class="report-content">
      <div class="report-meta">
        <span>{{ report.patient_name }}</span>
        <span class="text-muted">{{ report.generated_at }}</span>
      </div>
      <div class="report-body" v-html="renderMarkdown(report.report)" />
    </div>

    <div v-if="!report && !loading" class="report-empty">
      <el-icon :size="40" color="var(--text-muted)"><Document /></el-icon>
      <p>选择孕妇后点击"生成报告"，AI将生成孕期健康报告</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { dashboardApi, doctorAiApi } from '@/api/endpoints'
import { marked } from 'marked'
import type { Pregnant } from '@/types'

const selectedPatient = ref('')
const loading = ref(false)
const report = ref<any>(null)
const pregnantList = ref<Pregnant[]>([])

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string
}

async function loadPatientList() {
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data || []
  } catch { /* ignore */ }
}

async function generateReport() {
  if (!selectedPatient.value) return
  loading.value = true
  report.value = null
  try {
    const res = await doctorAiApi.generateReport(selectedPatient.value)
    report.value = res.data
  } catch (error) {
    console.error('生成报告失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPatientList()
})
</script>

<style scoped>
.doctor-report {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.report-header {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.report-content {
  flex: 1;
  overflow-y: auto;
}

.report-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 13px;
}

.text-muted {
  color: var(--text-muted);
}

.report-body {
  font-size: 13px;
  line-height: 1.6;
}

.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3) {
  margin: 12px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.report-body :deep(p) {
  margin: 8px 0;
}

.report-body :deep(ul),
.report-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.report-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
```

- [ ] **Step 2: 添加生成报告API接口**

```typescript
// 在 endpoints.ts 的 doctorAiApi 中添加

export const doctorAiApi = {
  analyze: (pregnantId: string, query: string = '') =>
    client.post<any>(`/doctor/analyze/${pregnantId}`, { pregnant_id: pregnantId, query }),
  chatStream: (data: { message: string; pregnant_id?: string }, callbacks: SSEStreamCallbacks, signal?: AbortSignal) =>
    doctorChatStream(data, callbacks, signal),
  generateReport: (pregnantId: string) =>
    client.post<any>(`/doctor/report/${pregnantId}`),
}
```

- [ ] **Step 3: 修改DoctorAIFab增加报告Tab**

```vue
<!-- 在 DoctorAIFab.vue 的 el-tabs 中添加新Tab -->

<el-tab-pane label="报告" name="report">
  <DoctorReport />
</el-tab-pane>
```

- [ ] **Step 4: 导入DoctorReport组件**

```typescript
// 在 DoctorAIFab.vue 的 script 中添加

import DoctorReport from '../DoctorReport.vue'
```

- [ ] **Step 5: 提交代码**

```bash
git add frontend/src/views/doctor/DoctorReport.vue frontend/src/views/doctor/DoctorAIFab.vue frontend/src/api/endpoints.ts
git commit -m "feat: add report generation to doctor AI panel"
```

---

## Task 12: 前端 - 医生端增加问题处理功能

**Files:**
- Modify: `frontend/src/views/doctor/DoctorAIFab.vue`

- [ ] **Step 1: 添加问题处理Tab**

```vue
<!-- 在 DoctorAIFab.vue 的 el-tabs 中添加新Tab -->

<el-tab-pane label="问题" name="issues">
  <div class="issues-tab">
    <div class="issues-list">
      <div v-for="issue in issues" :key="issue.id" class="issue-item">
        <div class="issue-header">
          <el-tag :type="getPriorityType(issue.priority)" size="small">
            {{ getPriorityLabel(issue.priority) }}
          </el-tag>
          <span class="issue-time">{{ formatTime(issue.created_at) }}</span>
        </div>
        <div class="issue-title">{{ issue.title }}</div>
        <div class="issue-desc">{{ issue.description }}</div>
        <div class="issue-footer">
          <span class="issue-patient">{{ issue.patient_name }}</span>
          <el-button
            v-if="issue.status === 'pending'"
            type="primary"
            size="small"
            @click="resolveIssue(issue)"
          >
            处理
          </el-button>
          <el-tag v-else type="success" size="small">已处理</el-tag>
        </div>
      </div>
      <div v-if="!issues.length" class="issues-empty">
        <el-icon :size="40" color="var(--text-muted)"><Bell /></el-icon>
        <p>暂无待处理问题</p>
      </div>
    </div>
  </div>
</el-tab-pane>
```

- [ ] **Step 2: 添加问题处理逻辑**

```typescript
// 在 DoctorAIFab.vue 的 script 中添加

import { collaborationApi } from '@/api/endpoints'

const issues = ref<any[]>([])

async function loadIssues() {
  try {
    const res = await collaborationApi.listIssues('pending')
    issues.value = res.data || []
  } catch { /* ignore */ }
}

function getPriorityType(priority: string) {
  const map: Record<string, string> = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    urgent: 'danger',
  }
  return map[priority] || 'info'
}

function getPriorityLabel(priority: string) {
  const map: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    urgent: '紧急',
  }
  return map[priority] || '中'
}

function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function resolveIssue(issue: any) {
  try {
    await ElMessageBox.confirm('确认已处理该问题？', '处理确认')
    await collaborationApi.resolveIssue(issue.id, '已处理')
    ElMessage.success('问题已处理')
    loadIssues()
  } catch { /* ignore */ }
}

// 在 onMounted 中加载问题
onMounted(() => {
  loadPatientList()
  loadIssues()
})
```

- [ ] **Step 3: 添加问题Tab样式**

```css
/* 在 DoctorAIFab.vue 的 style 中添加 */

.issues-tab {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}

.issue-item {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
}

.issue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.issue-time {
  font-size: 12px;
  color: var(--text-muted);
}

.issue-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.issue-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.issue-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.issue-patient {
  font-size: 13px;
  color: var(--text-muted);
}

.issues-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 12px;
  color: var(--text-muted);
}
```

- [ ] **Step 4: 提交代码**

```bash
git add frontend/src/views/doctor/DoctorAIFab.vue
git commit -m "feat: add issue handling to doctor AI panel"
```

---

## Task 13: WebSocket增加问题推送支持

**Files:**
- Modify: `backend/app/core/websocket_manager.py`
- Modify: `frontend/src/utils/websocket.ts`

- [ ] **Step 1: 修改WebSocket管理器支持问题推送**

```python
# 在 websocket_manager.py 的 WebSocketManager 类中添加

async def broadcast_issue(self, issue_data: dict):
    """广播问题通知给所有医生端"""
    message = {
        "type": "new_issue",
        "data": issue_data,
    }
    await self.broadcast(json.dumps(message))
```

- [ ] **Step 2: 前端WebSocket增加问题回调**

```typescript
// 在 websocket.ts 中添加

export interface WebSocketClient {
  // ... existing methods ...
  onIssue: (callback: (issue: any) => void) => void
  offIssue: (callback: (issue: any) => void) => void
}

// 在 WebSocketClient 类中添加

private issueCallbacks: ((issue: any) => void)[] = []

onIssue(callback: (issue: any) => void) {
  this.issueCallbacks.push(callback)
}

offIssue(callback: (issue: any) => void) {
  this.issueCallbacks = this.issueCallbacks.filter(cb => cb !== callback)
}

// 在 handleMessage 方法中添加

if (data.type === 'new_issue') {
  this.issueCallbacks.forEach(cb => cb(data.data))
}
```

- [ ] **Step 3: 提交代码**

```bash
git add backend/app/core/websocket_manager.py frontend/src/utils/websocket.ts
git commit -m "feat: add WebSocket support for issue notifications"
```

---

## Task 14: 集成测试

- [ ] **Step 1: 测试护士端问题上报**

```bash
# 启动后端
cd e:/githubproject/medical_agent1/backend
python run.py

# 测试上报接口
curl -X POST http://localhost:8000/api/v1/nurse/issues/report \
  -H "Content-Type: application/json" \
  -d '{
    "pregnant_id": "test_pregnant_001",
    "issue_type": "risk_alert",
    "title": "血压异常",
    "description": "孕妇今日血压140/90mmHg，需关注",
    "priority": "high"
  }'
```

- [ ] **Step 2: 测试医生端报告生成**

```bash
curl -X POST http://localhost:8000/api/v1/doctor/report/test_pregnant_001
```

- [ ] **Step 3: 测试医生端问题列表**

```bash
curl http://localhost:8000/api/v1/doctor/issues?status=pending
```

- [ ] **Step 4: 提交最终代码**

```bash
git add .
git commit -m "feat: complete doctor AI agent expansion with nurse-doctor collaboration"
```

---

## 演示流程

### 场景1：医护协同闭环
1. 护士发现孕妇血压异常
2. 点击悬浮球 → 切换到"上报"Tab
3. 填写问题描述 → 点击"上报给医生"
4. 医生端收到WebSocket推送通知
5. 医生点击悬浮球 → 切换到"问题"Tab
6. 查看问题详情 → 点击"处理"
7. 生成医嘱 → 推送给护士/孕妇

### 场景2：智能报告生成
1. 医生点击悬浮球 → 切换到"报告"Tab
2. 选择孕妇 → 点击"生成报告"
3. AI自动生成结构化孕期健康报告
4. 展示报告内容（Markdown渲染）

### 场景3：智能体任务分解演示（护士端）
1. 护士输入："帮我查看一下张三的最近情况，如果有异常就上报给医生"
2. AI展示意图识别结果：`识别意图: query_data`
3. AI自动调用工具：`agno_query_patient_data`
4. AI分析数据，发现血压异常
5. AI自动调用工具：`agno_report_issue_to_doctor`
6. 展示完整任务执行过程和结果

### 场景4：智能体任务分解演示（医生端）
1. 医生输入："分析一下李四的高危因素，生成一份医嘱"
2. AI展示意图识别结果：`识别意图: analyze_patient`
3. AI自动调用工具：`agno_analyze_patient_comprehensive`
4. AI分析数据，识别风险因素
5. AI自动调用工具：`agno_generate_medical_order`
6. 展示完整任务执行过程和结果

---

## 计划完成

**Plan complete and saved to `docs/superpowers/plans/2026-05-20-doctor-ai-agent-expansion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
