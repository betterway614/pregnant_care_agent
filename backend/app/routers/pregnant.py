"""孕妇管理 API"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
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
        HealthDataPoint.metric_code == "sbp"
    ).order_by(HealthDataPoint.recorded_at.desc()).first()
    dbp = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.metric_code == "dbp"
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
