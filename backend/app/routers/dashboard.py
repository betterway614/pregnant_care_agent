"""数据统计 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
from ..database import get_db
from ..models import Pregnant, Alert, FollowUpRecord, FgrAssessment
from ..core.auth import get_current_user, TokenPayload
from ..schemas import DashboardStats
from ..utils.timezone import beijing_now

router = APIRouter(prefix="/api/v1/dashboard", tags=["数据统计"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取统计看板数据"""
    total_pregnant = db.query(func.count(Pregnant.pregnant_id)).scalar() or 0
    pending_alerts = db.query(func.count(Alert.id)).filter(
        Alert.status.in_(["PENDING", "ESCALATED"])
    ).scalar() or 0
    now = beijing_now()
    today_followups = db.query(func.count(FollowUpRecord.id)).filter(
        func.date(FollowUpRecord.follow_up_date) == now.date()
    ).scalar() or 0
    high_risk_count = db.query(func.count(FgrAssessment.id)).filter(
        FgrAssessment.risk_level.in_(["high", "critical"])
    ).scalar() or 0

    pending_reviews = db.query(func.count(FollowUpRecord.id)).filter(
        FollowUpRecord.status == "draft"
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
    )


@router.get("/pregnant")
def get_pregnant_list(db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇列表"""
    pregnant = db.query(Pregnant).order_by(Pregnant.created_at.desc()).limit(50).all()
    return [
        {
            "pregnant_id": p.pregnant_id,
            "display_name": p.display_name,
            "nickname": p.nickname,
            "phone": p.phone,
            "hospital_id": p.hospital_id,
            "gestational_age_days": p.gestational_age_days,
            "edd": p.edd.isoformat() if p.edd else None,
            "risk_tags": p.risk_tags or [],
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pregnant
    ]


@router.get("/pregnant/{pregnant_id}")
def get_pregnant_detail(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇详情"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="孕妇不存在")

    # 统计数据
    alert_count = db.query(func.count(Alert.id)).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "CONFIRMED",
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
