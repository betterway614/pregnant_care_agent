"""Agno Workflow 编排 - 预警分析流程"""
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
