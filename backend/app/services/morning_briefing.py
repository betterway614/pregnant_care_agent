"""每日晨报服务 — 汇总当日高危患者、待办随访及 AI 推荐"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Alert, FollowUpRecord, Pregnant
from ..utils.timezone import beijing_now


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class BriefingPatient(BaseModel):
    """晨报中的患者摘要"""
    pregnant_id: str
    display_name: str
    gest_week: int
    risk_level: str  # RED / ORANGE / YELLOW
    alert_count: int
    latest_alert_message: Optional[str] = None


class MorningBriefing(BaseModel):
    """每日晨报数据"""
    date: date
    total_patients: int
    red_patients: List[BriefingPatient] = Field(default_factory=list)
    orange_patients: List[BriefingPatient] = Field(default_factory=list)
    yellow_patients: List[BriefingPatient] = Field(default_factory=list)
    today_followups: int = 0
    pending_reviews: int = 0
    ai_recommendations: List[str] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

# 预警等级优先级：RED > ORANGE > YELLOW
_LEVEL_PRIORITY: dict[str, int] = {"RED": 3, "ORANGE": 2, "YELLOW": 1}


class MorningBriefingService:
    """智能每日晨报服务"""

    @staticmethod
    def generate(db: Session) -> MorningBriefing:
        """生成每日晨报

        1. 查询所有孕妇
        2. 对每位孕妇检查 PENDING 预警，按最高等级分类
        3. 统计今日随访数 & 待审核数
        4. 生成 AI 推荐列表和摘要文本
        """
        today = beijing_now().date()
        now = beijing_now()

        # ------------------------------------------------------------------
        # 1. 查询所有孕妇
        # ------------------------------------------------------------------
        all_patients: list[Pregnant] = db.query(Pregnant).all()
        total_patients = len(all_patients)

        # ------------------------------------------------------------------
        # 2. 批量拉取所有 PENDING + ESCALATED 预警，按 pregnant_id 分组
        #    （与 dashboard stats 的 pending_alerts 口径一致）
        # ------------------------------------------------------------------
        pending_alerts: list[Alert] = (
            db.query(Alert).filter(Alert.status.in_(["PENDING", "ESCALATED"])).all()
        )
        alerts_by_patient: dict[str, list[Alert]] = {}
        for alert in pending_alerts:
            alerts_by_patient.setdefault(alert.pregnant_id, []).append(alert)

        # ------------------------------------------------------------------
        # 3. 为每位孕妇分类
        # ------------------------------------------------------------------
        red_patients: list[BriefingPatient] = []
        orange_patients: list[BriefingPatient] = []
        yellow_patients: list[BriefingPatient] = []

        for patient in all_patients:
            patient_alerts = alerts_by_patient.get(patient.pregnant_id, [])
            if not patient_alerts:
                continue

            # 取最高等级
            highest_level = max(
                patient_alerts,
                key=lambda a: _LEVEL_PRIORITY.get(a.level, 0),
            )
            risk_level = highest_level.level  # RED / ORANGE / YELLOW
            latest_alert = max(patient_alerts, key=lambda a: a.created_at)

            from .patient_context_service import compute_gestational_days
            gd = compute_gestational_days(patient)
            gest_week = gd // 7 if gd else 0

            bp = BriefingPatient(
                pregnant_id=patient.pregnant_id,
                display_name=patient.display_name,
                gest_week=gest_week,
                risk_level=risk_level,
                alert_count=len(patient_alerts),
                latest_alert_message=latest_alert.message,
            )

            if risk_level == "RED":
                red_patients.append(bp)
            elif risk_level == "ORANGE":
                orange_patients.append(bp)
            else:
                yellow_patients.append(bp)

        # 各组内按预警数量降序排列
        red_patients.sort(key=lambda p: p.alert_count, reverse=True)
        orange_patients.sort(key=lambda p: p.alert_count, reverse=True)
        yellow_patients.sort(key=lambda p: p.alert_count, reverse=True)

        # ------------------------------------------------------------------
        # 4. 今日随访数
        # ------------------------------------------------------------------
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today + timedelta(days=1), datetime.min.time())

        today_followups: int = (
            db.query(func.count(FollowUpRecord.id))
            .filter(
                FollowUpRecord.follow_up_date >= today_start,
                FollowUpRecord.follow_up_date < today_end,
            )
            .scalar()
            or 0
        )

        # ------------------------------------------------------------------
        # 5. 待审核随访数 (status = completed, 尚未 confirmed)
        # ------------------------------------------------------------------
        pending_reviews: int = (
            db.query(func.count(FollowUpRecord.id))
            .filter(FollowUpRecord.status == "completed")
            .scalar()
            or 0
        )

        # ------------------------------------------------------------------
        # 6. AI 推荐列表
        # ------------------------------------------------------------------
        recommendations = MorningBriefingService._build_recommendations(
            red_patients=red_patients,
            orange_patients=orange_patients,
            yellow_patients=yellow_patients,
            today_followups=today_followups,
            pending_reviews=pending_reviews,
            total_patients=total_patients,
        )

        # ------------------------------------------------------------------
        # 7. 摘要文本
        # ------------------------------------------------------------------
        summary = MorningBriefingService._build_summary(
            today=today,
            total_patients=total_patients,
            red_count=len(red_patients),
            orange_count=len(orange_patients),
            yellow_count=len(yellow_patients),
            today_followups=today_followups,
            pending_reviews=pending_reviews,
        )

        return MorningBriefing(
            date=today,
            total_patients=total_patients,
            red_patients=red_patients,
            orange_patients=orange_patients,
            yellow_patients=yellow_patients,
            today_followups=today_followups,
            pending_reviews=pending_reviews,
            ai_recommendations=recommendations,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_recommendations(
        *,
        red_patients: list[BriefingPatient],
        orange_patients: list[BriefingPatient],
        yellow_patients: list[BriefingPatient],
        today_followups: int,
        pending_reviews: int,
        total_patients: int,
    ) -> list[str]:
        """根据当前数据动态生成 AI 推荐 — 聚焦具体患者和可执行动作"""
        recs: list[str] = []

        # 红色预警：逐人给出具体建议
        for p in red_patients:
            alert_msg = p.latest_alert_message or "预警"
            # 截断过长的预警消息
            if len(alert_msg) > 40:
                alert_msg = alert_msg[:40] + "..."
            recs.append(
                f"{p.display_name}（孕{p.gest_week}周）：{alert_msg}，建议优先安排面诊或电话随访。"
            )

        # 如果有多个红色预警，追加批量处理建议
        if len(red_patients) >= 3:
            recs.append(
                "红色预警患者较多，建议组织科室晨会集中讨论高危病例。"
            )

        # 待审核记录堆积时提醒（不在 stat cards 中重复简单计数）
        if pending_reviews >= 5:
            recs.append(
                f"待审核随访记录积压 {pending_reviews} 份，建议集中处理避免超时。"
            )

        # 橙色患者：只在无红色患者时给出概括性建议
        if not red_patients and orange_patients:
            names = "、".join(p.display_name for p in orange_patients[:3])
            suffix = "等" if len(orange_patients) > 3 else ""
            recs.append(
                f"橙色关注患者：{names}{suffix}，建议上午完成评估。"
            )

        # 无任何预警
        if not red_patients and not orange_patients and not yellow_patients:
            recs.append("今日无高危预警，可安排常规随访和档案整理工作。")

        return recs

    @staticmethod
    def _build_summary(
        *,
        today: date,
        total_patients: int,
        red_count: int,
        orange_count: int,
        yellow_count: int,
        today_followups: int,
        pending_reviews: int,
    ) -> str:
        """生成叙事性摘要 — 聚焦高危患者，避免与 stat cards 重复计数"""
        if red_count > 0:
            if red_count == 1:
                return (
                    f"早，今日有 1 名红色预警患者需重点关注，"
                    f"建议优先安排面诊或电话随访。"
                )
            return (
                f"早，今日有 {red_count} 名红色预警患者需重点关注，"
                f"建议优先安排面诊或电话随访。"
            )

        if orange_count > 0:
            return (
                f"早，今日无红色预警，有 {orange_count} 名橙色关注患者，"
                f"可按计划开展常规随访。"
            )

        if yellow_count > 0:
            return (
                f"早，今日无高危预警，有 {yellow_count} 名黄色提醒患者，"
                f"可在随访时一并关注。"
            )

        return "早，今日无待处理预警，可安排常规随访和档案整理。"
