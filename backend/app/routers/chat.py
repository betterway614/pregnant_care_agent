"""对话管理 API"""
import json
import re
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from ..schemas import ChatSendRequest, ChatResponse, ChatNLUResult
from ..core import get_llm_client, nlu_engine, memory_manager, rag_engine
from ..core.followup_tools import FOLLOWUP_TOOLS, dispatch_tool
from ..core.agno_client import get_agno_client
from ..core.agno_rag import agno_rag_engine
from ..models import HealthDataPoint, Pregnant, FollowUpRecord
from ..database import SessionLocal
from ..config import settings

MAX_AGENT_TURNS = 15

router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])
llm = get_llm_client()


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatSendRequest):
    """发送对话消息"""
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

    # 1.1 孕周感知上下文注入
    patient_context = ""
    patient_db = SessionLocal()
    try:
        pregnant = patient_db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
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

    # 4. 构建对话上下文
    system_prompt_content = (
        "你是'小安'，一位温暖、专业的孕期智能助手。你的职责是：\n"
        "1. 用温暖亲切的语气回答孕期相关问题\n"
        "2. 帮助记录孕妇的健康数据（体重、血压、胎动等）\n"
        "3. 提供情绪安抚和支持\n"
        "4. 回答孕期基础生理知识\n"
        "5. 绝不出具诊断结论或用药建议\n"
        "6. 所有知识性回答末尾必须标注'知识来源'标签，格式为：『知识来源：<具体指南/文献名称>』\n"
        "7. 若识别到紧急情况，引导就医\n"
        "8. 若孕妇询问的问题超出你的知识范围，请回复：'这个问题建议您咨询产检医生，小安暂时无法提供确切答案。'\n\n"
        "记住：你是辅助工具，不能替代医生的专业判断。"
    )
    if patient_context:
        system_prompt_content = patient_context + system_prompt_content
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
            response = await llm.chat([system_prompt, user_msg], max_tokens=1024)
    except Exception as e:
        # LLM调用失败时回退到mock
        from ..core import MockLLMClient
        mock = MockLLMClient()
        response = await mock.chat([system_prompt, user_msg])

    # 追加引导提问
    if follow_up_question:
        response = response.rstrip() + follow_up_question

    return ChatResponse(
        content=response,
        nlu_result=ChatNLUResult(
            intent=nlu_result.intent,
            entities=nlu_result.entities
        ) if nlu_result else None,
        session_id=req.session_id or f"SESS_{req.pregnant_id[:8]}",
        memory_updated=memory_entries,
        source="AI_CARE"
    )


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

    # 5. 孕周感知上下文
    patient_context = ""
    patient_db = SessionLocal()
    try:
        pregnant = patient_db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
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

    # 6. 构建 system prompt
    system_prompt_content = (
        "你是'小安'，一位温暖、专业的孕期智能助手。你的职责是：\n"
        "1. 用温暖亲切的语气回答孕期相关问题\n"
        "2. 帮助记录孕妇的健康数据（体重、血压、胎动等）\n"
        "3. 提供情绪安抚和支持\n"
        "4. 回答孕期基础生理知识\n"
        "5. 绝不出具诊断结论或用药建议\n"
        "6. 所有知识性回答末尾必须标注'知识来源'标签，格式为：『知识来源：<具体指南/文献名称>』\n"
        "7. 若识别到紧急情况，引导就医\n"
        "8. 若孕妇询问的问题超出你的知识范围，请回复：'这个问题建议您咨询产检医生，小安暂时无法提供确切答案。'\n\n"
        "记住：你是辅助工具，不能替代医生的专业判断。"
    )
    if patient_context:
        system_prompt_content = patient_context + system_prompt_content

    return {
        "nlu_result": nlu_result,
        "is_emergency": is_emergency,
        "emergency_msg": emergency_msg,
        "memory_entries": memory_entries,
        "follow_up_question": follow_up_question,
        "messages": [
            {"role": "system", "content": system_prompt_content},
            {"role": "user", "content": req.message},
        ],
        "pregnant_id": req.pregnant_id,
        "session_id": req.session_id or f"SESS_{req.pregnant_id[:8]}",
    }


@router.post("/send/stream")
async def send_message_stream(req: ChatSendRequest):
    """发送对话消息（SSE 流式输出）"""
    # 随访模式暂不支持流式，回退到非流式
    if req.record_id:
        result = await _handle_followup_chat(req)
        return JSONResponse(result.model_dump())

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

        # 调用LLM流式接口（支持 Agno 模式切换）
        try:
            if settings.agno_enabled:
                agno = get_agno_client()
                async for chunk in agno.chat_stream(ctx["messages"]):
                    full_response += chunk
                    yield {"event": "chunk", "data": chunk}
            else:
                async for chunk in llm.chat_stream(ctx["messages"], max_tokens=1024):
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

    return EventSourceResponse(event_generator())




async def _handle_followup_chat(req: ChatSendRequest) -> ChatResponse:
    """随访模式 ReAct 循环：工具感知的智能体对话"""
    db = SessionLocal()
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(req.record_id)
        ).first()
        if not record:
            return ChatResponse(content="随访记录不存在。", session_id=req.session_id)
        if str(record.pregnant_id) != req.pregnant_id:
            return ChatResponse(content="孕妇信息不匹配，无法继续随访。", session_id=req.session_id)

        # 已归档则直接返回
        if record.status == "confirmed":
            return ChatResponse(
                content=f"本次随访已于 {record.follow_up_date.strftime('%Y-%m-%d %H:%M')} 完成。\n\n摘要：{record.summary or '无'}",
                session_id=req.session_id,
            )

        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
        system_prompt = _build_followup_system_prompt(pregnant, record, req.record_id)

        messages = [{"role": "system", "content": system_prompt}]
        # 加载历史消息（基于 session_id 的简单追踪）
        history = _load_followup_history(req.session_id, req.record_id)
        messages.extend(history)
        messages.append({"role": "user", "content": req.message})

        # ReAct 循环
        final_response = ""
        progress = None
        for turn in range(MAX_AGENT_TURNS):
            result = await llm.chat_with_tools(messages, FOLLOWUP_TOOLS)

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
                # 记录到历史
                _save_followup_history(req.session_id, req.record_id, messages[-4:])
            else:
                final_response = result.get("content", "")
                break
        else:
            final_response = "随访流程已结束，感谢您的配合！如有其他问题，随时可以问我。"

        return ChatResponse(
            content=final_response,
            session_id=req.session_id or f"FU_{req.record_id[:8]}",
            source="FOLLOWUP",
            followup_progress=progress,
        )
    except Exception as e:
        return ChatResponse(
            content="随访对话出现异常，请稍后重试或联系护士。",
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

    return f"""你是'小安'，一位温暖、贴心的孕期智能助手。当前处于【随访模式】。

【孕妇信息】
- 称呼: {patient_name}
- 孕周: {gw}周
- 风险标签: {risk_text}

【随访信息】
- 随访记录ID: {record_id}
- template_name: {tmpl_name}
- 随访状态: {record.status}

【核心人设要求——务必遵守】
你必须用以下风格与孕妇交流：

1. 【称呼方式】直接称呼孕妇昵称"{patient_name}"，不要说"{patient_name}妈妈"或"妈妈"。例如："{patient_name}，您好呀~"、"{patient_name}真棒！"

2. 【语气风格】温暖亲切，像闺蜜或姐姐一样聊天。多用语气词（呀、呢、哦、嘛、啦），适当使用 emoji（💗😊👶💪🌟🎉）

3. 【提问方式】每次只问一个问题，用自然的过渡引出：
   ✅ "那再问您一个小问题哦~关于{话题}方面："
   ❌ 不要生硬地说"下一个问题"

4. 【回答反馈】每次孕妇回答后，先给予温暖的认可和简单反馈，再问下一题：
   - 正面回答："听到您这么说我就放心啦~😊"
   - 不适症状："孕期有些小不适很正常的，您辛苦了~🥺 如果加重的话记得及时就医哦"
   - 体重/血压数据："好的，已经帮您记下啦！您坚持记录真棒~👏"

5. 【情绪价值】主动关心孕妇感受，提供简短温馨的健康提示。结束时送祝福。

6. 【规则】绝不出具诊断结论或用药建议。如果孕妇表现出紧急症状，引导就医。

【工具使用流程】
1. 首先调用 get_followup_context 获取随访模板和当前进度
2. 根据模板逐一提问，每次用 record_answer 记录孕妇回答（回答会自动保存健康数据）
3. 所有问题完成后，调用 complete_followup 归档记录

【健康教育内容】
{health_edu if health_edu else "无"}
"""


# ==================== 随访会话历史管理 ====================

_followup_history: dict[str, list[dict]] = {}

def _history_key(session_id: str, record_id: str) -> str:
    return f"{session_id or ''}:{record_id}"

def _load_followup_history(session_id: str, record_id: str) -> list[dict]:
    return _followup_history.get(_history_key(session_id, record_id), [])

def _save_followup_history(session_id: str, record_id: str, new_msgs: list[dict]):
    key = _history_key(session_id, record_id)
    if key not in _followup_history:
        _followup_history[key] = []
    _followup_history[key].extend(new_msgs)


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
    """保存健康数据到数据库"""
    metric_map = {
        "weight": ("weight", "kg"),
        "sbp": ("sbp", "mmHg"),
        "dbp": ("dbp", "mmHg"),
        "fetal_movement": ("fetal_movement", "次/小时"),
        "blood_sugar": ("blood_sugar", "mmol/L"),
        "heart_rate": ("heart_rate", "bpm"),
        "sleep_hours": ("sleep_hours", "小时"),
        "steps": ("steps", "步"),
    }
    db = SessionLocal()
    try:
        for key, value in entities.items():
            if key in metric_map:
                code, unit = metric_map[key]
                if key == "weight" and isinstance(value, (int, float)):
                    value = float(value)
                point = HealthDataPoint(
                    pregnant_id=pregnant_id,
                    metric_code=code,
                    value=float(value),
                    unit=unit,
                    source="PATIENT_REPORT",
                )
                db.add(point)
        db.commit()
    except Exception:
        db.rollback()
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
