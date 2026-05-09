"""预警管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime
from ..database import get_db
from ..models import Alert, Pregnant
from ..schemas import AlertResponse, AlertReviewRequest
from ..core import rule_engine

router = APIRouter(prefix="/api/v1/alerts", tags=["预警管理"])


@router.get("", response_model=list[AlertResponse])
def get_alerts(status: Optional[str] = None,
               level: Optional[str] = None,
               pregnant_id: Optional[str] = None,
               db: Session = Depends(get_db)):
    """获取预警列表"""
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    if level:
        query = query.filter(Alert.level == level)
    if pregnant_id:
        query = query.filter(Alert.pregnant_id == pregnant_id)

    alerts = query.order_by(Alert.created_at.desc()).limit(100).all()

    result = []
    for a in alerts:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == a.pregnant_id).first()
        result.append(AlertResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
            gestational_age_days=pregnant.gestational_age_days if pregnant else None,
        ))
    return result


@router.get("/evaluate")
def evaluate_alerts(pregnant_id: str, data: dict, db: Session = Depends(get_db)):
    """手动评估某孕妇的规则"""
    hits = rule_engine.evaluate_all(data)

    created = []
    for hit in hits:
        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="RULE_ENGINE",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details={"trigger_data": data},
        )
        db.add(alert)
        created.append(alert)
    db.commit()

    return {
        "message": f"触发了 {len(created)} 条预警",
        "alerts": [AlertResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            patient_name=""
        ) for a in created]
    }


@router.put("/{alert_id}/review", response_model=AlertResponse)
def review_alert(alert_id: str, review: AlertReviewRequest,
                  db: Session = Depends(get_db)):
    """审核预警"""
    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    if review.action == "confirm":
        alert.status = "CONFIRMED"
    elif review.action == "dismiss":
        alert.status = "DISMISSED"
    elif review.action == "escalate":
        alert.status = "CONFIRMED"

    alert.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()
    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )
