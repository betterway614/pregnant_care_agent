"""Agno Agent 定义 - 主 Agent（小安）+ 场景变体（工具路由）

Agent 变体:
- chat: 闲聊/情绪安抚（3 tools）
- record: 健康数据记录（4 tools）
- qa: 孕期知识问答（3 tools）
- emergency: 紧急检测（2 tools）
- main: 全量兜底（10 tools）

安全设计：所有变体共享同一个 Db（session 跨变体连续）
数据库适配：PostgreSQL 优先（消除 SQLite 并发锁竞争），回退到 SQLite
"""
import logging
from functools import lru_cache

from agno.agent import Agent
from agno.filters import IN
from ..config import settings
from .agno_client import get_agno_model
from .agno_knowledge import knowledge
from .prompts import get_pregnant_system_prompt_instructions, VARIANT_INSTRUCTIONS
from .agno_tools import MEDICAL_TOOLS, TOOL_GROUPS
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail

logger = logging.getLogger(__name__)

# 孕妇端知识库过滤器：仅检索面向孕妇和通用的知识
_PREGNANT_KNOWLEDGE_FILTERS = [IN("audience", ["patient", "all"])]

import os

_db_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")


def _create_pregnant_db():
    """创建孕妇端 Agent 会话数据库

    PostgreSQL 优先（消除并发锁竞争），回退到 SQLite。
    所有变体共享同一 session_table，保证对话历史跨变体连续。
    """
    if settings.db_type == "postgres":
        from agno.db.postgres import PostgresDb
        return PostgresDb(
            db_url=settings.agno_database_url,
            session_table="agent_sessions_pregnant",
        )
    from agno.db.sqlite import SqliteDb
    return SqliteDb(db_file=_pregnant_db_path)


def _build_agent(variant_name: str, tools: list, tool_call_limit: int,
                 enable_knowledge: bool | None = None) -> Agent:
    """通用 Agent 构造器 — 所有变体共享 SqliteDb

    知识检索机制:
        search_knowledge=True 触发 Agno 框架自动注入 search_knowledge_base 工具。
        仅 qa 和 complex (兜底) 变体默认启用知识检索；chat/record/emergency 关闭，
        减少非必要场景的 RAG 误触发。

    角色级过滤通过 knowledge_filters=_PREGNANT_KNOWLEDGE_FILTERS 控制，
    仅返回 audience 为 'patient' 或 'all' 的知识条目。

    Args:
        enable_knowledge: 是否启用知识检索。None 时按变体名默认决定:
            qa/complex → True, 其余 → False
    """
    # 知识检索门控: 仅知识问答和兜底变体默认启用
    if enable_knowledge is None:
        enable_knowledge = variant_name in ("qa", "main", "complex", "qa-full")

    kwargs = dict(
        name=f"小安-{variant_name}",
        model=get_agno_model(role="pregnant"),
        instructions=VARIANT_INSTRUCTIONS.get(variant_name, get_pregnant_system_prompt_instructions()),
        tools=tools,
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
    if knowledge is not None and enable_knowledge:
        kwargs["knowledge"] = knowledge
        kwargs["search_knowledge"] = True
        kwargs["knowledge_filters"] = _PREGNANT_KNOWLEDGE_FILTERS
    elif knowledge is not None and not enable_knowledge:
        # 不启用知识检索但保留 knowledge 引用 (运行时可由 LLM 通过其他工具间接获取)
        logger.debug("[RAG] Pregnant Agent '%s': knowledge 可用但主动关闭检索 (非知识场景)", variant_name)
    else:
        logger.warning("[RAG] Pregnant Agent '%s': knowledge 不可用，禁用知识库检索。请检查 RAG_ENABLED 和 DB_TYPE 配置。", variant_name)
    return Agent(**kwargs)


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
    """孕期知识问答 Agent（2 tools + 框架自动注入 search_knowledge）"""
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
