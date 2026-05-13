"""对话管理 API"""
import json
import re
import os
import asyncio
import uuid as _uuid
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from ..schemas import ChatSendRequest, ChatResponse, ChatNLUResult
from loguru import logger
from ..core import get_llm_client, nlu_engine, memory_manager, rag_engine
from ..core.followup_tools import FOLLOWUP_TOOLS, dispatch_tool
from ..core.agno_client import get_agno_client
from ..core.agno_rag import agno_rag_engine
from ..core.conversation_store import conversation_store
from ..core.prompts import (
    get_pregnant_system_prompt,
    get_followup_system_prompt,
)
from ..models import HealthDataPoint, Pregnant, FollowUpRecord
from ..database import SessionLocal, db_call
from ..config import settings


def _generate_session_id(pregnant_id: str) -> str:
    """生成唯一的 session_id

    格式: SESS_{pregnant_id前8位}_{日期}_{随机4位}
    确保同一孕妇不同时间段的对话隔离
    """
    date_str = datetime.now().strftime("%Y%m%d")
    rand_str = _uuid.uuid4().hex[:4]
    return f"SESS_{pregnant_id[:8]}_{date_str}_{rand_str}"

MAX_AGENT_TURNS = 15

# 文件日志（绕开 stdout 重定向问题）
_DEBUG_LOG = os.path.join(os.path.dirname(__file__), "../../debug_chat.log")


def _debug_log(msg: str):
    """写入调试日志文件"""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
            f.flush()
    except Exception:
        pass  # 日志写入失败不影响主流程


def _query_patient_context(pregnant_id: str) -> str:
    """同步函数：查询孕妇上下文信息（在 db_call 线程池中执行）"""
    from datetime import datetime, timedelta
    from ..models import HealthDataPoint, Pregnant
    from ..core.trend_engine import trend_engine
    from ..database import SessionLocal

    patient_context = ""
    patient_db = SessionLocal()
    try:
        pregnant = patient_db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if pregnant and pregnant.gestational_age_days:
            gw = pregnant.gestational_age_days // 7
            gd = pregnant.gestational_age_days % 7
            patient_context = f"当前孕妇孕周：{gw}+{gd}周。"
            if pregnant.risk_tags:
                patient_context += f" 风险标签：{', '.join(pregnant.risk_tags)}。"
            if pregnant.nickname:
                patient_context += f" 孕妇昵称：{pregnant.nickname}。"

            # 注入健康趋势分析
            try:
                two_weeks_ago = datetime.now() - timedelta(days=14)
                recent_records = patient_db.query(HealthDataPoint).filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.recorded_at >= two_weeks_ago,
                ).order_by(HealthDataPoint.recorded_at).all()

                if recent_records:
                    records_data = [
                        {"metric": r.metric_code, "value": r.value, "unit": r.unit, "recorded_at": str(r.recorded_at)}
                        for r in recent_records
                    ]
                    trends = trend_engine.analyze(records_data, gest_week=gw)
                    if trends:
                        trend_summaries = [t.summary for t in trends if t.summary]
                        if trend_summaries:
                            patient_context += " 【近期健康趋势】" + " ".join(trend_summaries)
            except Exception:
                pass  # 趋势分析失败不影响主流程
    finally:
        patient_db.close()
    return patient_context


def _get_patient_context_simple(pregnant_id: str) -> str:
    """同步函数：简单查询孕妇基本信息（在线程池中执行）"""
    from ..models import Pregnant
    from ..database import SessionLocal

    patient_context = ""
    patient_db = SessionLocal()
    try:
        pregnant = patient_db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if pregnant and pregnant.gestational_age_days:
            gw = pregnant.gestational_age_days // 7
            gd = pregnant.gestational_age_days % 7
            patient_context = f"当前孕妇孕周：{gw}+{gd}周。"
            if pregnant.risk_tags:
                patient_context += f" 风险标签：{', '.join(pregnant.risk_tags)}。"
            if pregnant.nickname:
                patient_context += f" 孕妇昵称：{pregnant.nickname}。"
    finally:
        patient_db.close()
    return patient_context


def _init_followup_db(record_id: str, pregnant_id: str):
    """同步函数：随访初始数据库查询（在线程池中执行）"""
    from uuid import UUID
    from ..models import FollowUpRecord, Pregnant
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
        if not record:
            return ChatResponse(content="随访记录不存在。")
        if str(record.pregnant_id) != pregnant_id:
            return ChatResponse(content="孕妇信息不匹配，无法继续随访。")

        # 已归档则直接返回
        if record.status == "confirmed":
            return ChatResponse(
                content=f"本次随访已于 {record.follow_up_date.strftime('%Y-%m-%d %H:%M')} 完成。\n\n摘要：{record.summary or '无'}",
            )

        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        system_prompt = _build_followup_system_prompt(pregnant, record, record_id)
        return system_prompt
    finally:
        db.close()


router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])

from ..core.llm_client import get_pregnant_llm_client


@router.get("/ping")
def ping():
    """调试：检查服务器是否运行最新代码"""
    from datetime import datetime
    return {"pong": datetime.now().isoformat(), "version": "debug_v4"}


@router.get("/debug-log")
def get_debug_log():
    """读取调试日志"""
    try:
        with open(_DEBUG_LOG, "r", encoding="utf-8") as f:
            content = f.read()
        return {"log": content}
    except FileNotFoundError:
        return {"log": f"(log file not found at {_DEBUG_LOG})"}
    except Exception as e:
        return {"log": f"(error reading log: {e})"}


def _get_chat_llm():
    """获取对话专用LLM客户端：mixed模式下孕妇对话用真实API"""
    from ..config import settings
    if settings.llm_mode == "mixed":
        return get_pregnant_llm_client()
    return get_llm_client()


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatSendRequest):
    """发送对话消息"""
    import traceback
    _dbg = f"[SEND] agno_enabled={settings.agno_enabled}, record_id={req.record_id}, pregnant_id={req.pregnant_id}"
    _debug_log(_dbg)
    logger.info("send_message 开始 pregnant_id={} record_id={}", req.pregnant_id[:8], req.record_id)
    _debug_log(f"[SEND] calling agno_enabled={settings.agno_enabled}")
    # Agno Agent 模式
    if settings.agno_enabled:
        from ..core.agno_chat_handler import handle_chat_with_agno, handle_followup_chat_with_agno
        if req.record_id:
            return await handle_followup_chat_with_agno(req)
        return await handle_chat_with_agno(req)

    # 随访Agent模式：当传入 record_id 时进入结构随访对话
    if req.record_id:
        return await _handle_followup_chat(req)

    # 1. NLU解析
    nlu_result = nlu_engine.parse(req.message)

    # 1.5 扩展NLU实体提取（补充nlu_engine未覆盖的数据项：睡眠时长、运动步数）
    _extract_extra_entities(req.message, nlu_result)

    # 2. 紧急检测
    if nlu_result.is_emergency:
        if nlu_result.intent == "SUICIDE_RISK":
            msg = ("⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，"
                   "或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。")
        else:
            msg = ("⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。"
                   "如果情况紧急，请拨打120急救电话！")
        return ChatResponse(content=msg, nlu_result=ChatNLUResult(
            intent=nlu_result.intent,
            entities=nlu_result.entities
        ) if nlu_result else None, session_id=req.session_id)

    # 3. 健康数据自动存储
    if nlu_result.intent == "HEALTH_DATA_REPORT" and nlu_result.entities:
        _save_health_data(req.pregnant_id, nlu_result.entities)
        memory_entries = []
        if "weight" in nlu_result.entities:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            memory_manager.set(req.pregnant_id, "last_weight_date", today)
            memory_entries.append(f"last_weight_date: {today}")
        if "sbp" in nlu_result.entities or "dbp" in nlu_result.entities:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            memory_manager.set(req.pregnant_id, "last_bp_date", today)
            memory_entries.append(f"last_bp_date: {today}")
    else:
        memory_entries = []

    # 1.2 引导式数据收集：检查是否需要主动询问缺失数据
    follow_up_question = ""
    if nlu_result.intent not in ("EMERGENCY", "SUICIDE_RISK"):
        if not nlu_result.entities:
            if memory_manager.should_ask_weight(req.pregnant_id):
                follow_up_question = " 对了，小安看到您今天还没记录体重呢，方便现在告诉我吗？"
            elif memory_manager.should_ask_bp(req.pregnant_id):
                follow_up_question = " 另外，记得今天测血压了吗？可以告诉我数值哦。"

    # 1.1 孕周感知上下文注入（在线程池中执行，避免阻塞事件循环）
    patient_context = await db_call(_query_patient_context, req.pregnant_id)

    # 4. 构建对话上下文
    system_prompt_content = get_pregnant_system_prompt(patient_context)
    system_prompt = {
        "role": "system",
        "content": system_prompt_content
    }
    user_msg = {"role": "user", "content": req.message}

    # 5. 调用LLM获取回复（支持 Agno 模式切换）
    try:
        if settings.agno_enabled:
            agno = get_agno_client()
            response = await agno.chat([system_prompt, user_msg])
        else:
            response = await _get_chat_llm().chat([system_prompt, user_msg], max_tokens=1024)
    except Exception as e:
        # LLM调用失败时回退到mock
        from ..core import MockLLMClient
        mock = MockLLMClient()
        response = await mock.chat([system_prompt, user_msg])

    # 追加引导提问
    if follow_up_question:
        response = response.rstrip() + follow_up_question

    # 对话原文不入库，仅返回响应
    session_id = req.session_id or _generate_session_id(req.pregnant_id)

    resp_len = len(response)
    logger.info("send_message 完成 pregnant_id={} resp_len={}", req.pregnant_id[:8], resp_len)
    return ChatResponse(
        content=response,
        nlu_result=ChatNLUResult(
            intent=nlu_result.intent,
            entities=nlu_result.entities
        ) if nlu_result else None,
        session_id=session_id,
        memory_updated=memory_entries,
        source="AI_CARE"
    )


@router.get("/conversation/{pregnant_id}")
async def get_conversation_history(pregnant_id: str, session_id: str = ""):
    """获取对话历史记录（当前为会话内缓存，不持久化）"""
    return {"session_id": session_id, "messages": [], "message": "对话历史仅在会话内有效"}


@router.delete("/conversation/{pregnant_id}")
async def clear_conversation_history(pregnant_id: str, session_id: str = ""):
    """清除对话历史（当前为会话内缓存，无需清除）"""
    return {"message": "对话历史仅在会话内有效，无需清除"}


# ==================== SSE 流式输出 ====================

import typing
from ..core import MockLLMClient


async def _build_chat_context(req: ChatSendRequest) -> dict:
    """构建对话上下文，供流式/非流式端点共用"""
    # 1. NLU解析
    nlu_result = nlu_engine.parse(req.message)
    _extract_extra_entities(req.message, nlu_result)

    # 2. 紧急检测
    is_emergency = bool(nlu_result.is_emergency)
    emergency_msg = ""
    if is_emergency:
        if nlu_result.intent == "SUICIDE_RISK":
            emergency_msg = ("⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，"
                             "或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。")
        else:
            emergency_msg = ("⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。"
                             "如果情况紧急，请拨打120急救电话！")

    # 3. 健康数据存储
    memory_entries: list[str] = []
    if nlu_result.intent == "HEALTH_DATA_REPORT" and nlu_result.entities:
        _save_health_data(req.pregnant_id, nlu_result.entities)
        if "weight" in nlu_result.entities:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            memory_manager.set(req.pregnant_id, "last_weight_date", today)
            memory_entries.append(f"last_weight_date: {today}")
        if "sbp" in nlu_result.entities or "dbp" in nlu_result.entities:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            memory_manager.set(req.pregnant_id, "last_bp_date", today)
            memory_entries.append(f"last_bp_date: {today}")

    # 4. 引导式数据收集
    follow_up_question = ""
    if not is_emergency and not nlu_result.entities:
        if memory_manager.should_ask_weight(req.pregnant_id):
            follow_up_question = " 对了，小安看到您今天还没记录体重呢，方便现在告诉我吗？"
        elif memory_manager.should_ask_bp(req.pregnant_id):
            follow_up_question = " 另外，记得今天测血压了吗？可以告诉我数值哦。"

    # 5. 孕周感知上下文（在线程池中执行，避免阻塞事件循环）
    patient_context = await db_call(_get_patient_context_simple, req.pregnant_id)

    # 6. 构建 system prompt
    system_prompt_content = get_pregnant_system_prompt(patient_context)

    # 7. 加载对话历史（异步）
    session_id = req.session_id or _generate_session_id(req.pregnant_id)
    history = await conversation_store.async_load_history(session_id, req.pregnant_id)

    messages = [{"role": "system", "content": system_prompt_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": req.message})

    return {
        "nlu_result": nlu_result,
        "is_emergency": is_emergency,
        "emergency_msg": emergency_msg,
        "memory_entries": memory_entries,
        "follow_up_question": follow_up_question,
        "messages": messages,
        "pregnant_id": req.pregnant_id,
        "session_id": session_id,
    }


def _chat_response_to_sse(result: ChatResponse):
    """将非流式 ChatResponse 包装为 SSE 事件流，确保流式端点始终输出 SSE 格式"""
    nlu = result.nlu_result
    async def wrapper():
        yield {"event": "chunk", "data": result.content}
        yield {"event": "done", "data": json.dumps({
            "session_id": result.session_id,
            "source": result.source or "AI_CARE",
            "nlu_result": {"intent": nlu.intent, "entities": nlu.entities} if nlu else None,
            "memory_updated": result.memory_updated or [],
            "followup_progress": result.followup_progress,
        })}
    return EventSourceResponse(wrapper())


@router.post("/send/stream")
async def send_message_stream(req: ChatSendRequest):
    """发送对话消息（SSE 流式输出）"""
    # Agno Agent 模式 — 流式 SSE 输出
    if settings.agno_enabled:
        from ..core.agno_chat_handler import handle_chat_with_agno_stream, handle_followup_chat_with_agno_stream
        if req.record_id:
            return EventSourceResponse(handle_followup_chat_with_agno_stream(req))
        return EventSourceResponse(handle_chat_with_agno_stream(req))

    # 随访模式 — 包装为 SSE 格式
    if req.record_id:
        result = await _handle_followup_chat(req)
        return _chat_response_to_sse(result)

    ctx = await _build_chat_context(req)
    session_id = ctx["session_id"]
    memory_entries = ctx["memory_entries"]

    # 紧急情况：直接输出完整消息
    if ctx["is_emergency"]:
        async def emergency_gen():
            yield {"event": "chunk", "data": ctx["emergency_msg"]}
            yield {"event": "done", "data": json.dumps({
                "session_id": session_id,
                "source": "AI_CARE",
                "nlu_result": {
                    "intent": ctx["nlu_result"].intent,
                    "entities": ctx["nlu_result"].entities,
                },
                "memory_updated": memory_entries,
            })}
        return EventSourceResponse(emergency_gen())

    async def event_generator():
        """SSE 事件生成器"""
        full_response = ""

        # 发送思考状态事件
        thinking_messages = {
            "HEALTH_DATA_REPORT": "正在分析您的健康数据...",
            "EMOTION_EXPRESS": "正在理解您的感受...",
            "KNOWLEDGE_QUERY": "正在查阅孕期知识库...",
            "SCHEDULE_INQUIRY": "正在查看您的产检安排...",
            "GREETING": "正在准备回复...",
        }
        thinking_msg = thinking_messages.get(
            ctx["nlu_result"].intent if ctx["nlu_result"] else "",
            "小安正在思考..."
        )
        yield {"event": "thinking", "data": thinking_msg}

        # 调用LLM流式接口（支持 Agno 模式切换）
        try:
            if settings.agno_enabled:
                agno = get_agno_client()
                async for chunk in agno.chat_stream(ctx["messages"]):
                    full_response += chunk
                    yield {"event": "chunk", "data": chunk}
            else:
                async for chunk in _get_chat_llm().chat_stream(ctx["messages"], max_tokens=1024):
                    full_response += chunk
                    yield {"event": "chunk", "data": chunk}
        except Exception:
            mock = MockLLMClient()
            async for chunk in mock.chat_stream(ctx["messages"]):
                full_response += chunk
                yield {"event": "chunk", "data": chunk}

        # 追加引导提问
        if ctx["follow_up_question"]:
            full_response += ctx["follow_up_question"]
            yield {"event": "chunk", "data": ctx["follow_up_question"]}

        # 发送完成事件（含元数据）
        yield {"event": "done", "data": json.dumps({
            "session_id": session_id,
            "source": "AI_CARE",
            "nlu_result": {
                "intent": ctx["nlu_result"].intent if ctx["nlu_result"] else "",
                "entities": ctx["nlu_result"].entities if ctx["nlu_result"] else {},
            },
            "memory_updated": memory_entries,
        })}

        # 持久化对话消息
        try:
            user_msg = ctx["messages"][-1]  # 最后一条是用户消息
            await conversation_store.async_save_single(session_id, ctx["pregnant_id"], "user", user_msg["content"])
            await conversation_store.async_save_single(session_id, ctx["pregnant_id"], "assistant", full_response)
        except Exception:
            pass  # 持久化失败不影响主流程

    return EventSourceResponse(event_generator())




async def _handle_followup_chat(req: ChatSendRequest) -> ChatResponse:
    """随访模式 ReAct 循环：工具感知的智能体对话"""
    logger.info("FOLLOWUP_CHAT record_id={} pregnant_id={}", req.record_id, req.pregnant_id)
    llm = _get_chat_llm()
    _debug_log(f"[FOLLOWUP_CHAT] llm_type={type(llm).__name__}")
    logger.info("FOLLOWUP_CHAT LLM client: {}", type(llm).__name__)

    # 初始数据库查询（在线程池中执行，避免阻塞事件循环）
    db_init = await db_call(_init_followup_db, req.record_id, req.pregnant_id)
    if isinstance(db_init, ChatResponse):
        return db_init
    system_prompt = db_init

    messages = [{"role": "system", "content": system_prompt}]
    # 加载历史消息（异步）
    fu_session_id = f"FU_{req.record_id[:8]}"
    history = await conversation_store.async_load_history(fu_session_id, req.pregnant_id)

    # ReAct 循环需要一个共享的 db session 传给 dispatch_tool
    db = SessionLocal()
    try:
        messages.extend(history)
        messages.append({"role": "user", "content": req.message})

        # ReAct 循环
        final_response = ""
        progress = None
        for turn in range(MAX_AGENT_TURNS):
            logger.info("FOLLOWUP_CHAT Turn {} llm.chat_with_tools...", turn)
            result = await llm.chat_with_tools(messages, FOLLOWUP_TOOLS)
            logger.info("FOLLOWUP_CHAT Turn {} tool_calls={} content={}", turn, bool(result.get('tool_calls')), result.get('content', '')[:50])

            if result.get("tool_calls"):
                messages.append(result)
                for tc in result["tool_calls"]:
                    tool_result = await dispatch_tool(tc, db)
                    progress = {
                        "answered": tool_result.get("answered_count", 0),
                        "total": tool_result.get("total_count", 0),
                        "status": tool_result.get("status", "in_progress"),
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })
                # 记录到历史（持久化）
                try:
                    user_and_assistant = [m for m in messages[-4:] if m.get("role") in ("user", "assistant")]
                    await conversation_store.async_save_messages(fu_session_id, req.pregnant_id, user_and_assistant)
                except Exception:
                    pass
            else:
                final_response = result.get("content", "")
                break
        else:
            final_response = "随访流程已结束，感谢您的配合！如有其他问题，随时可以问我。"

        # 持久化最终回复
        try:
            await conversation_store.async_save_single(fu_session_id, req.pregnant_id, "assistant", final_response)
        except Exception:
            pass

        return ChatResponse(
            content=final_response,
            session_id=req.session_id or f"FU_{req.record_id[:8]}",
            source="FOLLOWUP",
            followup_progress=progress,
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("FOLLOWUP_CHAT 异常 {}: {}", type(e).__name__, str(e)[:200])
        return ChatResponse(
            content=f"随访对话异常（{type(e).__name__}）：{str(e)[:200]}",
            session_id=req.session_id,
        )
    finally:
        db.close()


def _build_followup_system_prompt(pregnant, record, record_id: str) -> str:
    """构建随访模式的 system prompt"""
    gw = f"{pregnant.gestational_age_days // 7}+{pregnant.gestational_age_days % 7}" if pregnant and pregnant.gestational_age_days else "?"
    risk_text = "、".join(pregnant.risk_tags) if pregnant and pregnant.risk_tags else "无"
    health_edu = "\n".join(f"- {item}" for item in (record.health_education or []))

    # 反向推断模板名称
    template = None
    from ..services.followup_service import FOLLOWUP_TEMPLATES
    for tid, tmpl in FOLLOWUP_TEMPLATES.items():
        if tmpl["name"] in (record.self_reported_data or {}).get("_template", ""):
            template = tid
            break
    tmpl_name = template or "standard"

    patient_name = pregnant.nickname or pregnant.display_name if pregnant else "准妈妈"

    return get_followup_system_prompt(
        patient_name=patient_name,
        gest_week=gw,
        risk_text=risk_text,
        record_id=record_id,
        template_name=tmpl_name,
        record_status=record.status,
        health_education=health_edu,
    )



def _extract_extra_entities(message: str, nlu_result):
    """扩展NLU实体提取：补充睡眠时长、运动步数等nlu_engine未覆盖的数据项"""
    # 睡眠时长: 睡了X小时 / 睡了X.X小时
    sleep_match = re.search(r"睡了?(\d+\.?\d*)\s*小时", message)
    if sleep_match:
        nlu_result.entities["sleep_hours"] = float(sleep_match.group(1))
        if nlu_result.intent == "UNKNOWN":
            nlu_result.intent = "HEALTH_DATA_REPORT"

    # 运动步数: X步 / X千步
    steps_match = re.search(r"(\d+)\s*(步|千步)", message)
    if steps_match:
        if steps_match.group(2) == "千步":
            nlu_result.entities["steps"] = float(steps_match.group(1)) * 1000
        else:
            nlu_result.entities["steps"] = float(steps_match.group(1))
        if nlu_result.intent == "UNKNOWN":
            nlu_result.intent = "HEALTH_DATA_REPORT"


@router.get("/history")
async def get_memory(patient_id: str):
    """获取用户记忆键值对"""
    memory = memory_manager.get_all(patient_id)
    return {"pregnant_id": patient_id, "memory": memory}


@router.delete("/memory")
async def clear_memory(patient_id: str):
    """清除用户全部记忆"""
    memory_manager.clear(patient_id)
    return {"message": "记忆已清除", "pregnant_id": patient_id}


@router.get("/context/{pregnant_id}")
def get_pregnant_context(pregnant_id: str):
    """获取孕妇的孕期上下文信息（孕周、风险、最近数据）"""
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

        # 获取最近10条健康数据
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


def _save_health_data(pregnant_id: str, entities: dict):
    """保存健康数据到数据库（调用统一入库服务）"""
    from ..core.health_data_service import save_health_metrics, HealthDataSource
    save_health_metrics(pregnant_id, entities, HealthDataSource.PATIENT_CHAT)


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
    """RAG知识库问答 - 基于产科知识库的智能回答"""
    if not settings.rag_enabled:
        raise HTTPException(400, "RAG功能未启用，请设置 RAG_ENABLED=true")

    # 获取孕妇上下文
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

    if settings.agno_enabled:
        result = await agno_rag_engine.ask(
            question=req.question,
            patient_context=patient_context,
            top_k=req.top_k,
        )
    else:
        result = await rag_engine.ask(
            question=req.question,
            patient_context=patient_context,
            top_k=req.top_k,
        )
    return RAGAskResponse(**result)


@router.get("/rag/status")
def rag_status():
    """查询RAG知识库状态"""
    db = SessionLocal()
    try:
        from ..models.vector_models import KnowledgeChunk
        total = db.query(KnowledgeChunk).count()
        from sqlalchemy import func, distinct
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
    """获取孕妇近期健康趋势"""
    from datetime import datetime, timedelta
    from ..models import HealthDataPoint
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
    greeting_type: str  # morning, afternoon, evening, night
    icon: str


@router.get("/proactive/{pregnant_id}", response_model=ProactiveGreeting)
async def get_proactive_greeting(pregnant_id: str):
    """基于上下文生成主动问候消息"""
    from datetime import datetime
    from ..models import HealthDataPoint

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            return ProactiveGreeting(message="欢迎回来！", greeting_type="morning", icon="👋")

        hour = datetime.now().hour
        gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0

        # 检查最近是否有健康数据录入
        from datetime import timedelta
        recent_data = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= datetime.now() - timedelta(days=1)
        ).count()

        # 孕周里程碑
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

        # 时段问候
        if hour < 9:
            greeting_type = "morning"
            icon = "🌅"
            if recent_data == 0:
                msg = f"早安~今天记得记录体重和血压哦！{milestone_msg or ''}"
            else:
                msg = f"早安~今天已经记录了健康数据，真棒！{milestone_msg or '祝您今天心情愉快~'}"
        elif hour < 14:
            greeting_type = "afternoon"
            icon = "☀️"
            msg = f"下午好~午饭后散散步对宝宝有好处哦。{milestone_msg or ''}"
        elif hour < 18:
            greeting_type = "evening"
            icon = "🌆"
            msg = f"傍晚好~别忘了数胎动哦，每天固定时间数一数更准确。{milestone_msg or ''}"
        else:
            greeting_type = "night"
            icon = "🌙"
            msg = f"晚上好~今天辛苦了，早点休息对宝宝最好。{milestone_msg or ''}"

        if not msg:
            msg = "欢迎回来！有什么需要小安帮忙的吗？"

        # 检查是否有新签署的医嘱
        from ..models import MedicalOrder
        pending_orders = db.query(MedicalOrder).filter(
            MedicalOrder.pregnant_id == pregnant_id,
            MedicalOrder.status == "signed",
        ).count()
        if pending_orders > 0:
            msg += f"\n\n📋 您有 {pending_orders} 条新医嘱待查看，请在首页查看。"

        return ProactiveGreeting(
            message=msg,
            greeting_type=greeting_type,
            icon=icon,
        )
    finally:
        db.close()
