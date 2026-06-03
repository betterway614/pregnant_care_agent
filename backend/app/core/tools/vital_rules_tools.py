"""
生命体征规则评估工具

职责: 将健康指标喂入规则引擎，检测异常并返回告警列表。
"""
from __future__ import annotations

from agno.run import RunContext
from agno.tools import tool

from .common import _resolve_pid


@tool
def agno_evaluate_vital_rules(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
    sbp: float = 0,
    dbp: float = 0,
    weight: float = 0,
    fetal_movement: float = 0,
    fetal_movement_avg: float = 0,
    weight_gain_weekly: float = 0,
    emotion_score_avg_7d: float = 0,
    blood_sugar_fasting: float = 0,
    blood_sugar_postprandial: float = 0,
    sleep_hours: float = 8,
    gest_week: float = 0,
) -> dict:
    """评估生命体征规则，返回触发的告警列表。用于检测异常指标。
    pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..rule_engine import rule_engine

    ctx = {
        "sbp": sbp, "dbp": dbp,
        "weight": weight,
        "fetal_movement": fetal_movement,
        "fetal_movement_avg": fetal_movement_avg,
        "weight_gain_weekly": weight_gain_weekly,
        "emotion_score_avg_7d": emotion_score_avg_7d,
        "blood_sugar_fasting": blood_sugar_fasting,
        "blood_sugar_postprandial": blood_sugar_postprandial,
        "sleep_hours": sleep_hours,
        "gest_week": gest_week,
    }
    alerts = rule_engine.evaluate_all(ctx)
    return {
        "pregnant_id": pid,
        "alerts": alerts,
        "alert_count": len(alerts),
        "has_critical": any(a["level"] == "RED" for a in alerts),
    }
