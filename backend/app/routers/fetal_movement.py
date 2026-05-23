"""胎动计数 API"""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..database import SessionLocal
from ..models import FetalMovementSession
from ..utils.timezone import beijing_now

router = APIRouter(prefix="/api/v1/fetal-movement", tags=["胎动计数"])


class SessionCreateRequest(BaseModel):
    pregnant_id: str


class SessionUpdateRequest(BaseModel):
    total_count: int
    kick_times: list[str] = []
    notes: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    pregnant_id: str
    start_time: str
    end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_count: int
    kick_times: list[str] = []
    notes: Optional[str] = None

    @classmethod
    def from_orm(cls, session):
        return cls(
            id=str(session.id),
            pregnant_id=session.pregnant_id,
            start_time=session.start_time.isoformat() if session.start_time else "",
            end_time=session.end_time.isoformat() if session.end_time else None,
            duration_minutes=session.duration_minutes,
            total_count=session.total_count,
            kick_times=session.kick_times or [],
            notes=session.notes,
        )


@router.post("/sessions", response_model=SessionResponse)
def create_session(req: SessionCreateRequest):
    """创建新的胎动计数会话"""
    db = SessionLocal()
    try:
        session = FetalMovementSession(
            pregnant_id=req.pregnant_id,
            start_time=beijing_now(),
            total_count=0,
            kick_times=[],
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return SessionResponse.from_orm(session)
    finally:
        db.close()


@router.put("/sessions/{session_id}", response_model=SessionResponse)
def update_session(session_id: str, req: SessionUpdateRequest):
    """更新胎动计数会话（保存计数和每次胎动时刻）"""
    db = SessionLocal()
    try:
        session = db.query(FetalMovementSession).filter(
            FetalMovementSession.id == UUID(session_id)
        ).first()
        if not session:
            raise HTTPException(404, "会话不存在")

        session.total_count = req.total_count
        session.kick_times = req.kick_times
        session.end_time = beijing_now()
        if req.kick_times:
            # 根据 kick_times 计算持续分钟数
            times = sorted(req.kick_times)
            if len(times) >= 2:
                try:
                    t0 = datetime.fromisoformat(times[0])
                    t1 = datetime.fromisoformat(times[-1])
                    session.duration_minutes = max(1, int((t1 - t0).total_seconds() / 60))
                except (ValueError, TypeError):
                    session.duration_minutes = max(1, len(times))
            else:
                session.duration_minutes = 1
        if req.notes:
            session.notes = req.notes
        db.commit()
        db.refresh(session)
        return SessionResponse.from_orm(session)
    finally:
        db.close()


@router.get("/sessions/{pregnant_id}", response_model=list[SessionResponse])
def list_sessions(pregnant_id: str, limit: int = 20):
    """获取孕妇的胎动计数历史"""
    db = SessionLocal()
    try:
        sessions = db.query(FetalMovementSession).filter(
            FetalMovementSession.pregnant_id == pregnant_id
        ).order_by(FetalMovementSession.start_time.desc()).limit(limit).all()
        return [SessionResponse.from_orm(s) for s in sessions]
    finally:
        db.close()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """删除一条胎动计数记录"""
    db = SessionLocal()
    try:
        session = db.query(FetalMovementSession).filter(
            FetalMovementSession.id == UUID(session_id)
        ).first()
        if not session:
            raise HTTPException(404, "会话不存在")
        db.delete(session)
        db.commit()
        return {"message": "已删除"}
    finally:
        db.close()
