"""护士AI辅助 API"""
import asyncio
import time
import uuid
from datetime import date, datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from ..utils.timezone import beijing_now
from sqlalchemy import desc, func
from ..database import SessionLocal, get_db
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment
from ..schemas import (
    NurseAnalyzeRequest, NurseAnalyzeResponse, FollowUpGenerateRequest, FollowUpGenerateResponse,
    FollowupScheduleResponse, FollowupScheduleRecommendation, FollowupScheduleContext,
    ChatStreamRequest, FOLLOWUP_ACTIVE_STATUSES,
)
from ..core import get_llm_client
from ..core.json_parser import parse_llm_json
from ..core.websocket_manager import ws_manager
from ..core.auth import extract_user_from_header, get_current_user, TokenPayload
from ..config import settings
from ..services.audit_service import AuditService
from loguru import logger

# 护士端工具调用 → 用户友好的中文描述
NURSE_TOOL_THINKING_MAP: dict[str, str] = {
    "agno_list_patients": "正在查询孕妇列表...",
    "agno_query_patient_data": "正在查询患者数据...",
    "agno_analyze_patient_comprehensive": "正在综合分析患者情况...",
    "agno_create_followup_record": "正在创建随访记录...",
    "agno_report_issue_to_doctor": "正在上报问题给医生...",
    "agno_analyze_health_trends": "正在分析健康趋势...",
    "agno_evaluate_vital_rules": "正在评估生命体征...",
    "search_knowledge_base": "正在查阅护理知识库...",
    "agno_get_patient_context": "正在获取患者信息...",
}

# _save_nurse_audit_log 已迁移到 app/services/audit_service.py → AuditService.save_log()

# 保持后台审计任务引用，防止 fire-and-forget 被 GC 回收
_audit_tasks: set = set()

router = APIRouter(prefix="/api/v1/nurse", tags=["护士AI辅助"])


@router.post("/analyze", response_model=NurseAnalyzeResponse)
async def nurse_analyze(req: NurseAnalyzeRequest, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI分析孕妇数据，返回护理建议"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []

    # 收集孕妇数据
    patient_data = _collect_patient_data_for_nurse(db, req.pregnant_id, gest_week, gest_day)

    # 尝试LLM分析
    llm_result = await _try_llm_nurse_analyze(pregnant, gest_week, gest_day, risk_tags, patient_data)
    if llm_result:
        result = llm_result
    else:
        # 模板兜底
        result = _fallback_nurse_analyze(pregnant, gest_week, gest_day, risk_tags, patient_data)

    # 分析完成后自动创建预警（基于 LLM 动态判断的预警级别）
    # 应用患者安全后处理：拦截诊断性/用药性结论
    from ..core.agno_guardrails import apply_patient_facing_safety
    result.summary = apply_patient_facing_safety(result.summary or "")
    result.risk_assessment = apply_patient_facing_safety(result.risk_assessment or "")
    result.nursing_suggestions = apply_patient_facing_safety(result.nursing_suggestions or "")

    # 动态判断预警级别：优先使用 LLM 返回的 alert_level，回退到关键词匹配
    llm_level = (result.alert_level or "").upper()
    if llm_level in ("RED", "ORANGE", "YELLOW"):
        alert_level = llm_level
    elif "高风险" in (result.risk_assessment or "") or "异常" in (result.risk_assessment or ""):
        alert_level = "ORANGE"
    else:
        alert_level = None

    if alert_level:
        from ..services.alert_service import alert_service
        from ..utils.timezone import beijing_now

        alert = alert_service.create_alert(
            db=db,
            pregnant_id=req.pregnant_id,
            rule_id="NURSE_AI_ALERT",
            domain="vital",
            level=alert_level,
            message=f"护士AI分析提示：{result.risk_assessment[:100]}",
            trigger_source="MANUAL",
            details={
                "action": "ALERT_NURSE_AND_DOCTOR" if alert_level == "RED" else "ALERT_NURSE",
                "triggered_rules": ["NURSE_AI_ALERT"],
                "risk_assessment": result.risk_assessment[:200] if result.risk_assessment else "",
                "created_at": beijing_now().isoformat(),
            },
        )

        rule_action = "ALERT_NURSE_AND_DOCTOR" if alert_level == "RED" else "ALERT_NURSE"
        alert_data = {
            "id": str(alert.id),
            "pregnant_id": req.pregnant_id,
            "patient_name": pregnant.display_name,
            "level": alert_level,
            "message": f"护士AI分析提示：{result.risk_assessment[:100]}",
            "trigger_source": "MANUAL",
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "gestational_age_days": pregnant.gestational_age_days,
            "source_role": "system",
            "action": "created",
            "details": {"action": rule_action},
        }

        # 使用 route_alert 按级别和动作路由推送，而非广播给所有人
        await ws_manager.route_alert(alert_data)

    # 生成随访排期推荐
    schedule_result = tool_recommend_followup_schedule(db, req.pregnant_id)
    if "error" not in schedule_result:
        result.followup_schedule = FollowupScheduleResponse(**schedule_result)

    return result


@router.get("/schedule-recommend/{pregnant_id}")
def recommend_followup_schedule(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取随访排期推荐列表"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")

    result = tool_recommend_followup_schedule(db, pregnant_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


def _collect_patient_data_for_nurse(db, pregnant_id: str, gest_week: int, gest_day: int) -> dict:
    """收集孕妇数据用于护士分析"""
    from ..services.patient_context_service import get_recent_health_data, get_active_alerts

    data = {
        "gestational_week": f"{gest_week}+{gest_day}",
        "recent_health": [],
        "active_alerts": [],
        "recent_fgr": None,
        "recent_followup": None,
    }

    # 最近健康数据
    health_points = get_recent_health_data(db, pregnant_id, limit=10)
    for hp in health_points:
        data["recent_health"].append({
            "metric": hp["metric"],
            "value": hp["value"],
            "unit": hp["unit"],
            "recorded_at": hp["recorded_at"],
        })

    # 活跃预警
    alerts = get_active_alerts(db, pregnant_id, limit=5)
    for a in alerts:
        data["active_alerts"].append({
            "level": a["level"],
            "message": a["message"],
            "source": a["source"],
            "created_at": a["created_at"],
        })

    # 最近FGR评估
    fgr = db.query(FgrAssessment).filter(
        FgrAssessment.pregnant_id == pregnant_id
    ).order_by(desc(FgrAssessment.assessed_at)).first()
    if fgr:
        data["recent_fgr"] = {
            "risk_level": fgr.risk_level,
            "gestational_weeks": fgr.gestational_weeks,
            "explanation": fgr.explanation
        }

    # 最近随访记录
    followup = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(desc(FollowUpRecord.created_at)).first()
    if followup:
        data["recent_followup"] = {
            "status": followup.status,
            "chief_complaint": followup.chief_complaint,
            "summary": followup.summary
        }

    return data


async def _try_llm_nurse_analyze(pregnant: Pregnant, gest_week: int, gest_day: int,
                                 risk_tags: list, patient_data: dict) -> NurseAnalyzeResponse | None:
    """通过 Agno 护士 Agent 分析（工具驱动 + 结构化输出）"""
    try:
        from ..core.agno_medical_agents import get_nurse_analyze_agent
        from ..core.agno_structured import extract_structured_content

        risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
        prompt = (
            f"请为孕妇 {pregnant.display_name}（孕{gest_week}周+{gest_day}天，风险标签：{risk_text}）"
            "提供护理分析。请先调用工具获取最新数据，再输出结构化分析结果。"
        )

        from ..core.agno_tools import tool_metrics as _tm

        agent = get_nurse_analyze_agent()
        _tm.start_session()
        t0 = time.time()
        response = await agent.arun(input=prompt, user_id=pregnant.pregnant_id)
        elapsed_ms = int((time.time() - t0) * 1000)
        _metrics_snap = _tm.end_session()
        await asyncio.to_thread(
            AuditService.save_log,
            session_id=f"nurse_analyze_{pregnant.pregnant_id}",
            user_id=pregnant.pregnant_id,
            agent_role="nurse",
            agent_variant="analyze",
            intent_classification="ANALYZE",
            user_message=None,
            run_response=response,
            total_latency_ms=elapsed_ms,
            tool_metrics_session=_metrics_snap,
        )
        data = extract_structured_content(response.content)
        if not data:
            return None

        return NurseAnalyzeResponse(
            pregnant_id=pregnant.pregnant_id,
            patient_name=pregnant.display_name,
            summary=data.get("summary", ""),
            risk_assessment=data.get("risk_assessment", ""),
            nursing_suggestions=data.get("nursing_suggestions", ""),
            followup_focus=data.get("followup_focus", []),
            alert_level=data.get("alert_level", "NONE"),
        )
    except Exception as e:
        logger.warning("护士LLM分析降级: %s", e)
        return None


def _fallback_nurse_analyze(pregnant: Pregnant, gest_week: int, gest_day: int,
                            risk_tags: list, patient_data: dict) -> NurseAnalyzeResponse:
    """模板兜底护士分析"""
    gest_week_str = f"{gest_week}+{gest_day}"

    # 综合概述
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
    alert_count = len(patient_data.get("active_alerts", []))
    data_count = len(patient_data.get("recent_health", []))
    summary = f"孕妇{pregnant.display_name}，孕{gest_week_str}周，风险标签：{risk_text}。"
    if alert_count > 0:
        summary += f"当前有{alert_count}条活跃预警需要关注。"
    else:
        summary += "目前暂无活跃预警。"
    summary += f"最近有{data_count}条健康数据记录。"

    # 风险评估
    risk_parts = []
    if gest_week <= 12:
        risk_parts.append("孕早期需关注流产风险和胚胎发育情况")
    elif gest_week <= 28:
        risk_parts.append("孕中期需关注胎儿生长速率和母体营养状况")
    else:
        risk_parts.append("孕晚期需关注早产风险、胎盘功能和分娩准备")
    if "FGR高危" in risk_tags:
        risk_parts.append("FGR高危：需定期B超监测胎儿生长情况，关注胎动")
    if "GDM" in risk_tags:
        risk_parts.append("妊娠期糖尿病：需严格控制血糖，定期监测空腹及餐后血糖")
    if "高血压" in risk_tags:
        risk_parts.append("妊娠期高血压：需每日监测血压，警惕子痫前期")
    risk_assessment = "；".join(risk_parts) + "。"

    # 护理建议
    nursing_parts = [
        f"1. 按时进行孕{gest_week}周常规产检，关注血压、体重、宫高腹围变化",
        "2. 每日固定时间（建议饭后1小时）自数胎动，每小时不少于3-5次",
        "3. 保持均衡营养，按推荐摄入蛋白质、钙、铁等营养素",
        "4. 保持心情舒畅，保证充足睡眠，建议左侧卧位",
        "5. 如有阴道出血、腹痛、胎动异常等，及时就医"
    ]
    if "GDM" in risk_tags:
        nursing_parts.insert(2, "（重点）控制饮食中碳水化合物摄入，记录每日血糖值")
    if "高血压" in risk_tags:
        nursing_parts.insert(2, "（重点）每日早晚各测一次血压并记录，限盐饮食")
    nursing_suggestions = "\n".join(nursing_parts)

    # 随访重点
    followup_focus = [
        "确认产检是否按时进行",
        "了解饮食习惯和营养摄入",
        "询问胎动变化情况",
    ]
    if "FGR高危" in risk_tags:
        followup_focus.append("了解最近B超结果和胎儿生长参数")
    if "GDM" in risk_tags:
        followup_focus.append("检查血糖监测记录，评估血糖控制")
    if "高血压" in risk_tags:
        followup_focus.append("检查血压监测记录，筛查子痫前期症状")
    followup_focus.append("询问有无不适症状和异常体征")

    return NurseAnalyzeResponse(
        pregnant_id=pregnant.pregnant_id,
        patient_name=pregnant.display_name,
        summary=summary,
        risk_assessment=risk_assessment,
        nursing_suggestions=nursing_suggestions,
        followup_focus=followup_focus[:5],
    )


@router.post("/followup/generate", response_model=FollowUpGenerateResponse)
async def generate_followup(req: FollowUpGenerateRequest, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI生成个性化随访对话脚本"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []

    # 收集孕妇上下文
    patient_data = _collect_patient_data_for_nurse(db, req.pregnant_id, gest_week, gest_day)

    # 尝试LLM生成
    llm_result = await _try_llm_followup_generate(pregnant, gest_week, gest_day, risk_tags,
                                                   patient_data, req.template_id)
    if llm_result:
        return llm_result

    # 模板兜底
    return _fallback_followup_generate(pregnant, gest_week, gest_day, risk_tags,
                                       patient_data, req.template_id)


async def _try_llm_followup_generate(pregnant: Pregnant, gest_week: int, gest_day: int,
                                      risk_tags: list, patient_data: dict,
                                      template_id: str) -> FollowUpGenerateResponse | None:
    """Agno Agent 生成随访脚本，失败返回 None（由模板兜底）"""
    try:
        from ..core.agno_medical_agents import get_followup_generate_agent
        from ..core.agno_structured import extract_structured_content

        prompt = _build_followup_generate_prompt(pregnant, gest_week, gest_day, risk_tags,
                                                  patient_data, template_id)
        agent = get_followup_generate_agent()
        t0 = time.time()
        response = await agent.arun(prompt)
        elapsed_ms = int((time.time() - t0) * 1000)
        await asyncio.to_thread(
            AuditService.save_log,
            session_id=f"nurse_followup_{pregnant.pregnant_id}",
            user_id=pregnant.pregnant_id,
            agent_role="nurse",
            agent_variant="followup",
            intent_classification="FOLLOWUP_GENERATE",
            user_message=None,
            run_response=response,
            total_latency_ms=elapsed_ms,
        )
        data = extract_structured_content(response.content)
        if not data:
            return None

        return FollowUpGenerateResponse(
            pregnant_id=pregnant.pregnant_id,
            opening_message=data.get("opening_message", ""),
            questions=data.get("questions", []),
            closing_message=data.get("closing_message", ""),
        )
    except Exception as e:
        logger.warning("随访脚本生成LLM降级: %s", e)
        return None


def _build_followup_generate_prompt(pregnant: Pregnant, gest_week: int, gest_day: int,
                                     risk_tags: list, patient_data: dict,
                                     template_id: str) -> str:
    """构建随访生成提示词"""
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
    return f"""请为以下孕妇生成本次随访对话脚本：

孕妇：{pregnant.display_name}
孕周：{gest_week}周+{gest_day}天
风险标签：{risk_text}
随访模板：{template_id}

请生成三段内容：
1. opening_message: 亲切的开场白（30-50字），包含问候和本次随访目的说明
2. questions: 随访问题列表（4-6个问题），每个问题包含：
   - question: 具体提问内容
   - purpose: 该问题的随访目的（如：了解饮食情况、监测胎动、筛查风险等）
3. closing_message: 温暖的结束语（30-50字），包含下次随访时间提示和紧急联系方式提醒

请以JSON格式返回，键名使用英文，值使用中文。"""


def _fallback_followup_generate(pregnant: Pregnant, gest_week: int, gest_day: int,
                                 risk_tags: list, patient_data: dict,
                                 template_id: str) -> FollowUpGenerateResponse:
    """模板兜底随访生成"""
    gest_week_str = f"{gest_week}+{gest_day}"

    opening = f"{pregnant.display_name}您好！我是您的随访护士小安，今天来了解一下您孕{gest_week_str}的近况。请问方便聊几句吗？"

    questions = [
        {"question": "最近身体感觉怎么样？有没有不舒服的地方？", "purpose": "了解一般身体状况和不适症状"},
        {"question": "最近的饮食情况如何？胃口好不好？", "purpose": "了解饮食摄入和营养状况"},
        {"question": "这几天有感觉到宝宝动了吗？大概一天能感觉到几次？", "purpose": "监测胎动情况，筛查胎儿宫内窘迫风险"},
        {"question": "最近一次测量体重是多少？有测量过血压吗？", "purpose": "收集关键健康指标，监测体重增长和血压变化"},
    ]

    if "GDM" in risk_tags:
        questions.insert(2, {"question": "最近血糖监测情况怎么样？空腹和餐后血糖值大概多少？",
                              "purpose": "评估血糖控制情况"})
    if "高血压" in risk_tags:
        questions.insert(2, {"question": "最近每天测量血压了吗？数值大概是多少？有头疼、眼花这些症状吗？",
                              "purpose": "监测血压变化，筛查子痫前期症状"})

    questions.append({"question": "下次产检是什么时候？准备好去了吗？", "purpose": "确认产检计划，督促按时产检"})

    closing = f"好的，感谢您的耐心回答！记得孕{gest_week}周的常规产检按时去哦。如果出现腹痛、出血、胎动异常等情况，请立即联系医院。祝您和宝宝都健康！"

    return FollowUpGenerateResponse(
        pregnant_id=pregnant.pregnant_id,
        opening_message=opening,
        questions=questions[:6],
        closing_message=closing,
    )


# ==================== 护士 AI 持续对话 ====================

from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse


async def _transcribe_audio_with_llm(audio_data: str, audio_format: str, role: str) -> str:
    """已移除：LLM 不适合做 ASR，请使用 cloud 或 local 模式的专用 ASR 服务。"""
    return "（语音识别服务不可用，请使用文字输入）"


@router.post("/chat/stream")
async def nurse_chat_stream(req: ChatStreamRequest, user: TokenPayload = Depends(get_current_user)):
    """护士 AI 持续对话（SSE 流式）— 意图感知动态工具注入

    优化点：
    1. NLU 意图驱动工具子集选择（不再丢弃意图分类结果）
    2. 利用 Agno Agent.tools 可变属性动态注入工具
    3. NLU 上下文作为前缀注入，避免 Agent 重复调用 NLU 工具
    """
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")
    message = req.message
    pregnant_id = req.pregnant_id
    message_type = req.message_type
    audio_data = req.audio_data
    audio_format = req.audio_format

    # ASR 预处理：音频输入转文本（使用专用 ASR 服务）
    if message_type == "AUDIO" and audio_data:
        from ..services.asr_service import asr_service

        transcribed = await asr_service.transcribe(audio_data, audio_format, "nurse")
        if transcribed:
            message = transcribed
        else:
            message = "（语音识别失败，请重试或使用文字输入）"

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    from ..core.patient_targeting import (
        build_patient_target_session_state,
        build_patient_target_system_prefix,
        resolve_patient_target_from_text,
    )
    from ..core.agno_medical_agents import get_nurse_chat_variant_agent, get_nurse_agent
    from ..core.agno_tools import resolve_nurse_tools_by_intent, NURSE_TOOLS, tool_metrics
    from ..core.agno_sse import AgnoSseConfig, AgnoSseState, agno_sse_event_generator

    target = await asyncio.to_thread(
        resolve_patient_target_from_text,
        message,
        fallback_pregnant_id=pregnant_id,
    )
    if target.explicit and not target.pregnant_id:
        return JSONResponse({"error": target.unresolved_reason or "未找到指定孕妇"}, status_code=404)
    pregnant_id = target.pregnant_id or pregnant_id
    target_prefix = build_patient_target_system_prefix(target)
    target_session_state = build_patient_target_session_state(target)

    # 1. NLU 意图解析 — 结果用于动态工具选择 + 上下文注入
    intent_variant = "chat"
    intent_classification = None
    input_text = f"{target_prefix}\n{message}" if target_prefix else message
    if message.strip():
        try:
            from ..core.nlu_engine import nlu_engine
            nlu_result = nlu_engine.parse(message.strip())
            intent_classification = nlu_result.intent

            # 根据意图选择工具子集
            tools, intent_variant = resolve_nurse_tools_by_intent({
                "intent": nlu_result.intent,
                "entities": nlu_result.entities,
            })

            # NLU 上下文注入：将预分析结果作为前缀，避免 Agent 重复调用 NLU 工具
            nlu_prefix = (
                f"[系统预分析] 意图:{nlu_result.intent} "
                f"实体:{nlu_result.entities} "
                f"情绪:{nlu_result.emotion.get('level', 'neutral')}"
            )
            if nlu_result.suggested_tools:
                nlu_prefix += f" 建议工具:{','.join(nlu_result.suggested_tools)}"
            body = f"{nlu_prefix}\n{message}"
            input_text = f"{target_prefix}\n{body}" if target_prefix else body

            # 利用 Agno Agent.tools 可变属性动态注入工具子集
            agent = get_nurse_chat_variant_agent()
            agent.tools = tools
            logger.info("护士端NLU: intent=%s, variant=%s, tools=%d",
                       nlu_result.intent, intent_variant, len(tools))
        except Exception as e:
            logger.warning("护士端意图分类降级: %s", e)
            agent = get_nurse_chat_variant_agent()
            agent.tools = NURSE_TOOLS
    else:
        agent = get_nurse_chat_variant_agent()
        agent.tools = NURSE_TOOLS

    # 复杂意图：升级到全量工具 Agent，支持多步工具链（查询→分析→上报→随访）
    if intent_variant == "complex":
        logger.info("护士端复杂意图，升级到全量工具 Agent")
        agent = get_nurse_agent()

    # 会话 ID：前端传入或自动生成（用于 Agent 多轮对话上下文管理）
    # 安全校验：前端传入的 session_id 必须匹配当前 pregnant_id，防止越权访问他人对话
    if req.session_id:
        expected_prefix = f"nurse_{pregnant_id[:8]}" if pregnant_id else "nurse_anon"
        if not req.session_id.startswith(expected_prefix):
            logger.warning("session_id 归属校验失败: {} vs expected prefix {}", req.session_id[:20], expected_prefix)
            req.session_id = None  # 重置，下方会自动生成
    session_id = req.session_id or f"nurse_{pregnant_id[:8] if pregnant_id else 'anon'}_{uuid.uuid4().hex[:6]}"

    async def agno_event_generator():
        state = AgnoSseState()
        config = AgnoSseConfig(
            agent=agent,
            input_text=input_text,
            user_id=pregnant_id or "anonymous",
            session_id=session_id,
            thinking_map=NURSE_TOOL_THINKING_MAP,
            initial_thinking="小护正在思考...",
            error_log_message="Nurse chat stream error",
            error_chunk_content="\n\n抱歉，AI服务暂时不可用，请稍后再试。",
            done_source="NURSE_AI",
            session_state=target_session_state,
            done_extra={"target_pregnant_id": pregnant_id} if pregnant_id else None,
        )

        tool_metrics.start_session()
        async for event in agno_sse_event_generator(config, state):
            yield event

        metrics_snap = tool_metrics.end_session()

        # 审计日志（后台异步写入，不阻塞响应）
        _bg_task = asyncio.create_task(asyncio.to_thread(
            AuditService.save_log,
            session_id=session_id,
            user_id=pregnant_id or "anonymous",
            agent_role="nurse",
            agent_variant=intent_variant,
            intent_classification=intent_classification,
            user_message=message,
            run_response=state.run_response,
            total_latency_ms=state.elapsed_ms,
            tool_metrics_session=metrics_snap,
        ))
        _bg_task.add_done_callback(_audit_tasks.discard)
        _audit_tasks.add(_bg_task)

    return EventSourceResponse(agno_event_generator(), ping=15)


# ==================== 小Hu 工具函数 ====================

def tool_create_alert(db, pregnant_id: str, level: str, message: str, trigger_source: str = "MANUAL") -> dict:
    """创建预警记录"""
    from ..services.alert_service import alert_service
    from ..utils.timezone import beijing_now

    alert = alert_service.create_alert(
        db=db,
        pregnant_id=pregnant_id,
        rule_id="AGENT_TOOL_ALERT",
        domain="vital",
        level=level,
        message=message,
        trigger_source=trigger_source,
        details={
            "action": "ALERT_NURSE_AND_DOCTOR" if level == "RED" else "ALERT_NURSE",
            "triggered_rules": ["AGENT_TOOL_ALERT"],
            "created_at": beijing_now().isoformat(),
        },
    )
    return {"success": True, "alert_id": str(alert.id), "message": f"已创建{level}级预警"}


def tool_generate_followup_record(db, pregnant_id: str, template_id: str, chief_complaint: str) -> dict:
    """生成随访记录（草稿状态）"""
    from ..services import followup_service
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return {"error": "孕妇不存在"}

    gw = (pregnant.gestational_age_days or 168) // 7
    template = followup_service.get_template(template_id)
    health_edu = followup_service.generate_health_education(gw, pregnant.risk_tags or [])

    record = FollowUpRecord(
        pregnant_id=pregnant_id,
        gestational_week=str(gw),
        chief_complaint=chief_complaint,
        health_education=health_edu,
        status="draft",
    )
    db.add(record)
    db.commit()
    return {"success": True, "record_id": str(record.id), "message": "随访记录已创建（草稿）"}


def tool_update_nursing_note(db, record_id: str, summary: str, health_education: list = None) -> dict:
    """更新护理笔记"""
    from uuid import UUID
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        return {"error": "随访记录不存在"}
    record.summary = summary
    if health_education:
        record.health_education = health_education
    db.commit()
    return {"success": True, "message": "护理笔记已更新"}


# ==================== 随访排期推荐 ====================

def _determine_base_interval(gest_week: int, risk_tags: list, has_critical: bool) -> int:
    """返回建议随访间隔（天）"""
    if has_critical:
        return 0  # 立即
    if gest_week >= 38:
        return 7   # 足月后每周
    if gest_week >= 36:
        return 10  # 36-37周：每10天
    if any(t in risk_tags for t in ("FGR高危", "高血压")):
        return 10
    if "GDM" in risk_tags:
        return 14
    if gest_week < 16:
        return 28  # 孕早期：每月，减少过早打扰
    return 21      # 孕中期常规


def _select_template(risk_tags: list, gest_week: int) -> str:
    """根据风险标签和孕周选择随访模板

    选择逻辑（基于医学指南）：
    - 孕周 < 12: early_pregnancy
    - 孕周 >= 36: late_pregnancy
    - GDM: gdm
    - 高血压: hypertension
    - FGR高危: fgr_high_risk
    - 心理健康: mental_health
    - 其他: standard
    """
    if gest_week < 12:
        return "early_pregnancy"
    if gest_week >= 36:
        return "late_pregnancy"
    if "GDM" in risk_tags:
        return "gdm"
    if any(t in risk_tags for t in ("高血压", "子痫前期")):
        return "hypertension"
    if any(t in risk_tags for t in ("FGR高危", "FGR")):
        return "fgr_high_risk"
    if any(t in risk_tags for t in ("心理健康", "抑郁风险")):
        return "mental_health"
    return "standard"


def _build_suggested_actions(gest_week: int, risk_tags: list, data_freq: str) -> list[str]:
    """根据条件生成建议动作列表"""
    actions = ["确认随访时间并通知孕妇"]
    if "FGR高危" in risk_tags:
        actions.append("提醒携带最近B超报告")
    if any(t in risk_tags for t in ("高血压", "子痫前期")):
        actions.append("提醒携带血压监测记录")
    if "GDM" in risk_tags:
        actions.append("提醒携带血糖监测记录")
    if data_freq == "inactive":
        if gest_week >= 28:
            actions.append("数据上报不活跃，随访时重点了解原因")
        else:
            actions.append("提醒孕妇养成定期上报健康数据的习惯")
    if gest_week >= 38:
        actions.append("确认分娩准备情况（待产包、医院联系等）")
    elif gest_week >= 36:
        actions.append("提醒做好分娩准备工作")
    if 20 <= gest_week <= 24:
        actions.append("提醒预约大排畸B超检查")
    if 24 <= gest_week <= 28:
        actions.append("提醒预约妊娠期糖尿病筛查（OGTT）")
    return actions


def tool_recommend_followup_schedule(db, pregnant_id: str, *, read_only: bool = False) -> dict:
    """根据历史随访和数据上报情况，生成随访排期推荐列表

    Args:
        db: 数据库会话
        pregnant_id: 孕妇 ID
        read_only: 为 True 时不执行僵尸随访自动归档（用于 GET 端点，避免读请求修改 DB 状态）
    """
    # 1. 查询孕妇信息
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return {"error": "孕妇不存在", "pregnant_id": pregnant_id}

    gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []
    current_date = beijing_now().date()

    # 1.5a 预先查询活跃预警和健康数据（用于后续阻止旁路判断）
    active_alerts_pre = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "PENDING"
    ).all()
    has_critical_pre = any(a.level in ("RED", "ORANGE") for a in active_alerts_pre)

    fourteen_days_ago_pre = beijing_now() - timedelta(days=14)
    data_count_14d_pre = db.query(func.count(HealthDataPoint.id)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= fourteen_days_ago_pre,
    ).scalar() or 0

    # 1.5b 检查是否有进行中的随访任务
    # 超时僵尸随访自动归档后继续推荐；未超时的活跃随访在特定条件下可旁路
    active_followup = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id,
        FollowUpRecord.status.in_(["draft", "in_progress"]),
    ).first()
    if active_followup:
        age_days = (current_date - active_followup.created_at.date()).days if active_followup.created_at else 0
        old_status = active_followup.status

        is_zombie = False
        if old_status == "draft" and age_days > settings.followup_zombie_draft_timeout_days:
            is_zombie = True
        elif old_status == "in_progress" and age_days > settings.followup_zombie_inprogress_timeout_days:
            is_zombie = True

        if not is_zombie:
            # ── 旁路条件：即使有活跃 draft，以下情况仍生成推荐 ──
            # ① 存在高级别预警（RED / ORANGE）→ 安全优先，必须暴露
            # ② 数据严重不活跃：14 天零数据 +（高危孕妇 或 孕 ≥28 周）
            risk_tag_set = set(risk_tags)
            _high_risk_tags = {"FGR高危", "高血压", "子痫前期", "GDM"}
            is_high_risk = bool(risk_tag_set & _high_risk_tags)
            is_late_inactive = (data_count_14d_pre == 0 and gest_week >= 28)

            bypass_reasons: list[str] = []
            if has_critical_pre:
                bypass_reasons.append("存在高级别预警需立即处理")
            if data_count_14d_pre == 0 and (is_high_risk or is_late_inactive):
                bypass_reasons.append("14天零数据且属高风险/孕晚期")

            if not bypass_reasons:
                return {
                    "pregnant_id": pregnant_id,
                    "current_gestational_week": f"{gest_week}+{gest_day}",
                    "recommendations": [],
                    "context_summary": {
                        "days_since_last_followup": age_days,
                        "last_followup_date": str(active_followup.created_at.date()) if active_followup.created_at else None,
                        "last_followup_status": old_status,
                        "health_data_frequency": "active",
                        "health_data_count_14d": data_count_14d_pre,
                        "active_alert_count": len(active_alerts_pre),
                        "has_critical_alerts": has_critical_pre,
                        "risk_tags": risk_tags,
                    },
                    "skip_reason": (
                        f"该孕妇已有进行中的随访任务（{old_status}, {age_days}天），"
                        f"请先处理完成后再推荐"
                    ),
                }
            else:
                logger.info(
                    "活跃随访旁路: pregnant_id={} bypass_reasons={} old_status={} age_days={}",
                    pregnant_id, bypass_reasons, old_status, age_days,
                )
        else:
            if read_only:
                # GET 请求不修改 DB，仅记录日志，仍然继续推荐
                logger.info(
                    "检测到僵尸随访(read_only跳过归档) id={} pregnant_id={} old_status={} age_days={}",
                    active_followup.id, pregnant_id, old_status, age_days,
                )
            else:
                # 自动归档僵尸随访，继续执行后续推荐逻辑
                active_followup.status = "archived"
                active_followup.review_comment = (
                    f"[系统自动归档] 原状态 {old_status} 已超过超时时间（{age_days}天），自动关闭。"
                    f"原创建时间: {active_followup.created_at}"
                )
                db.flush()
                logger.info(
                    "自动归档僵尸随访 id={} pregnant_id={} old_status={} age_days={}",
                    active_followup.id, pregnant_id, old_status, age_days,
                )

    # 2. 查询最近随访记录
    last_followup = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(desc(FollowUpRecord.created_at)).first()

    days_since_last = None
    last_followup_date = None
    last_followup_status = None
    if last_followup and last_followup.created_at:
        last_followup_date = last_followup.created_at.date()
        days_since_last = (current_date - last_followup_date).days
        last_followup_status = last_followup.status

    # 3. 查询活跃预警（复用 1.5a 预查询结果）
    active_alerts = active_alerts_pre
    has_critical = has_critical_pre
    alert_count = len(active_alerts)

    # 4. 14天健康数据量（复用 1.5a 预查询结果）
    data_count_14d = data_count_14d_pre

    if data_count_14d >= 5:
        data_freq = "active"
    elif data_count_14d >= 2:
        data_freq = "moderate"
    else:
        data_freq = "inactive"

    # 5. 计算排期
    interval = _determine_base_interval(gest_week, risk_tags, has_critical)
    template = _select_template(risk_tags, gest_week)
    recommendations = []

    # 5.1 立即随访：高危预警
    if has_critical:
        critical_alerts = [a for a in active_alerts if a.level in ("RED", "ORANGE")]
        reasons = [f"[{a.level}] {a.message}" for a in critical_alerts[:3]]
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": _select_template(risk_tags, gest_week),
            "reason": f"存在{len(critical_alerts)}条高级别预警需立即处理：{'；'.join(reasons)}",
            "priority": "high",
            "is_overdue": False,
            "suggested_actions": ["立即联系孕妇进行随访", "确认预警详情并处理"],
        })

    # 5.2 逾期检查
    if interval > 0 and days_since_last is not None and days_since_last > interval * 2.0:
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": f"已超过{days_since_last}天未随访（建议间隔{interval}天），需尽快安排",
            "priority": "high",
            "is_overdue": True,
            "suggested_actions": ["尽快安排随访", "了解未随访原因"],
        })
    elif interval > 0 and days_since_last is None and gest_week >= 16:
        # 孕16周以上从未随访：需关注但仅高危或孕晚期标high
        no_followup_priority = "high" if (
            any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期")) or gest_week >= 28
        ) else "medium"
        # 区分触发原因
        no_followup_reasons = []
        if gest_week >= 28:
            no_followup_reasons.append("已进入孕晚期")
        if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期")):
            matched = [t for t in ("FGR高危", "高血压", "子痫前期") if t in risk_tags]
            no_followup_reasons.append(f"存在高危因素（{'/'.join(matched)}）")
        urgency_suffix = "，" + "；".join(no_followup_reasons) if no_followup_reasons else ""
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": f"该孕妇尚无随访记录（已孕{gest_week}周），建议尽快安排首次随访{urgency_suffix}",
            "priority": no_followup_priority,
            "is_overdue": True,
            "suggested_actions": ["安排首次随访", "建立随访档案"],
        })

    # 5.3 信息缺失检查：从未上报任何健康数据 或 基础信息缺失
    total_data_count = db.query(func.count(HealthDataPoint.id)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
    ).scalar() or 0

    has_basic_info = bool(
        pregnant.gestational_age_days and
        pregnant.height_cm and
        pregnant.pre_pregnancy_weight_kg
    )

    if total_data_count == 0 and gest_week >= 16:
        # 孕16周以上从未上报数据：需联系但仅高危或孕晚期标high
        no_data_priority = "high" if (
            any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期", "GDM")) or gest_week >= 28
        ) else "medium"
        # 区分触发原因
        no_data_reasons = []
        if gest_week >= 28:
            no_data_reasons.append("已进入孕晚期")
        if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期", "GDM")):
            matched = [t for t in ("FGR高危", "高血压", "子痫前期", "GDM") if t in risk_tags]
            no_data_reasons.append(f"存在高危因素（{'/'.join(matched)}）")
        urgency_suffix = "，" + "；".join(no_data_reasons) if no_data_reasons else ""
        reason = f"该孕妇从未上报任何健康数据（已孕{gest_week}周）"
        if not has_basic_info:
            reason += "，且基础信息（孕周/身高/孕前体重）缺失"
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": reason + "，需联系确认情况并督促数据上报" + urgency_suffix,
            "priority": no_data_priority,
            "is_overdue": False,
            "suggested_actions": [
                "联系孕妇确认基础信息并补全档案",
                "指导孕妇如何使用健康数据上报功能",
                "了解未上报数据的原因（技术障碍/认知不足/健康问题）",
            ],
        })
    elif not has_basic_info and gest_week >= 16:
        # 有部分数据但基础信息缺失
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": "孕妇基础信息不完整（孕周/身高/孕前体重缺失），影响风险评估和个性化推荐",
            "priority": "medium",
            "is_overdue": False,
            "suggested_actions": ["联系孕妇补全基础信息", "核实孕周和预产期"],
        })

    # 5.4 数据督促：14天内数据不活跃
    # 默认medium；仅孕晚期(≥28周)零数据 或 高危孕妇零数据 才标high
    if data_freq == "inactive":
        has_data_engagement = any(r.get("reason", "").startswith("数据不活跃") for r in recommendations)
        if not has_data_engagement and not total_data_count == 0:  # 避免与 5.3 重复
            if data_count_14d == 0 and (
                gest_week >= 28 or
                any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期"))
            ):
                priority = "high"
                # 区分触发原因，避免孕晚期被误标为"高危因素"
                urgency_reasons = []
                if gest_week >= 28:
                    urgency_reasons.append("已进入孕晚期需密切监测")
                if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期")):
                    matched_risks = [t for t in ("FGR高危", "高血压", "子痫前期") if t in risk_tags]
                    urgency_reasons.append(f"存在{'/'.join(matched_risks)}，需立即跟进")
                urgency_note = "，" + "；".join(urgency_reasons)
            else:
                priority = "medium"
                urgency_note = ""
            recommendations.append({
                "recommended_date": "immediate",
                "gestational_week": f"{gest_week}+{gest_day}",
                "template_id": template,
                "reason": f"数据不活跃：14天内仅上报{data_count_14d}条数据，需跟进确认情况{urgency_note}",
                "priority": priority,
                "is_overdue": False,
                "suggested_actions": (
                    ["立即联系孕妇确认健康状况", "督促加强健康数据上报"]
                    if priority == "high" else
                    ["提醒孕妇加强健康数据上报", "了解数据未上报原因"]
                ),
            })

    # 5.5 未来排期（2-3次）
    for i in range(1, 4):
        future_date = current_date + timedelta(days=interval * i)
        future_days_offset = interval * i
        future_gest_week = gest_week + (future_days_offset // 7)
        future_gest_day = gest_day + (future_days_offset % 7)
        if future_gest_day >= 7:
            future_gest_week += 1
            future_gest_day -= 7

        if future_gest_week > 42:
            break

        # 优先级：≥38周足月→high；36-37周+高危→high；36-37周无合并症→medium
        if future_gest_week >= 38:
            priority = "high"
        elif future_gest_week >= 36:
            if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期", "GDM")):
                priority = "high"
            else:
                priority = "medium"
        elif any(t in risk_tags for t in ("FGR高危", "高血压")):
            priority = "medium"
        else:
            priority = "low"

        if data_freq == "inactive" and priority == "low":
            priority = "medium"

        future_template = _select_template(risk_tags, future_gest_week)

        reason_parts = []
        if future_gest_week >= 38:
            reason_parts.append(f"孕{future_gest_week}周已足月，需每周随访密切关注")
        elif future_gest_week >= 36:
            if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期", "GDM")):
                matched_future = [t for t in ("FGR高危", "高血压", "子痫前期", "GDM") if t in risk_tags]
                reason_parts.append(f"孕{future_gest_week}周孕晚期合并{'/'.join(matched_future)}，需加密随访")
            else:
                reason_parts.append(f"孕{future_gest_week}周进入孕晚期，建议加密随访")
        # 高危因素：与 priority 判定保持一致
        if any(t in risk_tags for t in ("FGR高危", "高血压", "子痫前期")):
            matched_high = [t for t in ("FGR高危", "高血压", "子痫前期") if t in risk_tags]
            reason_parts.append(f"{'/'.join(matched_high)}孕妇需加密随访")
        if "GDM" in risk_tags:
            reason_parts.append("妊娠期糖尿病需定期监测")
        if not reason_parts:
            reason_parts.append(f"常规随访（建议间隔{interval}天）")

        recommendations.append({
            "recommended_date": future_date.isoformat(),
            "gestational_week": f"{future_gest_week}+{future_gest_day}",
            "template_id": future_template,
            "reason": "；".join(reason_parts),
            "priority": priority,
            "is_overdue": False,
            "suggested_actions": _build_suggested_actions(future_gest_week, risk_tags, data_freq),
        })

    # 6. 排序：immediate优先，然后按priority，最后按日期
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: (
        0 if r["recommended_date"] == "immediate" else 1,
        priority_order.get(r["priority"], 2),
        r["recommended_date"] if r["recommended_date"] != "immediate" else "",
    ))

    return {
        "pregnant_id": pregnant_id,
        "current_gestational_week": f"{gest_week}+{gest_day}",
        "recommendations": recommendations[:5],  # 最多5条
        "context_summary": {
            "days_since_last_followup": days_since_last,
            "last_followup_date": last_followup_date.isoformat() if last_followup_date else None,
            "last_followup_status": last_followup_status,
            "health_data_frequency": data_freq,
            "health_data_count_14d": data_count_14d,
            "active_alert_count": alert_count,
            "has_critical_alerts": has_critical,
            "risk_tags": risk_tags,
        },
    }


@router.get("/followup-recommendations")
def get_followup_recommendations(user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """批量获取所有孕妇的随访排期推荐

    查询所有孕妇，对每人调用排期推荐算法，聚合返回 Top 10 推荐。
    按优先级排序：immediate > high > medium > low。
    """
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")

    all_pregnant = db.query(Pregnant).all()

    # ── 第一层去重：批量查出已有活跃随访的孕妇，这些不参与推荐 ──
    active_pregnant_ids: set[str] = {
        row[0] for row in db.query(FollowUpRecord.pregnant_id).filter(
            FollowUpRecord.status.in_(FOLLOWUP_ACTIVE_STATUSES),
        ).distinct().all()
    }

    # ── 第二层去重：每人只保留最优的 1 条推荐（按 pregnant_id 去重）──
    priority_order = {"high": 0, "medium": 1, "low": 2}

    def _rec_sort_key(r: dict):
        return (
            0 if r["recommended_date"] == "immediate" else 1,
            priority_order.get(r.get("priority", "low"), 2),
            r["recommended_date"] if r["recommended_date"] != "immediate" else "",
        )

    best_by_patient: dict[str, dict] = {}
    skipped_active = 0
    skipped_duplicate = 0

    for p in all_pregnant:
        # 已有活跃随访 → 跳过
        if p.pregnant_id in active_pregnant_ids:
            skipped_active += 1
            continue

        result = tool_recommend_followup_schedule(db, p.pregnant_id, read_only=True)
        if "error" in result:
            continue
        for rec in result.get("recommendations", []):
            # 只保留 immediate 和未来 7 天内的推荐
            if rec["recommended_date"] != "immediate":
                try:
                    from datetime import date as date_cls
                    rec_date = date_cls.fromisoformat(rec["recommended_date"])
                    if (rec_date - beijing_now().date()).days > 7:
                        continue
                except (ValueError, TypeError):
                    continue

            entry = {
                "pregnant_id": p.pregnant_id,
                "patient_name": p.display_name,
                "gestational_week": result.get("current_gestational_week", ""),
                **rec,
            }

            existing = best_by_patient.get(p.pregnant_id)
            if existing is None:
                best_by_patient[p.pregnant_id] = entry
            elif _rec_sort_key(entry) < _rec_sort_key(existing):
                best_by_patient[p.pregnant_id] = entry
                skipped_duplicate += 1
            else:
                skipped_duplicate += 1

    if skipped_active or skipped_duplicate:
        logger.info(
            "推荐去重：跳过{}名活跃随访孕妇，去除{}条同患者重复推荐，最终{}条",
            skipped_active, skipped_duplicate, len(best_by_patient),
        )

    all_recommendations = sorted(best_by_patient.values(), key=_rec_sort_key)

    return {"recommendations": all_recommendations[:10]}


# ==================== AI 分析结果持久化 ====================

from pydantic import BaseModel
from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db


class SaveAiAnalysisRequest(BaseModel):
    pregnant_id: str
    result_data: dict
    analysis_type: str = "general"


class AiAnalysisResponse(BaseModel):
    id: str
    pregnant_id: str
    result_data: dict
    analysis_type: str
    created_at: datetime


@router.post("/ai-analysis", response_model=AiAnalysisResponse)
async def save_ai_analysis(req: SaveAiAnalysisRequest, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """保存 AI 分析结果"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")
    from ..models import AiAnalysisResult

    result = AiAnalysisResult(
        pregnant_id=req.pregnant_id,
        result_data=req.result_data,
        analysis_type=req.analysis_type,
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    return AiAnalysisResponse(
        id=str(result.id),
        pregnant_id=result.pregnant_id,
        result_data=result.result_data,
        analysis_type=result.analysis_type,
        created_at=result.created_at,
    )


@router.get("/ai-analysis/{pregnant_id}", response_model=list[AiAnalysisResponse])
async def get_ai_analysis_history(pregnant_id: str, db: Session = Depends(get_db), user: TokenPayload = Depends(get_current_user)):
    """获取孕妇的 AI 分析历史"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")
    from ..models import AiAnalysisResult

    results = db.query(AiAnalysisResult).filter(
        AiAnalysisResult.pregnant_id == pregnant_id
    ).order_by(desc(AiAnalysisResult.created_at)).limit(20).all()

    return [
        AiAnalysisResponse(
            id=str(r.id),
            pregnant_id=r.pregnant_id,
            result_data=r.result_data,
            analysis_type=r.analysis_type,
            created_at=r.created_at,
        )
        for r in results
    ]


# ==================== 医护协作 - 问题上报 ====================

from ..schemas import NurseDoctorIssueCreate, NurseDoctorIssueResponse


@router.post("/issues/report", response_model=NurseDoctorIssueResponse)
async def report_issue(req: NurseDoctorIssueCreate, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """护士上报问题给医生"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")
    from ..models import NurseDoctorIssue
    from ..core.websocket_manager import ws_manager

    nurse_id = user.sub

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    issue = NurseDoctorIssue(
        pregnant_id=req.pregnant_id,
        reported_by=nurse_id,
        issue_type=req.issue_type,
        title=req.title,
        description=req.description,
        priority=req.priority,
        status="pending",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    # 通过 WebSocket 推送给医生端（护士上报→医生专属，不广播给其他护士）
    issue_level = "ORANGE" if req.priority in ("high", "urgent") else "YELLOW"
    issue_data = {
        "id": str(issue.id),
        "pregnant_id": req.pregnant_id,
        "patient_name": pregnant.display_name,
        "issue_type": req.issue_type,
        "title": req.title,
        "description": req.description,
        "priority": req.priority,
        "status": "pending",
        "created_at": issue.created_at.isoformat(),
        "message": f"[问题上报] {req.title}",
        "level": issue_level,
        "source_role": "nurse",
        "action": "created",
        "details": {"action": "ALERT_DOCTOR"},
    }
    await ws_manager.route_alert(issue_data)

    return NurseDoctorIssueResponse(
        id=str(issue.id),
        pregnant_id=req.pregnant_id,
        patient_name=pregnant.display_name,
        reported_by=issue.reported_by,
        issue_type=issue.issue_type,
        title=issue.title,
        description=issue.description,
        priority=issue.priority,
        status=issue.status,
        created_at=issue.created_at,
    )


@router.get("/issues", response_model=list[NurseDoctorIssueResponse])
async def list_issues(status: str = "pending", user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取护士上报的问题列表"""
    if user.role != "nurse":
        raise HTTPException(status_code=403, detail="需要护士权限")
    from ..models import NurseDoctorIssue

    issues = db.query(NurseDoctorIssue).filter(
        NurseDoctorIssue.status == status
    ).order_by(NurseDoctorIssue.created_at.desc()).limit(20).all()

    result = []
    for issue in issues:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == issue.pregnant_id).first()
        result.append(NurseDoctorIssueResponse(
            id=str(issue.id),
            pregnant_id=issue.pregnant_id,
            patient_name=pregnant.display_name if pregnant else "未知",
            reported_by=issue.reported_by,
            issue_type=issue.issue_type,
            title=issue.title,
            description=issue.description,
            priority=issue.priority,
            status=issue.status,
            assigned_to=issue.assigned_to,
            resolution=issue.resolution,
            created_at=issue.created_at,
        ))

    return result


# ==================== 每日晨报 & 批量随访 ====================


@router.get("/morning-briefing")
async def get_morning_briefing(user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取每日晨报 — 汇总全院孕妇预警、随访和建议"""
    if user.role not in ("nurse", "doctor"):
        raise HTTPException(status_code=403, detail="需要护士或医生权限")
    from ..services.morning_briefing import MorningBriefingService

    briefing = MorningBriefingService.generate(db)
    return briefing


class BatchTriggerRequest(BaseModel):
    pregnant_ids: list[str]
    template_id: str | None = None


@router.post("/followup/batch-trigger")
async def batch_trigger_followup(req: BatchTriggerRequest, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """批量触发随访记录"""
    if user.role not in ("nurse", "doctor"):
        raise HTTPException(status_code=403, detail="需要护士或医生权限")
    if not req.pregnant_ids:
        raise HTTPException(status_code=400, detail="请选择至少一位孕妇")
    if len(req.pregnant_ids) > 50:
        raise HTTPException(status_code=400, detail="单次批量触发不能超过 50 人")
    from ..services.batch_followup import BatchFollowupService

    service = BatchFollowupService()
    result = service.batch_trigger(db, pregnant_ids=req.pregnant_ids, template_id=req.template_id)
    return result.to_dict()
