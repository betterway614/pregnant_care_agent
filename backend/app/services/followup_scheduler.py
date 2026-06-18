"""随访自动调度服务

每日定时扫描，仅执行僵尸随访清理（长期 draft/in_progress 未处理的记录）。
随访草稿不再自动生成 —— 必须由护士通过 AI 推荐面板手动触发。
"""
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Pregnant, FollowUpRecord, HealthDataPoint, Alert
from ..utils.timezone import beijing_now


def _archive_zombie_followup(db: Session, record: FollowUpRecord) -> bool:
    """归档僵尸随访记录。返回 True 表示已归档。"""
    try:
        record.status = "archived"
        record.review_comment = (
            f"[系统自动归档] {record.status} 状态超过超时时间，自动关闭。"
            f"原创建时间: {record.created_at}"
        )
        logger.info(
            "归档僵尸随访 id={} pregnant_id={} old_status={} age_days={}",
            record.id,
            record.pregnant_id,
            record.status,
            (beijing_now().date() - record.created_at.date()).days if record.created_at else 0,
        )
        return True
    except Exception:
        logger.exception("归档僵尸随访失败 id={}", record.id)
        return False


def _cleanup_zombie_followups(db: Session) -> int:
    """清理所有超时的僵尸随访记录。返回清理数量。"""
    now = beijing_now()
    draft_timeout = now - timedelta(days=settings.followup_zombie_draft_timeout_days)
    inprogress_timeout = now - timedelta(days=settings.followup_zombie_inprogress_timeout_days)

    # 用 OR 条件在一条查询中同时捕获 draft 和 in_progress 僵尸
    zombies = db.query(FollowUpRecord).filter(
        FollowUpRecord.status.in_(["draft", "in_progress"]),
        (FollowUpRecord.created_at < draft_timeout)
        | (
            (FollowUpRecord.status == "in_progress")
            & (FollowUpRecord.created_at < inprogress_timeout)
        ),
    ).all()

    cleaned = 0
    for record in zombies:
        if _archive_zombie_followup(db, record):
            cleaned += 1

    if cleaned:
        db.commit()  # 必须 commit，否则归档变更不会持久化
        logger.info("僵尸随访清理完成: 共归档 {} 条", cleaned)
    else:
        db.rollback()  # 无变更时回滚，避免长事务
    return cleaned


def _scan_and_cleanup_zombies(db: Session) -> dict[str, int]:
    """扫描并清理僵尸随访记录（仅清理，不自动创建）。

    设计决策：随访必须由护士在 AI 推荐面板中手动触发，系统不自动生成
    草稿，避免护士看到未预期的"进行中"记录。
    """
    all_pregnant = db.query(Pregnant).all()
    if not all_pregnant:
        logger.info("随访调度: 无孕妇数据，跳过扫描")
        return {"total": 0, "created": 0, "skipped": 0, "zombies_cleaned": 0}

    # 清理僵尸随访
    zombies_cleaned = _cleanup_zombie_followups(db)
    if zombies_cleaned:
        db.commit()

    total = len(all_pregnant)
    logger.info("随访调度扫描完成: total={} zombies_cleaned={} (自动创建已禁用)", total, zombies_cleaned)

    return {
        "total": total,
        "created": 0,
        "skipped": 0,
        "zombies_cleaned": zombies_cleaned,
    }


def _daily_scan_job():
    """定时任务：每日扫描所有孕妇，自动生成随访推荐。

    此函数在 APScheduler 的后台线程中运行，需要自行管理 DB session。
    """
    logger.info("随访定时调度开始执行...")
    db = SessionLocal()
    try:
        stats = _scan_and_cleanup_zombies(db)
        logger.info(
            "随访定时调度完成: total={total} created={created} "
            "skipped={skipped} zombies={zombies_cleaned}",
            **stats,
        )
    except Exception:
        logger.exception("随访定时调度执行失败")
    finally:
        db.close()


# 模块级单例
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """启动随访定时调度器。幂等：重复调用不会创建第二个调度器。"""
    global _scheduler
    if _scheduler is not None:
        logger.info("随访调度器已在运行，跳过重复启动")
        return _scheduler

    if not settings.followup_scheduler_enabled:
        logger.info("随访调度器已禁用（followup_scheduler_enabled=false）")
        return None

    _scheduler = BackgroundScheduler(daemon=True)

    trigger = CronTrigger(
        hour=settings.followup_scheduler_hour,
        minute=settings.followup_scheduler_minute,
        timezone="Asia/Shanghai",
    )
    _scheduler.add_job(
        _daily_scan_job,
        trigger=trigger,
        id="daily_followup_scan",
        name="每日随访自动扫描",
        misfire_grace_time=3600,  # 错过 1 小时内仍可补执行
        replace_existing=True,
    )

    # ---------- 日记定时生成 job ----------
    if settings.diary_scheduler_enabled:
        from .diary_scheduler import _weekly_diary_job

        diary_trigger = CronTrigger(
            day_of_week=settings.diary_scheduler_day_of_week,
            hour=settings.diary_scheduler_hour,
            minute=settings.diary_scheduler_minute,
            timezone="Asia/Shanghai",
        )
        _scheduler.add_job(
            _weekly_diary_job,
            trigger=diary_trigger,
            id="weekly_diary_generation",
            name="每周孕期日记自动生成",
            misfire_grace_time=7200,
            replace_existing=True,
        )
        logger.info(
            "日记调度已注册: 每周{} {:02d}:{:02d} (北京时间)",
            settings.diary_scheduler_day_of_week,
            settings.diary_scheduler_hour,
            settings.diary_scheduler_minute,
        )

    _scheduler.start()
    logger.info(
        "随访调度器已启动: 每日 {:02d}:{:02d} (北京时间) 执行扫描 "
        "draft超时={}天 in_progress超时={}天",
        settings.followup_scheduler_hour,
        settings.followup_scheduler_minute,
        settings.followup_zombie_draft_timeout_days,
        settings.followup_zombie_inprogress_timeout_days,
    )
    return _scheduler


def stop_scheduler():
    """停止随访定时调度器。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("随访调度器已停止")


def trigger_scan_now() -> dict[str, int]:
    """手动触发一次全量扫描（仅清理僵尸，不自动创建随访）。"""
    db = SessionLocal()
    try:
        return _scan_and_cleanup_zombies(db)
    finally:
        db.close()
