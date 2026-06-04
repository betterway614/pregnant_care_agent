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
        # 2. 批量拉取所有 PENDING 预警，按 pregnant_id 分组
        # ------------------------------------------------------------------
        pending_alerts: list[Alert] = (
            db.query(Alert).filter(Alert.status == "PENDING").all()
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

            gest_week = (
                patient.gestational_age_days // 7
                if patient.gestational_age_days
                else 0
            )

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
        """根据当前数据动态生成 AI 推荐"""
        recs: list[str] = []

        if red_patients:
            recs.append(
                f"今日有 {len(red_patients)} 名红色预警患者，请优先安排面诊或电话随访。"
            )
            # 如果有多个红色预警，建议批量处理
            if len(red_patients) >= 3:
                recs.append(
                    "红色预警患者较多，建议组织科室晨会讨论高危病例。"
                )

        if orange_patients:
            recs.append(
                f"今日有 {len(orange_patients)} 名橙色预警患者，建议上午完成评估。"
            )

        if yellow_patients:
            recs.append(
                f"今日有 {len(yellow_patients)} 名黄色预警患者，可在随访时一并关注。"
            )

        if pending_reviews > 0:
            recs.append(
                f"有 {pending_reviews} 份随访记录待审核，请及时确认。"
            )

        if today_followups > 0:
            recs.append(
                f"今日计划随访 {today_followups} 人次，请提前准备随访资料。"
            )

        if not red_patients and not orange_patients and not yellow_patients:
            recs.append("今日暂无 PENDING 预警，可利用空闲时间整理历史档案。")

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
        """生成简短摘要"""
        total_alerts = red_count + orange_count + yellow_count
        parts: list[str] = [
            f"{today.isoformat()} 晨报：",
            f"在管孕妇 {total_patients} 人，",
            f"当前 PENDING 预警 {total_alerts} 条"
            f"（红 {red_count} / 橙 {orange_count} / 黄 {yellow_count}），",
            f"今日随访 {today_followups} 人次，",
            f"待审核 {pending_reviews} 份。",
        ]

        if red_count > 0:
            parts.append(f"重点关注 {red_count} 名红色预警患者，建议优先处理。")

        return "".join(parts)
