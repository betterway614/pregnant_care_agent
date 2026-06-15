"""用户反馈 API（支持孕妇/护士/医生三端）"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Feedback, AgentAuditLog
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/feedback", tags=["用户反馈"])


class FeedbackRequest(BaseModel):
    rating: Literal["thumbs_up", "thumbs_down"]
    message_id: str
    pregnant_id: str | None = None  # 孕妇端必填；护士/医生端可选
    feedback_role: Literal["pregnant", "nurse", "doctor"] = "pregnant"
    comment: str | None = None
    session_id: str | None = None
    audit_log_id: int | None = None  # 关联的审计日志 ID


@router.post("")
async def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """提交 AI 回复反馈

    支持三种角色提交反馈：
    - pregnant: 孕妇对小安回复的评价（需 pregnant_id）
    - nurse: 护士对小护回复的评价
    - doctor: 医生对 Dr.智回复的评价

    通过 audit_log_id 关联到具体的 Agent 调用记录，
    实现反馈 ↔ 审计日志的双向追溯。
    """
    # 孕妇端权限校验
    if req.feedback_role == "pregnant":
        if not req.pregnant_id:
            raise HTTPException(status_code=400, detail="孕妇端反馈需要 pregnant_id")
        if user.role == "pregnant" and user.pregnant_id != req.pregnant_id:
            raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    # 护士/医生端权限校验
    elif req.feedback_role == "nurse" and user.role not in ("nurse", "admin"):
        raise HTTPException(status_code=403, detail="需要护士权限")
    elif req.feedback_role == "doctor" and user.role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="需要医生权限")

    feedback = Feedback(
        pregnant_id=req.pregnant_id,
        feedback_role=req.feedback_role,
        user_id=user.sub if req.feedback_role in ("nurse", "doctor") else None,
        message_id=req.message_id,
        rating=req.rating,
        comment=req.comment,
        session_id=req.session_id,
        audit_log_id=req.audit_log_id,
    )
    db.add(feedback)
    # 反馈数据仅存 Feedback 表，不再反向写入 AgentAuditLog（保持审计日志只追加不可篡改）
    db.commit()
    return {"success": True, "id": str(feedback.id)}


@router.get("/stats")
async def get_feedback_stats(
    pregnant_id: str | None = None,
    feedback_role: str | None = None,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    """获取反馈统计（医护可查全部；孕妇仅可查自身）"""
    # 孕妇角色：只能查自己的反馈统计
    if user.role == "pregnant":
        if not pregnant_id:
            raise HTTPException(status_code=400, detail="孕妇端需要指定 pregnant_id")
        if user.pregnant_id != pregnant_id:
            raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from sqlalchemy import func
    query = db.query(Feedback)
    if pregnant_id:
        query = query.filter(Feedback.pregnant_id == pregnant_id)
    if feedback_role:
        query = query.filter(Feedback.feedback_role == feedback_role)

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
            "feedback_role": f.feedback_role,
            "user_id": f.user_id,
            "message_id": f.message_id,
            "rating": f.rating,
            "comment": f.comment,
            "session_id": f.session_id,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in feedbacks
    ]
