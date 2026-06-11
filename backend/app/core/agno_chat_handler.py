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
import time
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Union

from agno.agent import RunEvent
from agno.media import Image as AgnoImage
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..core.conversation_store import conversation_store
from ..config import settings, get_asr_mode
from ..services.audit_service import AuditService
from .agno_tools import set_nlu_context, pop_nlu_context

# 保持后台审计任务引用，防止 fire-and-forget 被 GC 回收
_audit_tasks: set = set()

# 工具名称 → 用户友好的中文描述（用于前端 thinking 步骤展示）
TOOL_THINKING_MAP: dict[str, str] = {
    "agno_parse_nlu": "正在理解您的需求...",
    "agno_get_nlu_result": "正在理解您的需求...",
    "agno_check_emergency": "正在进行安全检查...",
    "search_knowledge_base": "正在查阅孕期知识库...",
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

    格式: SESS_{pregnant_id前8位}_{日期(北京时间)}_{随机4位}
    确保同一孕妇不同时间段的对话隔离
    """
    from ..utils.timezone import beijing_now
    date_str = beijing_now().strftime("%Y%m%d")
    rand_str = uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"


def _validate_session_id(session_id: str | None, pregnant_id: str) -> str | None:
    """校验 session_id 归属，防止客户端注入他人会话 ID

    合法的 session_id 必须以 SESS_{pregnant_id前8位} 开头。
    不合法则返回 None，由调用方重新生成。
    """
    if not session_id:
        return None
    expected_prefix = f"SESS_{pregnant_id[:8]}"
    if not session_id.startswith(expected_prefix):
        logger.warning("session_id 归属校验失败: {} vs expected prefix {}", session_id[:20], expected_prefix)
        return None
    return session_id


# _save_audit_log 已迁移到 app/services/audit_service.py → AuditService.save_log()


async def _transcribe_audio_pregnant(audio_data: str, audio_format: str) -> str:
    """小安对话 ASR 预处理：调用专用 ASR 服务（cloud/local）转录音频为文本。

    音频不会嵌入主对话请求，避免浪费 token。

    Returns:
        转录文本（失败时返回错误提示文本，不会返回 None）
    """
    from ..services.asr_service import asr_service

    mode = get_asr_mode("pregnant")
    logger.info("[ASR-pregnant] mode={}", mode)

    transcribed = await asr_service.transcribe(audio_data, audio_format, "pregnant")
    if transcribed:
        logger.info("[ASR-pregnant] 转录成功: {}字", len(transcribed))
        return transcribed

    logger.warning("[ASR-pregnant] ASR 转录失败")
    return "（语音识别失败，请重试或使用文字输入）"


def _build_multimodal_input(req: ChatSendRequest, transcribed_text: str | None = None) -> str:
    """构建消息 input 文本

    - AUDIO：始终使用 ASR 转录后的纯文本
    - IMAGE：返回附带文字说明（图片通过 _build_images 单独传递给 Agent）
    - TEXT：纯文本

    Returns:
        消息文本字符串
    """
    if req.message_type == "AUDIO" and req.audio_data:
        return transcribed_text or "（语音识别失败，请重试或使用文字输入）"

    if req.message_type == "IMAGE":
        img_count = _count_images(req)
        default_text = f"请分析这{img_count}张图片并给出回复" if img_count > 1 else "请分析这张图片并给出回复"
        return req.message.strip() or default_text

    return req.message.strip()


def _count_images(req: ChatSendRequest) -> int:
    """计算请求中的图片数量"""
    if req.images:
        return len(req.images)
    if req.audio_data and req.message_type == "IMAGE":
        return 1
    return 0


def _build_images(req: ChatSendRequest) -> list[AgnoImage] | None:
    """从请求中提取图片，构建 Agno Image 对象列表

    Agno 框架通过 agent.arun(images=...) 参数传递多模态图片，
    框架内部会自动转换为 OpenAI 兼容的 image_url 格式。
    """
    if req.message_type != "IMAGE":
        return None

    images: list[AgnoImage] = []

    if req.images:
        # 新的多图字段
        for img in req.images:
            fmt = img.format or "jpeg"
            images.append(AgnoImage(url=f"data:image/{fmt};base64,{img.data}"))
    elif req.audio_data:
        # 兼容旧的单图字段
        fmt = req.audio_format or "jpeg"
        images.append(AgnoImage(url=f"data:image/{fmt};base64,{req.audio_data}"))

    if images:
        logger.info(
            "构建图片对象 IMAGE pregnant_id={} count={}",
            req.pregnant_id[:8], len(images),
        )
    return images if images else None


async def handle_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """主对话 Agno Agent 处理（非流式）— 工具路由 + 审计日志"""
    from .agno_agent import AGENT_VARIANT_MAP, get_main_agent

    session_id = _validate_session_id(req.session_id, req.pregnant_id) or _generate_session_id(req.pregnant_id)
    start_time = time.time()

    # ASR 预处理
    transcribed_text = None
    if req.message_type == "AUDIO" and req.audio_data:
        transcribed_text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)

    agent_input = _build_multimodal_input(req, transcribed_text)
    agent_images = _build_images(req)  # 多模态图片（通过 Agno images 参数传递）

    # 1. 快速意图分类（复用 NLU 引擎，不通过 Agent 减少一次 LLM 调用）
    nlu_result = None
    intent_variant = "complex"
    try:
        from ..core.nlu_engine import nlu_engine
        user_text = req.message.strip() if req.message else ""
        if user_text:
            nlu_result = nlu_engine.parse(user_text)

            # UNKNOWN 意图：尝试 LLM 辅助分类（同步 LLM 调用移到线程池，避免阻塞事件循环）
            if nlu_result.intent == "UNKNOWN":
                import asyncio
                refined_intent = await asyncio.to_thread(nlu_engine.classify_with_llm, user_text)
                if refined_intent != "UNKNOWN":
                    from .nlu_engine import NLUResult as _NR
                    nlu_result.intent = refined_intent
                    nlu_result.category = nlu_engine._classify_category(
                        refined_intent, nlu_result.entities, user_text,
                    )

            nlu_dict = {
                "intent": nlu_result.intent,
                "entities": nlu_result.entities,
                "emotion": nlu_result.emotion,
                "is_emergency": nlu_result.is_emergency,
                "suggested_tools": nlu_result.suggested_tools,
            }
            from .agno_tools import resolve_tools_by_intent
            _, intent_variant = resolve_tools_by_intent(nlu_dict)
            # 注入 NLU 结果到模块级上下文
            set_nlu_context(session_id, nlu_dict)
        else:
            # 空消息：默认使用聊天变体 + GREETING 意图（避免审计日志为空）
            intent_variant = "chat"
    except Exception:
        logger.warning("NLU意图分类失败，使用兜底Agent", exc_info=True)

    # 复杂症状/检查查询走工作流（多步编排）；图片消息跳过（工作流不支持多模态）
    if not agent_images and intent_variant == "complex" and nlu_result and nlu_result.intent in ("ASK_SYMPTOM", "ASK_EXAM", "KNOWLEDGE_QUERY"):
        try:
            from .agno_workflow import create_prenatal_workflow
            workflow = create_prenatal_workflow()
            workflow.session_state = {"patient_id": req.pregnant_id, "risk_level": "routine"}
            logger.info("路由到孕检工作流 intent={}", nlu_result.intent)
            workflow_response = await workflow.arun(input=agent_input)
            content = workflow_response.content if hasattr(workflow_response, "content") else str(workflow_response) if workflow_response is not None else None
            if content:
                elapsed_ms = int((time.time() - start_time) * 1000)
                import asyncio
                # 为工作流响应构造兼容结构（用于审计日志）
                class _WorkflowResponse:
                    def __init__(self, wf_resp):
                        self.content = getattr(wf_resp, "content", "") or ""
                        self.messages = getattr(wf_resp, "messages", []) or []
                        self.metrics = getattr(wf_resp, "metrics", None)
                        self.model = getattr(wf_resp, "model", "") or ""
                audit_log_id = await asyncio.to_thread(
                    AuditService.save_log,
                    session_id=session_id,
                    user_id=req.pregnant_id,
                    agent_role="pregnant",
                    agent_variant="workflow",
                    intent_classification=nlu_result.intent,
                    user_message=req.message,
                    nlu_detail=nlu_dict if nlu_result else None,
                    run_response=_WorkflowResponse(workflow_response),
                    total_latency_ms=elapsed_ms,
                )
                if settings.persist_chat_messages:
                    try:
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "user", req.message)
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "assistant", content)
                    except Exception:
                        logger.warning("工作流对话持久化失败 session_id={}", session_id, exc_info=True)
                return ChatResponse(content=content, session_id=session_id, source="AI_CARE", audit_log_id=audit_log_id)
        except Exception as e:
            logger.warning("工作流路由失败，回退到单Agent: {}", e)

    # 2. 注入 NLU 预分析结果到 agent_input，避免 Agent 内重复调用 agno_parse_nlu
    if nlu_result:
        nlu_context = (
            f"[系统预分析] 意图:{nlu_result.intent} "
            f"情绪:{nlu_result.emotion.get('level', 'neutral') if nlu_result.emotion else 'neutral'} "
            f"紧急:{nlu_result.is_emergency} "
            f"实体:{nlu_result.entities}\n\n"
        )
        if isinstance(agent_input, str):
            agent_input = nlu_context + agent_input

    # 3. Agent 路由
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()

    # 4. arun
    response = await agent.arun(
        input=agent_input,
        images=agent_images,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    elapsed_ms = int((time.time() - start_time) * 1000)
    content = response.content or ""

    # 5. 审计日志（通过线程池执行同步 DB 写入，避免阻塞事件循环）
    import asyncio
    audit_log_id = await asyncio.to_thread(
        AuditService.save_log,
        session_id=session_id,
        user_id=req.pregnant_id,
        agent_role="pregnant",
        agent_variant=intent_variant,
        intent_classification=nlu_result.intent if nlu_result else None,
        user_message=req.message,
        nlu_detail=nlu_dict if nlu_result else None,
        run_response=response,
        total_latency_ms=elapsed_ms,
    )

    # 6. 对话持久化
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

    # 清理 NLU 上下文
    pop_nlu_context(session_id)

    return ChatResponse(
        content=content,
        session_id=session_id,
        source="AI_CARE",
        audit_log_id=audit_log_id,
    )


async def handle_chat_with_agno_stream(req: ChatSendRequest) -> AsyncGenerator[dict, None]:
    """主对话 Agno Agent 流式处理 — 工具路由 + 审计日志"""
    from .agno_agent import AGENT_VARIANT_MAP, get_main_agent

    session_id = _validate_session_id(req.session_id, req.pregnant_id) or _generate_session_id(req.pregnant_id)
    start_time = time.time()

    # ASR 预处理
    transcribed_text = None
    if req.message_type == "AUDIO" and req.audio_data:
        transcribed_text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)

    agent_input = _build_multimodal_input(req, transcribed_text)
    agent_images = _build_images(req)  # 多模态图片（通过 Agno images 参数传递）

    # 1. 快速意图分类
    nlu_result = None
    intent_variant = "complex"
    try:
        from ..core.nlu_engine import nlu_engine
        user_text = req.message.strip() if req.message else ""
        if user_text:
            nlu_result = nlu_engine.parse(user_text)

            # UNKNOWN 意图：尝试 LLM 辅助分类（同步 LLM 调用移到线程池，避免阻塞事件循环）
            if nlu_result.intent == "UNKNOWN":
                import asyncio
                refined_intent = await asyncio.to_thread(nlu_engine.classify_with_llm, user_text)
                if refined_intent != "UNKNOWN":
                    from .nlu_engine import NLUResult as _NR
                    nlu_result.intent = refined_intent
                    nlu_result.category = nlu_engine._classify_category(
                        refined_intent, nlu_result.entities, user_text,
                    )

            nlu_dict = {
                "intent": nlu_result.intent,
                "entities": nlu_result.entities,
                "emotion": nlu_result.emotion,
                "is_emergency": nlu_result.is_emergency,
                "suggested_tools": nlu_result.suggested_tools,
            }
            from .agno_tools import resolve_tools_by_intent
            _, intent_variant = resolve_tools_by_intent(nlu_dict)
            # 注入 NLU 结果到模块级上下文
            set_nlu_context(session_id, nlu_dict)
        else:
            # 空消息：默认使用聊天变体（避免审计日志为空）
            intent_variant = "chat"
    except Exception:
        logger.warning("NLU意图分类失败，使用兜底Agent", exc_info=True)

    # 复杂症状/检查查询走工作流（多步编排）；图片消息跳过（工作流不支持多模态）
    if not agent_images and intent_variant == "complex" and nlu_result and nlu_result.intent in ("ASK_SYMPTOM", "ASK_EXAM", "KNOWLEDGE_QUERY"):
        try:
            from .agno_workflow import create_prenatal_workflow
            workflow = create_prenatal_workflow()
            workflow.session_state = {"patient_id": req.pregnant_id, "risk_level": "routine"}
            logger.info("路由到孕检工作流 intent={}", nlu_result.intent)
            workflow_response = await workflow.arun(input=agent_input)
            content = workflow_response.content if hasattr(workflow_response, "content") else str(workflow_response) if workflow_response is not None else None
            if content:
                yield {"event": "chunk", "data": content}
                elapsed_ms = int((time.time() - start_time) * 1000)
                import asyncio
                class _WorkflowResponse:
                    def __init__(self, wf_resp):
                        self.content = getattr(wf_resp, "content", "") or ""
                        self.messages = getattr(wf_resp, "messages", []) or []
                        self.metrics = getattr(wf_resp, "metrics", None)
                        self.model = getattr(wf_resp, "model", "") or ""
                audit_log_id = await asyncio.to_thread(
                    AuditService.save_log,
                    session_id=session_id,
                    user_id=req.pregnant_id,
                    agent_role="pregnant",
                    agent_variant="workflow",
                    intent_classification=nlu_result.intent,
                    user_message=req.message,
                    nlu_detail=nlu_dict if nlu_result else None,
                    run_response=_WorkflowResponse(workflow_response),
                    total_latency_ms=elapsed_ms,
                )
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "session_id": session_id,
                        "source": "AI_CARE",
                        "nlu_result": None,
                        "memory_updated": [],
                        "tool_steps": ["工作流处理"],
                        "transcribed_text": transcribed_text,
                        "audit_log_id": audit_log_id,
                    }),
                }
                if settings.persist_chat_messages:
                    try:
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "user", req.message)
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "assistant", content)
                    except Exception:
                        logger.warning("工作流对话持久化失败 session_id={}", session_id, exc_info=True)
                return  # Exit the generator, skip single Agent path
        except Exception as e:
            logger.warning("工作流路由失败，回退到单Agent: {}", e)

    # 2. 注入 NLU 预分析结果到 agent_input，避免 Agent 内重复调用 agno_parse_nlu
    if nlu_result:
        nlu_context = (
            f"[系统预分析] 意图:{nlu_result.intent} "
            f"情绪:{nlu_result.emotion.get('level', 'neutral') if nlu_result.emotion else 'neutral'} "
            f"紧急:{nlu_result.is_emergency} "
            f"实体:{nlu_result.entities}\n\n"
        )
        if isinstance(agent_input, str):
            agent_input = nlu_context + agent_input

    # 3. Agent 路由
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()

    # 初始思考状态
    yield {"event": "thinking", "data": "小安正在思考..."}

    full_response = ""
    tool_steps: list[str] = []
    run_response = None

    try:
        try:
            async for chunk in agent.arun(
                input=agent_input,
                images=agent_images,
                stream=True,
                stream_events=True,
                user_id=req.pregnant_id,
                session_id=session_id,
            ):
                event = chunk.event

                if event == RunEvent.tool_call_started and chunk.tool is not None:
                    tool_name = getattr(chunk.tool, "tool_name", "") or ""
                    thinking_msg = TOOL_THINKING_MAP.get(
                        tool_name, f"正在处理（{tool_name}）..."
                    )
                    yield {"event": "thinking", "data": thinking_msg}

                elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                    tool_name = getattr(chunk.tool, "tool_name", "") or ""
                    step_desc = TOOL_THINKING_MAP.get(tool_name, "")
                    if step_desc and step_desc not in tool_steps:
                        tool_steps.append(step_desc)

                elif event == RunEvent.run_content:
                    if chunk.content and isinstance(chunk.content, str):
                        full_response += chunk.content
                        yield {"event": "chunk", "data": chunk.content}

                elif event == RunEvent.run_completed:
                    run_response = chunk

            # 兜底：当 Agent 使用 output_schema 时，run_content 不会触发，
            # 结构化输出需从 run_response.content 提取并发送到前端。
            if not full_response and run_response is not None:
                from .agno_medical_agents import format_structured_output_to_markdown
                fallback_text = format_structured_output_to_markdown(run_response.content)
                if fallback_text:
                    yield {"event": "chunk", "data": fallback_text}

        except Exception:
            import traceback
            logger.error("Agno stream error: {}", traceback.format_exc())
            yield {"event": "chunk", "data": "\n\n抱歉，我遇到了问题，请稍后再试。"}

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 先 yield done，避免审计日志写入阻塞 SSE 流式结束
        yield {
            "event": "done",
            "data": json.dumps({
                "session_id": session_id,
                "source": "AI_CARE",
                "nlu_result": None,
                "memory_updated": [],
                "tool_steps": tool_steps,
                "transcribed_text": transcribed_text,
            }),
        }

        # 审计日志（后台异步写入，不阻塞 SSE 响应）
        import asyncio
        _bg_audit_task = asyncio.create_task(asyncio.to_thread(
            AuditService.save_log,
            session_id=session_id,
            user_id=req.pregnant_id,
            agent_role="pregnant",
            agent_variant=intent_variant,
            intent_classification=nlu_result.intent if nlu_result else None,
            user_message=req.message,
            nlu_detail=nlu_dict if nlu_result else None,
            run_response=run_response,
            total_latency_ms=elapsed_ms,
        ))
        _bg_audit_task.add_done_callback(_audit_tasks.discard)
        _audit_tasks.add(_bg_audit_task)

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
    finally:
        # 保证客户端断开时也能清理 NLU 上下文，防止内存泄漏
        pop_nlu_context(session_id)