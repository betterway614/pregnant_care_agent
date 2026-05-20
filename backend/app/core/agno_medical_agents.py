"""护士/医生 AI 专用 Agent — 意图识别 + 工具路由 + Structured Output

充分利用 Agno 框架原生能力：
- 工具路由：Agent 根据用户意图自动选择合适的工具
- tool_call_limit：限制工具调用次数，控制 token 消耗
- max_tool_calls_from_history：限制历史工具调用，减少上下文 token
- output_schema：结构化输出，类型安全
- session_state + SqliteDb：工具间上下文持久化

安全设计：每个角色使用独立的 SqliteDb，防止敏感信息泄露
- 孕妇端（小安）：agent_sessions_pregnant.db
- 护士端（小护）：agent_sessions_nurse.db
- 医生端（智医）：agent_sessions_doctor.db
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .agno_tools import (
    NURSE_TOOLS,
    DOCTOR_TOOLS,
    agno_query_patient_data,
    agno_analyze_patient_comprehensive,
)

import os

# Agent 会话持久化数据库路径（每个角色独立，防止敏感信息泄露）
_db_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)

# 每个角色独立的数据库文件
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")
_nurse_db_path = os.path.join(_db_dir, "agent_sessions_nurse.db")
_doctor_db_path = os.path.join(_db_dir, "agent_sessions_doctor.db")


def _create_pregnant_db():
    """创建孕妇端 Agent 专用 SqliteDb"""
    return SqliteDb(db_file=_pregnant_db_path)


def _create_nurse_db():
    """创建护士端 Agent 专用 SqliteDb"""
    return SqliteDb(db_file=_nurse_db_path)


def _create_doctor_db():
    """创建医生端 Agent 专用 SqliteDb"""
    return SqliteDb(db_file=_doctor_db_path)


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


class ChatOutput(BaseModel):
    """对话输出 — 用于流式对话场景"""
    content: str = Field(description="回复内容")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")


# ==================== Agent 工厂 ====================


def create_nurse_agent() -> Agent:
    """创建护士 AI Agent — 自动工具路由 + Token 优化 + 上下文持久化

    Agno 原生能力：
    - 工具路由：根据用户意图自动选择 agno_query_patient_data / agno_create_followup_record 等
    - tool_call_limit=5：单次对话最多调用5次工具，防止 token 爆炸
    - max_tool_calls_from_history=3：只保留最近3次工具调用历史
    - session_state + SqliteDb：工具间上下文持久化（如查询结果传递给上报工具）

    安全设计：使用独立的 nurse_db，与孕妇端/医生端数据隔离
    """
    return Agent(
        name="小护",
        model=get_agno_model(role="nurse"),
        instructions=[
            "你是'小护'，一位专业、高效的产科护理AI助手。",
            "",
            "【工作方式】",
            "根据用户意图，自动选择合适的工具完成任务：",
            "- 查询数据 → agno_query_patient_data",
            "- 创建随访 → agno_create_followup_record",
            "- 上报问题 → agno_report_issue_to_doctor",
            "- 分析趋势 → agno_analyze_health_trends",
            "- 评估规则 → agno_evaluate_vital_rules",
            "- 搜索知识 → agno_search_knowledge",
            "",
            "【工具联动】",
            "- 如果用户说'查看XX情况，有异常就上报'，先查询数据，再根据结果决定是否上报",
            "- 上报时可以不指定 pregnant_id，系统会自动使用上次查询的孕妇",
            "",
            "【重要规则】",
            "- 绝不出具诊断结论，复杂情况建议咨询医生",
            "- 回答要简洁、专业、可操作",
        ],
        tools=NURSE_TOOLS,
        output_schema=NurseAnalysisOutput,
        session_state={},  # 初始化 session_state 用于工具间上下文共享
        db=_create_nurse_db(),  # 持久化 session_state（护士端独立数据库）
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=5,
        max_tool_calls_from_history=3,
    )


def create_doctor_agent() -> Agent:
    """创建医生 AI Agent — 自动工具路由 + Token 优化 + 上下文持久化

    Agno 原生能力：
    - 工具路由：根据用户意图自动选择 agno_analyze_patient_comprehensive / agno_generate_medical_order 等
    - tool_call_limit=5：单次对话最多调用5次工具，防止 token 爆炸
    - max_tool_calls_from_history=3：只保留最近3次工具调用历史
    - session_state + SqliteDb：工具间上下文持久化（如分析结果传递给医嘱生成工具）

    安全设计：使用独立的 doctor_db，与孕妇端/护士端数据隔离
    """
    return Agent(
        name="智医",
        model=get_agno_model(role="doctor"),
        instructions=[
            "你是'Dr.智'，一位资深的产科AI临床助手。",
            "",
            "【工作方式】",
            "根据用户意图，自动选择合适的工具完成任务：",
            "- 分析患者 → agno_analyze_patient_comprehensive",
            "- 生成医嘱 → agno_generate_medical_order",
            "- 处理问题 → agno_handle_issue",
            "- 查询指南 → agno_query_clinical_guideline",
            "- 分析趋势 → agno_analyze_health_trends",
            "- 评估规则 → agno_evaluate_vital_rules",
            "- 搜索知识 → agno_search_knowledge",
            "",
            "【工具联动】",
            "- 如果用户说'分析XX情况，然后生成医嘱'，先分析数据，再根据结果生成医嘱",
            "- 生成医嘱时可以不指定 pregnant_id，系统会自动使用上次分析的孕妇",
            "",
            "【重要规则】",
            "- 所有医学建议需标注证据来源",
            "- 提供分析参考，最终决策由医生做出",
        ],
        tools=DOCTOR_TOOLS,
        output_schema=DoctorAnalysisOutput,
        session_state={},  # 初始化 session_state 用于工具间上下文共享
        db=_create_doctor_db(),  # 持久化 session_state（医生端独立数据库）
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=5,
        max_tool_calls_from_history=3,
    )


def create_nurse_chat_agent() -> Agent:
    """创建护士对话 Agent — 流式对话场景

    用于护士端悬浮球的对话功能，不使用 output_schema 以支持流式输出。
    支持工具间上下文持久化（护士端独立数据库）。
    """
    return Agent(
        name="小护-对话",
        model=get_agno_model(role="nurse"),
        instructions=[
            "你是'小护'，一位专业、高效的产科护理AI助手。",
            "根据用户意图使用工具获取数据，然后给出专业建议。",
            "",
            "【工具联动】",
            "- 如果用户说'查看XX情况，有异常就上报'，先查询数据，再根据结果决定是否上报",
            "- 上报时可以不指定 pregnant_id，系统会自动使用上次查询的孕妇",
            "",
            "绝不出具诊断结论，复杂情况建议咨询医生。",
            "回答要简洁、专业、可操作。",
        ],
        tools=NURSE_TOOLS,
        session_state={},
        db=_create_nurse_db(),  # 持久化 session_state（护士端独立数据库）
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=3,
        max_tool_calls_from_history=2,
    )


def create_doctor_chat_agent() -> Agent:
    """创建医生对话 Agent — 流式对话场景

    用于医生端悬浮球的对话功能，不使用 output_schema 以支持流式输出。
    支持工具间上下文持久化（医生端独立数据库）。
    """
    return Agent(
        name="智医-对话",
        model=get_agno_model(role="doctor"),
        instructions=[
            "你是'Dr.智'，一位资深的产科AI临床助手。",
            "根据用户意图使用工具获取数据，然后给出专业分析。",
            "",
            "【工具联动】",
            "- 如果用户说'分析XX情况，然后生成医嘱'，先分析数据，再根据结果生成医嘱",
            "- 生成医嘱时可以不指定 pregnant_id，系统会自动使用上次分析的孕妇",
            "",
            "所有医学建议需标注证据来源。",
            "回答要专业、严谨、有循证依据。",
        ],
        tools=DOCTOR_TOOLS,
        session_state={},
        db=_create_doctor_db(),  # 持久化 session_state（医生端独立数据库）
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=3,
        max_tool_calls_from_history=2,
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
