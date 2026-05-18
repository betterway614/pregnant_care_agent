"""Agno Workflow 编排 - 确定性流程

使用 Agno Workflow 实现孕检和随访的标准化流程编排，
替代手动 if/else 管道。

Level 5: 有状态和确定性的智能体工作流
"""
from __future__ import annotations

from functools import lru_cache

from agno.workflow import Step, Workflow, Router, Condition
from agno.agent import Agent
from .agno_client import get_agno_model
from .agno_tools import (
    agno_get_patient_context,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
)
from .agno_medical_agents import (
    NurseAnalysisOutput,
    DoctorAnalysisOutput,
)


# ==================== Workflow Agent 定义 ====================


def _create_data_collection_agent() -> Agent:
    """数据采集 Agent - 收集孕妇健康数据"""
    return Agent(
        name="数据采集员",
        model=get_agno_model(),
        instructions=[
            "你是健康数据采集专员，负责收集孕妇的最新健康数据。",
            "使用工具获取孕妇的上下文信息和近期数据。",
            "整理并输出结构化的数据摘要。",
        ],
        tools=[agno_get_patient_context, agno_analyze_health_trends],
        markdown=True,
    )


def _create_risk_assessment_agent() -> Agent:
    """风险评估 Agent - 评估孕妇风险等级"""
    return Agent(
        name="风险评估师",
        model=get_agno_model(),
        instructions=[
            "你是风险评估专家，负责评估孕妇的健康风险。",
            "使用工具获取数据并评估规则，输出风险等级。",
            "风险等级分为：低危(low)、中危(medium)、高危(high)、紧急(urgent)。",
        ],
        tools=[agno_evaluate_vital_rules, agno_analyze_health_trends],
        markdown=True,
    )


def _create_routine_agent() -> Agent:
    """常规处理 Agent - 低危孕妇的标准处理"""
    return Agent(
        name="常规护理员",
        model=get_agno_model(),
        instructions=[
            "你负责低危孕妇的常规护理指导。",
            "提供标准的健康建议和下次产检提醒。",
            "语气温暖亲切，给予鼓励。",
        ],
        markdown=True,
    )


def _create_high_risk_agent() -> Agent:
    """高危处理 Agent - 中高危孕妇的特殊处理"""
    return Agent(
        name="高危护理专家",
        model=get_agno_model(),
        instructions=[
            "你负责中高危孕妇的护理指导。",
            "提供更详细的健康建议和注意事项。",
            "强调定期产检和遵医嘱的重要性。",
            "语气专业但温暖，给予支持。",
        ],
        tools=[agno_analyze_health_trends],
        markdown=True,
    )


def _create_emergency_agent() -> Agent:
    """紧急处理 Agent - 紧急情况的处理"""
    return Agent(
        name="紧急响应员",
        model=get_agno_model(),
        instructions=[
            "你负责紧急情况的处理。",
            "立即引导孕妇就医，提供清晰的就医指引。",
            "保持冷静专业的语气，不要惊慌。",
            "提供必要的急救建议（非医疗诊断）。",
        ],
        markdown=True,
    )


def _create_report_agent() -> Agent:
    """报告生成 Agent - 生成检查报告"""
    return Agent(
        name="报告生成员",
        model=get_agno_model(),
        instructions=[
            "你负责生成孕检报告。",
            "整合数据采集、风险评估的结果，生成结构化报告。",
            "报告包含：数据摘要、风险等级、护理建议、下次产检提醒。",
            "使用清晰的格式输出。",
        ],
        markdown=True,
    )


# ==================== Workflow 定义 ====================


def create_prenatal_workflow() -> Workflow:
    """创建孕检流程 Workflow

    流程：
    1. 数据收集 → 收集孕妇最新健康数据
    2. 风险评估 → 评估风险等级
    3. 路由决策 → 根据风险等级选择处理路径
    4. 报告生成 → 生成综合报告

    支持状态持久化，可中断恢复。
    """
    return Workflow(
        name="孕检流程",
        description="标准化孕检流程编排：数据收集 → 风险评估 → 路由处理 → 报告生成",
        steps=[
            Step(
                name="健康数据采集",
                agent=_create_data_collection_agent(),
                description="收集孕妇最新健康数据",
            ),
            Step(
                name="风险评估",
                agent=_create_risk_assessment_agent(),
                description="评估孕妇健康风险等级",
            ),
            Router(
                name="处理路由",
                selector="session_state.risk_level",
                choices=[
                    Step(
                        name="常规处理",
                        agent=_create_routine_agent(),
                        description="低危孕妇的标准处理",
                    ),
                    Step(
                        name="高危处理",
                        agent=_create_high_risk_agent(),
                        description="中高危孕妇的特殊处理",
                    ),
                    Step(
                        name="紧急处理",
                        agent=_create_emergency_agent(),
                        description="紧急情况的处理",
                    ),
                ],
                description="根据风险等级路由到合适的处理流程",
            ),
            Step(
                name="报告生成",
                agent=_create_report_agent(),
                description="生成综合孕检报告",
            ),
        ],
    )


# ==================== Workflow 缓存 ====================


@lru_cache(maxsize=1)
def get_prenatal_workflow() -> Workflow:
    """获取孕检流程 Workflow 单例"""
    return create_prenatal_workflow()
