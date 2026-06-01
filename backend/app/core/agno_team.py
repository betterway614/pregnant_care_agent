"""Agno Team 模式 - 多 Agent 协作

使用 Agno Team 实现小安、小护、智医的协作，
由协调者根据用户问题自动路由到合适的 Agent。

Level 4: 能够推理和协作的智能体团队
"""
from __future__ import annotations

from functools import lru_cache

from agno.team import Team
from agno.team.mode import TeamMode
from .agno_agent import create_main_agent
from .agno_client import get_agno_model
from .agno_medical_agents import (
    create_nurse_agent,
    create_doctor_agent,
    get_nurse_agent,
    get_doctor_agent,
)


def create_care_team() -> Team:
    """创建孕期护理团队

    成员：
    - 小安：日常健康咨询、数据记录、情绪支持
    - 小护：护理分析、健康教育、随访重点
    - 智医：医疗分析、循证建议、风险评估

    协调模式：Route（路由）
    根据用户问题自动选择最合适的 Agent 处理。
    """
    return Team(
        name="AI-Care 孕期护理团队",
        model=get_agno_model(role="pregnant"),
        members=[
            create_main_agent(),
            create_nurse_agent(),
            create_doctor_agent(),
        ],
        instructions=[
            "你是AI-Care孕期护理团队的协调者。",
            "根据用户问题的性质，自动路由到最合适的团队成员：",
            "- 日常健康咨询、数据记录、情绪支持 → 小安",
            "- 护理分析、健康教育、随访相关 → 小护",
            "- 医疗分析、风险评估、循证建议 → 智医",
            "- 紧急情况 → 直接引导就医，不路由",
            "选择最合适的成员处理用户问题，展示成员的专业分析。",
        ],
        show_members_responses=True,
        get_member_information_tool=True,
        add_member_tools_to_context=True,
        markdown=True,
        debug_mode=True,
    )


@lru_cache(maxsize=1)
def get_care_team() -> Team:
    """获取孕期护理团队单例"""
    return create_care_team()


def create_alert_team() -> Team:
    """创建预警响应团队 — 护士+医生并行分析

    用于告警触发时，护士和医生从各自专业角度同时分析，
    综合两者意见给出最终处理建议。
    """
    return Team(
        name="预警响应团队",
        model=get_agno_model(role="pregnant"),
        mode=TeamMode.broadcast,
        members=[
            get_nurse_agent(),
            get_doctor_agent(),
        ],
        instructions=[
            "你们是预警响应团队，收到告警后需要协作处理。",
            "小护：从护理角度分析异常指标，评估护理风险，给出护理建议。",
            "智医：从医疗角度分析异常指标，评估临床风险，给出医学建议。",
            "综合两人的分析，给出最终处理建议：确认观察/需进一步检查/紧急就医。",
        ],
        show_members_responses=True,
        get_member_information_tool=True,
        add_member_tools_to_context=True,
        markdown=True,
        debug_mode=True,
    )


@lru_cache(maxsize=1)
def get_alert_team() -> Team:
    """获取预警响应团队单例"""
    return create_alert_team()
