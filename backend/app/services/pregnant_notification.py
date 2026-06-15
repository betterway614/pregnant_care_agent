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

        # ---- 1a. 预警通知：仅保留基本生命体征(vital)域预警，过滤高危预警 ----
        # FGR、抑郁等高危预警不应在孕妇端显示，避免引起焦虑
        # 体重、血压等基本指标以温馨提示的口吻呈现
        _PREGNANT_VISIBLE_DOMAINS = {"vital"}  # 仅显示生命体征域
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status.in_(["PENDING", "CONFIRMED"]),
                    Alert.trigger_source != "FGR_ALGORITHM",
                )
                .all()
            )
            for alert in alerts:
                details = alert.details or {}
                # 过滤非生命体征域的高危预警（fetal/mental域不展示给孕妇）
                alert_domain = details.get("domain", "vital")
                if alert_domain not in _PREGNANT_VISIBLE_DOMAINS:
                    continue
                is_read = bool(details.get("pregnant_read", False))
                if unread_only and is_read:
                    continue

                level = (alert.level or "YELLOW").upper()
                # 孕妇端不显示RED级别（即使是vital域的RED也应转给医生处理）
                if level == "RED":
                    continue
                notifications.append(PregnantNotification(
                    id=str(alert.id),
                    type="alert",
                    title=self._alert_title(level),
                    body=self._gentle_body(alert.message or "", level),
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
                    Alert.trigger_source != "FGR_ALGORITHM",
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

        # 预警未读（与 get_notifications 过滤逻辑一致：仅 vital 域、排除 RED）
        _PREGNANT_VISIBLE_DOMAINS = {"vital"}
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status.in_(["PENDING", "CONFIRMED"]),
                    Alert.trigger_source != "FGR_ALGORITHM",
                )
                .all()
            )
            for alert in alerts:
                details = alert.details or {}
                # 过滤非 vital 域和 RED 级别
                alert_domain = details.get("domain", "vital")
                if alert_domain not in _PREGNANT_VISIBLE_DOMAINS:
                    continue
                level = (alert.level or "YELLOW").upper()
                if level == "RED":
                    continue
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
    # 内部辅助 — 将临床预警消息温和化，绝不增加孕妇焦虑
    # ------------------------------------------------------------------

    # 规则消息 → 孕妇端温和措辞映射表
    # 原则：不用"预警""警告""异常""危险""诊断"等字样，统一用关怀+建议的口吻
    _GENTLE_MESSAGE_MAP: dict[str, str] = {
        # 血压
        "血压异常升高（≥140/90mmHg）":
            "近期血压值稍高，建议保持低盐饮食、适当休息，如有不适随时联系您的护士哦～",
        "血压偏高（≥135/85mmHg），需要关注":
            "血压比平时略高一些，不用太担心，注意休息和清淡饮食，护士会帮您持续关注哒～",
        "血压偏低，需关注":
            "血压有点偏低呢，记得多喝水、起身时动作慢一点，有不舒服随时说哦～",
        "孕晚期血压偏高（≥130mmHg），需加强监测":
            "进入孕晚期啦，血压有小幅波动是常见的，注意少盐多休息，护士会帮您密切留意的～",
        # 血糖
        "餐后血糖偏高（>7.0mmol/L），建议调整饮食并复查":
            "餐后血糖比参考值稍高一点点，可以试试少食多餐、减少甜食，下次产检时让医生帮您看看就好～",
        "空腹血糖偏高（≥5.1mmol/L），符合GDM诊断标准，建议复查":
            "空腹血糖比参考范围略高，这在孕期比较常见，不用紧张。建议近期饮食上注意少糖，并在下次产检时复查确认一下，医生会给您最合适的建议～",
        # 体重
        "体重周增长偏快（>2kg/周），建议咨询营养师":
            "最近体重增长稍微快了些，可以适当增加散步时间、注意均衡饮食，营养师也可以为您提供个性化建议～",
        "体重增长过慢，需关注营养摄入":
            "体重增长偏慢呢，试着少食多餐、增加优质蛋白的摄入，有好胃口的时候多吃一点喜欢的健康食物～",
        # 胎动 (胎动类通常不在孕妇端显示，但保留映射以防将来调整)
        "胎动显著减少（低于平均50%）":
            "请关注宝宝的胎动情况，如果感觉比平时少了很多，建议联系医生确认一下，安全第一哦～",
        "胎动极少（<3次/小时），请立即就医":
            "宝宝今天的胎动比较少，为了安全起见，建议您尽快联系产检医生确认情况～",
        # 情绪
        "近7日情绪评分持续极低（平均≤1.0分），需立即心理干预":
            "最近心情可能比较低落，孕期情绪起伏是正常的。如果愿意的话，可以和身边人多聊聊天，也可以随时找我倾诉，护士和医生也一直关心着您～",
        "近7日情绪评分持续偏低（平均≤1.5分），建议心理干预":
            "最近的睡眠时间偏少呢，孕期休息很重要。试着睡前泡个温水澡、减少看手机的时间，好好照顾自己哦～",
        "睡眠严重不足（<4小时），建议改善睡眠":
            "最近的睡眠时间偏少呢，孕期休息很重要。试着睡前泡个温水澡、减少看手机的时间，好好照顾自己哦～",
    }

    @staticmethod
    def _alert_title(level: str) -> str:
        """孕妇端统一使用温馨提示语气，不用'预警''警告'等字样"""
        return "温馨提示"

    @staticmethod
    def _gentle_body(message: str, level: str) -> str:
        """将临床预警消息转换为孕妇端的温和关怀口吻。

        优先使用预定义的温和措辞映射表；未匹配的消息做通用温和处理。
        绝不包含'预警''警告''异常''危险''诊断'等增加焦虑的词汇。
        """
        # 1. 精确匹配预定义温和措辞
        if message in PregnantNotificationService._GENTLE_MESSAGE_MAP:
            return PregnantNotificationService._GENTLE_MESSAGE_MAP[message]

        # 2. 模糊匹配：对未在映射表中的消息，移除预警性前缀并温和化
        gentle = message
        # 去掉可能的预警前缀
        for prefix in ["重要预警：", "预警：", "警告：", "注意："]:
            if gentle.startswith(prefix):
                gentle = gentle[len(prefix):]

        # 3. 根据级别追加温和建议
        if level == "ORANGE":
            return f"{gentle}。建议您多加关注，有需要随时联系护士或医生哦～"
        elif level == "YELLOW":
            return f"{gentle}。请注意日常监测，保持好心情～"
        return f"{gentle}。有任何疑问都可以随时问我哦～"

    @staticmethod
    def _alert_icon(level: str) -> str:
        """孕妇端统一使用友好图标（太阳/花朵），不用警告图标"""
        return "info"


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------
pregnant_notification_service = PregnantNotificationService()
