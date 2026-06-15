"""孕妇管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import get_db
from ..models import Pregnant, HealthDataPoint, ScheduleNode
from ..schemas import PregnantResponse, PregnantUpdateRequest, PregnantHomeData
from ..core.auth import get_current_user, TokenPayload
from ..data.pregnancy_weeks import get_week_data

router = APIRouter(prefix="/api/v1/pregnant", tags=["孕妇管理"])

@router.get("/{pregnant_id}", response_model=PregnantResponse)
def get_pregnant(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇完整资料"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")
    return pregnant

@router.put("/{pregnant_id}", response_model=PregnantResponse)
def update_pregnant(pregnant_id: str, req: PregnantUpdateRequest, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """更新孕妇资料（昵称、手机号、医院ID）"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")
    if req.nickname is not None:
        pregnant.nickname = req.nickname
    if req.phone is not None:
        pregnant.phone = req.phone
    if req.hospital_id is not None:
        pregnant.hospital_id = req.hospital_id
    if req.display_name is not None:
        pregnant.display_name = req.display_name
    db.commit()
    db.refresh(pregnant)
    return pregnant

@router.get("/{pregnant_id}/home", response_model=PregnantHomeData)
def get_pregnant_home(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇主页数据（孕周、发育信息、今日检查、推荐）"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    # 实时计算孕周：优先从 lmp_date（末次月经）动态计算，兜底使用静态字段
    from datetime import date, datetime, timedelta
    today = date.today()
    if pregnant.lmp_date:
        delta = (today - pregnant.lmp_date).days
        gest_days = max(0, delta)  # 不允许负数
    else:
        # 兜底：使用静态字段（首次录入时的值，不会自动增长）
        gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7

    # 孕期知识库数据（40周全量覆盖）
    week_data = get_week_data(gest_week)

    # 宝宝发育信息
    baby_info = week_data.as_baby_info()

    # 妈妈变化
    mom_changes = week_data.as_mom_changes()

    # 今日任务
    today = date.today()
    today_tasks = []

    # 检查今日排期（仅已发布的）
    schedule_nodes = db.query(ScheduleNode).filter(
        ScheduleNode.pregnant_id == pregnant_id,
        ScheduleNode.scheduled_date == today,
        ScheduleNode.is_published == 1
    ).all()
    for node in schedule_nodes:
        today_tasks.append({
            "type": "checkup",
            "title": node.item,
            "time": "按预约时间",
            "status": "pending" if node.status != "completed" else "done"
        })

    # 检查是否需要记录健康数据
    today_str = today.isoformat()
    recorded_today = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= today_str
    ).count()
    if recorded_today == 0:
        today_tasks.append({
            "type": "health_record",
            "title": "今日健康数据记录",
            "time": "建议睡前完成",
            "status": "pending"
        })

    # 近期检查（仅已发布的）
    upcoming = db.query(ScheduleNode).filter(
        ScheduleNode.pregnant_id == pregnant_id,
        ScheduleNode.scheduled_date >= today,
        ScheduleNode.scheduled_date <= today + timedelta(days=14),
        ScheduleNode.is_published == 1
    ).order_by(ScheduleNode.scheduled_date).limit(5).all()
    upcoming_checks = [{"date": n.scheduled_date.isoformat(), "item": n.item, "type": n.node_type} for n in upcoming]

    # AI推荐（从知识库获取基础建议，再叠加风险标签）
    recommendations = week_data.as_recommendations()
    _apply_risk_overrides(pregnant.risk_tags or [], recommendations)

    # 健康摘要
    health_summary = _get_health_summary(db, pregnant_id, gest_week)

    return PregnantHomeData(
        pregnant=PregnantResponse.model_validate(pregnant),
        gestational_week=f"{gest_week}+{gest_day}",
        gestational_day=gest_days,
        baby_info=baby_info,
        mom_changes=mom_changes,
        today_tasks=today_tasks,
        upcoming_checks=upcoming_checks,
        recommendations=recommendations,
        health_summary=health_summary
    )

def _apply_risk_overrides(risk_tags: list, rec: dict) -> None:
    """叠加风险标签的针对性建议到推荐字典上（原地修改）。"""
    if not risk_tags:
        return
    if "FGR高危" in risk_tags:
        rec["weekly_tips"] += " 您是FGR高危孕妇，请严格按医嘱进行B超监测，注意胎动变化。"
    if "GDM" in risk_tags:
        rec["diet_advice"] += " 请严格控制糖分摄入，监测空腹及餐后血糖。"
    if "高血压" in risk_tags:
        rec["warning_signs"] += " 每日监测血压，如收缩压≥140或舒张压≥90请立即就医。"

def _get_health_summary(db: Session, pregnant_id: str, week: int) -> dict:
    """获取健康数据摘要"""
    from sqlalchemy import func
    summary = {"weight_kg": 0, "bp": "", "fetal_movement": 0, "last_record_date": ""}

    # 最近体重
    weight = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "weight"
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if weight:
        summary["weight_kg"] = weight.value
        summary["last_record_date"] = weight.recorded_at.strftime("%Y-%m-%d") if weight.recorded_at else ""

    # 最近血压
    sbp = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "systolic"
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    dbp = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "diastolic"
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if sbp and dbp:
        summary["bp"] = f"{int(sbp.value)}/{int(dbp.value)}"

    # 最近胎动
    fm = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "fetal_movement"
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if fm:
        summary["fetal_movement"] = int(fm.value)

    return summary


# ==================== 健康数据直接提交 API ====================

class HealthDataSubmit(BaseModel):
    """孕妇端健康数据提交（直接入库，不经过NLU）"""
    weight: Optional[float] = None              # 体重 kg
    systolic: Optional[float] = None            # 收缩压 mmHg
    diastolic: Optional[float] = None           # 舒张压 mmHg
    fetal_movement: Optional[float] = None      # 胎动 次/小时
    blood_sugar: Optional[float] = None         # 血糖 mmol/L
    blood_sugar_type: Optional[str] = None      # 血糖类型: fasting/postprandial
    heart_rate: Optional[float] = None          # 心率 bpm
    sleep_hours: Optional[float] = None         # 睡眠 小时
    steps: Optional[int] = None                 # 步数
    mood: Optional[str] = None                  # 情绪: good/neutral/bad


class HealthDataSubmitResponse(BaseModel):
    success: bool
    saved_metrics: list[str] = []
    count: int = 0
    message: str = ""


@router.post("/{pregnant_id}/health-data", response_model=HealthDataSubmitResponse)
async def submit_health_data(pregnant_id: str, req: HealthDataSubmit, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """孕妇端直接提交健康数据（不经过NLU，确保100%入库）"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from ..core.health_data_service import save_health_metrics, HealthDataSource

    # 验证孕妇存在
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    # 构建指标数据
    metrics = {}
    if req.weight is not None:
        metrics["weight"] = req.weight
    if req.systolic is not None:
        metrics["systolic"] = req.systolic
    if req.diastolic is not None:
        metrics["diastolic"] = req.diastolic
    if req.fetal_movement is not None:
        metrics["fetal_movement"] = req.fetal_movement
    if req.heart_rate is not None:
        metrics["heart_rate"] = req.heart_rate
    if req.sleep_hours is not None:
        metrics["sleep_hours"] = req.sleep_hours
    if req.steps is not None:
        metrics["steps"] = req.steps
    if req.mood:
        metrics["mood"] = req.mood

    # 血糖特殊处理
    if req.blood_sugar is not None:
        sugar_type = req.blood_sugar_type or "fasting"
        metrics[f"blood_sugar_{sugar_type}"] = req.blood_sugar

    # 调用统一入库服务
    saved = save_health_metrics(pregnant_id, metrics, HealthDataSource.PATIENT_DIRECT)

    # ===== 自动触发规则引擎评估 =====
    if saved:
        try:
            await _auto_evaluate_alerts(db, pregnant_id)
        except Exception as e:
            from loguru import logger
            logger.warning(f"自动预警评估失败 (pregnant_id={pregnant_id}): {e}")

    return HealthDataSubmitResponse(
        success=True,
        saved_metrics=saved,
        count=len(saved),
        message=f"成功保存 {len(saved)} 项数据" if saved else "没有需要保存的数据",
    )


async def _auto_evaluate_alerts(db: Session, pregnant_id: str):
    """健康数据入库后自动执行规则引擎评估并创建预警"""
    from ..core.rule_engine import rule_engine
    from ..services.alert_service import alert_service
    from ..core.websocket_manager import ws_manager
    from loguru import logger

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return

    gest_week = (pregnant.gestational_age_days or 0) // 7

    # 构建评估上下文
    context = _build_rule_context(db, pregnant_id, gest_week)

    # 执行规则引擎
    hits = rule_engine.evaluate_all(context)
    if not hits:
        return

    # 创建预警（alert_service 内部已做去重）
    created = alert_service.create_alerts_from_hits(db, pregnant_id, hits, "RULE_ENGINE")
    new_alerts = [a for a in created if a.status == "PENDING"]

    if not new_alerts:
        return

    logger.info(f"自动预警: {pregnant_id} 触发 {len(new_alerts)} 条新预警")

    # 后台异步 LLM 分析（传 IDs，让 task 自建 session）
    import asyncio
    for alert in new_alerts:
        asyncio.create_task(alert_service.enrich_alert_with_llm(alert.id, pregnant_id))

    # WebSocket 推送给医生端
    for alert in new_alerts:
        alert_data = {
            "id": str(alert.id),
            "pregnant_id": pregnant_id,
            "patient_name": pregnant.display_name,
            "level": alert.level,
            "message": alert.message,
            "trigger_source": alert.trigger_source,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "gestational_age_days": pregnant.gestational_age_days,
        }
        try:
            await ws_manager.broadcast_alert(alert_data)
        except Exception as e:
            logger.warning(f"WebSocket广播失败: {e}")


def _build_rule_context(db: Session, pregnant_id: str, gest_week: int) -> dict:
    """构建规则引擎评估上下文，从数据库查询最新健康数据"""
    from datetime import timedelta
    from ..utils.timezone import beijing_now
    from sqlalchemy import func

    context = {"gest_week": gest_week}
    now = beijing_now()

    # 最新血压
    sbp = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "systolic",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    dbp = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "diastolic",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if sbp:
        context["sbp"] = sbp.value
    if dbp:
        context["dbp"] = dbp.value

    # 最新胎动
    fm = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "fetal_movement",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if fm:
        context["fetal_movement"] = fm.value

    # 近7天胎动平均值
    week_ago = now - timedelta(days=7)
    fm_avg = db.query(func.avg(HealthDataPoint.value)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "fetal_movement",
        HealthDataPoint.recorded_at >= week_ago,
    ).scalar()
    if fm_avg:
        context["fetal_movement_avg"] = float(fm_avg)

    # 最新体重 + 周增长
    weight = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "weight",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if weight:
        context["weight"] = weight.value
    two_weeks_ago = now - timedelta(days=14)
    weight_prev = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "weight",
        HealthDataPoint.recorded_at <= two_weeks_ago,
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if weight and weight_prev and weight_prev.value > 0:
        context["weight_gain_weekly"] = (weight.value - weight_prev.value) / 2.0

    # 最新血糖
    bs_fasting = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "blood_sugar_fasting",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    bs_post = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "blood_sugar_postprandial",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if bs_fasting:
        context["blood_sugar_fasting"] = bs_fasting.value
    if bs_post:
        context["blood_sugar_postprandial"] = bs_post.value

    # 近7天情绪评分平均
    emotion_avg = db.query(func.avg(HealthDataPoint.value)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "emotion_score",
        HealthDataPoint.recorded_at >= week_ago,
    ).scalar()
    if emotion_avg:
        context["emotion_score_avg_7d"] = float(emotion_avg)

    # 最新睡眠
    sleep = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "sleep_hours",
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    if sleep:
        context["sleep_hours"] = sleep.value

    return context


# ==================== 主动通知 & 孕记 ====================


@router.get("/{pregnant_id}/proactive-notifications")
def get_proactive_notifications(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇的主动健康通知列表"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from ..services.proactive_monitor import ProactiveMonitorService

    notifications = ProactiveMonitorService.scan_notifications(db, pregnant_id)
    return [n.model_dump() for n in notifications]


@router.get("/{pregnant_id}/daily-task-status")
def get_daily_task_status(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """查询今日各项健康数据是否已记录，供前端「今日待办」展示动态完成状态。

    Returns:
        {"weight": bool, "blood_pressure": bool, "fetal_movement": bool}
    """
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from ..services.proactive_monitor import get_daily_task_status

    return get_daily_task_status(db, pregnant_id)


@router.get("/{pregnant_id}/diary")
async def get_pregnancy_diary(
    pregnant_id: str,
    weeks: int = 4,
    use_cache: bool = True,
    regenerate: bool = False,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    """获取孕妇孕记 — 按周汇总健康数据的温暖叙事

    Args:
        weeks: 回溯周数，默认 4 周
        use_cache: 是否使用已持久化的缓存日记（默认 True）
        regenerate: 强制重新生成（默认 False）
    """
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from ..services.pregnancy_diary import PregnancyDiaryService

    service = PregnancyDiaryService()
    diary = await service.generate_weekly_diary_async(
        db, pregnant_id, weeks=weeks,
        use_cache=use_cache, regenerate=regenerate,
    )
    return diary.model_dump()
