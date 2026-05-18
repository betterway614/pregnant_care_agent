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
from ..database import db_call
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
            # 只处理 RunContent 事件，且内容必须是字符串（过滤工具返回的 dict）
            if event.event == "RunContent" and event.content and isinstance(event.content, str):
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
