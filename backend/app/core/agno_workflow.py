"""Agno Workflow 编排 - 预警分析流程 & 孕检工作流 & 护士/医生多步工作流"""
from __future__ import annotations

from functools import lru_cache

from agno.workflow import Step, Workflow
from .agno_medical_agents import (
    get_nurse_agent, get_doctor_agent,
    get_nurse_analyze_agent, get_doctor_analyze_agent,
)


def create_alert_analysis_workflow() -> Workflow:
    """Alert 处理：护士护理分析 → 医生预分析"""
    return Workflow(
        name="预警分析流程",
        description="护士护理分析 → 医生预分析",
        steps=[
            Step(name="护士护理分析", agent=get_nurse_agent()),
            Step(name="医生预分析", agent=get_doctor_agent()),
        ],
    )


@lru_cache(maxsize=1)
def get_alert_analysis_workflow() -> Workflow:
    return create_alert_analysis_workflow()


def create_prenatal_workflow() -> Workflow:
    """孕检工作流：护士初步分析 → 医生深度分析

    用于 ASK_SYMPTOM / ASK_EXAM / KNOWLEDGE_QUERY 等复杂意图，
    先由护士 Agent 做初步分析，再由医生 Agent 给出专业建议。
    """
    return Workflow(
        name="孕检工作流",
        description="护士初步分析 → 医生深度分析",
        steps=[
            Step(name="护士初步分析", agent=get_nurse_agent()),
            Step(name="医生深度分析", agent=get_doctor_agent()),
        ],
    )


def create_nurse_workflow() -> Workflow:
    """护士多步工作流：数据查询分析 → 预警评估

    用于护士端复杂护理场景（如"全面评估+异常上报+排期推荐"），
    将原本依赖 LLM 自主推理链的多步操作固化为显式工作流，
    确保步骤完整性和顺序。
    """
    return Workflow(
        name="护士多步工作流",
        description="数据查询分析 → 预警评估与上报",
        steps=[
            Step(name="数据查询与分析", agent=get_nurse_analyze_agent()),
            Step(name="预警评估与上报", agent=get_nurse_agent()),
        ],
    )


@lru_cache(maxsize=1)
def get_nurse_workflow() -> Workflow:
    return create_nurse_workflow()


def create_doctor_workflow() -> Workflow:
    """医生多步工作流：综合分析 → 指南检索 → 医嘱建议

    用于医生端复杂诊疗场景（如"全面分析+查指南+出医嘱"），
    将多步工具调用链固化为工作流，保证：先分析数据 → 再查指南 → 最后生成建议。
    """
    return Workflow(
        name="医生多步工作流",
        description="综合分析 → 临床指南检索 → 医嘱建议",
        steps=[
            Step(name="综合分析", agent=get_doctor_analyze_agent()),
            Step(name="指南检索与医嘱建议", agent=get_doctor_agent()),
        ],
    )


@lru_cache(maxsize=1)
def get_doctor_workflow() -> Workflow:
    return create_doctor_workflow()
