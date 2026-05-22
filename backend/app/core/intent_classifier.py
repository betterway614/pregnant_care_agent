"""意图分类器 - 规则 NLU 为主，供路由与 Workflow 编排使用"""
from __future__ import annotations

from enum import Enum

from .nlu_engine import nlu_engine


class IntentCategory(str, Enum):
    CHAT = "chat"
    ANALYZE = "analyze"
    EMERGENCY = "emergency"
    KNOWLEDGE = "knowledge"
    FOLLOWUP = "followup"
    ALERT = "alert"
    REPORT = "report"


_ANALYZE_KEYWORDS = ("分析", "评估", "解读", "看看", "怎么样", "情况如何")
_KNOWLEDGE_KEYWORDS = ("指南", "标准", "什么是", "怎么算", "正常范围", "知识")
_FOLLOWUP_KEYWORDS = ("随访", "回访", "打电话", "问卷")
_ALERT_KEYWORDS = ("预警", "告警", "上报", "异常")
_REPORT_KEYWORDS = ("上报医生", "通知医生", "转医生", " escalate")


def classify_intent(text: str, role: str = "pregnant") -> IntentCategory:
    """基于 NLU + 关键词的轻量意图分类"""
    if not text or not text.strip():
        return IntentCategory.CHAT

    parsed = nlu_engine.parse(text)
    if parsed.is_emergency:
        return IntentCategory.EMERGENCY

    lower = text.lower()
    if any(kw in text for kw in _REPORT_KEYWORDS):
        return IntentCategory.REPORT
    if any(kw in text for kw in _ALERT_KEYWORDS):
        return IntentCategory.ALERT
    if any(kw in text for kw in _FOLLOWUP_KEYWORDS):
        return IntentCategory.FOLLOWUP
    if role in ("nurse", "doctor") and any(kw in text for kw in _ANALYZE_KEYWORDS):
        return IntentCategory.ANALYZE
    if any(kw in text for kw in _KNOWLEDGE_KEYWORDS):
        return IntentCategory.KNOWLEDGE
    if any(kw in text for kw in _ANALYZE_KEYWORDS):
        return IntentCategory.ANALYZE

    return IntentCategory.CHAT
