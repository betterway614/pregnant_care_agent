"""Agno Chat Handler - 用 Agent tool loop 替代命令式 if/else 管道

当 settings.agno_enabled=True 时，Chat Router 委托给 Agno Agent，
由 Agent 自主决定调用哪些工具（NLU、规则引擎、健康数据、趋势分析等）。

增强特性：
- RunEvent 级别工具调用事件捕获，转换为用户友好的 thinking SSE 事件
- Plan-and-Execute 任务规划可视化
- 对话持久化（通过 Agno 原生 SqliteDb + conversation_store）
- 多模态音频输入支持（AUDIO message_type）
"""
from __future__ import annotations

import json
import base64
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Union

from agno.agent import RunEvent
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..database import db_call
from ..core.conversation_store import conversation_store
from ..config import settings


# 工具名称 → 用户友好的中文描述（用于前端 thinking 步骤展示）
TOOL_THINKING_MAP: dict[str, str] = {
    "agno_parse_nlu": "正在理解您的需求...",
    "agno_check_emergency": "正在进行安全检查...",
    "agno_search_knowledge": "正在查阅孕期知识库...",
    "agno_get_patient_context": "正在了解您的健康情况...",
    "agno_analyze_health_trends": "正在分析您的健康趋势...",
    "agno_evaluate_vital_rules": "正在评估健康指标...",
    "agno_save_health_data": "正在保存您的健康数据...",
    "agno_should_ask_weight": "正在检查今日记录状态...",
    "agno_should_ask_bp": "正在检查今日记录状态...",
    "agno_get_epds_result": "正在分析心理评估结果...",
}


def _generate_session_id(pregnant_id: str) -> str:
    """生成唯一的 session_id

    格式: SESS_{pregnant_id前8位}_{日期}_{随机4位}
    确保同一孕妇不同时间段的对话隔离
    """
    date_str = datetime.now().strftime("%Y%m%d")
    rand_str = uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"


def _build_multimodal_input(req: ChatSendRequest) -> Union[str, List[Dict[str, Any]]]:
    """构建多模态消息 input（支持文本和音频）

    当 message_type == "AUDIO" 时，构建包含音频的 content array，
    兼容 OpenAI 兼容的多模态模型（Qwen3.6-35B 等）。

    Returns:
        纯文本时返回字符串；音频消息时返回 content array
    """
    if req.message_type in ("AUDIO", "IMAGE") and req.audio_data:
        content_parts: List[Dict[str, Any]] = []

        text = req.message.strip() or ("请分析这段语音内容并给出回复" if req.message_type == "AUDIO" else "请分析这张图片并给出回复")
        content_parts.append({"type": "text", "text": text})

        if req.message_type == "AUDIO":
            content_parts.append({
                "type": "input_audio",
                "input_audio": {
                    "data": req.audio_data,
                    "format": req.audio_format or "webm",
                },
            })
        else:
            # IMAGE: 使用 image_url 格式（OpenAI 兼容多模态模型）
            fmt = req.audio_format or "jpeg"
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{fmt};base64,{req.audio_data}",
                },
            })

        logger.info(
            "构建多模态消息 type={} pregnant_id={} data_len={} format={}",
            req.message_type, req.pregnant_id[:8], len(req.audio_data), req.audio_format,
        )
        return content_parts

    # 纯文本消息
    return req.message.strip()


async def handle_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """主对话 Agno Agent 处理（非流式）

    Agent 自主调用工具链：parse_nlu → check_emergency → save_health_data
    → should_ask_weight → get_patient_context → analyze_health_trends → ...

    支持多模态音频输入（message_type=AUDIO 时使用多模态消息格式）
    """
    from .agno_agent import get_main_agent

    agent = get_main_agent()
    session_id = req.session_id or _generate_session_id(req.pregnant_id)

    agent_input = _build_multimodal_input(req)

    response = await agent.arun(
        input=agent_input,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    content = response.content or ""

    # 对话持久化
    if settings.persist_chat_messages:
        try:
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "user", req.message,
            )
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "assistant", content,
            )
        except Exception:
            logger.warning("非流式对话持久化失败 session_id={}", session_id, exc_info=True)

    return ChatResponse(
        content=content,
        session_id=session_id,
        source="AI_CARE",
    )


async def handle_chat_with_agno_stream(req: ChatSendRequest) -> AsyncGenerator[dict, None]:
    """主对话 Agno Agent 流式处理 — 逐 token 产出 SSE 事件

    增强特性：
    - 捕获 RunEvent.tool_call_started/completed，产出 thinking 事件
    - 工具调用过程对用户透明可见（展示 Agent 的"思考"过程）
    - 完成后持久化对话消息
    """
    from .agno_agent import get_main_agent

    agent = get_main_agent()
    session_id = req.session_id or _generate_session_id(req.pregnant_id)

    # 构建多模态输入
    agent_input = _build_multimodal_input(req)

    # 初始思考状态
    yield {"event": "thinking", "data": "小安正在思考..."}

    full_response = ""
    tool_steps: list[str] = []  # 已完成工具调用的中文描述列表

    try:
        async for chunk in agent.arun(
            input=agent_input,
            stream=True,
            stream_events=True,
            user_id=req.pregnant_id,
            session_id=session_id,
        ):
            event = chunk.event

            # 工具调用开始 → 发送 thinking 事件
            if event == RunEvent.tool_call_started and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                thinking_msg = TOOL_THINKING_MAP.get(
                    tool_name, f"正在处理（{tool_name}）..."
                )
                yield {"event": "thinking", "data": thinking_msg}

            # 工具调用完成 → 记录步骤
            elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                step_desc = TOOL_THINKING_MAP.get(tool_name, "")
                if step_desc and step_desc not in tool_steps:
                    tool_steps.append(step_desc)

            # 流式内容输出
            elif event == RunEvent.run_content:
                if chunk.content and isinstance(chunk.content, str):
                    full_response += chunk.content
                    yield {"event": "chunk", "data": chunk.content}

    except Exception:
        import traceback
        logger.error("Agno stream error: {}", traceback.format_exc())
        yield {"event": "chunk", "data": "\n\n抱歉，我遇到了问题，请稍后再试。"}

    # 发送完成事件（含工具调用步骤信息）
    yield {
        "event": "done",
        "data": json.dumps({
            "session_id": session_id,
            "source": "AI_CARE",
            "nlu_result": None,
            "memory_updated": [],
            "tool_steps": tool_steps,
        }),
    }

    # 对话持久化
    if settings.persist_chat_messages:
        try:
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "user", req.message,
            )
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "assistant", full_response,
            )
        except Exception:
            logger.warning("流式对话持久化失败 session_id={}", session_id, exc_info=True)