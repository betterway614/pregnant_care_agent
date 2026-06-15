"""主动健康管家服务 — 扫描孕妇健康数据，生成提醒/预警通知

通知栏只放需要用户处理的重要事项：
- 血压异常（健康预警，需要关注）
- 产检排期（未来7天有待完成检查）
- 随访待完成（有待处理的随访记录）
- 医嘱待确认（有待确认的医嘱）

日常记录提醒（体重/血压/胎动）放在「今日待办」区域，不在通知栏显示。
"""
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
        """扫描孕妇健康数据，返回待推送通知列表。

        只包含需要用户处理的重要事项，日常记录提醒由「今日待办」负责。
        按优先级降序、时间降序排列，最多 10 条。
        """
        now = beijing_now()
        notifications: list[ProactiveNotification] = []

        # ------------------------------------------------------------------
        # 1. 血压异常：近7天平均收缩压>135 或舒张压>85
        #    妊娠期高血压诊断标准，7天窗口是临床常用观察周期
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
                    title="血压小贴士",
                    body="近期血压比平时略高，注意低盐饮食和充分休息就好～有需要随时联系护士哦",
                    icon="Sunny",
                    priority=2,  # 高于普通提醒
                    action_route="/pregnant/tools/health-record",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 2. 产检排期：未来7天内有待完成的检查项
        #    提前7天提醒，给孕妇充足时间安排出行
        # ------------------------------------------------------------------
        try:
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
                    action_route="/pregnant/schedule",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 3. 随访：有进行中的随访记录
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
                    action_route=f"/pregnant/tools/followup/{active_followup.id}",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 4. 医嘱：已签署但孕妇未确认
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
                    action_route=f"/pregnant/orders/{unacked_order.id}",
                    created_at=now.isoformat(),
                ))
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 排序：优先级降序 → 创建时间降序，限制10条
        # ------------------------------------------------------------------
        notifications.sort(key=lambda n: (n.priority, n.created_at), reverse=True)
        return notifications[:10]


# ---------------------------------------------------------------------------
# 每日待办状态查询（供前端今日待办区域使用）
# ---------------------------------------------------------------------------

def get_daily_task_status(
    db: Session,
    pregnant_id: str,
) -> dict:
    """查询今日各项健康数据是否已记录，供前端「今日待办」区域展示动态完成状态。

    Returns:
        {
            "weight": true/false,       # 今日是否已记录体重
            "blood_pressure": true/false, # 今日是否已记录血压
            "fetal_movement": true/false, # 今日是否已记录胎动
        }
    """
    now = beijing_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def has_today_record(metric_code: str) -> bool:
        try:
            return db.query(HealthDataPoint.id).filter(
                HealthDataPoint.pregnant_id == pregnant_id,
                HealthDataPoint.metric_code == metric_code,
                HealthDataPoint.recorded_at >= today_start,
            ).first() is not None
        except Exception:
            return False

    return {
        "weight": has_today_record("weight"),
        "blood_pressure": has_today_record("systolic"),
        "fetal_movement": has_today_record("fetal_movement"),
    }
