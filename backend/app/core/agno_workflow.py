"""Agno Workflow 编排 - 孕检流程 + 预警分析流程"""
from __future__ import annotations

from functools import lru_cache

from agno.workflow import Step, Workflow, Router
from agno.agent import Agent

from .agno_client import get_agno_model
from .agno_tools import (
    agno_get_patient_context,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
)
from .agno_medical_agents import get_nurse_agent, get_doctor_agent


def _create_data_collection_agent() -> Agent:
    return Agent(
        name="数据采集员",
        model=get_agno_model(role="pregnant"),
        instructions=[
            "你是健康数据采集专员，负责收集孕妇的最新健康数据。",
            "使用工具获取孕妇的上下文信息和近期数据。",
        ],
        tools=[agno_get_patient_context, agno_analyze_health_trends],
        markdown=True,
    )


def _create_risk_assessment_agent() -> Agent:
    return Agent(
        name="风险评估师",
        model=get_agno_model(role="pregnant"),
        instructions=[
            "你是风险评估专家，负责评估孕妇的健康风险。",
            "使用工具获取数据并评估规则，输出风险等级。",
        ],
        tools=[agno_evaluate_vital_rules, agno_analyze_health_trends],
        markdown=True,
    )


def _create_routine_agent() -> Agent:
    return Agent(
        name="常规护理员",
        model=get_agno_model(role="pregnant"),
        instructions=["你负责低危孕妇的常规护理指导。"],
        markdown=True,
    )


def _create_high_risk_agent() -> Agent:
    return Agent(
        name="高危护理专家",
        model=get_agno_model(role="pregnant"),
        instructions=["你负责中高危孕妇的护理指导。"],
        tools=[agno_analyze_health_trends],
        markdown=True,
    )


def _create_emergency_agent() -> Agent:
    return Agent(
        name="紧急响应员",
        model=get_agno_model(role="pregnant"),
        instructions=["你负责紧急情况的处理，引导孕妇就医。"],
        markdown=True,
    )


def _create_report_agent() -> Agent:
    return Agent(
        name="报告生成员",
        model=get_agno_model(role="pregnant"),
        instructions=["你负责生成孕检报告。"],
        markdown=True,
    )


def create_prenatal_workflow() -> Workflow:
    return Workflow(
        name="孕检流程",
        description="数据收集 → 风险评估 → 路由处理 → 报告生成",
        steps=[
            Step(name="健康数据采集", agent=_create_data_collection_agent()),
            Step(name="风险评估", agent=_create_risk_assessment_agent()),
            Router(
                name="处理路由",
                selector="session_state.risk_level",
                choices=[
                    Step(name="常规处理", agent=_create_routine_agent()),
                    Step(name="高危处理", agent=_create_high_risk_agent()),
                    Step(name="紧急处理", agent=_create_emergency_agent()),
                ],
            ),
            Step(name="报告生成", agent=_create_report_agent()),
        ],
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
def get_prenatal_workflow() -> Workflow:
    return create_prenatal_workflow()


@lru_cache(maxsize=1)
def get_alert_analysis_workflow() -> Workflow:
    return create_alert_analysis_workflow()
