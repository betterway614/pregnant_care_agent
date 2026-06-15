"""
生命体征规则评估工具

职责: 将健康指标喂入规则引擎，检测异常并返回告警列表。
"""
from __future__ import annotations

import time as _time

from agno.run import RunContext
from agno.tools import tool

from .common import _resolve_pid, truncate_tool_result


@tool
def agno_evaluate_vital_rules(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
    sbp: float | None = None,
    dbp: float | None = None,
    weight: float | None = None,
    fetal_movement: float | None = None,
    fetal_movement_avg: float | None = None,
    weight_gain_weekly: float | None = None,
    emotion_score_avg_7d: float | None = None,
    blood_sugar_fasting: float | None = None,
    blood_sugar_postprandial: float | None = None,
    sleep_hours: float | None = None,
    gest_week: float = 0,
) -> dict:
    """评估生命体征规则，返回触发的告警列表。用于检测异常指标。
    未传入的指标不会参与评估（避免缺失数据被误判为异常值）。
    pregnant_id 可选，留空时自动使用当前登录用户。"""
    _t0 = _time.perf_counter()
    pid = _resolve_pid(pregnant_id, run_context)
    from ..rule_engine import rule_engine

    # 仅传入有值的指标，缺失指标不参与规则评估
    # 例如：fetal_movement=0 会触发 RED "胎动极少"，但 None 不会
    ctx = {"gest_week": gest_week}
    if sbp is not None:
        ctx["sbp"] = sbp
    if dbp is not None:
        ctx["dbp"] = dbp
    if weight is not None:
        ctx["weight"] = weight
    if fetal_movement is not None:
        ctx["fetal_movement"] = fetal_movement
    if fetal_movement_avg is not None:
        ctx["fetal_movement_avg"] = fetal_movement_avg
    if weight_gain_weekly is not None:
        ctx["weight_gain_weekly"] = weight_gain_weekly
    if emotion_score_avg_7d is not None:
        ctx["emotion_score_avg_7d"] = emotion_score_avg_7d
    if blood_sugar_fasting is not None:
        ctx["blood_sugar_fasting"] = blood_sugar_fasting
    if blood_sugar_postprandial is not None:
        ctx["blood_sugar_postprandial"] = blood_sugar_postprandial
    if sleep_hours is not None:
        ctx["sleep_hours"] = sleep_hours
    alerts = rule_engine.evaluate_all(ctx)
    return truncate_tool_result({
        "pregnant_id": pid,
        "alerts": alerts[:5],
        "alert_count": len(alerts),
        "has_critical": any(a["level"] == "RED" for a in alerts),
    }, tool_name="agno_evaluate_vital_rules", tool_start_time=_t0)
