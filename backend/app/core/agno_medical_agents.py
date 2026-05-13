"""护士/医生 AI 专用 Agent — Structured Output + Agno 工具

使用 Agno output_schema 替代手动 _parse_llm_json() 正则解析，
提供类型安全的结构化输出。

Phase 4.1 升级：为护士/医生 Agent 配备工具集，
让它们能自主获取所需数据，而非在 router 层手动拼装上下文。
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from agno.agent import Agent
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .agno_tools import (
    agno_get_patient_context,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
    agno_search_knowledge,
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


# ==================== Agent 工厂 ====================


def create_nurse_agent() -> Agent:
    """创建护士 AI Agent — Structured Output + 自主数据获取

    配备工具：患者上下文、趋势分析、规则评估、知识搜索，
    让小护能自主获取所需数据进行分析。
    """
    return Agent(
        name="小护",
        model=get_agno_model(),
        instructions=[
            "你是一位经验丰富的产科护士，擅长孕产妇护理和健康教育。",
            "使用工具获取孕妇数据后进行专业分析。",
            "绝不出具诊断结论，复杂情况建议咨询医生。",
        ],
        tools=[
            agno_get_patient_context,
            agno_analyze_health_trends,
            agno_evaluate_vital_rules,
            agno_search_knowledge,
        ],
        output_schema=NurseAnalysisOutput,
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=5,
    )


def create_doctor_agent() -> Agent:
    """创建医生 AI Agent — Structured Output + 自主数据获取

    配备工具：患者上下文、趋势分析、规则评估、知识搜索，
    让智医能自主获取所需数据进行综合分析。
    """
    return Agent(
        name="智医",
        model=get_agno_model(),
        instructions=[
            "你是一位资深的产科医生，擅长高危妊娠管理和循证医学。",
            "使用工具获取孕妇数据后进行专业分析，引用权威医学指南。",
            "绝不出具诊断结论或用药建议，仅提供分析参考。",
        ],
        tools=[
            agno_get_patient_context,
            agno_analyze_health_trends,
            agno_evaluate_vital_rules,
            agno_search_knowledge,
        ],
        output_schema=DoctorAnalysisOutput,
        knowledge=agno_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        tool_call_limit=5,
    )


def create_followup_generate_agent() -> Agent:
    """创建随访脚本生成 Agent — Structured Output"""
    return Agent(
        name="小安-随访生成",
        model=get_agno_model(),
        instructions=[
            "你是一位经验丰富的产科随访护士，擅长与孕妇进行有效的电话/微信随访沟通。",
            "请严格按结构化格式返回结果。",
        ],
        output_schema=FollowUpGenerateOutput,
        markdown=True,
    )
