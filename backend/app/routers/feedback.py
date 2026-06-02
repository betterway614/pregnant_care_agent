"""用户反馈 API"""
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Feedback
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/feedback", tags=["用户反馈"])


class FeedbackRequest(BaseModel):
    pregnant_id: str
    message_id: str
    rating: Literal["thumbs_up", "thumbs_down"]
    comment: str | None = None
    session_id: str | None = None


@router.post("")
async def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """提交 AI 回复反馈"""
    if user.role == "pregnant" and user.pregnant_id != req.pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    feedback = Feedback(
        pregnant_id=req.pregnant_id,
        message_id=req.message_id,
        rating=req.rating,
        comment=req.comment,
        session_id=req.session_id,
    )
    db.add(feedback)
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
