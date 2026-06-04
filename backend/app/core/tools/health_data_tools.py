"""
健康数据工具 — 持久化、查询、提醒、趋势分析、心理筛查

职责: 体重/血压/胎动/血糖/心率/睡眠数据的保存、查询、趋势分析。

DIP 改进: 优先通过 run_context.dependencies 获取仓储实例，
回退到直接 DB 访问以保持向后兼容。
"""
from __future__ import annotations

import asyncio

from agno.run import RunContext
from agno.tools import tool

from ...utils.timezone import beijing_now
from .common import _resolve_pid


def _get_patient_repo(run_context: RunContext | None):
    """从 RunContext.dependencies 获取 PatientRepository，不存在则返回 None"""
    if run_context and hasattr(run_context, "dependencies") and run_context.dependencies:
        return run_context.dependencies.get("patient_repo")
    return None


# ==================== 健康数据持久化 ====================


def _save_health_data_sync(
    pregnant_id: str,
    weight: float, sbp: float, dbp: float,
    fetal_movement: float, blood_sugar: float,
    heart_rate: float, sleep_hours: float, steps: float,
) -> dict:
    """同步保存健康数据（在线程池中执行） — 直接 DB 回退路径"""
    from ...database import SessionLocal
    from ...models import HealthDataPoint

    metric_map = {
        "weight": ("weight", "kg"), "sbp": ("systolic", "mmHg"),
        "dbp": ("diastolic", "mmHg"), "fetal_movement": ("fetal_movement", "次/小时"),
        "blood_sugar": ("blood_sugar", "mmol/L"), "heart_rate": ("heart_rate", "bpm"),
        "sleep_hours": ("sleep_hours", "小时"), "steps": ("steps", "步"),
    }
    values = {
        "weight": weight, "sbp": sbp, "dbp": dbp,
        "fetal_movement": fetal_movement, "blood_sugar": blood_sugar,
        "heart_rate": heart_rate, "sleep_hours": sleep_hours, "steps": steps,
    }

    saved = []
    db = SessionLocal()
    try:
        for key, value in values.items():
            if value and value > 0:
                code, unit = metric_map[key]
                point = HealthDataPoint(
                    pregnant_id=pregnant_id, metric_code=code,
                    value=float(value), unit=unit, source="AGENT_REPORT",
                )
                db.add(point)
                saved.append(key)
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.warning("健康数据保存失败 pregnant_id=%s metrics=%s", pregnant_id, saved, exc_info=True)
    finally:
        db.close()
    return {"saved_metrics": saved, "count": len(saved)}


@tool
async def agno_save_health_data(
    pregnant_id: str = "", run_context: RunContext | None = None,
    weight: float = 0, sbp: float = 0, dbp: float = 0,
    fetal_movement: float = 0, blood_sugar: float = 0,
    heart_rate: float = 0, sleep_hours: float = 0, steps: float = 0,
) -> dict:
    """保存孕妇健康数据到数据库。只传入有值的参数，0 表示未提供。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    metrics = {}
    for name, val in [("weight", weight), ("sbp", sbp), ("dbp", dbp),
                       ("fetal_movement", fetal_movement), ("blood_sugar", blood_sugar),
                       ("heart_rate", heart_rate), ("sleep_hours", sleep_hours), ("steps", steps)]:
        if val and val > 0:
            metrics[name] = val

    # DIP: 优先使用仓储接口
    repo = _get_patient_repo(run_context)
    if repo is not None:
        saved = await asyncio.to_thread(repo.save_health_metrics, pid, metrics, "CHAT")
        return {"saved_metrics": saved, "count": len(saved)}

    # 回退: 直接 DB 访问
    return await asyncio.to_thread(
        _save_health_data_sync, pid, weight, sbp, dbp,
        fetal_movement, blood_sugar, heart_rate, sleep_hours, steps,
    )


# ==================== 患者上下文查询 ====================


def _get_patient_context_sync(pregnant_id: str) -> dict:
    """同步获取患者上下文 — 直接 DB 回退路径"""
    from ...database import SessionLocal
    from ...services.patient_context_service import get_patient_basic, get_recent_health_data

    db = SessionLocal()
    try:
        basic = get_patient_basic(db, pregnant_id)
        if not basic:
            return {"error": "孕妇不存在"}
        recent = get_recent_health_data(db, pregnant_id, limit=10)
        return {
            "pregnant_id": pregnant_id,
            "display_name": basic["display_name"],
            "nickname": basic["nickname"],
            "gestational_week": basic["gestational_week"],
            "gest_week": basic["gest_week"],
            "risk_tags": basic["risk_tags"],
            "recent_data": [{"metric": d["metric"], "value": d["value"], "unit": d["unit"]} for d in recent],
        }
    finally:
        db.close()


@tool
async def agno_get_patient_context(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """获取孕妇的完整上下文信息：孕周、风险标签、昵称、最近健康数据。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)

    # DIP: 优先使用仓储接口
    repo = _get_patient_repo(run_context)
    if repo is not None:
        basic = await asyncio.to_thread(repo.get_by_id, pid)
        if not basic:
            return {"error": "孕妇不存在"}
        recent = await asyncio.to_thread(repo.get_recent_health_data, pid, 7)
        alerts = await asyncio.to_thread(repo.get_active_alerts, pid)
        return {**basic, "recent_data": recent, "active_alerts": alerts}

    # 回退: 直接 DB 访问
    return await asyncio.to_thread(_get_patient_context_sync, pid)


# ==================== 记忆查询 ====================


@tool
def agno_should_ask_weight(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """检查今天是否需要询问孕妇体重。pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..memory_manager import memory_manager
    return {"pregnant_id": pid, "should_ask": memory_manager.should_ask_weight(pid)}


@tool
def agno_should_ask_bp(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """检查今天是否需要询问孕妇血压。pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..memory_manager import memory_manager
    return {"pregnant_id": pid, "should_ask": memory_manager.should_ask_bp(pid)}


# ==================== 趋势分析 ====================


def _analyze_health_trends_sync(pregnant_id: str) -> dict:
    """同步分析健康趋势 — 直接 DB 回退路径"""
    from datetime import timedelta
    from ...database import SessionLocal
    from ...models import Pregnant, HealthDataPoint
    from ..trend_engine import trend_engine

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        gest_week = (pregnant.gestational_age_days // 7) if pregnant and pregnant.gestational_age_days else 0

        two_weeks_ago = beijing_now() - timedelta(days=14)
        records = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= two_weeks_ago,
        ).order_by(HealthDataPoint.recorded_at).all()

        records_data = [
            {"metric": r.metric_code, "value": r.value, "unit": r.unit, "recorded_at": str(r.recorded_at)}
            for r in records
        ]
        trends = trend_engine.analyze(records_data, gest_week=gest_week)
        return {
            "pregnant_id": pregnant_id, "data_count": len(records_data),
            "trends": [
                {"metric": t.metric, "current_value": t.current_value, "trend": t.trend,
                 "summary": t.summary, "is_normal": t.is_normal}
                for t in trends
            ],
        }
    finally:
        db.close()


@tool
async def agno_analyze_health_trends(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """分析孕妇近14天健康数据趋势，返回各指标的变化趋势和摘要。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    return await asyncio.to_thread(_analyze_health_trends_sync, pid)


# ==================== 心理筛查 ====================

# EPDS 风险等级配置表（OCP: 新增等级只需添加条目）
_EPDS_THRESHOLDS: list[tuple[int, str, str, list[str]]] = [
    (9, "low", "正常范围，心理健康状况良好",
     ["保持良好的生活习惯", "继续定期产检"]),
    (12, "moderate", "轻度抑郁倾向，建议关注",
     ["建议与家人多沟通，寻求支持", "适当增加户外活动和运动", "如症状持续2周以上，建议咨询心理医生"]),
    (15, "high", "中度抑郁风险，建议专业评估",
     ["强烈建议咨询专业心理医生", "告知家人您的感受，获得支持", "保持规律作息，避免独处"]),
    (30, "severe", "重度抑郁风险，需要立即关注",
     ["请立即联系心理医生或前往医院", "拨打心理援助热线：400-161-9995", "不要独处，确保身边有人陪伴"]),
]


@tool
def agno_get_epds_result(total_score: int) -> dict:
    """根据EPDS量表总分返回心理健康筛查结果和建议。分数范围0-30。"""
    for threshold, level, desc, recs in _EPDS_THRESHOLDS:
        if total_score <= threshold:
            return {
                "total_score": total_score,
                "risk_level": level,
                "risk_description": desc,
                "recommendations": recs,
            }
    _, level, desc, recs = _EPDS_THRESHOLDS[-1]
    return {"total_score": total_score, "risk_level": level, "risk_description": desc, "recommendations": recs}
