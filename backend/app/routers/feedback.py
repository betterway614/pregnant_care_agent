"""用户反馈 API"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Feedback, AgentAuditLog
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/feedback", tags=["用户反馈"])


class FeedbackRequest(BaseModel):
    pregnant_id: str
    message_id: str
    rating: Literal["thumbs_up", "thumbs_down"]
    comment: str | None = None
    session_id: str | None = None
    audit_log_id: int | None = None  # 关联的审计日志 ID


@router.post("")
async def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """提交 AI 回复反馈

    支持通过 audit_log_id 关联到具体的 Agent 调用记录，
    实现反馈 ↔ 审计日志的双向追溯。
    """
    if user.role == "pregnant" and user.pregnant_id != req.pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")

    feedback = Feedback(
        pregnant_id=req.pregnant_id,
        message_id=req.message_id,
        rating=req.rating,
        comment=req.comment,
        session_id=req.session_id,
        audit_log_id=req.audit_log_id,
    )
    db.add(feedback)

    # 反向写入审计日志的冗余字段，便于聚合查询
    if req.audit_log_id:
        audit_log = db.query(AgentAuditLog).filter(AgentAuditLog.id == req.audit_log_id).first()
        if audit_log:
            audit_log.feedback_rating = req.rating
            audit_log.feedback_comment = req.comment

    db.commit()
    return {"success": True, "id": str(feedback.id)}


@router.get("/stats")
async def get_feedback_stats(pregnant_id: str | None = None, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取反馈统计"""
    if user.role == "pregnant" and pregnant_id and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from sqlalchemy import func
    query = db.query(Feedback)
    if pregnant_id:
        query = query.filter(Feedback.pregnant_id == pregnant_id)

    total = query.count()
    thumbs_up = query.filter(Feedback.rating == "thumbs_up").count()
    thumbs_down = query.filter(Feedback.rating == "thumbs_down").count()

    return {
        "total": total,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "satisfaction_rate": round(thumbs_up / total * 100, 1) if total > 0 else 0,
    }


@router.get("/by-audit/{audit_log_id}")
async def get_feedback_by_audit(audit_log_id: int, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """根据审计日志 ID 获取关联的反馈"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    feedbacks = db.query(Feedback).filter(Feedback.audit_log_id == audit_log_id).all()
    return [
        {
            "id": str(f.id),
            "pregnant_id": f.pregnant_id,
            "message_id": f.message_id,
            "rating": f.rating,
            "comment": f.comment,
            "session_id": f.session_id,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in feedbacks
    ]
