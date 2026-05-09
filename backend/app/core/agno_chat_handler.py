"""Agno Chat Handler - 用 Agent tool loop 替代命令式 if/else 管道

当 settings.agno_enabled=True 时，Chat Router 委托给 Agno Agent，
由 Agent 自主决定调用哪些工具（NLU、规则引擎、健康数据、趋势分析等），
替代 chat.py 中 800 行的手动流程。
"""
from __future__ import annotations

import json
from uuid import UUID

from ..schemas import ChatSendRequest, ChatResponse, ChatNLUResult
from ..models import FollowUpRecord, Pregnant
from ..database import SessionLocal
from ..core.conversation_store import conversation_store


async def handle_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """主对话 Agno Agent 处理

    Agent 自主调用工具链：parse_nlu → check_emergency → save_health_data
    → should_ask_weight → get_patient_context → analyze_health_trends → ...
    """
    from .agno_agent import create_main_agent

    agent = create_main_agent()

    # 加载对话历史
    session_id = req.session_id or f"SESS_{req.pregnant_id[:8]}"
    history = conversation_store.load_history(session_id, req.pregnant_id)

    # 构建输入（Agent 会通过 tool 自获取患者上下文）
    user_input = req.message

    response = await agent.arun(
        input=user_input,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    content = response.content or ""

    # 持久化对话
    try:
        conversation_store.save_single(session_id, req.pregnant_id, "user", req.message)
        conversation_store.save_single(session_id, req.pregnant_id, "assistant", content)
    except Exception:
        pass

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

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(req.record_id)
        ).first()
        if not record:
            return ChatResponse(content="随访记录不存在。", session_id=req.session_id)
        if str(record.pregnant_id) != req.pregnant_id:
            return ChatResponse(content="孕妇信息不匹配，无法继续随访。", session_id=req.session_id)

        if record.status == "confirmed":
            return ChatResponse(
                content=f"本次随访已于 {record.follow_up_date.strftime('%Y-%m-%d %H:%M')} 完成。\n\n摘要：{record.summary or '无'}",
                session_id=req.session_id,
            )

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == req.pregnant_id
        ).first()

        patient_name = pregnant.nickname or pregnant.display_name if pregnant else "准妈妈"
        gest_week = f"{pregnant.gestational_age_days // 7}+{pregnant.gestational_age_days % 7}" if pregnant and pregnant.gestational_age_days else "?"
        risk_tags = pregnant.risk_tags if pregnant else []

        # 反向推断模板名称
        from ..services.followup_service import FOLLOWUP_TEMPLATES
        template_name = "standard"
        for tid, tmpl in FOLLOWUP_TEMPLATES.items():
            if tmpl["name"] in (record.self_reported_data or {}).get("_template", ""):
                template_name = tid
                break

        agent = create_followup_agent(
            patient_name=patient_name,
            gest_week=gest_week,
            risk_tags=risk_tags,
            record_id=req.record_id,
            template_name=template_name,
            health_education=record.health_education,
        )

        session_id = f"FU_{req.record_id[:8]}"
        response = await agent.arun(
            input=req.message,
            user_id=req.pregnant_id,
            session_id=session_id,
        )

        content = response.content or ""

        # 持久化
        try:
            conversation_store.save_single(session_id, req.pregnant_id, "user", req.message)
            conversation_store.save_single(session_id, req.pregnant_id, "assistant", content)
        except Exception:
            pass

        return ChatResponse(
            content=content,
            session_id=req.session_id or session_id,
            source="FOLLOWUP",
        )
    finally:
        db.close()
