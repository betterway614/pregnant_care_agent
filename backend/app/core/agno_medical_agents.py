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

from functools import lru_cache

from pydantic import BaseModel, Field
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from .agno_client import get_agno_model
from .agno_guardrails import NurseSafetyGuardrail, DoctorDraftGuardrail
from .agno_tools import (
    NURSE_TOOLS,
    DOCTOR_TOOLS,
)
from .prompts import (
    get_nurse_system_prompt_instructions,
    get_nurse_chat_system_prompt_instructions,
    get_doctor_system_prompt_instructions,
    get_doctor_chat_system_prompt_instructions,
    get_followup_generate_instructions,
    get_followup_analysis_instructions,
    get_followup_review_instructions,
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


class FollowUpAnalysisOutput(BaseModel):
    """随访完成后 LLM 结构化分析结果"""
    warm_summary: str = Field(description="温馨总结（30-50字），语气温和自然")
    abnormal_indicators: list[str] = Field(default_factory=list, description="异常指标列表")
    trend_analysis: str = Field(default="", description="与历史数据对比的趋势分析（50-100字）")
    personalized_advice: str = Field(default="", description="基于回答内容的个性化建议（50-100字）")
    nurse_action_suggestion: str = Field(default="", description="护士行动建议")


class FollowUpAiReviewOutput(BaseModel):
    """护士审核随访时的 AI 辅助分析结果"""
    summary: str = Field(description="本次随访要点摘要（100-200字）")
    abnormal_flags: list[str] = Field(default_factory=list, description="异常指标标红列表")
    action_needed: bool = Field(default=False, description="是否需要上报医生")
    recommendation: str = Field(description="审核建议：确认通过/需进一步沟通/紧急上报")
    detail_analysis: str = Field(default="", description="详细分析（100-200字）")


class ChatOutput(BaseModel):
    """对话输出 — 用于流式对话场景"""
    content: str = Field(description="回复内容")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")


# ==================== Agent 工厂 ====================


def create_nurse_agent() -> Agent:
    """创建护士 AI Agent — 工具路由 + 结构化输出"""
    return Agent(
        name="小护",
        model=get_agno_model(role="nurse"),
        instructions=get_nurse_system_prompt_instructions(),
        tools=NURSE_TOOLS,
        output_schema=NurseAnalysisOutput,
        session_state={},
        db=_create_nurse_db(),
        search_knowledge=False,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[NurseSafetyGuardrail()],
        tool_call_limit=5,
        max_tool_calls_from_history=3,
    )


def create_doctor_agent() -> Agent:
    """创建医生 AI Agent — 工具路由 + 结构化输出"""
    return Agent(
        name="智医",
        model=get_agno_model(role="doctor"),
        instructions=get_doctor_system_prompt_instructions(),
        tools=DOCTOR_TOOLS,
        output_schema=DoctorAnalysisOutput,
        session_state={},
        db=_create_doctor_db(),
        search_knowledge=False,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[DoctorDraftGuardrail()],
        tool_call_limit=3,
        max_tool_calls_from_history=2,
    )


def create_nurse_chat_agent() -> Agent:
    """创建护士对话 Agent — 流式对话场景

    用于护士端悬浮球的对话功能，不使用 output_schema 以支持流式输出。
    支持工具间上下文持久化（护士端独立数据库）。
    """
    return Agent(
        name="小护-对话",
        model=get_agno_model(role="nurse"),
        instructions=get_nurse_chat_system_prompt_instructions(),
        tools=NURSE_TOOLS,
        session_state={},
        db=_create_nurse_db(),
        search_knowledge=False,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[NurseSafetyGuardrail()],
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
        instructions=get_doctor_chat_system_prompt_instructions(),
        tools=DOCTOR_TOOLS,
        session_state={},
        db=_create_doctor_db(),
        search_knowledge=False,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[DoctorDraftGuardrail()],
        tool_call_limit=3,
        max_tool_calls_from_history=2,
    )


def create_followup_generate_agent() -> Agent:
    """创建随访脚本生成 Agent — Structured Output"""
    return Agent(
        name="小安-随访生成",
        model=get_agno_model(role="pregnant"),
        instructions=get_followup_generate_instructions(),
        output_schema=FollowUpGenerateOutput,
        markdown=True,
    )


def create_followup_analysis_agent() -> Agent:
    """创建随访分析 Agent — 随访完成后生成结构化分析报告

    用于随访完成时，对比历史数据，生成包含异常指标、趋势分析、
    个性化建议和护士行动建议的结构化报告。
    """
    return Agent(
        name="小安-随访分析",
        model=get_agno_model(role="pregnant"),
        instructions=get_followup_analysis_instructions(),
        output_schema=FollowUpAnalysisOutput,
        markdown=True,
    )


def create_followup_review_agent() -> Agent:
    """创建随访审核辅助 Agent — 护士审核时生成 AI 辅助报告

    用于护士点击'确认审核'时，分析随访数据并给出审核建议。
    """
    return Agent(
        name="小护-审核辅助",
        model=get_agno_model(role="nurse"),
        instructions=get_followup_review_instructions(),
        output_schema=FollowUpAiReviewOutput,
        markdown=True,
        post_hooks=[NurseSafetyGuardrail()],
    )


@lru_cache(maxsize=1)
def get_nurse_agent() -> Agent:
    return create_nurse_agent()


@lru_cache(maxsize=1)
def get_doctor_agent() -> Agent:
    return create_doctor_agent()


@lru_cache(maxsize=1)
def get_nurse_chat_agent() -> Agent:
    return create_nurse_chat_agent()


@lru_cache(maxsize=1)
def get_doctor_chat_agent() -> Agent:
    return create_doctor_chat_agent()
