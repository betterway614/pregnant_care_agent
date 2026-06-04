"""主动健康管家服务 — 扫描孕妇健康数据，生成提醒/预警通知"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    HealthDataPoint,
    MedicalOrder,
    Pregnant,
    ScheduleNode,
    FollowUpRecord,
)
from ..utils.timezone import beijing_now


# ---------------------------------------------------------------------------
# 通知模型
# ---------------------------------------------------------------------------

class ProactiveNotification(BaseModel):
    """主动推送通知"""
    id: str
    type: str
    title: str
    body: str
    icon: str
    priority: int
    action_route: str | None = None
    created_at: str  # ISO 格式字符串


# ---------------------------------------------------------------------------
# 主动监控服务
# ---------------------------------------------------------------------------

class ProactiveMonitorService:
    """主动健康管家 — 定期扫描数据，生成前端通知列表"""

    @staticmethod
    def scan_notifications(
        db: Session,
        pregnant_id: str,
    ) -> list[ProactiveNotification]:
        """扫描孕妇健康数据，返回待推送通知列表（按优先级降序、时间降序，最多10条）"""
        now = beijing_now()
        notifications: list[ProactiveNotification] = []

        # ------------------------------------------------------------------
        # 1. 体重：48h 未记录
        # ------------------------------------------------------------------
        try:
            cutoff_48h = now - timedelta(hours=48)
            has_weight = (
                db.query(HealthDataPoint.id)
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == "weight",
                    HealthDataPoint.recorded_at >= cutoff_48h,
                )
                .first()
            )
            if not has_weight:
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="missed_record",
                    title="体重记录提醒",
                    body="两天没记录体重了，记一下吧",
                    icon="ScaleToOriginal",
                    priority=1,
                    action_route="/pregnant/tools/health-record",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 2. 血压：48h 未记录
        # ------------------------------------------------------------------
        try:
            cutoff_48h = now - timedelta(hours=48)
            has_bp = (
                db.query(HealthDataPoint.id)
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == "systolic",
                    HealthDataPoint.recorded_at >= cutoff_48h,
                )
                .first()
            )
            if not has_bp:
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="missed_record",
                    title="血压记录提醒",
                    body="两天没记录血压了，记一下吧",
                    icon="ColdDrink",
                    priority=1,
                    action_route="/pregnant/tools/health-record",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 3. 胎动：孕28周后，24h 未记录
        # ------------------------------------------------------------------
        try:
            pregnant = db.query(Pregnant).filter(
                Pregnant.pregnant_id == pregnant_id,
            ).first()
            if pregnant and (pregnant.gestational_age_days or 0) >= 28 * 7:
                cutoff_24h = now - timedelta(hours=24)
                has_fetal = (
                    db.query(HealthDataPoint.id)
                    .filter(
                        HealthDataPoint.pregnant_id == pregnant_id,
                        HealthDataPoint.metric_code == "fetal_movement",
                        HealthDataPoint.recorded_at >= cutoff_24h,
                    )
                    .first()
                )
                if not has_fetal:
                    notifications.append(ProactiveNotification(
                        id=str(uuid4()),
                        type="missed_record",
                        title="胎动记录提醒",
                        body="今天还没记录胎动，记得数一下哦",
                        icon="Opportunity",
                        priority=1,
                        action_route="/pregnant/tools/fetal-movement",
                        created_at=now.isoformat(),
                    ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 4. 血压异常：近7天平均收缩压>135 或舒张压>85
        # ------------------------------------------------------------------
        try:
            cutoff_7d = now - timedelta(days=7)
            avg_systolic = (
                db.query(func.avg(HealthDataPoint.value))
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == "systolic",
                    HealthDataPoint.recorded_at >= cutoff_7d,
                )
                .scalar()
            )
            avg_diastolic = (
                db.query(func.avg(HealthDataPoint.value))
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == "diastolic",
                    HealthDataPoint.recorded_at >= cutoff_7d,
                )
                .scalar()
            )
            if (avg_systolic is not None and avg_systolic > 135) or \
               (avg_diastolic is not None and avg_diastolic > 85):
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="health_alert",
                    title="血压偏高提醒",
                    body="近7天血压平均值偏高，请注意监测",
                    icon="Warning",
                    priority=2,
                    action_route="/pregnant/tools/health-record",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 5. 产检排期：未来7天内有待完成的检查项
        # ------------------------------------------------------------------
        try:
            from datetime import date as _date

            today = now.date()
            cutoff_7d_date = today + timedelta(days=7)
            pending_nodes = (
                db.query(ScheduleNode)
                .filter(
                    ScheduleNode.pregnant_id == pregnant_id,
                    ScheduleNode.status != "completed",
                    ScheduleNode.scheduled_date >= today,
                    ScheduleNode.scheduled_date <= cutoff_7d_date,
                )
                .all()
            )
            for node in pending_nodes:
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="schedule_reminder",
                    title="产检提醒",
                    body=f"近期有产检安排：{node.item}（{node.scheduled_date}）",
                    icon="Calendar",
                    priority=1,
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 6. 随访：有进行中的随访记录
        # ------------------------------------------------------------------
        try:
            active_followup = (
                db.query(FollowUpRecord)
                .filter(
                    FollowUpRecord.pregnant_id == pregnant_id,
                    FollowUpRecord.status.in_(["draft", "in_progress"]),
                )
                .first()
            )
            if active_followup:
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="followup_pending",
                    title="随访待完成",
                    body="您有一次随访尚未完成，请及时填写",
                    icon="Document",
                    priority=1,
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 7. 医嘱：已签署但孕妇未确认
        # ------------------------------------------------------------------
        try:
            unacked_order = (
                db.query(MedicalOrder)
                .filter(
                    MedicalOrder.pregnant_id == pregnant_id,
                    MedicalOrder.status == "signed",
                    MedicalOrder.acknowledged_at.is_(None),
                )
                .first()
            )
            if unacked_order:
                notifications.append(ProactiveNotification(
                    id=str(uuid4()),
                    type="order_pending",
                    title="医嘱待确认",
                    body="有新的医嘱需要您确认阅读",
                    icon="DocumentChecked",
                    priority=1,
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 排序：优先级降序 → 创建时间降序，限制10条
        # ------------------------------------------------------------------
        notifications.sort(key=lambda n: (n.priority, n.created_at), reverse=True)
        return notifications[:10]
