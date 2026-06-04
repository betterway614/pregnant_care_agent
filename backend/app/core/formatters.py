"""结构化输出 → Markdown 格式化器

使用 functools.singledispatch 实现 OCP:
新增输出类型只需 @format_to_markdown.register，无需修改已有代码。

替代原 agno_medical_agents.py 中的 isinstance 链。
"""
from __future__ import annotations

import json
from functools import singledispatch

from .schemas.nurse_schemas import NurseAnalysisOutput
from .schemas.doctor_schemas import DoctorAnalysisOutput
from .schemas.followup_schemas import (
    FollowUpGenerateOutput, FollowUpAnalysisOutput, FollowUpAiReviewOutput,
)


@singledispatch
def format_to_markdown(content) -> str | None:
    """通用格式化 — 未知类型返回 JSON"""
    if content is None:
        return None
    if isinstance(content, str):
        return content.strip() or None
    if hasattr(content, "model_dump"):
        return json.dumps(content.model_dump(), ensure_ascii=False, indent=2)
    return str(content)


@format_to_markdown.register
def _(content: NurseAnalysisOutput) -> str | None:
    parts: list[str] = []
    if content.summary:
        parts.append(f"## 综合概述\n\n{content.summary}")
    if content.risk_assessment:
        parts.append(f"## 风险评估\n\n{content.risk_assessment}")
    if content.alert_level and content.alert_level != "NONE":
        parts.append(f"## 预警级别\n\n{content.alert_level}")
    if content.nursing_suggestions:
        parts.append(f"## 护理建议\n\n{content.nursing_suggestions}")
    if content.followup_focus:
        items = "\n".join(f"- {item}" for item in content.followup_focus)
        parts.append(f"## 随访重点\n\n{items}")
    return "\n\n".join(parts) if parts else None


@format_to_markdown.register
def _(content: DoctorAnalysisOutput) -> str | None:
    parts: list[str] = []
    if content.analysis:
        parts.append(f"## 综合分析\n\n{content.analysis}")
    if content.evidence_references:
        items = "\n".join(f"- {ref}" for ref in content.evidence_references)
        parts.append(f"## 证据引用\n\n{items}")
    if content.suggested_orders:
        parts.append(f"## 建议医嘱\n\n{content.suggested_orders}")
    if content.risk_summary:
        parts.append(f"## 风险摘要\n\n{content.risk_summary}")
    if content.reasoning_chain:
        items = "\n".join(f"- {step}" for step in content.reasoning_chain)
        parts.append(f"## 推理链\n\n{items}")
    return "\n\n".join(parts) if parts else None


@format_to_markdown.register
def _(content: FollowUpGenerateOutput) -> str | None:
    parts: list[str] = []
    if content.opening_message:
        parts.append(content.opening_message)
    if content.questions:
        for i, q in enumerate(content.questions, 1):
            parts.append(f"**{i}. {q.question}**")
            if q.purpose:
                parts.append(f"*目的: {q.purpose}*")
    if content.closing_message:
        parts.append(content.closing_message)
    return "\n\n".join(parts) if parts else None


@format_to_markdown.register
def _(content: FollowUpAnalysisOutput) -> str | None:
    parts: list[str] = []
    if content.warm_summary:
        parts.append(f"## 温馨总结\n\n{content.warm_summary}")
    if content.abnormal_indicators:
        items = "\n".join(f"- {item}" for item in content.abnormal_indicators)
        parts.append(f"## 异常指标\n\n{items}")
    if content.trend_analysis:
        parts.append(f"## 趋势分析\n\n{content.trend_analysis}")
    if content.personalized_advice:
        parts.append(f"## 个性化建议\n\n{content.personalized_advice}")
    if content.nurse_action_suggestion:
        parts.append(f"## 护士行动建议\n\n{content.nurse_action_suggestion}")
    return "\n\n".join(parts) if parts else None


# 向后兼容别名
format_structured_output_to_markdown = format_to_markdown
