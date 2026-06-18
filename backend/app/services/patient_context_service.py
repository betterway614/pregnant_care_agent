"""患者上下文统一采集服务

收口 chat.py / nurse_ai.py / doctor_ai.py / agno_tools.py 中分散的
孕妇查询逻辑，确保字段口径一致。
"""
from __future__ import annotations

from typing import Optional
from datetime import date
from sqlalchemy import desc
from sqlalchemy.orm import Session


def compute_gestational_days(pregnant) -> int:
    """动态计算孕周天数：优先从 lmp_date 实时推算，兜底使用静态字段

    这是全系统统一的孕周计算入口。lmp_date（末次月经）是唯一真值源，
    gestational_age_days 仅作为 lmp_date 缺失时的兜底。

    Args:
        pregnant: Pregnant ORM 对象（需有 lmp_date 和 gestational_age_days 属性）

    Returns:
        孕周天数（整数）
    """
    if pregnant.lmp_date:
        delta = (date.today() - pregnant.lmp_date).days
        return max(0, delta)  # 不允许负数
    return pregnant.gestational_age_days or 0


def get_patient_basic(db: Session, pregnant_id: str) -> Optional[dict]:
    """获取孕妇基础信息：孕周、风险标签、昵称、显示名

    Returns:
        dict 或 None（不存在时）
    """
    from ..models import Pregnant

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return None

    gest_days = compute_gestational_days(pregnant)
    return {
        "pregnant_id": pregnant_id,
        "display_name": pregnant.display_name,
        "nickname": pregnant.nickname,
        "gestational_age_days": gest_days,
        "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
        "gest_week": gest_days // 7,
        "gest_day": gest_days % 7,
        "risk_tags": pregnant.risk_tags or [],
        "lmp_date": pregnant.lmp_date,
        "edd": pregnant.edd,
    }


def get_recent_health_data(
    db: Session,
    pregnant_id: str,
    limit: int = 10,
    days: Optional[int] = None,
) -> list[dict]:
    """获取最近健康数据

    Args:
        db: 数据库 session
        pregnant_id: 孕妇 ID
        limit: 最多返回条数
        days: 可选，只返回最近 N 天的数据

    Returns:
        健康数据列表，按 recorded_at 降序
    """
    from ..models import HealthDataPoint
    from datetime import timedelta
    from ..utils.timezone import beijing_now

    query = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
    )
    if days is not None:
        cutoff = beijing_now() - timedelta(days=days)
        query = query.filter(HealthDataPoint.recorded_at >= cutoff)

    points = query.order_by(desc(HealthDataPoint.recorded_at)).limit(limit).all()

    return [
        {
            "metric": p.metric_code,
            "value": p.value,
            "unit": p.unit,
            "recorded_at": p.recorded_at.isoformat() if p.recorded_at else "",
            "source": p.source,
        }
        for p in points
    ]


def get_active_alerts(db: Session, pregnant_id: str, limit: int = 5) -> list[dict]:
    """获取活跃预警列表"""
    from ..models import Alert

    alerts = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "PENDING",
    ).order_by(desc(Alert.created_at)).limit(limit).all()

    return [
        {
            "id": str(a.id),
            "level": a.level,
            "message": a.message,
            "source": a.trigger_source,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for a in alerts
    ]
