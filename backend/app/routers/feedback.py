"""用户反馈 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..database import SessionLocal
from ..models import Feedback

router = APIRouter(prefix="/api/v1/feedback", tags=["用户反馈"])


class FeedbackRequest(BaseModel):
    pregnant_id: str
    message_id: str
    rating: str  # thumbs_up / thumbs_down
    comment: str | None = None
    session_id: str | None = None


@router.post("")
async def submit_feedback(req: FeedbackRequest):
    """提交 AI 回复反馈"""
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@router.get("/stats")
async def get_feedback_stats(pregnant_id: str | None = None):
    """获取反馈统计"""
    db = SessionLocal()
    try:
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
    finally:
        db.close()
