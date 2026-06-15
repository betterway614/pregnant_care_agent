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

from agno.media import Image as AgnoImage
from .agno_sse import AgnoSseConfig, AgnoSseState, agno_sse_event_generator
from loguru import logger

from ..schemas import ChatSendRequest, ChatResponse
from ..core.conversation_store import conversation_store
from ..config import settings, get_asr_mode
from ..services.audit_service import AuditService
from .agno_tools import set_nlu_context, pop_nlu_context, tool_metrics

# 保持后台审计任务引用，防止 fire-and-forget 被 GC 回收
_audit_tasks: set = set()

# NLU 实体 key → health_data_service METRIC_MAP key 映射
_NLU_ENTITY_TO_METRIC: dict[str, str] = {
    "weight": "weight",
    "sbp": "systolic",
    "dbp": "diastolic",
    "fetal_movement": "fetal_movement",
    "blood_sugar": "blood_sugar",
    "heart_rate": "heart_rate",
    "sleep_hours": "sleep_hours",
}

# 健康数据合理范围校验 (min, max)
_METRIC_RANGES: dict[str, tuple[float, float]] = {
    "weight": (30, 200),
    "systolic": (60, 250),
    "diastolic": (30, 180),
    "fetal_movement": (0, 50),
    "blood_sugar": (1, 30),
    "heart_rate": (40, 220),
    "sleep_hours": (0, 24),
}


def _auto_save_nlu_health_data(pregnant_id: str, entities: dict) -> dict:
    """根据 NLU 提取的实体自动保存健康数据到数据库

    在 Agent 执行前调用，确保数据不依赖 LLM 工具调用决策。
    已存在的当日记录会被跳过（去重）。

    Returns:
        {"saved": [...], "skipped": [...]}
    """
    from .health_data_service import save_health_metrics, HealthDataSource
    from ..database import SessionLocal
    from ..models import HealthDataPoint
    from datetime import date, datetime, timedelta

    metrics_to_save: dict = {}
    for nlukey, value in _NLU_ENTITY_TO_METRIC.items():
        if nlukey not in entities:
            continue
        val = entities[nlukey]
        if val is None:
            continue
        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue
        # 范围校验
        range_check = _METRIC_RANGES.get(value)
        if range_check:
            lo, hi = range_check
            if fval < lo or fval > hi:
                logger.info("NLU实体值超出合理范围，跳过自动保存: key=%s value=%s range=%s", nlukey, fval, range_check)
                continue
        metrics_to_save[value] = fval

    if not metrics_to_save:
        return {"saved": [], "skipped": []}

    # 当日去重：查询今日已记录的 metric_codes
    today_start = datetime.combine(date.today(), datetime.min.time())
    db = SessionLocal()
    try:
        existing = (
            db.query(HealthDataPoint.metric_code)
            .filter(
                HealthDataPoint.pregnant_id == pregnant_id,
                HealthDataPoint.recorded_at >= today_start,
                HealthDataPoint.metric_code.in_(list(metrics_to_save.keys())),
            )
            .distinct()
            .all()
        )
        existing_codes = {row[0] for row in existing}

        deduped: dict = {}
        skipped: list[str] = []
        for mc, val in metrics_to_save.items():
            if mc in existing_codes:
                skipped.append(mc)
            else:
                deduped[mc] = val

        if deduped:
            saved = save_health_metrics(
                pregnant_id, deduped,
                source=HealthDataSource.PATIENT_CHAT,
            )
            # save_health_metrics 返回的是 metric_key (如 "weight", "systolic")
            # 我们需要 metric_code 名称返回给前端
            saved_codes = [mc for mc in deduped if mc in saved
                           or any(mc == _NLU_ENTITY_TO_METRIC.get(s, "") for s in saved)]
            if not saved_codes:
                saved_codes = list(deduped.keys())  # 回退
        else:
            saved_codes = []

        return {"saved": saved_codes, "skipped": skipped}
    except Exception:
        logger.warning("NLU实体自动保存失败 pregnant_id=%s", pregnant_id, exc_info=True)
        return {"saved": [], "skipped": []}
    finally:
        db.close()

# 工具名称 → 用户友好的中文描述（用于前端 thinking 步骤展示）
TOOL_THINKING_MAP: dict[str, str] = {
    "agno_get_nlu_result": "正在理解您的需求...",
    "agno_check_emergency": "正在进行安全检查...",
    "search_knowledge_base": "正在查阅孕期知识库...",
    "agno_get_patient_context": "正在了解您的健康情况...",
    "agno_analyze_health_trends": "正在分析您的健康趋势...",
    "agno_evaluate_vital_rules": "正在评估健康指标...",
    "agno_save_health_data": "正在保存您的健康数据...",
    "agno_get_pending_prompts": "正在检查今日记录状态...",
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

    # 1b. 自动保存 NLU 提取的健康数据实体（不依赖 Agent 工具调用）
    auto_saved = {"saved": [], "skipped": []}
    if nlu_result and nlu_result.entities:
        import asyncio
        auto_saved = await asyncio.to_thread(_auto_save_nlu_health_data, req.pregnant_id, nlu_result.entities)

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

    # 2. 注入 NLU 预分析结果到 agent_input，避免 Agent 内重复解析
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
    tool_metrics.start_session()
    response = await agent.arun(
        input=agent_input,
        images=agent_images,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    elapsed_ms = int((time.time() - start_time) * 1000)
    content = response.content or ""
    metrics_snap = tool_metrics.end_session()

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
        tool_metrics_session=metrics_snap,
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
        saved_health_data=auto_saved,
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

    # 1b. 自动保存 NLU 提取的健康数据实体（不依赖 Agent 工具调用）
    auto_saved = {"saved": [], "skipped": []}
    if nlu_result and nlu_result.entities:
        import asyncio
        auto_saved = await asyncio.to_thread(_auto_save_nlu_health_data, req.pregnant_id, nlu_result.entities)

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

    # 2. 注入 NLU 预分析结果到 agent_input，避免 Agent 内重复解析
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

    state = AgnoSseState()
    config = AgnoSseConfig(
        agent=agent,
        input_text=agent_input,
        user_id=req.pregnant_id,
        session_id=session_id,
        thinking_map=TOOL_THINKING_MAP,
        initial_thinking="小安正在思考...",
        error_log_message="Agno stream error",
        error_chunk_content="\n\n抱歉，我遇到了问题，请稍后再试。",
        done_source="AI_CARE",
        images=agent_images,
        done_extra={
            "nlu_result": nlu_dict if nlu_result else None,
            "memory_updated": [],
            "transcribed_text": transcribed_text,
            "saved_health_data": auto_saved,
        },
    )

    try:
        tool_metrics.start_session()
        async for event in agno_sse_event_generator(config, state):
            yield event

        metrics_snap = tool_metrics.end_session()

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
            run_response=state.run_response,
            total_latency_ms=state.elapsed_ms,
            tool_metrics_session=metrics_snap,
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
                    session_id, req.pregnant_id, "assistant", state.full_response,
                )
            except Exception:
                logger.warning("流式对话持久化失败 session_id={}", session_id, exc_info=True)
    finally:
        # 保证客户端断开时也能清理 NLU 上下文，防止内存泄漏
        pop_nlu_context(session_id)