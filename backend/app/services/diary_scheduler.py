"""孕期日记定时调度服务

每周自动为所有孕妇生成本周日记（如有数据），
持久化到 PregnancyDiaryEntry 表，减少 API 调用时的重复计算。
"""
import asyncio
from datetime import timedelta

from loguru import logger

from ..config import settings
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, DailyHealthSummary, PregnancyDiaryEntry
from ..utils.timezone import beijing_now
from .pregnancy_diary import PregnancyDiaryService, _ALL_METRIC_CODES


def _has_week_data(db, pregnant_id: str, week_start, week_end) -> bool:
    """检查某孕妇某周是否有健康数据"""
    from datetime import datetime
    hdp_count = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code.in_(_ALL_METRIC_CODES),
        HealthDataPoint.recorded_at >= datetime.combine(week_start, datetime.min.time()),
        HealthDataPoint.recorded_at <= datetime.combine(week_end, datetime.max.time()),
    ).count()
    if hdp_count > 0:
        return True
    dhs_count = db.query(DailyHealthSummary).filter(
        DailyHealthSummary.pregnant_id == pregnant_id,
        DailyHealthSummary.date >= week_start,
        DailyHealthSummary.date <= week_end,
    ).count()
    return dhs_count > 0


def _generate_weekly_diaries(db) -> dict:
    """为所有孕妇生成本周日记"""
    svc = PregnancyDiaryService()
    today = beijing_now().date()

    all_pregnant = db.query(Pregnant).all()
    if not all_pregnant:
        logger.info("日记调度: 无孕妇数据，跳过")
        return {"total": 0, "generated": 0, "skipped": 0, "llm": 0, "template": 0}

    generated = 0
    skipped = 0
    llm_count = 0
    template_count = 0

    for p in all_pregnant:
        try:
            week = svc._calc_current_week(p)
            if week < 1:
                skipped += 1
                continue

            week_end = today
            week_start = week_end - timedelta(days=6)

            # 幂等检查：已有记录 → 跳过
            existing = db.query(PregnancyDiaryEntry).filter(
                PregnancyDiaryEntry.pregnant_id == p.pregnant_id,
                PregnancyDiaryEntry.week_number == week,
            ).first()
            if existing:
                skipped += 1
                continue

            # 无数据 → 跳过
            if not _has_week_data(db, p.pregnant_id, week_start, week_end):
                skipped += 1
                continue

            # 生成日记
            entry, source = svc.generate_single_week_sync(
                db, p.pregnant_id, week, week_start, week_end,
            )

            # 持久化
            if entry and svc._has_real_data(entry):
                svc._persist_entry(
                    db, p.pregnant_id, week, week_start, week_end,
                    entry, source,
                )
                generated += 1
                if "llm" in source:
                    llm_count += 1
                else:
                    template_count += 1
                logger.info(
                    "日记已生成: pid={} week={} source={}",
                    p.pregnant_id[:8], week, source,
                )
            else:
                skipped += 1

        except Exception:
            logger.exception("日记生成失败 pregnant_id={}", p.pregnant_id)
            skipped += 1

    if generated:
        db.commit()
    else:
        db.rollback()

    return {
        "total": len(all_pregnant),
        "generated": generated,
        "skipped": skipped,
        "llm": llm_count,
        "template": template_count,
    }


def _weekly_diary_job():
    """定时任务: 每周为所有孕妇生成本周日记"""
    logger.info("日记定时调度开始执行...")
    db = SessionLocal()
    try:
        stats = _generate_weekly_diaries(db)
        logger.info(
            "日记定时调度完成: total={total} generated={generated} "
            "skipped={skipped} llm={llm} template={template}",
            **stats,
        )
    except Exception:
        logger.exception("日记定时调度执行失败")
    finally:
        db.close()


def trigger_diary_now() -> dict:
    """手动触发一次全量日记生成（用于调试/测试/API调用）"""
    db = SessionLocal()
    try:
        return _generate_weekly_diaries(db)
    finally:
        db.close()
