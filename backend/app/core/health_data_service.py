"""健康数据统一入库服务

所有健康数据入库统一走此服务，确保：
1. 数据格式统一
2. 来源标识统一
3. 每日摘要同步更新
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from ..utils.timezone import beijing_now
from enum import Enum

from ..database import SessionLocal
from ..models import HealthDataPoint, DailyHealthSummary

logger = logging.getLogger(__name__)


class HealthDataSource(str, Enum):
    """健康数据来源枚举"""
    PATIENT_DIRECT = "PATIENT_DIRECT"    # 孕妇端直接录入
    PATIENT_CHAT = "PATIENT_CHAT"        # 对话中NLU识别
    FOLLOWUP = "FOLLOWUP"                # 随访中录入
    NURSE_INPUT = "NURSE_INPUT"          # 护士端录入
    DOCTOR_INPUT = "DOCTOR_INPUT"        # 医生端录入
    AGENT_REPORT = "AGENT_REPORT"        # Agent工具调用
    SEED_DATA = "SEED_DATA"              # 种子数据


# 指标映射: key -> (metric_code, unit)
METRIC_MAP = {
    "weight": ("weight", "kg"),
    "systolic": ("systolic", "mmHg"),
    "sbp": ("systolic", "mmHg"),
    "diastolic": ("diastolic", "mmHg"),
    "dbp": ("diastolic", "mmHg"),
    "fetal_movement": ("fetal_movement", "次/小时"),
    "blood_sugar": ("blood_sugar", "mmol/L"),
    "blood_sugar_fasting": ("blood_sugar_fasting", "mmol/L"),
    "blood_sugar_postprandial": ("blood_sugar_postprandial", "mmol/L"),
    "heart_rate": ("heart_rate", "bpm"),
    "sleep_hours": ("sleep_hours", "小时"),
    "steps": ("steps", "步"),
    "emotion_score": ("emotion_score", "分"),
}

# 每日摘要字段映射: metric_code -> summary_field
SUMMARY_FIELD_MAP = {
    "weight": "weight",
    "systolic": "systolic",
    "diastolic": "diastolic",
    "fetal_movement": "fetal_movement_avg",
    "blood_sugar_fasting": "blood_sugar_fasting",
    "blood_sugar_postprandial": "blood_sugar_postprandial",
    "emotion_score": "mood_score",
}


def save_health_metrics(
    pregnant_id: str,
    metrics: dict,
    source: HealthDataSource = HealthDataSource.PATIENT_DIRECT,
    recorded_at: Optional[datetime] = None,
) -> list[str]:
    """统一健康数据入库函数

    Args:
        pregnant_id: 孕妇ID
        metrics: 指标数据，格式如 {"weight": 65, "systolic": 120, "mood": "good"}
        source: 数据来源
        recorded_at: 记录时间，默认当前时间

    Returns:
        保存成功的指标列表
    """
    if not metrics:
        return []

    db = SessionLocal()
    saved = []
    now = recorded_at or beijing_now()

    try:
        for key, value in metrics.items():
            if value is None:
                continue

            # 处理情绪特殊字段
            if key == "mood" and isinstance(value, str):
                mood_score = {"good": 3, "neutral": 2, "bad": 1}.get(value)
                if mood_score is not None:
                    _insert_health_point(
                        db, pregnant_id, "emotion_score", float(mood_score),
                        "分", source.value, now
                    )
                    saved.append("mood")
                continue

            # 处理血压特殊字段（同时保存收缩压和舒张压）
            if key == "bp" and isinstance(value, dict):
                if "sbp" in value:
                    _insert_health_point(
                        db, pregnant_id, "systolic", float(value["sbp"]),
                        "mmHg", source.value, now
                    )
                    saved.append("systolic")
                if "dbp" in value:
                    _insert_health_point(
                        db, pregnant_id, "diastolic", float(value["dbp"]),
                        "mmHg", source.value, now
                    )
                    saved.append("diastolic")
                continue

            # 通用指标处理
            if key in METRIC_MAP:
                metric_code, unit = METRIC_MAP[key]
                try:
                    float_value = float(value)
                    if float_value > 0:
                        _insert_health_point(
                            db, pregnant_id, metric_code, float_value,
                            unit, source.value, now
                        )
                        saved.append(key)
                except (ValueError, TypeError):
                    logger.warning("无法转换指标值: key=%s, value=%s", key, value)

        db.commit()

        # 同步更新每日摘要
        if saved:
            _update_daily_summary(db, pregnant_id, saved, now)

        return saved
    except Exception:
        db.rollback()
        logger.warning("健康数据保存失败 pregnant_id=%s metrics=%s", pregnant_id, saved, exc_info=True)
        return []
    finally:
        db.close()


def _insert_health_point(
    db, pregnant_id: str, metric_code: str, value: float,
    unit: str, source: str, recorded_at: datetime
):
    """插入一条健康数据点"""
    point = HealthDataPoint(
        pregnant_id=pregnant_id,
        metric_code=metric_code,
        value=value,
        unit=unit,
        source=source,
        recorded_at=recorded_at,
    )
    db.add(point)


def _update_daily_summary(db, pregnant_id: str, saved_metrics: list[str], recorded_at: datetime):
    """更新每日健康摘要"""
    today = recorded_at.date()

    # 查询或创建今日摘要
    summary = db.query(DailyHealthSummary).filter(
        DailyHealthSummary.pregnant_id == pregnant_id,
        DailyHealthSummary.date == today,
    ).first()

    if not summary:
        summary = DailyHealthSummary(
            pregnant_id=pregnant_id,
            date=today,
        )
        db.add(summary)

    # 更新对应字段
    for metric_key in saved_metrics:
        if metric_key in SUMMARY_FIELD_MAP:
            field_name = SUMMARY_FIELD_MAP[metric_key]
            # 从 HealthDataPoint 查询今日最新值
            metric_code = METRIC_MAP.get(metric_key, (metric_key,))[0]
            latest = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == pregnant_id,
                HealthDataPoint.metric_code == metric_code,
                HealthDataPoint.recorded_at >= datetime.combine(today, datetime.min.time()),
            ).order_by(HealthDataPoint.recorded_at.desc()).first()

            if latest:
                setattr(summary, field_name, latest.value)

    summary.data_source = saved_metrics[0] if saved_metrics else None
    summary.updated_at = recorded_at


async def save_health_metrics_async(
    pregnant_id: str,
    metrics: dict,
    source: HealthDataSource = HealthDataSource.PATIENT_DIRECT,
    recorded_at: Optional[datetime] = None,
) -> list[str]:
    """异步版本的健康数据入库"""
    import asyncio
    return await asyncio.to_thread(
        save_health_metrics, pregnant_id, metrics, source, recorded_at
    )
