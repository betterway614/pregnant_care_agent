"""Agno Chat Handler - 用 Agent tool loop 替代命令式 if/else 管道

当 settings.agno_enabled=True 时，Chat Router 委托给 Agno Agent，
由 Agent 自主决定调用哪些工具（NLU、规则引擎、健康数据、趋势分析等），
替代 chat.py 中 800 行的手动流程。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import AsyncGenerator
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..database import SessionLocal, db_call
from ..core.conversation_store import conversation_store


def _generate_session_id(pregnant_id: str) -> str:
    """生成唯一的 session_id

    格式: SESS_{pregnant_id前8位}_{日期}_{随机4位}
    确保同一孕妇不同时间段的对话隔离
    """
    date_str = datetime.now().strftime("%Y%m%d")
    rand_str = uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"


async def handle_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """主对话 Agno Agent 处理

    Agent 自主调用工具链：parse_nlu → check_emergency → save_health_data
    → should_ask_weight → get_patient_context → analyze_health_trends → ...
    """
    from .agno_agent import get_main_agent

    agent = get_main_agent()

    # 会话上下文：由 Agno Agent 内存管理，不持久化对话原文
    session_id = req.session_id or _generate_session_id(req.pregnant_id)

    # 构建输入（Agent 会通过 tool 自获取患者上下文）
    user_input = req.message

    response = await agent.arun(
        input=user_input,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    content = response.content or ""

    # 对话原文不入库，仅返回响应
    return ChatResponse(
        content=content,
        session_id=session_id,
        source="AI_CARE",
    )


async def handle_followup_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """随访模式 Agno Agent 处理

    使用 followup Agent + 随访工具集，Agent 自主完成：
    get_followup_context → 逐一提问 → record_answer → complete_followup
    """
    from .agno_agent import create_followup_agent

    logger.info("AGNO_FOLLOWUP record_id={} pregnant_id={}", req.record_id, req.pregnant_id)

    # 初始数据库查询（在线程池中执行）
    initial = await db_call(_init_agno_followup_db, req.record_id, req.pregnant_id)
    if isinstance(initial, tuple):
        record, pregnant, patient_name, gest_week, risk_tags, template_name, health_education = initial
    else:
        return initial

    agent = create_followup_agent(
        patient_name=patient_name,
        gest_week=gest_week,
        risk_tags=risk_tags,
        record_id=req.record_id,
        template_name=template_name,
        health_education=health_education,
    )

    session_id = f"FU_{req.record_id[:8]}"
    response = await agent.arun(
        input=req.message,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    content = response.content or ""

    # 对话原文不入库，仅返回响应
    return ChatResponse(
        content=content,
        session_id=req.session_id or session_id,
        source="FOLLOWUP",
    )


async def handle_chat_with_agno_stream(req: ChatSendRequest) -> AsyncGenerator[dict, None]:
    """主对话 Agno Agent 流式处理 — 逐 token 产出 SSE 事件"""
    from .agno_agent import get_main_agent

    agent = get_main_agent()
    session_id = req.session_id or _generate_session_id(req.pregnant_id)

    yield {"event": "thinking", "data": "小安正在思考..."}

    full_response = ""
    try:
        async for event in agent.arun(
            input=req.message,
            stream=True,
            stream_events=True,
            user_id=req.pregnant_id,
            session_id=session_id,
        ):
            if event.event == "RunContent" and event.content:
                full_response += event.content
                yield {"event": "chunk", "data": event.content}
    except Exception:
        import traceback
        logger.error("Agno stream error: {}", traceback.format_exc())
        yield {"event": "chunk", "data": "\n\n抱歉，我遇到了问题，请稍后再试。"}

    yield {"event": "done", "data": json.dumps({
        "session_id": session_id,
        "source": "AI_CARE",
        "nlu_result": None,
        "memory_updated": [],
    })}

    try:
        await conversation_store.async_save_single(session_id, req.pregnant_id, "user", req.message)
        await conversation_store.async_save_single(session_id, req.pregnant_id, "assistant", full_response)
    except Exception:
        logger.warning("主对话流式持久化失败 session_id={}", session_id, exc_info=True)


async def handle_followup_chat_with_agno_stream(req: ChatSendRequest) -> AsyncGenerator[dict, None]:
    """随访模式 Agno Agent 流式处理 — 逐 token 产出 SSE 事件"""
    from .agno_agent import create_followup_agent
    import traceback

    logger.info("AGNO_FOLLOWUP_STREAM record_id={} pregnant_id={}", req.record_id, req.pregnant_id)

    initial = await db_call(_init_agno_followup_db, req.record_id, req.pregnant_id)
    if isinstance(initial, ChatResponse):
        yield {"event": "chunk", "data": initial.content}
        yield {"event": "done", "data": json.dumps({
            "session_id": req.session_id or f"FU_{req.record_id[:8]}",
            "source": "FOLLOWUP",
            "nlu_result": None,
            "memory_updated": [],
        })}
        return

    record, pregnant, patient_name, gest_week, risk_tags, template_name, health_education = initial

    agent = create_followup_agent(
        patient_name=patient_name,
        gest_week=gest_week,
        risk_tags=risk_tags,
        record_id=req.record_id,
        template_name=template_name,
        health_education=health_education,
    )

    session_id = f"FU_{req.record_id[:8]}"

    yield {"event": "thinking", "data": "小安正在为您进行随访..."}

    full_response = ""
    try:
        async for event in agent.arun(
            input=req.message,
            stream=True,
            stream_events=True,
            user_id=req.pregnant_id,
            session_id=session_id,
        ):
            if event.event == "RunContent" and event.content:
                full_response += event.content
                yield {"event": "chunk", "data": event.content}
    except Exception:
        logger.error("Agno followup stream error: {}", traceback.format_exc())

    yield {"event": "done", "data": json.dumps({
        "session_id": req.session_id or session_id,
        "source": "FOLLOWUP",
        "nlu_result": None,
        "memory_updated": [],
    })}

    try:
        await conversation_store.async_save_single(session_id, req.pregnant_id, "user", req.message)
        await conversation_store.async_save_single(session_id, req.pregnant_id, "assistant", full_response)
    except Exception:
        logger.warning("随访流式持久化失败 session_id={}", session_id, exc_info=True)


def _init_agno_followup_db(record_id: str, pregnant_id: str):
    """同步函数：随访 Agent 初始数据库查询（在线程池中执行）"""
    from uuid import UUID
    from ..models import FollowUpRecord, Pregnant
    from ..database import SessionLocal
    from ..services.followup_service import FOLLOWUP_TEMPLATES
    from ..schemas import FOLLOWUP_ACTIVE_STATUSES, FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CONFIRMED, FOLLOWUP_STATUS_ARCHIVED

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
        if not record:
            return ChatResponse(content="随访记录不存在。")
        if str(record.pregnant_id) != pregnant_id:
            return ChatResponse(content="孕妇信息不匹配，无法继续随访。")

        # 已完成/已确认/已归档 → 显示完成信息
        if record.status in (FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CONFIRMED, FOLLOWUP_STATUS_ARCHIVED):
            date_str = record.follow_up_date.strftime('%Y-%m-%d %H:%M') if record.follow_up_date else "未知时间"
            return ChatResponse(
                content=f"本次随访已于 {date_str} 完成。\n\n摘要：{record.summary or '无'}",
            )

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()

        patient_name = pregnant.nickname or pregnant.display_name if pregnant else "准妈妈"
        gest_week = f"{pregnant.gestational_age_days // 7}+{pregnant.gestational_age_days % 7}" if pregnant and pregnant.gestational_age_days else "?"
        risk_tags = pregnant.risk_tags if pregnant else []

        # 反向推断模板名称
        template_name = "standard"
        for tid, tmpl in FOLLOWUP_TEMPLATES.items():
            if tmpl["name"] in (record.self_reported_data or {}).get("_template", ""):
                template_name = tid
                break

        return (
            record,
            pregnant,
            patient_name,
            gest_week,
            risk_tags,
            template_name,
            record.health_education,
        )
    finally:
        db.close()
