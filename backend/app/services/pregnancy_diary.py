"""孕记服务 — 以周为单位生成温馨的孕期日记

从 DailyHealthSummary 表中汇总每周健康数据，生成带有情感温度的中文叙事，
帮助准妈妈回顾每一段孕期旅程。
"""
from datetime import datetime, timedelta, date
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from loguru import logger

from ..models import DailyHealthSummary, HealthDataPoint, Pregnant, Alert
from ..utils.timezone import beijing_now


# ---------------------------------------------------------------------------
# Pydantic 数据模型
# ---------------------------------------------------------------------------

class DiaryWeekSummary(BaseModel):
    """一周日记摘要"""
    week: int
    date_range: str
    weight_summary: Optional[str] = None
    bp_summary: Optional[str] = None
    fetal_movement_summary: Optional[str] = None
    mood_summary: Optional[str] = None
    blood_sugar_summary: Optional[str] = None
    heart_rate_summary: Optional[str] = None
    sleep_summary: Optional[str] = None
    steps_summary: Optional[str] = None
    highlights: List[str] = []
    ai_narrative: str = ""
    mood_emoji: str = ""


class DiaryResponse(BaseModel):
    """孕记响应"""
    pregnant_id: str
    current_week: int
    entries: List[DiaryWeekSummary] = []


# ---------------------------------------------------------------------------
# 情绪评分 -> emoji 映射
# ---------------------------------------------------------------------------
_MOOD_EMOJI_MAP = {
    (1.0, 1.5): "😢",
    (1.5, 2.0): "😔",
    (2.0, 2.5): "😊",
    (2.5, 3.0): "😄",
    (3.0, 3.5): "🥰",
}


def _mood_emoji(avg_mood: Optional[float]) -> str:
    """根据平均情绪评分返回对应 emoji"""
    if avg_mood is None:
        return "📝"
    for (lo, hi), emoji in _MOOD_EMOJI_MAP.items():
        if lo <= avg_mood < hi:
            return emoji
    return "😊"


# ---------------------------------------------------------------------------
# 孕记服务
# ---------------------------------------------------------------------------

class PregnancyDiaryService:
    """孕记服务：按周汇总健康数据，生成温暖的孕期叙事"""

    def generate_weekly_diary(
        self,
        db: Session,
        pregnant_id: str,
        weeks: int = 4,
    ) -> DiaryResponse:
        """生成最近 N 周的孕记

        Args:
            db: 数据库会话
            pregnant_id: 孕妇 ID
            weeks: 回溯周数，默认 4 周

        Returns:
            DiaryResponse 包含每周摘要
        """
        logger.info("生成孕记: pregnant_id={}, 回溯 {} 周", pregnant_id, weeks)

        # 获取孕妇信息，用于推算当前孕周
        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()
        if not pregnant:
            logger.warning("孕记生成失败: 孕妇 {} 不存在", pregnant_id)
            return DiaryResponse(pregnant_id=pregnant_id, current_week=0, entries=[])

        current_week = self._calc_current_week(pregnant)
        today = beijing_now().date()

        entries: List[DiaryWeekSummary] = []
        for i in range(weeks):
            week_num = current_week - i
            if week_num < 1:
                break

            # 本周日期范围：周一 ~ 周日（或今天）
            week_end = today - timedelta(days=i * 7)
            week_start = week_end - timedelta(days=6)
            date_range = f"{week_start.strftime('%m月%d日')} ~ {week_end.strftime('%m月%d日')}"

            # 查询该周的 DailyHealthSummary 记录
            summaries = db.query(DailyHealthSummary).filter(
                DailyHealthSummary.pregnant_id == pregnant_id,
                DailyHealthSummary.date >= week_start,
                DailyHealthSummary.date <= week_end,
            ).order_by(DailyHealthSummary.date.asc()).all()

            # 查询该周的 HealthDataPoint（心率/睡眠/步数等 DailyHealthSummary 未涵盖的指标）
            extra_points = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == pregnant_id,
                HealthDataPoint.metric_code.in_(["heart_rate", "sleep_hours", "steps"]),
                HealthDataPoint.recorded_at >= datetime.combine(week_start, datetime.min.time()),
                HealthDataPoint.recorded_at <= datetime.combine(week_end, datetime.max.time()),
            ).order_by(HealthDataPoint.recorded_at.asc()).all()

            # 该周是否有预警
            has_abnormal = db.query(Alert).filter(
                Alert.pregnant_id == pregnant_id,
                Alert.created_at >= datetime.combine(week_start, datetime.min.time()),
                Alert.created_at <= datetime.combine(week_end, datetime.max.time()),
            ).count() > 0

            entry = self._build_week_entry(
                week_num=week_num,
                date_range=date_range,
                summaries=summaries,
                extra_points=extra_points,
                has_abnormal=has_abnormal,
            )
            entries.append(entry)

        logger.info("孕记生成完成: pregnant_id={}, 共 {} 周", pregnant_id, len(entries))
        return DiaryResponse(
            pregnant_id=pregnant_id,
            current_week=current_week,
            entries=entries,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_current_week(pregnant: Pregnant) -> int:
        """根据末次月经或孕周天数推算当前孕周"""
        if pregnant.gestational_age_days:
            return pregnant.gestational_age_days // 7
        if pregnant.lmp_date:
            delta = beijing_now().date() - pregnant.lmp_date
            return delta.days // 7
        return 0

    def _build_week_entry(
        self,
        week_num: int,
        date_range: str,
        summaries: List[DailyHealthSummary],
        extra_points: List[HealthDataPoint],
        has_abnormal: bool,
    ) -> DiaryWeekSummary:
        """汇总一周数据，构建 DiaryWeekSummary"""

        if not summaries and not extra_points:
            return DiaryWeekSummary(
                week=week_num,
                date_range=date_range,
                weight_summary="本周暂无体重记录",
                bp_summary="本周暂无血压记录",
                fetal_movement_summary="本周暂无胎动记录",
                mood_summary="本周暂无情绪记录",
                blood_sugar_summary="本周暂无血糖记录",
                heart_rate_summary="本周暂无心率记录",
                sleep_summary="本周暂无睡眠记录",
                steps_summary="本周暂无步数记录",
                highlights=[],
                ai_narrative=self._generate_narrative(
                    week=week_num,
                    weight_delta=None,
                    avg_bp=None,
                    avg_fetal=None,
                    avg_blood_sugar_fasting=None,
                    avg_heart_rate=None,
                    avg_sleep=None,
                    has_abnormal=has_abnormal,
                ),
                mood_emoji="📝",
            )

        # -- 体重 --
        weights = [s.weight for s in summaries if s.weight is not None]
        weight_summary = None
        weight_delta = None
        if weights:
            avg_w = sum(weights) / len(weights)
            weight_summary = f"平均 {avg_w:.1f} kg，记录 {len(weights)} 次"
            if len(weights) >= 2:
                weight_delta = weights[-1] - weights[0]

        # -- 血压 --
        bp_pairs = [
            (s.systolic, s.diastolic)
            for s in summaries
            if s.systolic is not None and s.diastolic is not None
        ]
        bp_summary = None
        avg_bp = None
        if bp_pairs:
            avg_sys = sum(p[0] for p in bp_pairs) / len(bp_pairs)
            avg_dia = sum(p[1] for p in bp_pairs) / len(bp_pairs)
            avg_bp = (avg_sys, avg_dia)
            bp_summary = f"平均 {avg_sys:.0f}/{avg_dia:.0f} mmHg，记录 {len(bp_pairs)} 次"

        # -- 胎动 --
        fetal_values = [
            s.fetal_movement_avg for s in summaries
            if s.fetal_movement_avg is not None
        ]
        fetal_summary = None
        avg_fetal = None
        if fetal_values:
            avg_fetal = sum(fetal_values) / len(fetal_values)
            fetal_summary = f"平均 {avg_fetal:.1f} 次/小时，记录 {len(fetal_values)} 次"

        # -- 情绪 --
        mood_values = [
            s.mood_score for s in summaries if s.mood_score is not None
        ]
        mood_summary = None
        avg_mood = None
        if mood_values:
            avg_mood = sum(mood_values) / len(mood_values)
            mood_desc = self._mood_text(avg_mood)
            mood_summary = f"本周心情整体{mood_desc}，记录 {len(mood_values)} 次"

        # -- 血糖 --
        bs_fasting_vals = [
            s.blood_sugar_fasting for s in summaries
            if s.blood_sugar_fasting is not None
        ]
        bs_postprandial_vals = [
            s.blood_sugar_postprandial for s in summaries
            if s.blood_sugar_postprandial is not None
        ]
        blood_sugar_summary = None
        avg_blood_sugar_fasting = None
        if bs_fasting_vals or bs_postprandial_vals:
            parts = []
            if bs_fasting_vals:
                avg_blood_sugar_fasting = sum(bs_fasting_vals) / len(bs_fasting_vals)
                parts.append(f"空腹平均 {avg_blood_sugar_fasting:.1f} mmol/L（{len(bs_fasting_vals)}次）")
            if bs_postprandial_vals:
                avg_post = sum(bs_postprandial_vals) / len(bs_postprandial_vals)
                parts.append(f"餐后平均 {avg_post:.1f} mmol/L（{len(bs_postprandial_vals)}次）")
            blood_sugar_summary = "；".join(parts)

        # -- 心率 / 睡眠 / 步数（来自 HealthDataPoint） --
        hr_values = [p.value for p in extra_points if p.metric_code == "heart_rate"]
        sleep_values = [p.value for p in extra_points if p.metric_code == "sleep_hours"]
        steps_values = [p.value for p in extra_points if p.metric_code == "steps"]

        heart_rate_summary = None
        avg_heart_rate = None
        if hr_values:
            avg_heart_rate = sum(hr_values) / len(hr_values)
            heart_rate_summary = f"平均心率 {avg_heart_rate:.0f} bpm，记录 {len(hr_values)} 次"

        sleep_summary = None
        avg_sleep = None
        if sleep_values:
            avg_sleep = sum(sleep_values) / len(sleep_values)
            sleep_summary = f"平均睡眠 {avg_sleep:.1f} 小时，记录 {len(sleep_values)} 次"

        steps_summary = None
        if steps_values:
            avg_steps = sum(steps_values) / len(steps_values)
            steps_summary = f"日均 {avg_steps:.0f} 步，记录 {len(steps_values)} 次"

        # -- 亮点 --
        highlights = self._collect_highlights(
            summaries, weight_delta, avg_bp, avg_fetal, has_abnormal,
            avg_blood_sugar_fasting=avg_blood_sugar_fasting,
            avg_heart_rate=avg_heart_rate,
            avg_sleep=avg_sleep,
        )

        # -- 生成叙事 --
        narrative = self._generate_narrative(
            week=week_num,
            weight_delta=weight_delta,
            avg_bp=avg_bp,
            avg_fetal=avg_fetal,
            avg_blood_sugar_fasting=avg_blood_sugar_fasting,
            avg_heart_rate=avg_heart_rate,
            avg_sleep=avg_sleep,
            has_abnormal=has_abnormal,
        )

        return DiaryWeekSummary(
            week=week_num,
            date_range=date_range,
            weight_summary=weight_summary,
            bp_summary=bp_summary,
            fetal_movement_summary=fetal_summary,
            mood_summary=mood_summary,
            blood_sugar_summary=blood_sugar_summary,
            heart_rate_summary=heart_rate_summary,
            sleep_summary=sleep_summary,
            steps_summary=steps_summary,
            highlights=highlights,
            ai_narrative=narrative,
            mood_emoji=_mood_emoji(avg_mood),
        )

    @staticmethod
    def _mood_text(score: float) -> str:
        """情绪评分转文字描述"""
        if score < 1.5:
            return "有些低落"
        if score < 2.0:
            return "略有波动"
        if score < 2.5:
            return "平稳舒畅"
        if score < 3.0:
            return "愉悦开朗"
        return "非常幸福"

    @staticmethod
    def _collect_highlights(
        summaries: List[DailyHealthSummary],
        weight_delta: Optional[float],
        avg_bp: Optional[tuple],
        avg_fetal: Optional[float],
        has_abnormal: bool,
        avg_blood_sugar_fasting: Optional[float] = None,
        avg_heart_rate: Optional[float] = None,
        avg_sleep: Optional[float] = None,
    ) -> List[str]:
        """收集本周亮点与提醒"""
        highlights: List[str] = []

        record_days = len(summaries)
        if record_days >= 5:
            highlights.append(f"坚持记录了 {record_days} 天，非常棒！")

        if weight_delta is not None:
            if -0.5 <= weight_delta <= 0.5:
                highlights.append("体重变化平稳，继续保持")
            elif weight_delta > 0.5:
                highlights.append("体重有所增长，注意均衡饮食哦")
            else:
                highlights.append("体重略有下降，请关注营养摄入")

        if avg_bp is not None:
            sys, dia = avg_bp
            if 90 <= sys <= 140 and 60 <= dia <= 90:
                highlights.append("血压在正常范围内，真好")
            elif sys > 140 or dia > 90:
                highlights.append("血压偏高，建议及时咨询医生")

        if avg_fetal is not None:
            if avg_fetal >= 3:
                highlights.append("宝宝胎动活跃，发育良好")
            elif avg_fetal >= 1:
                highlights.append("胎动正常，记得坚持数胎动")
            else:
                highlights.append("胎动偏少，请密切关注")

        if avg_blood_sugar_fasting is not None:
            if 3.3 <= avg_blood_sugar_fasting <= 5.1:
                highlights.append("空腹血糖正常，继续保持")
            elif avg_blood_sugar_fasting > 5.1:
                highlights.append("空腹血糖偏高，建议咨询医生调整饮食")
            else:
                highlights.append("空腹血糖偏低，注意及时补充营养")

        if avg_heart_rate is not None:
            if 60 <= avg_heart_rate <= 100:
                highlights.append("心率正常，状态不错")
            elif avg_heart_rate > 100:
                highlights.append("心率偏快，注意休息和情绪调节")

        if avg_sleep is not None:
            if 7 <= avg_sleep <= 9:
                highlights.append("睡眠充足，很好")
            elif avg_sleep < 7:
                highlights.append("睡眠略少，尽量早点休息哦")

        if has_abnormal:
            highlights.append("本周有健康预警，请及时查看并遵医嘱")

        return highlights

    @staticmethod
    def _mood_emoji(avg_mood: Optional[float]) -> str:
        """根据平均情绪评分返回对应 emoji"""
        return _mood_emoji(avg_mood)

    def _generate_narrative(
        self,
        week: int,
        weight_delta: Optional[float],
        avg_bp: Optional[tuple],
        avg_fetal: Optional[float],
        avg_blood_sugar_fasting: Optional[float] = None,
        avg_heart_rate: Optional[float] = None,
        avg_sleep: Optional[float] = None,
        has_abnormal: bool = False,
    ) -> str:
        """生成个性化的温暖中文叙事

        Args:
            week: 孕周
            weight_delta: 本周体重变化（末值-首值），None 表示无数据
            avg_bp: 平均血压 (收缩压, 舒张压)，None 表示无数据
            avg_fetal: 平均胎动次数/小时，None 表示无数据
            avg_blood_sugar_fasting: 平均空腹血糖 mmol/L，None 表示无数据
            avg_heart_rate: 平均心率 bpm，None 表示无数据
            avg_sleep: 平均睡眠时长 小时，None 表示无数据
            has_abnormal: 本周是否有预警

        Returns:
            温馨的中文叙事文本
        """
        # -- 开篇：根据孕周阶段拟定问候语 --
        if week <= 12:
            opening = (
                f"亲爱的准妈妈，这是你怀孕的第 {week} 周。"
                "宝宝正在妈妈肚子里悄悄地发育着，虽然还很小很小，"
                "但已经是个了不起的小生命了。"
            )
        elif week <= 27:
            opening = (
                f"亲爱的准妈妈，转眼到了第 {week} 周。"
                "宝宝一天天长大，也许你已经能感受到ta的胎动了，"
                "每一次轻轻的踢动都是宝宝在和你打招呼呢。"
            )
        elif week <= 36:
            opening = (
                f"亲爱的准妈妈，第 {week} 周啦！"
                "宝宝在妈妈温暖的子宫里越长越大，"
                "你们正在一起为最后的见面做准备呢。"
            )
        else:
            opening = (
                f"亲爱的准妈妈，第 {week} 周！"
                "宝宝随时都可能和你见面了，"
                "记得保持好心情，做好迎接小天使的准备吧。"
            )

        # -- 体重叙述 --
        weight_text = ""
        if weight_delta is not None:
            if -0.3 <= weight_delta <= 0.3:
                weight_text = "这周体重很稳定，说明你的饮食和作息管理得很不错。"
            elif weight_delta > 0.3:
                weight_text = (
                    f"这周体重略有增加（约 {weight_delta:.1f} kg），"
                    "这是孕期的正常变化，记得适当活动、均衡饮食哦。"
                )
            else:
                weight_text = (
                    "这周体重有些下降，别太担心，"
                    "但如果持续下降记得咨询一下医生。"
                )

        # -- 血压叙述 --
        bp_text = ""
        if avg_bp is not None:
            sys, dia = avg_bp
            if 90 <= sys <= 140 and 60 <= dia <= 90:
                bp_text = "血压指标很不错，在正常范围内，继续保持好状态。"
            elif sys > 140 or dia > 90:
                bp_text = (
                    f"血压有些偏高（平均 {sys:.0f}/{dia:.0f} mmHg），"
                    "要注意休息，减少盐分摄入，必要时请遵医嘱。"
                )
            else:
                bp_text = "血压偏低，起身时注意慢一些，避免头晕。"

        # -- 胎动叙述 --
        fetal_text = ""
        if avg_fetal is not None:
            if avg_fetal >= 3:
                fetal_text = (
                    f"胎动很活跃哦（平均每小时 {avg_fetal:.1f} 次），"
                    "宝宝精力充沛，说明ta在肚子里过得很好呢。"
                )
            elif avg_fetal >= 1:
                fetal_text = (
                    f"胎动记录正常（平均每小时 {avg_fetal:.1f} 次），"
                    "坚持每天数胎动是给宝宝最好的守护。"
                )
            else:
                fetal_text = (
                    "胎动偏少，这可能是宝宝在休息，"
                    "但如果持续感觉不到胎动，请及时就医。"
                )

        # -- 血糖叙述 --
        blood_sugar_text = ""
        if avg_blood_sugar_fasting is not None:
            if 3.3 <= avg_blood_sugar_fasting <= 5.1:
                blood_sugar_text = (
                    f"空腹血糖控制得很好（平均 {avg_blood_sugar_fasting:.1f} mmol/L），"
                    "在正常范围内，继续保持这样的饮食习惯吧。"
                )
            elif avg_blood_sugar_fasting > 5.1:
                blood_sugar_text = (
                    f"空腹血糖略偏高（平均 {avg_blood_sugar_fasting:.1f} mmol/L），"
                    "建议减少高糖食物摄入，适当增加散步，并遵医嘱监测。"
                )
            else:
                blood_sugar_text = (
                    f"空腹血糖偏低（平均 {avg_blood_sugar_fasting:.1f} mmol/L），"
                    "注意按时进餐，随身备一些健康零食以防低血糖。"
                )

        # -- 心率叙述 --
        heart_rate_text = ""
        if avg_heart_rate is not None:
            if 60 <= avg_heart_rate <= 100:
                heart_rate_text = (
                    f"心率很平稳（平均 {avg_heart_rate:.0f} bpm），"
                    "说明身体状态不错，继续保持规律作息哦。"
                )
            elif avg_heart_rate > 100:
                heart_rate_text = (
                    f"心率稍快（平均 {avg_heart_rate:.0f} bpm），"
                    "孕期心脏负担增加是正常的，但要注意休息，避免过度劳累。"
                )
            else:
                heart_rate_text = (
                    f"心率偏低（平均 {avg_heart_rate:.0f} bpm），"
                    "如果没有不适可以不必担心，但建议下次产检时告知医生。"
                )

        # -- 睡眠叙述 --
        sleep_text = ""
        if avg_sleep is not None:
            if 7 <= avg_sleep <= 9:
                sleep_text = (
                    f"睡眠很充足呢（平均每晚 {avg_sleep:.1f} 小时），"
                    "好的睡眠是宝宝健康发育的重要保障。"
                )
            elif avg_sleep < 7:
                sleep_text = (
                    f"睡眠时间略少（平均每晚 {avg_sleep:.1f} 小时），"
                    "孕期容易疲劳，尽量早点休息，午间也可以小憩一会儿。"
                )
            else:
                sleep_text = (
                    f"睡眠时间较多（平均每晚 {avg_sleep:.1f} 小时），"
                    "充足的休息对身体很好，但白天也可以适当活动活动哦。"
                )

        # -- 异常提醒 --
        abnormal_text = ""
        if has_abnormal:
            abnormal_text = (
                "这周收到了一些健康预警提醒，别紧张，"
                "这说明我们的监测系统在认真守护你和宝宝的健康，"
                "建议及时查看并遵从医生的建议。"
            )

        # -- 组合叙事 --
        parts = [opening]
        if weight_text:
            parts.append(weight_text)
        if bp_text:
            parts.append(bp_text)
        if fetal_text:
            parts.append(fetal_text)
        if blood_sugar_text:
            parts.append(blood_sugar_text)
        if heart_rate_text:
            parts.append(heart_rate_text)
        if sleep_text:
            parts.append(sleep_text)
        if abnormal_text:
            parts.append(abnormal_text)

        # 如果所有数据都为空，给一段安慰的话
        if not (weight_text or bp_text or fetal_text or blood_sugar_text
                or heart_rate_text or sleep_text or abnormal_text):
            parts.append(
                "这周的健康记录还不太完整，"
                "记得每天花几分钟记录一下身体状况，"
                "让我们一起陪你度过每一个珍贵的日子。"
            )

        parts.append(
            "每一周都是一段新的旅程，你和宝宝都在一起成长。加油！"
        )

        return "".join(parts)


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------
pregnancy_diary_service = PregnancyDiaryService()
