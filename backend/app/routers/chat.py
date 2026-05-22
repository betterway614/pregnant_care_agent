"""对话管理 API - Agno Agent 生产路径"""
import json
import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..core import memory_manager, rag_engine
from ..core.agno_chat_handler import handle_chat_with_agno, handle_chat_with_agno_stream
from ..models import HealthDataPoint, Pregnant, MedicalOrder, ConversationMessage
from ..database import SessionLocal
from ..config import settings

router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])


def _generate_session_id(pregnant_id: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    rand_str = _uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"


@router.get("/ping")
def ping():
    return {"pong": datetime.now().isoformat(), "version": "agno_v1"}


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatSendRequest):
    """发送对话消息（Agno Agent）"""
    logger.info("send_message pregnant_id={}", req.pregnant_id[:8])
    return await handle_chat_with_agno(req)


@router.post("/send/stream")
async def send_message_stream(req: ChatSendRequest):
    """发送对话消息（SSE 流式）"""
    return EventSourceResponse(handle_chat_with_agno_stream(req))


class ASRRequest(BaseModel):
    audio_data: str
    audio_format: str = "webm"


class ASRResponse(BaseModel):
    text: str
    success: bool


@router.post("/asr", response_model=ASRResponse)
async def transcribe_audio(req: ASRRequest):
    """语音转文字（独立 ASR 接口，用于前端语音气泡长按转文本）

    支持 cloud/local 两种模式，调用专用 ASR 服务转录。
    """
    from ..core.agno_chat_handler import _transcribe_audio_pregnant

    text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)
    success = not text.startswith("（")
    return ASRResponse(text=text, success=success)


@router.get("/conversation/{pregnant_id}")
async def get_conversation_history(pregnant_id: str, session_id: str = ""):
    if not settings.persist_chat_messages:
        return {"session_id": session_id, "messages": [], "message": "对话持久化未启用"}

    db = SessionLocal()
    try:
        query = db.query(ConversationMessage).filter(
            ConversationMessage.pregnant_id == pregnant_id,
        )
        if session_id:
            query = query.filter(ConversationMessage.session_id == session_id)

        messages = (
            query.order_by(ConversationMessage.created_at.asc())
            .limit(200)
            .all()
        )
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "session_id": m.session_id,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }
    finally:
        db.close()


@router.delete("/conversation/{pregnant_id}")
async def clear_conversation_history(pregnant_id: str, session_id: str = ""):
    if not settings.persist_chat_messages:
        return {"message": "对话持久化未启用，无需清除"}

    db = SessionLocal()
    try:
        query = db.query(ConversationMessage).filter(
            ConversationMessage.pregnant_id == pregnant_id,
        )
        if session_id:
            query = query.filter(ConversationMessage.session_id == session_id)

        deleted = query.delete()
        db.commit()
        return {"message": f"已清除 {deleted} 条对话记录", "deleted_count": deleted}
    except Exception:
        db.rollback()
        raise HTTPException(500, "清除对话历史失败")
    finally:
        db.close()


@router.get("/history")
async def get_memory(patient_id: str):
    memory = memory_manager.get_all(patient_id)
    return {"pregnant_id": patient_id, "memory": memory}


@router.delete("/memory")
async def clear_memory(patient_id: str):
    memory_manager.clear(patient_id)
    return {"message": "记忆已清除", "pregnant_id": patient_id}


@router.get("/context/{pregnant_id}")
def get_pregnant_context(pregnant_id: str):
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        context = {
            "pregnant_id": pregnant_id,
            "display_name": pregnant.display_name,
            "nickname": pregnant.nickname,
            "gestational_age_days": pregnant.gestational_age_days,
            "gestational_week": "",
            "risk_tags": pregnant.risk_tags or [],
        }

        if pregnant.gestational_age_days:
            gw = pregnant.gestational_age_days // 7
            gd = pregnant.gestational_age_days % 7
            context["gestational_week"] = f"{gw}+{gd}周"

        recent_data = (
            db.query(HealthDataPoint)
            .filter(HealthDataPoint.pregnant_id == pregnant_id)
            .order_by(HealthDataPoint.recorded_at.desc())
            .limit(10)
            .all()
        )
        context["recent_data"] = [
            {
                "metric_code": d.metric_code,
                "value": d.value,
                "unit": d.unit,
                "recorded_at": d.recorded_at.isoformat() if d.recorded_at else None,
            }
            for d in recent_data
        ]
        return context
    finally:
        db.close()


# ==================== RAG 知识库问答 ====================

class RAGAskRequest(BaseModel):
    question: str
    patient_id: str = ""
    top_k: int = 5
    category: str = ""


class RAGAskResponse(BaseModel):
    answer: str
    sources: list[dict] = []
    chunks: list[dict] = []
    rag_used: bool = False


@router.post("/rag/ask", response_model=RAGAskResponse)
async def rag_ask(req: RAGAskRequest):
    if not settings.rag_enabled:
        raise HTTPException(400, "RAG功能未启用，请设置 RAG_ENABLED=true")

    patient_context = ""
    if req.patient_id:
        db = SessionLocal()
        try:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.patient_id).first()
            if pregnant and pregnant.gestational_age_days:
                gw = pregnant.gestational_age_days // 7
                gd = pregnant.gestational_age_days % 7
                patient_context = f"孕{gw}+{gd}周"
                if pregnant.risk_tags:
                    patient_context += f" 风险: {', '.join(pregnant.risk_tags)}"
        finally:
            db.close()

    result = await rag_engine.ask(
        question=req.question,
        patient_context=patient_context,
        top_k=req.top_k,
    )
    return RAGAskResponse(**result)


@router.get("/rag/status")
def rag_status():
    db = SessionLocal()
    try:
        from ..models.vector_models import KnowledgeChunk
        from sqlalchemy import func, distinct

        total = db.query(KnowledgeChunk).count()
        categories = db.query(
            KnowledgeChunk.doc_category, func.count(KnowledgeChunk.id)
        ).group_by(KnowledgeChunk.doc_category).all()
        docs = db.query(distinct(KnowledgeChunk.doc_title)).count()
        return {
            "enabled": settings.rag_enabled,
            "total_chunks": total,
            "total_docs": docs,
            "categories": [{"category": c, "count": cnt} for c, cnt in categories],
            "db_type": settings.db_type,
            "embedding_mode": settings.embedding_mode,
        }
    finally:
        db.close()


# ==================== 健康趋势分析 ====================

@router.get("/trends/{pregnant_id}")
async def get_health_trends(pregnant_id: str):
    from ..core.trend_engine import trend_engine

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        gest_week = (pregnant.gestational_age_days // 7) if pregnant and pregnant.gestational_age_days else 0

        two_weeks_ago = datetime.now() - timedelta(days=14)
        records = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= two_weeks_ago,
        ).order_by(HealthDataPoint.recorded_at).all()

        records_data = [
            {"metric": r.metric_code, "value": r.value, "unit": r.unit, "recorded_at": str(r.recorded_at)}
            for r in records
        ]
        trends = trend_engine.analyze(records_data, gest_week=gest_week)

        return {
            "pregnant_id": pregnant_id,
            "trends": [
                {
                    "metric": t.metric,
                    "current_value": t.current_value,
                    "unit": t.unit,
                    "trend": t.trend,
                    "summary": t.summary,
                    "is_normal": t.is_normal,
                }
                for t in trends
            ],
        }
    finally:
        db.close()


# ==================== 主动问候 ====================

class ProactiveGreeting(BaseModel):
    message: str
    greeting_type: str
    icon: str


@router.get("/proactive/{pregnant_id}", response_model=ProactiveGreeting)
async def get_proactive_greeting(pregnant_id: str):
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            return ProactiveGreeting(message="欢迎回来！", greeting_type="morning", icon="👋")

        hour = datetime.now().hour
        gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0

        recent_data = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= datetime.now() - timedelta(days=1),
        ).count()

        milestones = {
            12: "NT检查（颈项透明层扫描）",
            16: "唐氏筛查",
            20: "大排畸超声检查",
            24: "糖耐量检测（OGTT）",
            28: "开始数胎动",
            30: "孕晚期开始",
            32: "胎心监护",
            36: "每周产检",
            37: "足月",
            40: "预产期",
        }
        milestone_msg = None
        for week, desc in milestones.items():
            if gw == week:
                milestone_msg = f"本周需要做{desc}哦，记得提前预约~"
                break

        if hour < 9:
            greeting_type, icon = "morning", "🌅"
            msg = (
                f"早安~今天记得记录体重和血压哦！{milestone_msg or ''}"
                if recent_data == 0
                else f"早安~今天已经记录了健康数据，真棒！{milestone_msg or '祝您今天心情愉快~'}"
            )
        elif hour < 14:
            greeting_type, icon = "afternoon", "☀️"
            msg = f"下午好~午饭后散散步对宝宝有好处哦。{milestone_msg or ''}"
        elif hour < 18:
            greeting_type, icon = "evening", "🌆"
            msg = f"傍晚好~别忘了数胎动哦，每天固定时间数一数更准确。{milestone_msg or ''}"
        else:
            greeting_type, icon = "night", "🌙"
            msg = f"晚上好~今天辛苦了，早点休息对宝宝最好。{milestone_msg or ''}"

        pending_orders = db.query(MedicalOrder).filter(
            MedicalOrder.pregnant_id == pregnant_id,
            MedicalOrder.status == "signed",
        ).count()
        if pending_orders > 0:
            msg += f"\n\n📋 您有 {pending_orders} 条新医嘱待查看，请在首页查看。"

        return ProactiveGreeting(message=msg, greeting_type=greeting_type, icon=icon)
    finally:
        db.close()
