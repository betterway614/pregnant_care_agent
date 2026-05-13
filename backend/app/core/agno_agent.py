"""Agno Agent 定义 - 主 Agent 和随访 Agent

主 Agent（小安）：配备完整医疗工具集 + 紧急检测 guardrail
随访 Agent（小安-随访）：配备随访专用工具集
"""
from functools import lru_cache

from agno.agent import Agent
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .prompts import (
    get_pregnant_system_prompt_instructions,
    get_followup_agent_instructions,
)
from .agno_tools import MEDICAL_TOOLS, AGNO_FOLLOWUP_TOOLS
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


def create_followup_agent(patient_name: str = "准妈妈",
                          gest_week: str = "?",
                          risk_tags: list[str] | None = None,
                          record_id: str = "",
                          template_name: str = "standard",
                          health_education: list[str] | None = None) -> Agent:
    """创建随访模式 Agent（小安-随访）

    注意：随访 Agent 含动态患者上下文，每次请求需新建，不使用缓存。
    集成 Knowledge 和 Memory，提升随访对话质量。
    """
    risk_text = "、".join(risk_tags) if risk_tags else "无"
    edu_text = "\n".join(f"- {item}" for item in (health_education or []))

    return Agent(
        name="小安-随访",
        model=get_agno_model(),
        instructions=get_followup_agent_instructions(
            patient_name=patient_name,
            gest_week=gest_week,
            risk_text=risk_text,
            record_id=record_id,
            template_name=template_name,
            health_education=edu_text,
        ),
        tools=AGNO_FOLLOWUP_TOOLS,
        knowledge=agno_knowledge,
        search_knowledge=True,
        enable_agentic_memory=True,
        add_history_to_context=True,
        num_history_runs=3,
        add_datetime_to_context=True,
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],
        markdown=True,
        tool_call_limit=10,
        debug_mode=True,
    )
