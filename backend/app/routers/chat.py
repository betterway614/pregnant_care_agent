"""对话管理 API - Agno Agent 生产路径"""
import json
import uuid as _uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..core import memory_manager
from ..core.agno_knowledge import knowledge
from ..core.agno_chat_handler import handle_chat_with_agno, handle_chat_with_agno_stream
from ..core.auth import get_current_user, TokenPayload
from ..models import HealthDataPoint, Pregnant, MedicalOrder, ConversationMessage
from ..database import get_db
from ..config import settings
from ..utils.timezone import beijing_now

router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])


def _generate_session_id(pregnant_id: str) -> str:
    date_str = beijing_now().strftime("%Y%m%d")
    rand_str = _uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"


@router.get("/ping")
def ping(user: TokenPayload = Depends(get_current_user)):
    return {"pong": beijing_now().isoformat(), "version": "agno_v1"}


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatSendRequest, user: TokenPayload = Depends(get_current_user)):
    """发送对话消息（Agno Agent）"""
    if user.role == "pregnant" and user.pregnant_id != req.pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    logger.info("send_message pregnant_id={}", req.pregnant_id[:8])
    return await handle_chat_with_agno(req)


@router.post("/send/stream")
async def send_message_stream(req: ChatSendRequest, user: TokenPayload = Depends(get_current_user)):
    """发送对话消息（SSE 流式）"""
    if user.role == "pregnant" and user.pregnant_id != req.pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    return EventSourceResponse(handle_chat_with_agno_stream(req), ping=15)


class ASRRequest(BaseModel):
    audio_data: str
    audio_format: str = "webm"


class ASRResponse(BaseModel):
    text: str
    success: bool


@router.post("/asr", response_model=ASRResponse)
async def transcribe_audio(req: ASRRequest, user: TokenPayload = Depends(get_current_user)):
    """语音转文字（独立 ASR 接口，用于前端语音气泡长按转文本）

    支持 cloud/local 两种模式，调用专用 ASR 服务转录。
    """
    from ..core.agno_chat_handler import _transcribe_audio_pregnant

    text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)
    success = not text.startswith("（")
    return ASRResponse(text=text, success=success)


@router.get("/conversation/{pregnant_id}")
async def get_conversation_history(pregnant_id: str, session_id: str = "", user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    if not settings.persist_chat_messages:
        return {"session_id": session_id, "messages": [], "message": "对话持久化未启用"}

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


@router.delete("/conversation/{pregnant_id}")
async def clear_conversation_history(pregnant_id: str, session_id: str = "", user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    if not settings.persist_chat_messages:
        return {"message": "对话持久化未启用，无需清除"}

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


@router.get("/history")
async def get_memory(pregnant_id: str, user: TokenPayload = Depends(get_current_user)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    memory = memory_manager.get_all(pregnant_id)
    return {"pregnant_id": pregnant_id, "memory": memory}


@router.get("/sessions/{pregnant_id}")
async def list_sessions(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出该孕妇的所有历史会话（按时间倒序）"""
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    if not settings.persist_chat_messages:
        return {"sessions": []}

    from sqlalchemy import func

    # 查询所有不同的 session_id 及其消息数和最新时间
    rows = (
        db.query(
            ConversationMessage.session_id,
            func.count(ConversationMessage.id).label("message_count"),
            func.min(ConversationMessage.created_at).label("started_at"),
            func.max(ConversationMessage.created_at).label("last_message_at"),
        )
        .filter(ConversationMessage.pregnant_id == pregnant_id)
        .group_by(ConversationMessage.session_id)
        .order_by(func.max(ConversationMessage.created_at).desc())
        .limit(50)
        .all()
    )

    sessions = []
    for row in rows:
        # 获取该会话的第一条用户消息作为预览
        first_user_msg = (
            db.query(ConversationMessage.content)
            .filter(
                ConversationMessage.pregnant_id == pregnant_id,
                ConversationMessage.session_id == row.session_id,
                ConversationMessage.role == "user",
            )
            .order_by(ConversationMessage.created_at.asc())
            .first()
        )
        preview = first_user_msg.content[:50] if first_user_msg else ""

        sessions.append({
            "session_id": row.session_id,
            "message_count": row.message_count,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "preview": preview,
        })

    return {"sessions": sessions}


@router.delete("/memory")
async def clear_memory(pregnant_id: str, user: TokenPayload = Depends(get_current_user)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    memory_manager.clear(pregnant_id)
    return {"message": "记忆已清除", "pregnant_id": pregnant_id}


@router.get("/context/{pregnant_id}")
def get_pregnant_context(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")

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
async def rag_ask(req: RAGAskRequest, user: TokenPayload = Depends(get_current_user)):
    if user.role == "pregnant" and req.patient_id and user.pregnant_id != req.patient_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    if not settings.rag_enabled:
        raise HTTPException(400, "RAG功能未启用，请设置 RAG_ENABLED=true")
    if knowledge is None:
        raise HTTPException(503, "知识库服务暂不可用。请检查 pgvector PostgreSQL 连接和 DB_TYPE 配置。")

    try:
        results = knowledge.search(query=req.question, max_results=req.top_k)

        if not results:
            return RAGAskResponse(
                answer="抱歉，未找到相关医学知识。建议咨询产检医生。",
                sources=[],
                chunks=[],
                rag_used=False,
            )

        chunks = []
        sources = []
        for doc in results:
            content = doc.content[:200] if hasattr(doc, "content") else str(doc)[:200]
            source_name = getattr(doc, "name", "unknown")
            chunks.append({"content": content, "similarity": getattr(doc, "score", 0)})
            sources.append({"title": source_name, "category": "knowledge"})

        knowledge_text = "\n\n".join([
            f"【来源: {getattr(doc, 'name', '未知')}】\n{doc.content[:300]}"
            for doc in results
        ])
        answer = f"根据知识库信息：\n{knowledge_text}\n\n以上为参考信息，如需更详细解答，请咨询产检医生。"

        return RAGAskResponse(
            answer=answer,
            sources=sources,
            chunks=chunks,
            rag_used=True,
        )
    except Exception as e:
        raise HTTPException(500, f"知识检索失败: {str(e)}")


@router.get("/rag/status")
def rag_status(user: TokenPayload = Depends(get_current_user)):
    """获取 RAG 系统状态，包含实时健康监控结果

    返回:
        - 配置信息 (search_type, embedding_model 等)
        - knowledge 实例可用性 (实时检索测试)
        - 健康监控状态 (后台定时探针的最新结果，含嵌入服务和 pgvector 的独立状态)
        - 降级标志和原因
    """
    # ── 基础配置 ──
    result = {
        "enabled": settings.rag_enabled,
        "search_type": settings.rag_search_type,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_api_url": settings.embedding_api_url,
        "max_results": settings.rag_max_results,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "vector_db": "pgvector",
        "knowledge_table": settings.agno_knowledge_table,
    }

    # ── knowledge 实例状态 ──
    if knowledge is None:
        result["knowledge_status"] = "unavailable (knowledge instance is None)"
        result["rag_degraded"] = True
        result["rag_degraded_reason"] = "knowledge instance is None — check DB_TYPE=postgres and pgvector"
        result["health_monitor"] = None
        return result

    # ── 实时检索测试 ──
    try:
        search_results = knowledge.search(query="test", max_results=1)
        result["knowledge_status"] = "available" if search_results else "empty (no chunks ingested)"
    except Exception as e:
        result["knowledge_status"] = f"unavailable (search failed: {str(e)[:200]})"

    # ── 健康监控状态 (来自后台定时探针) ──
    try:
        from ..core.rag_health_monitor import get_health_status
        health = get_health_status()
        result["health_monitor"] = {
            "embedding_service": health.get("embedding_service", "unknown"),
            "pgvector": health.get("pgvector", "unknown"),
            "last_check_time": health.get("last_check_time"),
            "consecutive_failures": health.get("consecutive_failures", 0),
            "degraded": health.get("degraded", False),
            "degraded_reason": health.get("degraded_reason", ""),
        }
    except Exception:
        result["health_monitor"] = None

    # ── 综合降级状态 ──
    from ..core.agno_knowledge import is_rag_degraded, get_rag_degraded_reason
    result["rag_degraded"] = is_rag_degraded()
    if result["rag_degraded"]:
        result["rag_degraded_reason"] = get_rag_degraded_reason()

    return result


# ==================== 健康趋势分析 ====================

@router.get("/trends/{pregnant_id}")
async def get_health_trends(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")
    from ..core.trend_engine import trend_engine

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    gest_week = (pregnant.gestational_age_days // 7) if pregnant and pregnant.gestational_age_days else 0

    two_weeks_ago = beijing_now() - timedelta(days=14)
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


# ==================== 主动问候 ====================

class ProactiveGreeting(BaseModel):
    message: str
    greeting_type: str
    icon: str


@router.get("/proactive/{pregnant_id}", response_model=ProactiveGreeting)
async def get_proactive_greeting(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return ProactiveGreeting(message="欢迎回来！", greeting_type="morning", icon="👋")

    hour = beijing_now().hour
    gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0

    recent_data = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= beijing_now() - timedelta(days=1),
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
