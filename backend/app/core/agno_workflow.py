"""Agno Workflow 编排 - 预警分析流程 & 孕检工作流"""
from __future__ import annotations

from functools import lru_cache

from agno.workflow import Step, Workflow
from .agno_medical_agents import get_nurse_agent, get_doctor_agent


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
