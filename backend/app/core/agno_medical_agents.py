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
from .agno_knowledge import knowledge as medical_knowledge
from .agno_tools import (
    NURSE_TOOLS,
    DOCTOR_TOOLS,
    NURSE_TOOL_GROUPS,
    DOCTOR_TOOL_GROUPS,
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


# ==================== 结构化输出子模型 ====================


class DifferentialDiagnosis(BaseModel):
    """鉴别诊断条目"""
    condition: str = Field(description="疑似疾病/情况名称")
    supported_by: list[str] = Field(description="支持该考虑的依据")
    against: list[str] = Field(description="不支持/排除的依据")
    tests_needed: list[str] = Field(description="需要进一步完善的检查")


class FollowUpQuestion(BaseModel):
    """随访问题条目"""
    question: str = Field(description="问题文本")
    purpose: str = Field(description="该问题的目的/考察重点")


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
    differential_diagnosis: list[DifferentialDiagnosis] = Field(description="鉴别诊断考虑（至少2-3项）")
    reasoning_chain: list[str] = Field(description="推理链，展示从数据到结论的逐步推理过程")


class FollowUpGenerateOutput(BaseModel):
    """随访对话脚本生成结果"""
    opening_message: str = Field(description="亲切的开场白（30-50字）")
    questions: list[FollowUpQuestion] = Field(description="随访问题列表（4-6个问题）")
    closing_message: str = Field(description="温暖的结束语（30-50字）")


class FollowUpAnalysisOutput(BaseModel):
    """随访完成后 LLM 结构化分析结果"""
    warm_summary: str = Field(description="温馨总结（30-50字），语气温和自然")
    abnormal_indicators: list[str] = Field(description="异常指标列表，无异常则为空列表")
    trend_analysis: str = Field(description="与历史数据对比的趋势分析（50-100字）")
    personalized_advice: str = Field(description="基于回答内容的个性化建议（50-100字）")
    nurse_action_suggestion: str = Field(description="护士行动建议")


class FollowUpAiReviewOutput(BaseModel):
    """护士审核随访时的 AI 辅助分析结果"""
    summary: str = Field(description="本次随访要点摘要（100-200字）")
    abnormal_flags: list[str] = Field(description="异常指标标红列表，无异常则为空列表")
    action_needed: bool = Field(description="是否需要上报医生")
    recommendation: str = Field(description="审核建议：确认通过/需进一步沟通/紧急上报")
    detail_analysis: str = Field(description="详细分析（100-200字）")


class ChatOutput(BaseModel):
    """对话输出 — 用于流式对话场景"""
    content: str = Field(description="回复内容")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")


def format_structured_output_to_markdown(content: object) -> str | None:
    """将结构化输出 Pydantic 模型转换为可读的 Markdown 文本。

    当 Agent 使用 output_schema 时，Agno 框架不会产生 RunEvent.run_content
    流式事件。此函数将 run_response.content 转为前端可渲染的 Markdown。
    如果 content 已是字符串，直接返回；若非预期类型，返回 None。
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content if content.strip() else None

    # NurseAnalysisOutput
    if isinstance(content, NurseAnalysisOutput):
        parts: list[str] = []
        if content.summary:
            parts.append(f"## 综合概述\n\n{content.summary}")
        if content.risk_assessment:
            parts.append(f"## 风险评估\n\n{content.risk_assessment}")
        if content.nursing_suggestions:
            parts.append(f"## 护理建议\n\n{content.nursing_suggestions}")
        if content.followup_focus:
            items = "\n".join(f"- {item}" for item in content.followup_focus)
            parts.append(f"## 随访重点\n\n{items}")
        return "\n\n".join(parts) if parts else None

    # DoctorAnalysisOutput
    if isinstance(content, DoctorAnalysisOutput):
        parts: list[str] = []
        if content.analysis:
            parts.append(f"## 综合分析\n\n{content.analysis}")
        if content.evidence_references:
            items = "\n".join(f"- {ref}" for ref in content.evidence_references)
            parts.append(f"## 证据引用\n\n{items}")
        if content.suggested_orders:
            parts.append(f"## 建议医嘱\n\n{content.suggested_orders}")
        if content.risk_summary:
            parts.append(f"## 风险摘要\n\n{content.risk_summary}")
        if content.differential_diagnosis:
            items = "\n".join(
                f"- **{d.condition}**: 支持依据: {', '.join(d.supported_by) if d.supported_by else '无'}; 排除依据: {', '.join(d.against) if d.against else '无'}; 需检查: {', '.join(d.tests_needed) if d.tests_needed else '无'}"
                for d in content.differential_diagnosis
            )
            parts.append(f"## 鉴别诊断\n\n{items}")
        if content.reasoning_chain:
            items = "\n".join(f"- {step}" for step in content.reasoning_chain)
            parts.append(f"## 推理链\n\n{items}")
        return "\n\n".join(parts) if parts else None

    # FollowUpGenerateOutput
    if isinstance(content, FollowUpGenerateOutput):
        parts: list[str] = []
        if content.opening_message:
            parts.append(content.opening_message)
        if content.questions:
            for i, q in enumerate(content.questions, 1):
                parts.append(f"**{i}. {q.question}**")
                if q.purpose:
                    parts.append(f"*目的: {q.purpose}*")
        if content.closing_message:
            parts.append(content.closing_message)
        return "\n\n".join(parts) if parts else None

    # FollowUpAnalysisOutput
    if isinstance(content, FollowUpAnalysisOutput):
        parts: list[str] = []
        if content.warm_summary:
            parts.append(f"## 温馨总结\n\n{content.warm_summary}")
        if content.abnormal_indicators:
            items = "\n".join(f"- {item}" for item in content.abnormal_indicators)
            parts.append(f"## 异常指标\n\n{items}")
        if content.trend_analysis:
            parts.append(f"## 趋势分析\n\n{content.trend_analysis}")
        if content.personalized_advice:
            parts.append(f"## 个性化建议\n\n{content.personalized_advice}")
        if content.nurse_action_suggestion:
            parts.append(f"## 护士行动建议\n\n{content.nurse_action_suggestion}")
        return "\n\n".join(parts) if parts else None

    return None


def _build_nurse_agent_variant(variant_name: str, tools: list, tool_call_limit: int, use_schema: bool = True, instructions: list[str] | None = None) -> Agent:
    """护士 Agent 通用构造器"""
    kwargs = dict(
        name=f"小护-{variant_name}",
        model=get_agno_model(role="nurse"),
        instructions=instructions if instructions is not None else get_nurse_system_prompt_instructions(),
        tools=tools,
        session_state={},
        db=_create_nurse_db(),
        knowledge=medical_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[NurseSafetyGuardrail()],
        tool_call_limit=tool_call_limit,
        max_tool_calls_from_history=2,
    )
    if use_schema:
        kwargs["output_schema"] = NurseAnalysisOutput
    return Agent(**kwargs)


def _build_doctor_agent_variant(variant_name: str, tools: list, tool_call_limit: int, use_schema: bool = True, instructions: list[str] | None = None) -> Agent:
    """医生 Agent 通用构造器"""
    kwargs = dict(
        name=f"智医-{variant_name}",
        model=get_agno_model(role="doctor"),
        instructions=instructions if instructions is not None else get_doctor_system_prompt_instructions(),
        tools=tools,
        session_state={},
        db=_create_doctor_db(),
        knowledge=medical_knowledge,
        search_knowledge=True,
        add_datetime_to_context=True,
        markdown=True,
        post_hooks=[DoctorDraftGuardrail()],
        tool_call_limit=tool_call_limit,
        max_tool_calls_from_history=2,
    )
    if use_schema:
        kwargs["output_schema"] = DoctorAnalysisOutput
    return Agent(**kwargs)


# ==================== Agent 工厂 ====================


def create_nurse_agent() -> Agent:
    """护士分析 Agent（全量兜底，6 tools, output_schema）"""
    return _build_nurse_agent_variant("main", NURSE_TOOLS, tool_call_limit=5, use_schema=True)


def create_doctor_agent() -> Agent:
    """医生分析 Agent（全量兜底，7 tools, output_schema）"""
    return _build_doctor_agent_variant("main", DOCTOR_TOOLS, tool_call_limit=4, use_schema=True)


# ---- 护士端场景变体 ----

@lru_cache(maxsize=1)
def get_nurse_analyze_agent() -> Agent:
    """护士分析变体（4 tools: query + trends + rules + knowledge）"""
    return _build_nurse_agent_variant("analyze", NURSE_TOOL_GROUPS["analyze"], tool_call_limit=4)


@lru_cache(maxsize=1)
def get_nurse_followup_agent() -> Agent:
    """护士随访变体（2 tools: create_followup + query）"""
    return _build_nurse_agent_variant("followup", NURSE_TOOL_GROUPS["followup"], tool_call_limit=2)


@lru_cache(maxsize=1)
def get_nurse_report_agent() -> Agent:
    """护士上报变体（2 tools: report_issue + query）"""
    return _build_nurse_agent_variant("report", NURSE_TOOL_GROUPS["report"], tool_call_limit=2)


@lru_cache(maxsize=1)
def get_nurse_chat_variant_agent() -> Agent:
    """护士对话变体（3 tools: query + knowledge + trends, 无 schema 支持流式）"""
    return _build_nurse_agent_variant("chat", NURSE_TOOL_GROUPS["chat"], tool_call_limit=3, use_schema=False, instructions=get_nurse_chat_system_prompt_instructions())


# ---- 医生端场景变体 ----

@lru_cache(maxsize=1)
def get_doctor_analyze_agent() -> Agent:
    """医生分析变体（5 tools: comprehensive + trends + rules + knowledge + guideline）"""
    return _build_doctor_agent_variant("analyze", DOCTOR_TOOL_GROUPS["analyze"], tool_call_limit=5)


@lru_cache(maxsize=1)
def get_doctor_order_agent() -> Agent:
    """医生医嘱变体（2 tools: generate_order + comprehensive）"""
    return _build_doctor_agent_variant("order", DOCTOR_TOOL_GROUPS["order"], tool_call_limit=2)


@lru_cache(maxsize=1)
def get_doctor_issue_agent() -> Agent:
    """医生问题处理变体（2 tools: handle_issue + comprehensive）"""
    return _build_doctor_agent_variant("issue", DOCTOR_TOOL_GROUPS["issue"], tool_call_limit=2)


@lru_cache(maxsize=1)
def get_doctor_chat_variant_agent() -> Agent:
    """医生对话变体（3 tools: knowledge + trends + rules, 无 schema 支持流式）"""
    return _build_doctor_agent_variant("chat", DOCTOR_TOOL_GROUPS["chat"], tool_call_limit=3, use_schema=False, instructions=get_doctor_chat_system_prompt_instructions())


# ---- 向后兼容的 getter（全量兜底） ----

@lru_cache(maxsize=1)
def get_nurse_agent() -> Agent:
    """获取护士分析 Agent（全量兜底，向后兼容）"""
    return create_nurse_agent()


@lru_cache(maxsize=1)
def get_doctor_agent() -> Agent:
    """获取医生分析 Agent（全量兜底，向后兼容）"""
    return create_doctor_agent()


@lru_cache(maxsize=1)
def get_nurse_chat_agent() -> Agent:
    """获取护士对话 Agent（全量兜底，向后兼容）"""
    return _build_nurse_agent_variant("chat-full", NURSE_TOOLS, tool_call_limit=3, use_schema=False, instructions=get_nurse_chat_system_prompt_instructions())


@lru_cache(maxsize=1)
def get_doctor_chat_agent() -> Agent:
    """获取医生对话 Agent（全量兜底，向后兼容）"""
    return _build_doctor_agent_variant("chat-full", DOCTOR_TOOLS, tool_call_limit=3, use_schema=False, instructions=get_doctor_chat_system_prompt_instructions())


# ---- 向后兼容的 create_* 工厂函数 ----

def create_nurse_chat_agent() -> Agent:
    """创建护士对话 Agent（向后兼容别名）"""
    return _build_nurse_agent_variant("chat-full", NURSE_TOOLS, tool_call_limit=3, use_schema=False, instructions=get_nurse_chat_system_prompt_instructions())


def create_doctor_chat_agent() -> Agent:
    """创建医生对话 Agent（向后兼容别名）"""
    return _build_doctor_agent_variant("chat-full", DOCTOR_TOOLS, tool_call_limit=3, use_schema=False, instructions=get_doctor_chat_system_prompt_instructions())


# ---- 变体路由映射 ----

NURSE_AGENT_VARIANT_MAP = {
    "analyze": get_nurse_analyze_agent,
    "followup": get_nurse_followup_agent,
    "report": get_nurse_report_agent,
    "chat": get_nurse_chat_variant_agent,
    "complex": get_nurse_agent,
}

DOCTOR_AGENT_VARIANT_MAP = {
    "analyze": get_doctor_analyze_agent,
    "order": get_doctor_order_agent,
    "issue": get_doctor_issue_agent,
    "chat": get_doctor_chat_variant_agent,
    "complex": get_doctor_agent,
}


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
def get_followup_generate_agent() -> Agent:
    """获取随访脚本生成 Agent 单例"""
    return create_followup_generate_agent()


@lru_cache(maxsize=1)
def get_followup_analysis_agent() -> Agent:
    """获取随访分析 Agent 单例"""
    return create_followup_analysis_agent()


@lru_cache(maxsize=1)
def get_followup_review_agent() -> Agent:
    """获取随访审核辅助 Agent 单例"""
    return create_followup_review_agent()
