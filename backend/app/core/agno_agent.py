"""Agno Agent 定义 - 主 Agent（小安）

主 Agent（小安）：配备完整医疗工具集 + 紧急检测 guardrail
+ Plan-and-Execute 任务规划 + SqliteDb 会话持久化

安全设计：每个角色使用独立的 SqliteDb，防止敏感信息泄露
"""
from functools import lru_cache

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .prompts import get_pregnant_system_prompt_instructions
from .agno_tools import MEDICAL_TOOLS
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail
from ..config import settings

import os

# 会话持久化数据库路径（每个角色独立，防止敏感信息泄露）
_db_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)

# 孕妇端独立数据库
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")


def _create_pregnant_db():
    """创建孕妇端 Agent 专用 SqliteDb"""
    return SqliteDb(db_file=_pregnant_db_path)


def create_main_agent() -> Agent:
    """创建主对话 Agent（小安）

    配备 10 个医疗工具 + 紧急检测 pre-hook + 输出安全 post-hook，
    集成 Agno 原生 SqliteDb 会话持久化 + Knowledge + agentic Memory。
    Plan-and-Execute 任务规划通过 instructions 注入。

    安全设计：使用孕妇端独立数据库，与护士端/医生端数据隔离
    """
    return Agent(
        name="小安",
        model=get_agno_model(role="pregnant"),
        instructions=get_pregnant_system_prompt_instructions(),
        tools=MEDICAL_TOOLS,
        knowledge=agno_knowledge,
        search_knowledge=False,
        # 会话持久化：Agno 原生 SqliteDb，自动保存/加载对话历史与 session state
        db=_create_pregnant_db(),
        add_history_to_context=True,
        num_history_runs=8,
        enable_agentic_memory=True,
        add_datetime_to_context=True,
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],
        markdown=True,
        tool_call_limit=8,
        debug_mode=False,
    )


@lru_cache(maxsize=1)
def get_main_agent() -> Agent:
    """获取主对话 Agent 单例（缓存复用）"""
    return create_main_agent()
