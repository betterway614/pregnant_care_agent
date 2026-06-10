"""预警管理 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from ..database import get_db
from ..utils.timezone import beijing_now
from ..models import Alert, Pregnant
from ..schemas import AlertResponse, AlertReviewRequest
from ..core import rule_engine
from ..core.websocket_manager import ws_manager
from ..core.auth import get_current_user, TokenPayload

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
               db: Session = Depends(get_db),
               current_user: TokenPayload = Depends(get_current_user)):
    """获取预警列表"""
    query = db.query(Alert)
    if status:
        # 支持逗号分隔的多状态查询（如 "pending,escalated"），大小写不敏感
        status_list = [s.strip().upper() for s in status.split(",")]
        query = query.filter(Alert.status.in_(status_list))
    if level:
        query = query.filter(Alert.level == level)
    if pregnant_id:
        query = query.filter(Alert.pregnant_id == pregnant_id)

    alerts = query.order_by(Alert.created_at.desc()).limit(100).all()

    # 批量查询孕妇信息，避免 N+1 查询
    pregnant_ids = list(set(a.pregnant_id for a in alerts))
    pregnant_map = {}
    if pregnant_ids:
        pregnants = db.query(Pregnant).filter(Pregnant.pregnant_id.in_(pregnant_ids)).all()
        pregnant_map = {p.pregnant_id: p for p in pregnants}

    result = []
    for a in alerts:
        pregnant = pregnant_map.get(a.pregnant_id)
        result.append(AlertResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
            gestational_age_days=pregnant.gestational_age_days if pregnant else None,
        ))
    return result


@router.post("", response_model=AlertResponse)
async def create_alert(
    req: CreateAlertRequest,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
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

    # 2. 创建预警记录（统一走去重入口）
    from ..services.alert_service import alert_service
    alert = alert_service.create_alert(
        db=db,
        pregnant_id=req.pregnant_id,
        rule_id=req.rule_id or "MANUAL",
        domain=req.details.get("domain", "") if req.details else "",
        level=req.level,
        message=req.message,
        trigger_source=req.trigger_source,
        details=req.details,
    )

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
        alert_data["source_role"] = "system"
        alert_data["action"] = "created"
        await ws_manager.route_alert(alert_data)
    except Exception as e:
        logger.warning(f"WebSocket广播失败，预警已创建: {e}")

    # 5. 后台异步调用 LLM 生成分析摘要（enrich_alert_with_llm 内部创建独立session）
    import asyncio
    from ..services.alert_service import alert_service
    asyncio.create_task(alert_service.enrich_alert_with_llm(alert.id, req.pregnant_id))

    # 6. 返回预警响应
    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name,
        gestational_age_days=pregnant.gestational_age_days,
    )


@router.post("/evaluate")
def evaluate_alerts(pregnant_id: str, req: AlertEvaluateRequest, db: Session = Depends(get_db),
                    current_user: TokenPayload = Depends(get_current_user)):
    """手动评估某孕妇的规则"""
    hits = rule_engine.evaluate_all(req.data)

    from ..services.alert_service import alert_service
    created = alert_service.create_alerts_from_hits(db, pregnant_id, hits, "RULE_ENGINE")

    return {
        "message": f"触发了 {len(created)} 条预警",
        "alerts": [AlertResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            patient_name=""
        ) for a in created]
    }


@router.post("/{alert_id}/analyze-workflow")
async def analyze_alert_workflow(alert_id: str, db: Session = Depends(get_db),
                                 current_user: TokenPayload = Depends(get_current_user)):
    """执行 Alert→护士→医生 预分析 Workflow，结果写入 alert.details"""
    from ..services.alert_analysis_service import alert_analysis_service

    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    result = await alert_analysis_service.run_alert_workflow(db, alert, pregnant)
    db.refresh(alert)

    return {
        "alert_id": str(alert.id),
        "workflow_result": result,
        "details": alert.details,
    }


def _append_history(alert: Alert, action: str, source_role: str, level: str,
                   operator: str = None, reason: str = None):
    """在 alert.details.history 追加一条操作记录"""
    details = alert.details or {}
    history = details.get("history", [])
    history.append({
        "seq": len(history) + 1,
        "action": action,
        "source_role": source_role,
        "level": level,
        "operator": operator,
        "reason": reason,
        "timestamp": beijing_now().isoformat(),
    })
    details["history"] = history
    details["source_role"] = source_role
    alert.details = details
    flag_modified(alert, "details")


@router.put("/{alert_id}/review", response_model=AlertResponse)
async def review_alert(alert_id: str, review: AlertReviewRequest,
                  db: Session = Depends(get_db),
                  current_user: TokenPayload = Depends(get_current_user)):
    """审核预警 — 支持医生和护士的全部操作"""
    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    original_level = alert.level
    operator = current_user.sub
    source_role = current_user.role if current_user.role in ("doctor", "nurse") else "doctor"

    if review.action == "confirm":
        alert.status = "CONFIRMED"
        _append_history(alert, "confirm", source_role, alert.level, operator, review.reason)
    elif review.action == "dismiss":
        alert.status = "DISMISSED"
        _append_history(alert, "dismiss", source_role, alert.level, operator, review.reason)
    elif review.action == "escalate":
        alert.status = "ESCALATED"
        if alert.level != "RED":
            alert.level = "RED"
        _append_history(alert, "escalate", source_role, alert.level, operator, review.reason)
    elif review.action == "downgrade":
        if not review.target_level:
            raise HTTPException(400, "降级操作必须指定 target_level")
        if review.target_level == "GREEN":
            alert.status = "DISMISSED"
        else:
            alert.level = review.target_level
            alert.status = "PENDING"
        _append_history(alert, "downgrade", source_role, review.target_level, operator, review.reason)
    elif review.action == "supplement":
        _append_history(alert, "supplement", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_confirm":
        source_role = "nurse"
        alert.status = "CONFIRMED"
        _append_history(alert, "nurse_confirm", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_dismiss":
        source_role = "nurse"
        alert.status = "DISMISSED"
        _append_history(alert, "nurse_dismiss", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_escalate":
        source_role = "nurse"
        if alert.level == "YELLOW":
            alert.level = "ORANGE"
        elif alert.level == "ORANGE":
            alert.level = "RED"
        # RED 级别不做操作，但仍记录
        _append_history(alert, "nurse_escalate", source_role, alert.level, operator, review.reason)
    elif review.action == "nurse_appeal":
        source_role = "nurse"
        _append_history(alert, "nurse_appeal", source_role, alert.level, operator, review.reason)

    alert.reviewed_at = beijing_now()
    db.commit()
    db.refresh(alert)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()

    # WebSocket 路由推送
    try:
        alert_data = {
            "id": str(alert.id),
            "pregnant_id": alert.pregnant_id,
            "patient_name": pregnant.display_name if pregnant else "未知",
            "level": alert.level,
            "message": alert.message,
            "trigger_source": alert.trigger_source,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "gestational_age_days": pregnant.gestational_age_days if pregnant else None,
            "source_role": source_role,
            "action": review.action,
            "review_reason": review.reason,
        }

        if source_role == "doctor" and review.action == "escalate":
            prefix = "[已升级]" if alert.level == "RED" and original_level != "RED" else "[紧急通知]"
            alert_data["message"] = f"{prefix} {alert.message}"

        if source_role == "nurse" and review.action == "nurse_escalate":
            if alert.level == "RED":
                alert_data["message"] = f"[护士升级] {alert.message}"

        if source_role == "doctor" and review.action == "downgrade" and review.target_level != "GREEN":
            alert_data["message"] = f"[医生降级] {alert.message}"

        if source_role == "nurse" and review.action == "nurse_appeal":
            alert_data["message"] = f"[护士复议] {alert.message}"
            alert_details = alert.details or {}
            downgrade_entry = next(
                (h for h in reversed(alert_details.get("history", [])) if h["action"] == "downgrade"), None
            )
            if downgrade_entry:
                alert_data["target_doctor_id"] = downgrade_entry.get("operator")

        await ws_manager.route_alert(alert_data)
    except Exception as e:
        logger.warning(f"WebSocket路由推送失败: {e}")

    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )


@router.post("/auto-dismiss")
def auto_dismiss_alerts(db: Session = Depends(get_db),
                        current_user: TokenPayload = Depends(get_current_user)):
    """定时任务: 自动关闭超时 PENDING 预警"""
    from datetime import timedelta

    now = beijing_now()
    thresholds = {
        "RED": now - timedelta(hours=72),
        "ORANGE": now - timedelta(hours=48),
        "YELLOW": now - timedelta(hours=24),
    }

    dismissed_count = 0
    for level, cutoff in thresholds.items():
        stale = db.query(Alert).filter(
            Alert.status == "PENDING",
            Alert.level == level,
            Alert.created_at < cutoff,
        ).all()

        timeout_hours = {"RED": 72, "ORANGE": 48, "YELLOW": 24}.get(level, 24)
        for alert in stale:
            # 幂等保护：二次校验状态，避免并发重复处理
            if alert.status != "PENDING":
                continue
            _append_history(alert, "auto_dismiss", "system", alert.level,
                          reason=f"超时{timeout_hours}小时未处理")
            alert.status = "AUTO_DISMISSED"
            alert.reviewed_at = now
            dismissed_count += 1

    db.commit()
    logger.info(f"自动关闭 {dismissed_count} 条超时预警")
    return {"message": f"自动关闭了 {dismissed_count} 条超时预警", "count": dismissed_count}


@router.post("/repair-mismatched")
def repair_mismatched_alerts(db: Session = Depends(get_db),
                             current_user: TokenPayload = Depends(get_current_user)):
    """修复 rule_id 与 message 不匹配的预警记录（数据修复工具）"""
    from ..services.alert_service import alert_service
    repaired = alert_service.repair_mismatched_alerts(db)
    return {"message": f"修复了 {repaired} 条不匹配的预警记录", "repaired": repaired}


@router.post("/repair-details")
def repair_alert_details(db: Session = Depends(get_db),
                         current_user: TokenPayload = Depends(get_current_user)):
    """修复 details 字段格式，统一所有预警的 details 结构（数据修复工具）"""
    from ..services.alert_service import alert_service
    repaired = alert_service.repair_details(db)
    return {"message": f"修复了 {repaired} 条预警的 details 字段", "repaired": repaired}


# ==================== 孕妇端通知 API ====================


@router.get("/pregnant/{pregnant_id}/notifications")
def get_pregnant_notifications(pregnant_id: str, unread_only: bool = False, db: Session = Depends(get_db),
                               current_user: TokenPayload = Depends(get_current_user)):
    """获取孕妇的通知列表（预警、随访、医嘱）"""
    from ..services.pregnant_notification import PregnantNotificationService

    service = PregnantNotificationService()
    notifications = service.get_notifications(db, pregnant_id, unread_only=unread_only)
    return [n.model_dump() for n in notifications]


@router.put("/pregnant/{pregnant_id}/notifications/read-all")
def mark_all_notifications_read(pregnant_id: str, db: Session = Depends(get_db),
                                current_user: TokenPayload = Depends(get_current_user)):
    """标记该孕妇所有通知为已读"""
    from ..services.pregnant_notification import PregnantNotificationService

    service = PregnantNotificationService()
    count = service.mark_all_read(db, pregnant_id)
    return {"marked_count": count}


@router.put("/notifications/{alert_id}/read")
def mark_notification_read(alert_id: str, pregnant_id: str, db: Session = Depends(get_db),
                           current_user: TokenPayload = Depends(get_current_user)):
    """标记单条通知为已读"""
    from ..services.pregnant_notification import PregnantNotificationService

    service = PregnantNotificationService()
    success = service.mark_read(db, alert_id, pregnant_id)
    if not success:
        raise HTTPException(404, "通知不存在或无权限")
    return {"success": True}
