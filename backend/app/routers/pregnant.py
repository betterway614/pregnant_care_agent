"""孕妇管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, ScheduleNode
from ..schemas import PregnantResponse, PregnantUpdateRequest, PregnantHomeData

router = APIRouter(prefix="/api/v1/pregnant", tags=["孕妇管理"])

@router.get("/{pregnant_id}", response_model=PregnantResponse)
def get_pregnant(pregnant_id: str):
    """获取孕妇完整资料"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")
        return pregnant
    finally:
        db.close()

@router.put("/{pregnant_id}", response_model=PregnantResponse)
def update_pregnant(pregnant_id: str, req: PregnantUpdateRequest):
    """更新孕妇资料（昵称、手机号、医院ID）"""
    db = SessionLocal()
    try:
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
    finally:
        db.close()

@router.get("/{pregnant_id}/home", response_model=PregnantHomeData)
def get_pregnant_home(pregnant_id: str):
    """获取孕妇主页数据（孕周、发育信息、今日检查、推荐）"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        # 计算孕周
        from datetime import date, datetime, timedelta
        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7

        # 宝宝发育信息
        baby_info = _get_baby_info(gest_week)

        # 今日任务
        today = date.today()
        today_tasks = []

        # 检查今日排期
        schedule_nodes = db.query(ScheduleNode).filter(
            ScheduleNode.pregnant_id == pregnant_id,
            ScheduleNode.scheduled_date == today
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

        # 近期检查
        upcoming = db.query(ScheduleNode).filter(
            ScheduleNode.pregnant_id == pregnant_id,
            ScheduleNode.scheduled_date >= today,
            ScheduleNode.scheduled_date <= today + timedelta(days=14)
        ).order_by(ScheduleNode.scheduled_date).limit(5).all()
        upcoming_checks = [{"date": n.scheduled_date.isoformat(), "item": n.item, "type": n.node_type} for n in upcoming]

        # AI推荐（模板兜底）
        recommendations = _get_recommendations(gest_week, pregnant.risk_tags or [])

        # 健康摘要
        health_summary = _get_health_summary(db, pregnant_id, gest_week)

        return PregnantHomeData(
            pregnant=PregnantResponse.model_validate(pregnant),
            gestational_week=f"{gest_week}+{gest_day}",
            gestational_day=gest_days,
            baby_info=baby_info,
            today_tasks=today_tasks,
            upcoming_checks=upcoming_checks,
            recommendations=recommendations,
            health_summary=health_summary
        )
    finally:
        db.close()

def _get_baby_info(week: int) -> dict:
    """根据孕周返回宝宝发育信息"""
    milestones = {
        8: {"size": "覆盆子大小", "size_cm": "1.6cm", "weight": "1g", "milestone": "心脏开始跳动，四肢开始形成"},
        12: {"size": "李子大小", "size_cm": "5.4cm", "weight": "14g", "milestone": "手指脚趾分离，面部特征明显"},
        16: {"size": "牛油果大小", "size_cm": "11.6cm", "weight": "100g", "milestone": "能听到声音，开始有吮吸反射"},
        20: {"size": "香蕉大小", "size_cm": "16.4cm", "weight": "300g", "milestone": "能感知光线，开始有规律的活动"},
        24: {"size": "玉米大小", "size_cm": "30cm", "weight": "600g", "milestone": "肺部开始发育，能辨别声音"},
        28: {"size": "茄子大小", "size_cm": "37.6cm", "weight": "1000g", "milestone": "眼睛睁开，大脑快速发育"},
        32: {"size": "南瓜大小", "size_cm": "42.4cm", "weight": "1700g", "milestone": "骨骼完全形成，开始储存脂肪"},
        36: {"size": "生菜大小", "size_cm": "47.4cm", "weight": "2600g", "milestone": "肺部成熟，准备出生"},
        40: {"size": "西瓜大小", "size_cm": "51cm", "weight": "3400g", "milestone": "足月，随时准备出生"},
    }
    # Find closest milestone
    closest = min(milestones.keys(), key=lambda x: abs(x - week))
    info = milestones[closest].copy()
    info["current_week"] = week
    return info

def _get_recommendations(week: int, risk_tags: list) -> dict:
    """根据孕周和风险标签返回推荐"""
    rec = {
        "weekly_tips": "",
        "diet_advice": "",
        "exercise_advice": "",
        "warning_signs": "",
    }

    if week <= 12:
        rec["weekly_tips"] = "孕早期是胎儿器官发育关键期，请按时服用叶酸(0.4mg/天)，避免接触有害物质。"
        rec["diet_advice"] = "少量多餐，选择易消化食物。增加富含叶酸的食物（深绿色蔬菜、豆类）。"
        rec["exercise_advice"] = "适度散步即可，避免剧烈运动和长时间站立。每天15-20分钟。"
        rec["warning_signs"] = "如出现阴道出血、剧烈腹痛，请立即就医。"
    elif week <= 28:
        rec["weekly_tips"] = "孕中期是胎儿快速生长期，注意补充钙和铁。可以开始进行胎教。"
        rec["diet_advice"] = "增加优质蛋白（鱼、蛋、瘦肉），补充钙质（牛奶、豆制品），控制盐摄入。"
        rec["exercise_advice"] = "每天散步30分钟，可做孕妇瑜伽。避免仰卧位运动。每天注意胎动。"
        rec["warning_signs"] = "如出现规律宫缩、阴道流液、胎动明显减少，请立即就医。"
    else:
        rec["weekly_tips"] = "孕晚期请准备好待产包，确认分娩医院和交通路线。保持左侧卧位休息。"
        rec["diet_advice"] = "继续高蛋白饮食，控制碳水化合物，多吃含铁食物（红肉、动物肝脏）。"
        rec["exercise_advice"] = "每天散步20-30分钟，做骨盆底肌锻炼。避免长时间站立和弯腰。"
        rec["warning_signs"] = "如出现规律宫缩（每10分钟一次）、见红、破水，请立即前往医院。"

    if "FGR高危" in (risk_tags or []):
        rec["weekly_tips"] += " 您是FGR高危孕妇，请严格按医嘱进行B超监测，注意胎动变化。"
    if "GDM" in (risk_tags or []):
        rec["diet_advice"] += " 请严格控制糖分摄入，监测空腹及餐后血糖。"
    if "高血压" in (risk_tags or []):
        rec["warning_signs"] += " 每日监测血压，如收缩压≥140或舒张压≥90请立即就医。"

    return rec

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
async def submit_health_data(pregnant_id: str, req: HealthDataSubmit):
    """孕妇端直接提交健康数据（不经过NLU，确保100%入库）"""
    from ..core.health_data_service import save_health_metrics, HealthDataSource

    # 验证孕妇存在
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")
    finally:
        db.close()

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
            await _auto_evaluate_alerts(pregnant_id)
        except Exception as e:
            from loguru import logger
            logger.warning(f"自动预警评估失败 (pregnant_id={pregnant_id}): {e}")

    return HealthDataSubmitResponse(
        success=True,
        saved_metrics=saved,
        count=len(saved),
        message=f"成功保存 {len(saved)} 项数据" if saved else "没有需要保存的数据",
    )


async def _auto_evaluate_alerts(pregnant_id: str):
    """健康数据入库后自动执行规则引擎评估并创建预警"""
    from ..core.rule_engine import rule_engine
    from ..services.alert_service import alert_service
    from ..core.websocket_manager import ws_manager
    from ..models import FgrAssessment
    from loguru import logger
    from sqlalchemy import func

    db = SessionLocal()
    try:
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

        # 后台异步 LLM 分析
        import asyncio
        from ..services.alert_service import alert_service
        for alert in new_alerts:
            asyncio.create_task(alert_service.enrich_alert_with_llm(db, alert, pregnant))

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
    finally:
        db.close()


def _build_rule_context(db: Session, pregnant_id: str, gest_week: int) -> dict:
    """构建规则引擎评估上下文，从数据库查询最新健康数据"""
    from datetime import timedelta
    from sqlalchemy import func

    context = {"gest_week": gest_week}

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
    week_ago = datetime.now() - timedelta(days=7)
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
    two_weeks_ago = datetime.now() - timedelta(days=14)
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
