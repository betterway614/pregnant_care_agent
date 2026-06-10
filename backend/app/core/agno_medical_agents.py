"""护士/医生 AI 专用 Agent 工厂

职责: 创建和管理护士/医生/随访 Agent 变体实例。

重构: Schema 定义已移至 core/schemas/，格式化器已移至 core/formatters.py。
本模块仅保留 Agent 工厂函数和路由映射。
"""
from __future__ import annotations

from functools import lru_cache

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.filters import IN
from .agno_client import get_agno_model
from .agno_guardrails import NurseSafetyGuardrail, DoctorDraftGuardrail
from .agno_knowledge import knowledge as medical_knowledge
from .agno_tools import (
    NURSE_TOOLS, DOCTOR_TOOLS, NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS,
)

# 角色级知识库过滤器
_NURSE_KNOWLEDGE_FILTERS = [IN("audience", ["nurse", "all"])]
_DOCTOR_KNOWLEDGE_FILTERS = [IN("audience", ["doctor", "nurse", "all"])]
from .schemas import (
    NurseAnalysisOutput, DoctorAnalysisOutput,
    FollowUpGenerateOutput, FollowUpAnalysisOutput, FollowUpAiReviewOutput,
    ChatOutput, FollowUpQuestion,
)
from .formatters import format_structured_output_to_markdown
from .prompts import (
    get_nurse_system_prompt_instructions, get_nurse_chat_system_prompt_instructions,
    get_doctor_system_prompt_instructions, get_doctor_chat_system_prompt_instructions,
    get_followup_generate_instructions, get_followup_analysis_instructions,
    get_followup_review_instructions, get_nurse_followup_prompt_instructions,
    get_nurse_report_prompt_instructions, get_doctor_issue_prompt_instructions,
)

import os

# Agent 会话持久化数据库路径（每个角色独立，防止敏感信息泄露）
_db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),)
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")
_nurse_db_path = os.path.join(_db_dir, "agent_sessions_nurse.db")
_doctor_db_path = os.path.join(_db_dir, "agent_sessions_doctor.db")


def _create_pregnant_db():
    return SqliteDb(db_file=_pregnant_db_path)

def _create_nurse_db():
    return SqliteDb(db_file=_nurse_db_path)

def _create_doctor_db():
    return SqliteDb(db_file=_doctor_db_path)


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
        knowledge_filters=_NURSE_KNOWLEDGE_FILTERS,
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
        knowledge_filters=_DOCTOR_KNOWLEDGE_FILTERS,
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
    return _build_nurse_agent_variant("followup", NURSE_TOOL_GROUPS["followup"], tool_call_limit=2, instructions=get_nurse_followup_prompt_instructions())


@lru_cache(maxsize=1)
def get_nurse_report_agent() -> Agent:
    """护士上报变体（2 tools: report_issue + query）"""
    return _build_nurse_agent_variant("report", NURSE_TOOL_GROUPS["report"], tool_call_limit=2, instructions=get_nurse_report_prompt_instructions())


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
    return _build_doctor_agent_variant("issue", DOCTOR_TOOL_GROUPS["issue"], tool_call_limit=2, instructions=get_doctor_issue_prompt_instructions())


@lru_cache(maxsize=1)
def get_doctor_chat_variant_agent() -> Agent:
    """医生对话变体（3 tools: knowledge + trends + rules, 无 schema 支持流式）"""
    return _build_doctor_agent_variant("chat", DOCTOR_TOOL_GROUPS["chat"], tool_call_limit=3, use_schema=False, instructions=get_doctor_chat_system_prompt_instructions())


# ---- 全量兜底 Agent（router fallback，NLU 未命中时使用） ----

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
        name="小护-随访生成",
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
