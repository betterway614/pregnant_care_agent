"""Agno Agent 定义 - 主 Agent（小安）

主 Agent（小安）：配备完整医疗工具集 + 紧急检测 guardrail
"""
from functools import lru_cache

from agno.agent import Agent
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .prompts import get_pregnant_system_prompt_instructions
from .agno_tools import MEDICAL_TOOLS
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail


def create_main_agent() -> Agent:
    """创建主对话 Agent（小安）

    配备 10 个医疗工具 + 紧急检测 pre-hook + 输出安全 post-hook，
    集成 Agno 原生 Knowledge + Memory + Session 管理。
    """
    return Agent(
        name="小安",
        model=get_agno_model(),
        instructions=get_pregnant_system_prompt_instructions(),
        tools=MEDICAL_TOOLS,
        knowledge=agno_knowledge,
        search_knowledge=True,
        enable_agentic_memory=True,
        add_history_to_context=True,
        num_history_runs=5,
        add_datetime_to_context=True,
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],
        markdown=True,
        tool_call_limit=5,
        debug_mode=True,
    )


@lru_cache(maxsize=1)
def get_main_agent() -> Agent:
    """获取主对话 Agent 单例（缓存复用）"""
    return create_main_agent()
