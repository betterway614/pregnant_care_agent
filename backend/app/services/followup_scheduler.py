"""随访自动调度服务

每日定时扫描所有孕妇，自动：
1. 为符合条件（紧急告警/逾期/从未随访/数据不活跃/信息缺失）的孕妇生成随访草稿
2. 清理僵尸随访（长期 draft/in_progress 未处理的记录）
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Pregnant, FollowUpRecord, HealthDataPoint, Alert
from ..utils.timezone import beijing_now


def _create_draft_followup(
    db: Session,
    pregnant_id: str,
    rec: dict[str, Any],
) -> str | None:
    """根据推荐结果创建一条 draft 状态的随访记录。返回记录 ID，失败返回 None。"""
    try:
        now = beijing_now()
        record = FollowUpRecord(
            id=str(uuid.uuid4()),
            pregnant_id=pregnant_id,
            status="draft",
            gestational_week=rec.get("gestational_week", ""),
            self_reported_data={
                "template_id": rec.get("template_id", "standard"),
                "auto_generated": True,
                "reason": rec.get("reason", ""),
                "priority": rec.get("priority", "low"),
            },
            guidance_tags=rec.get("suggested_actions", []),
            created_at=now,
            follow_up_date=now,
        )
        db.add(record)
        db.flush()
        return record.id
    except Exception:
        logger.exception("创建随访草稿失败 pregnant_id={}", pregnant_id)
        return None


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

    zombies = db.query(FollowUpRecord).filter(
        FollowUpRecord.status.in_(["draft", "in_progress"]),
        FollowUpRecord.created_at < draft_timeout,
    ).all()

    # 对 in_progress 使用更长的超时时间
    inprogress_zombies = db.query(FollowUpRecord).filter(
        FollowUpRecord.status == "in_progress",
        FollowUpRecord.created_at >= draft_timeout,  # 未被上面查询覆盖的
        FollowUpRecord.created_at < inprogress_timeout,
    ).all()

    all_zombies = zombies + inprogress_zombies
    cleaned = 0
    for record in all_zombies:
        if _archive_zombie_followup(db, record):
            cleaned += 1

    if cleaned:
        db.flush()
        logger.info("僵尸随访清理完成: 共归档 {} 条", cleaned)
    return cleaned


def _scan_and_create_followups(db: Session) -> dict[str, int]:
    """扫描所有孕妇并自动创建随访推荐。返回统计信息。"""
    from ..routers.nurse_ai import tool_recommend_followup_schedule

    all_pregnant = db.query(Pregnant).all()
    if not all_pregnant:
        logger.info("随访调度: 无孕妇数据，跳过扫描")
        return {"total": 0, "created": 0, "skipped": 0, "zombies_cleaned": 0}

    # 先清理僵尸随访
    zombies_cleaned = _cleanup_zombie_followups(db)
    if zombies_cleaned:
        db.commit()  # 提交清理结果，避免后续推荐被僵尸阻塞

    created = 0
    skipped = 0

    for p in all_pregnant:
        try:
            result = tool_recommend_followup_schedule(db, p.pregnant_id)
            if "error" in result:
                skipped += 1
                continue

            recommendations = result.get("recommendations", [])
            skip_reason = result.get("skip_reason", "")

            # 查找 immediate 推荐（高优先级 + 推荐日期为 immediate）
            immediate_recs = [
                r for r in recommendations
                if r.get("recommended_date") == "immediate"
            ]

            if not immediate_recs:
                skipped += 1
                continue

            # 为每条 immediate 推荐创建随访草稿（实际通常只有 1 条）
            for rec in immediate_recs:
                record_id = _create_draft_followup(db, p.pregnant_id, rec)
                if record_id:
                    created += 1
                    logger.info(
                        "自动创建随访 draft: id={} pregnant_id={} reason={}",
                        record_id, p.pregnant_id, rec.get("reason", "")[:60],
                    )
        except Exception:
            logger.exception("扫描孕妇随访失败 pregnant_id={}", p.pregnant_id)
            skipped += 1

    if created:
        db.commit()
        logger.info("随访调度扫描完成: total={} created={} skipped={} zombies={}",
                     len(all_pregnant), created, skipped, zombies_cleaned)
    else:
        db.rollback()

    return {
        "total": len(all_pregnant),
        "created": created,
        "skipped": skipped,
        "zombies_cleaned": zombies_cleaned,
    }


def _daily_scan_job():
    """定时任务：每日扫描所有孕妇，自动生成随访推荐。

    此函数在 APScheduler 的后台线程中运行，需要自行管理 DB session。
    """
    logger.info("随访定时调度开始执行...")
    db = SessionLocal()
    try:
        stats = _scan_and_create_followups(db)
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
    """手动触发一次全量扫描（用于调试/测试/API调用）。"""
    db = SessionLocal()
    try:
        return _scan_and_create_followups(db)
    finally:
        db.close()
