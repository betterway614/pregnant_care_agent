"""数据统计 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
from typing import Optional
from ..database import get_db
from ..models import Pregnant, Alert, FollowUpRecord, FgrAssessment, MedicalOrder
from ..core.auth import get_current_user, TokenPayload
from ..schemas import DashboardStats
from ..utils.timezone import beijing_now

router = APIRouter(prefix="/api/v1/dashboard", tags=["数据统计"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取统计看板数据

    统计口径说明：
    - pending_alerts: PENDING + ESCALATED 状态的预警数（与预警列表筛选一致）
    - today_followups: follow_up_date 为今天的随访记录数（全状态）
    - high_risk_count: 有 high/critical 级别 FGR 评估的**去重孕妇数**（非评估记录数）
    - pending_orders: status=draft 或 pending_sign 的医嘱数（医生端"待签署医嘱"）
    - pending_reviews: status=completed 的随访记录数（护士端"待审核记录"——患者已完成，等待护士确认）
    """
    total_pregnant = db.query(func.count(Pregnant.pregnant_id)).scalar() or 0

    # 待处理预警：PENDING + ESCALATED（与列表筛选条件一致）
    pending_alerts = db.query(func.count(Alert.id)).filter(
        Alert.status.in_(["PENDING", "ESCALATED"])
    ).scalar() or 0

    now = beijing_now()

    # 今日随访：follow_up_date 为今天的记录数（所有状态）
    today_followups = db.query(func.count(FollowUpRecord.id)).filter(
        func.date(FollowUpRecord.follow_up_date) == now.date()
    ).scalar() or 0

    # 高危孕妇数：有 high/critical FGR 评估的去重孕妇数（避免同一患者多条评估重复计数）
    high_risk_count = db.query(
        func.count(func.distinct(FgrAssessment.pregnant_id))
    ).filter(
        FgrAssessment.risk_level.in_(["high", "critical"])
    ).scalar() or 0

    # FGR 高风险数：RED 级别且 trigger_source 含 'fgr' 的去重孕妇数
    fgr_high_risk_count = db.query(
        func.count(func.distinct(Alert.pregnant_id))
    ).filter(
        Alert.level == "RED",
        Alert.trigger_source.ilike("%fgr%"),
        Alert.status.in_(["PENDING", "ESCALATED", "CONFIRMED"]),
    ).scalar() or 0

    # 待审核随访记录：status=completed（患者已完成，等待护士审核确认）
    pending_reviews = db.query(func.count(FollowUpRecord.id)).filter(
        FollowUpRecord.status == "completed"
    ).scalar() or 0

    # 待签署医嘱：status=draft 或 pending_sign（医生端"待签署医嘱"卡片）
    pending_orders = db.query(func.count(MedicalOrder.id)).filter(
        MedicalOrder.status.in_(["draft", "pending_sign"])
    ).scalar() or 0

    week_ago = now - timedelta(days=7)
    weekly_new = db.query(func.count(Pregnant.pregnant_id)).filter(
        Pregnant.created_at >= week_ago
    ).scalar() or 0

    return DashboardStats(
        total_pregnant=total_pregnant,
        pending_alerts=pending_alerts,
        today_followups=today_followups,
        pending_reviews=pending_reviews,
        high_risk_count=high_risk_count,
        weekly_new_pregnant=weekly_new,
        pending_orders=pending_orders,
        fgr_high_risk_count=fgr_high_risk_count,
    )


@router.get("/pregnant")
def get_pregnant_list(
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
    search: Optional[str] = Query(None, description="按姓名/昵称搜索"),
    has_alert: Optional[bool] = Query(None, description="仅有活跃预警的孕妇"),
    risk_tag: Optional[str] = Query(None, description="按风险标签筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """获取孕妇列表（支持搜索、筛选、分页，含聚合信息）

    返回孕妇基本信息 + 活跃预警数 + 最近随访日期，用于孕妇管理页面。
    """
    query = db.query(Pregnant)

    # 搜索：姓名或昵称模糊匹配
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            Pregnant.display_name.ilike(pattern) | Pregnant.nickname.ilike(pattern)
        )

    # 筛选：按风险标签
    if risk_tag:
        # SQLite/PostgreSQL 通用：用 LIKE 匹配 JSON 数组中的值
        query = query.filter(Pregnant.risk_tags.like(f'%"{risk_tag}"%'))

    # 总数（分页用）
    total = query.count()

    # 分页
    offset = (page - 1) * page_size
    patients = query.order_by(Pregnant.created_at.desc()).offset(offset).limit(page_size).all()

    if not patients:
        return {"total": total, "page": page, "page_size": page_size, "data": []}

    pregnant_ids = [p.pregnant_id for p in patients]

    # 批量查询每位孕妇的活跃预警数（PENDING + ESCALATED）
    alert_counts = dict(
        db.query(Alert.pregnant_id, func.count(Alert.id))
        .filter(Alert.pregnant_id.in_(pregnant_ids), Alert.status.in_(["PENDING", "ESCALATED"]))
        .group_by(Alert.pregnant_id)
        .all()
    )

    # 批量查询每位孕妇的最近随访日期
    latest_followups = dict(
        db.query(
            FollowUpRecord.pregnant_id,
            func.max(FollowUpRecord.follow_up_date),
        )
        .filter(FollowUpRecord.pregnant_id.in_(pregnant_ids))
        .group_by(FollowUpRecord.pregnant_id)
        .all()
    )

    # 若 has_alert=True，只返回有活跃预警的孕妇（内存过滤，数据量小）
    result = []

    # Batch check FGR image bindings for the current page
    try:
        from fgr_compete.image_registry import load_patient_map
        image_map = load_patient_map()
    except Exception:
        image_map = {}

    for p in patients:
        ac = alert_counts.get(p.pregnant_id, 0)
        if has_alert and ac == 0:
            total -= 1
            continue
        lfu = latest_followups.get(p.pregnant_id)
        result.append({
            "pregnant_id": p.pregnant_id,
            "display_name": p.display_name,
            "nickname": p.nickname,
            "phone": p.phone,
            "hospital_id": p.hospital_id,
            "gestational_age_days": p.gestational_age_days,
            "edd": p.edd.isoformat() if p.edd else None,
            "risk_tags": p.risk_tags or [],
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "active_alert_count": ac,
            "latest_followup_date": lfu.isoformat() if lfu else None,
            "has_fgr_image": p.pregnant_id in image_map,
        })

    return {"total": total, "page": page, "page_size": page_size, "data": result}


@router.get("/pregnant/{pregnant_id}")
def get_pregnant_detail(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇详情"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="孕妇不存在")

    # 统计数据：该孕妇的活跃预警数（PENDING + ESCALATED + CONFIRMED）
    alert_count = db.query(func.count(Alert.id)).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status.in_(["PENDING", "ESCALATED", "CONFIRMED"]),
    ).scalar() or 0

    followup_count = db.query(func.count(FollowUpRecord.id)).filter(
        FollowUpRecord.pregnant_id == pregnant_id,
    ).scalar() or 0

    return {
        "pregnant_id": pregnant.pregnant_id,
        "display_name": pregnant.display_name,
        "gestational_age_days": pregnant.gestational_age_days,
        "gestational_week": f"{pregnant.gestational_age_days // 7}+{pregnant.gestational_age_days % 7}" if pregnant.gestational_age_days else "未知",
        "lmp_date": pregnant.lmp_date.isoformat() if pregnant.lmp_date else None,
        "edd": pregnant.edd.isoformat() if pregnant.edd else None,
        "risk_tags": pregnant.risk_tags or [],
        "alert_count": alert_count,
        "followup_count": followup_count,
    }
