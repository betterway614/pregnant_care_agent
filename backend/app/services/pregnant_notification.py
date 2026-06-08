"""孕妇通知服务 — 聚合预警、随访、医嘱为统一通知流

将 Alert (PENDING/CONFIRMED)、FollowUpRecord (待处理)、MedicalOrder (待确认)
统一转换为用户友好的通知列表，按级别优先级排序，限制最多 20 条。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from ..models import Alert, FollowUpRecord, MedicalOrder
from ..utils.timezone import beijing_now


# ---------------------------------------------------------------------------
# 通知级别优先级（数值越小越优先）
# ---------------------------------------------------------------------------
_LEVEL_PRIORITY: dict[str, int] = {
    "RED": 0,
    "ORANGE": 1,
    "YELLOW": 2,
}


# ---------------------------------------------------------------------------
# Pydantic 通知模型
# ---------------------------------------------------------------------------
class PregnantNotification(BaseModel):
    """单条通知"""
    id: str
    type: str           # alert / followup / order
    title: str
    body: str
    icon: str           # 前端图标标识
    level: str          # RED / ORANGE / YELLOW / INFO
    is_read: bool
    action_route: Optional[str] = None   # 前端跳转路由
    created_at: datetime


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------
class PregnantNotificationService:
    """聚合多数据源为孕妇端统一通知列表"""

    # ------------------------------------------------------------------
    # 1. 获取通知列表
    # ------------------------------------------------------------------
    def get_notifications(
        self,
        db: Session,
        pregnant_id: str,
        unread_only: bool = False,
    ) -> list[PregnantNotification]:
        """查询并合并预警、随访、医嘱通知，按级别优先级 + 时间倒序排列，限 20 条。

        Args:
            db:          SQLAlchemy Session
            pregnant_id: 孕妇 ID
            unread_only: 仅返回未读通知

        Returns:
            最多 20 条 PregnantNotification
        """
        now = beijing_now()
        notifications: list[PregnantNotification] = []

        # ---- 1a. 预警通知 (PENDING / CONFIRMED) ----
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status.in_(["PENDING", "CONFIRMED"]),
                )
                .all()
            )
            for alert in alerts:
                details = alert.details or {}
                is_read = bool(details.get("pregnant_read", False))
                if unread_only and is_read:
                    continue

                level = (alert.level or "YELLOW").upper()
                notifications.append(PregnantNotification(
                    id=str(alert.id),
                    type="alert",
                    title=self._alert_title(level),
                    body=alert.message or "",
                    icon=self._alert_icon(level),
                    level=level,
                    is_read=is_read,
                    action_route=None,
                    created_at=alert.created_at or now,
                ))
        except Exception as exc:
            logger.error("获取预警通知失败: pregnant_id={}, error={}", pregnant_id, exc)

        # ---- 1b. 随访待处理通知 ----
        try:
            followups = (
                db.query(FollowUpRecord)
                .filter(
                    FollowUpRecord.pregnant_id == pregnant_id,
                    FollowUpRecord.status.in_(["draft", "in_progress"]),
                )
                .all()
            )
            for fu in followups:
                details = fu.self_reported_data or {}
                # 随访记录使用 details 中的 pregnant_read 标记
                is_read = bool((fu.record_snapshot or {}).get("pregnant_read", False))
                if unread_only and is_read:
                    continue

                gest_week = fu.gestational_week or ""
                title = "随访待完成"
                body = f"孕{gest_week}周随访尚未完成，请及时填写。" if gest_week else "您有一条随访记录待完成，请及时填写。"
                notifications.append(PregnantNotification(
                    id=str(fu.id),
                    type="followup",
                    title=title,
                    body=body,
                    icon="clipboard-list",
                    level="INFO",
                    is_read=is_read,
                    action_route=f"/pregnant/tools/followup/{fu.id}",
                    created_at=fu.follow_up_date or fu.created_at or now,
                ))
        except Exception as exc:
            logger.error("获取随访通知失败: pregnant_id={}, error={}", pregnant_id, exc)

        # ---- 1c. 医嘱待确认通知 (已签署但孕妇未确认) ----
        try:
            orders = (
                db.query(MedicalOrder)
                .filter(
                    MedicalOrder.pregnant_id == pregnant_id,
                    MedicalOrder.status == "signed",
                    MedicalOrder.acknowledged_at.is_(None),
                )
                .all()
            )
            for order in orders:
                is_read = False  # acknowledged_at is None 意味着未读
                if unread_only and is_read:
                    continue

                content_preview = (order.content or "")[:60]
                if len(order.content or "") > 60:
                    content_preview += "..."
                notifications.append(PregnantNotification(
                    id=str(order.id),
                    type="order",
                    title="新医嘱待确认",
                    body=content_preview,
                    icon="file-text",
                    level="ORANGE",
                    is_read=is_read,
                    action_route=f"/pregnant/orders/{order.id}",
                    created_at=order.created_at or now,
                ))
        except Exception as exc:
            logger.error("获取医嘱通知失败: pregnant_id={}, error={}", pregnant_id, exc)

        # ---- 排序：级别优先级 > 创建时间倒序 ----
        notifications.sort(
            key=lambda n: (
                _LEVEL_PRIORITY.get(n.level, 99),
                -n.created_at.timestamp(),
            )
        )

        # ---- 限制 20 条 ----
        return notifications[:20]

    # ------------------------------------------------------------------
    # 2. 标记单条已读
    # ------------------------------------------------------------------
    def mark_read(
        self,
        db: Session,
        alert_id: str,
        pregnant_id: str,
    ) -> bool:
        """将指定预警标记为孕妇已读 (details["pregnant_read"] = True)。

        Args:
            db:        SQLAlchemy Session
            alert_id:  预警 ID
            pregnant_id: 孕妇 ID（用于权限校验）

        Returns:
            True 标记成功，False 未找到或无权限
        """
        try:
            alert = (
                db.query(Alert)
                .filter(
                    Alert.id == alert_id,
                    Alert.pregnant_id == pregnant_id,
                )
                .first()
            )
            if not alert:
                logger.warning("mark_read: 未找到预警 alert_id={}, pregnant_id={}", alert_id, pregnant_id)
                return False

            details = dict(alert.details or {})
            details["pregnant_read"] = True
            alert.details = details

            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(alert, "details")
            db.commit()
            logger.info("预警已标记已读: alert_id={}", alert_id)
            return True
        except Exception as exc:
            db.rollback()
            logger.error("mark_read 失败: alert_id={}, error={}", alert_id, exc)
            return False

    # ------------------------------------------------------------------
    # 3. 全部标记已读
    # ------------------------------------------------------------------
    def mark_all_read(
        self,
        db: Session,
        pregnant_id: str,
    ) -> int:
        """将该孕妇所有 PENDING/CONFIRMED 预警标记为已读。

        Args:
            db:          SQLAlchemy Session
            pregnant_id: 孕妇 ID

        Returns:
            实际标记数量
        """
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status.in_(["PENDING", "CONFIRMED"]),
                )
                .all()
            )
            count = 0
            from sqlalchemy.orm.attributes import flag_modified

            for alert in alerts:
                details = dict(alert.details or {})
                if details.get("pregnant_read"):
                    continue
                details["pregnant_read"] = True
                alert.details = details
                flag_modified(alert, "details")
                count += 1

            if count:
                db.commit()
                logger.info("批量标记已读: pregnant_id={}, count={}", pregnant_id, count)
            return count
        except Exception as exc:
            db.rollback()
            logger.error("mark_all_read 失败: pregnant_id={}, error={}", pregnant_id, exc)
            return 0

    # ------------------------------------------------------------------
    # 4. 未读计数
    # ------------------------------------------------------------------
    def get_unread_count(
        self,
        db: Session,
        pregnant_id: str,
    ) -> int:
        """返回该孕妇的未读通知总数（预警 + 随访 + 医嘱）。

        Args:
            db:          SQLAlchemy Session
            pregnant_id: 孕妇 ID

        Returns:
            未读通知数量
        """
        count = 0

        # 预警未读
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status.in_(["PENDING", "CONFIRMED"]),
                )
                .all()
            )
            for alert in alerts:
                details = alert.details or {}
                if not details.get("pregnant_read", False):
                    count += 1
        except Exception as exc:
            logger.error("get_unread_count(预警) 失败: pregnant_id={}, error={}", pregnant_id, exc)

        # 随访未读
        try:
            followups = (
                db.query(FollowUpRecord)
                .filter(
                    FollowUpRecord.pregnant_id == pregnant_id,
                    FollowUpRecord.status.in_(["draft", "in_progress"]),
                )
                .all()
            )
            for fu in followups:
                if not (fu.record_snapshot or {}).get("pregnant_read", False):
                    count += 1
        except Exception as exc:
            logger.error("get_unread_count(随访) 失败: pregnant_id={}, error={}", pregnant_id, exc)

        # 医嘱未读
        try:
            orders = (
                db.query(MedicalOrder)
                .filter(
                    MedicalOrder.pregnant_id == pregnant_id,
                    MedicalOrder.status == "signed",
                    MedicalOrder.acknowledged_at.is_(None),
                )
                .all()
            )
            count += len(orders)
        except Exception as exc:
            logger.error("get_unread_count(医嘱) 失败: pregnant_id={}, error={}", pregnant_id, exc)

        return count

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _alert_title(level: str) -> str:
        """根据预警级别生成通知标题"""
        titles = {
            "RED": "紧急预警",
            "ORANGE": "重要预警",
            "YELLOW": "健康提醒",
        }
        return titles.get(level, "健康提醒")

    @staticmethod
    def _alert_icon(level: str) -> str:
        """根据预警级别返回前端图标标识"""
        icons = {
            "RED": "alert-circle",
            "ORANGE": "alert-triangle",
            "YELLOW": "info",
        }
        return icons.get(level, "info")


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------
pregnant_notification_service = PregnantNotificationService()
