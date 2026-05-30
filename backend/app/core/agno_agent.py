"""Agno Agent 定义 - 主 Agent（小安）+ 场景变体（工具路由）

Agent 变体:
- chat: 闲聊/情绪安抚（3 tools）
- record: 健康数据记录（4 tools）
- qa: 孕期知识问答（3 tools）
- emergency: 紧急检测（2 tools）
- main: 全量兜底（10 tools）

安全设计：所有变体共享同一个 SqliteDb（session 跨变体连续）
"""
from functools import lru_cache

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .prompts import get_pregnant_system_prompt_instructions, VARIANT_INSTRUCTIONS
from .agno_tools import MEDICAL_TOOLS, TOOL_GROUPS
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail

import os

_db_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")


def _create_pregnant_db():
    """创建孕妇端 Agent 专用 SqliteDb（所有变体共享）"""
    return SqliteDb(db_file=_pregnant_db_path)


def _build_agent(variant_name: str, tools: list, tool_call_limit: int) -> Agent:
    """通用 Agent 构造器 — 所有变体共享 SqliteDb"""
    return Agent(
        name=f"小安-{variant_name}",
        model=get_agno_model(role="pregnant"),
        instructions=VARIANT_INSTRUCTIONS.get(variant_name, get_pregnant_system_prompt_instructions()),
        tools=tools,
        knowledge=agno_knowledge,
        search_knowledge=False,
        db=_create_pregnant_db(),
        add_history_to_context=True,
        num_history_runs=8,
        enable_agentic_memory=True,
        add_datetime_to_context=True,
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],
        markdown=True,
        tool_call_limit=tool_call_limit,
        debug_mode=False,
    )


def create_main_agent() -> Agent:
    """全量兜底 Agent（10 tools）"""
    return _build_agent("main", MEDICAL_TOOLS, tool_call_limit=8)


@lru_cache(maxsize=1)
def get_main_agent() -> Agent:
    """获取主对话 Agent 单例（缓存复用）— 全量兜底"""
    return create_main_agent()


@lru_cache(maxsize=1)
def get_chat_agent() -> Agent:
    """闲聊/情绪安抚 Agent（3 tools）"""
    return _build_agent("chat", TOOL_GROUPS["chat"], tool_call_limit=3)


@lru_cache(maxsize=1)
def get_record_agent() -> Agent:
    """健康数据记录 Agent（4 tools）"""
    return _build_agent("record", TOOL_GROUPS["record"], tool_call_limit=4)


@lru_cache(maxsize=1)
def get_qa_agent() -> Agent:
    """孕期知识问答 Agent（3 tools）"""
    return _build_agent("qa", TOOL_GROUPS["qa"], tool_call_limit=4)


@lru_cache(maxsize=1)
def get_emergency_agent() -> Agent:
    """紧急检测 Agent（2 tools）"""
    return _build_agent("emergency", TOOL_GROUPS["emergency"], tool_call_limit=1)


# variant → factory 映射（供 chat_handler 路由使用）
AGENT_VARIANT_MAP = {
    "chat": get_chat_agent,
    "record": get_record_agent,
    "qa": get_qa_agent,
    "emergency": get_emergency_agent,
    "complex": get_main_agent,
}
