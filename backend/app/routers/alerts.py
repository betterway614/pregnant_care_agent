"""预警管理 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from ..database import get_db
from ..models import Alert, Pregnant
from ..schemas import AlertResponse, AlertReviewRequest
from ..core import rule_engine
from ..core.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["预警管理"])


class AlertEvaluateRequest(BaseModel):
    """预警评估请求"""
    data: dict


class CreateAlertRequest(BaseModel):
    """创建预警请求"""
    pregnant_id: str
    level: Literal["RED", "ORANGE", "YELLOW"]  # 限制合法值
    message: str
    trigger_source: Literal["MANUAL", "RULE_ENGINE", "FGR_ALGORITHM"] = "MANUAL"
    rule_id: Optional[str] = None
    details: Optional[dict] = None


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


@router.post("", response_model=AlertResponse)
async def create_alert(
    req: CreateAlertRequest,
    db: Session = Depends(get_db)
):
    """
    创建预警记录并推送给医生端

    护士确认后调用此接口创建预警
    """
    # 1. 校验孕妇是否存在
    pregnant = db.query(Pregnant).filter(
        Pregnant.pregnant_id == req.pregnant_id
    ).first()
    if not pregnant:
        raise HTTPException(404, f"孕妇 {req.pregnant_id} 不存在")

    # 2. 创建预警记录
    alert = Alert(
        pregnant_id=req.pregnant_id,
        trigger_source=req.trigger_source,
        rule_id=req.rule_id,
        level=req.level,
        message=req.message,
        details=req.details or {},
        status="PENDING",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # 3. 构建推送数据
    alert_data = {
        "id": str(alert.id),
        "pregnant_id": req.pregnant_id,
        "patient_name": pregnant.display_name,
        "level": req.level,
        "message": req.message,
        "trigger_source": req.trigger_source,
        "status": alert.status,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "gestational_age_days": pregnant.gestational_age_days,
    }

    # 4. 实时推送给医生端
    try:
        await ws_manager.broadcast_alert(alert_data)
    except Exception as e:
        logger.warning(f"WebSocket广播失败，预警已创建: {e}")

    # 5. 返回预警响应
    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name,
        gestational_age_days=pregnant.gestational_age_days,
    )


@router.post("/evaluate")
def evaluate_alerts(pregnant_id: str, req: AlertEvaluateRequest, db: Session = Depends(get_db)):
    """手动评估某孕妇的规则"""
    hits = rule_engine.evaluate_all(req.data)

    created = []
    for hit in hits:
        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="RULE_ENGINE",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details={"trigger_data": req.data},
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
