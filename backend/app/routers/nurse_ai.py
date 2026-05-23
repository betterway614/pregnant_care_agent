"""护士AI辅助 API"""
import json
import asyncio
from datetime import date, datetime, timedelta
from fastapi import APIRouter, HTTPException
from ..utils.timezone import beijing_now
from sqlalchemy import desc, func
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment
from ..schemas import (
    NurseAnalyzeRequest, NurseAnalyzeResponse, FollowUpGenerateRequest, FollowUpGenerateResponse,
    FollowupScheduleResponse, FollowupScheduleRecommendation, FollowupScheduleContext,
)
from ..core import get_llm_client
from ..core.json_parser import parse_llm_json
from ..core.websocket_manager import ws_manager
from ..config import settings

# 护士端工具调用 → 用户友好的中文描述
NURSE_TOOL_THINKING_MAP: dict[str, str] = {
    "agno_query_patient_data": "正在查询患者数据...",
    "agno_analyze_patient_comprehensive": "正在综合分析患者情况...",
    "agno_create_followup_record": "正在创建随访记录...",
    "agno_report_issue_to_doctor": "正在上报问题给医生...",
    "agno_analyze_health_trends": "正在分析健康趋势...",
    "agno_evaluate_vital_rules": "正在评估生命体征...",
    "agno_search_knowledge": "正在查阅护理知识库...",
    "agno_get_patient_context": "正在获取患者信息...",
}

router = APIRouter(prefix="/api/v1/nurse", tags=["护士AI辅助"])


@router.post("/analyze", response_model=NurseAnalyzeResponse)
async def nurse_analyze(req: NurseAnalyzeRequest):
    """AI分析孕妇数据，返回护理建议"""
    db = SessionLocal()
    try:
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
            alert = Alert(
                pregnant_id=req.pregnant_id,
                trigger_source="MANUAL",
                level=alert_level,
                message=f"护士AI分析提示：{result.risk_assessment[:100]}",
                status="PENDING",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)

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
            }

            await ws_manager.broadcast_alert(alert_data)

        # 生成随访排期推荐
        schedule_result = tool_recommend_followup_schedule(db, req.pregnant_id)
        if "error" not in schedule_result:
            result.followup_schedule = FollowupScheduleResponse(**schedule_result)

        return result
    finally:
        db.close()


@router.get("/schedule-recommend/{pregnant_id}")
def recommend_followup_schedule(pregnant_id: str):
    """获取随访排期推荐列表"""
    db = SessionLocal()
    try:
        result = tool_recommend_followup_schedule(db, pregnant_id)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result
    finally:
        db.close()


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
        from ..core.agno_medical_agents import get_nurse_agent
        from ..core.agno_structured import extract_structured_content

        risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
        prompt = (
            f"请为孕妇 {pregnant.display_name}（孕{gest_week}周+{gest_day}天，风险标签：{risk_text}）"
            "提供护理分析。请先调用工具获取最新数据，再输出结构化分析结果。"
        )

        agent = get_nurse_agent()
        response = await agent.arun(input=prompt, user_id=pregnant.pregnant_id)
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
    except Exception:
        return None


def _build_nurse_analyze_prompt(pregnant: Pregnant, gest_week: int, gest_day: int,
                                 risk_tags: list, patient_data: dict) -> str:
    """构建护士分析提示词"""
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
    health_text = "\n".join(
        f"  - {h['metric']}: {h['value']}{h['unit']} (记录于 {h['recorded_at']})"
        for h in patient_data.get("recent_health", [])[:7]
    ) or "  暂无健康数据"
    alerts_text = "\n".join(
        f"  - [{a['level']}] {a['message']} ({a['created_at']})"
        for a in patient_data.get("active_alerts", [])
    ) or "  暂无活跃预警"
    fgr_text = ""
    if patient_data.get("recent_fgr"):
        f = patient_data["recent_fgr"]
        fgr_text = f"  风险等级: {f['risk_level']}, 评估孕周: {f['gestational_weeks']}周, 说明: {f.get('explanation', '')}"

    return f"""请为以下孕妇提供护理分析：

孕妇：{pregnant.display_name}
孕周：{gest_week}周+{gest_day}天
风险标签：{risk_text}

最近健康数据：
{health_text}

活跃预警：
{alerts_text}

最近FGR评估：
{fgr_text or '无'}

请提供：
1. summary: 综合概述（100-200字），概括孕妇当前整体状况
2. risk_assessment: 风险评估（100-200字），分析当前主要风险因素
3. nursing_suggestions: 护理建议（150-300字），具体的护理措施和健康教育要点
4. followup_focus: 随访重点（字符串数组，3-5个项目），列出随访时需要特别关注的内容
5. alert_level: 预警级别判断，取值：
   - "RED"（高危）：需要立即医疗干预，如血压≥140/90、胎动极少、餐后血糖>7.0
   - "ORANGE"（预警）：需要密切关注，如血压偏高、体重增长异常、血糖偏高
   - "YELLOW"（关注）：需要一般关注，如情绪偏高、睡眠不足
   - "NONE"：无需预警

请以JSON格式返回，键名使用英文，值使用中文。"""


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
async def generate_followup(req: FollowUpGenerateRequest):
    """AI生成个性化随访对话脚本"""
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def _try_llm_followup_generate(pregnant: Pregnant, gest_week: int, gest_day: int,
                                      risk_tags: list, patient_data: dict,
                                      template_id: str) -> FollowUpGenerateResponse | None:
    """Agno Agent 生成随访脚本，失败返回 None（由模板兜底）"""
    try:
        from ..core.agno_medical_agents import create_followup_generate_agent
        from ..core.agno_structured import extract_structured_content

        prompt = _build_followup_generate_prompt(pregnant, gest_week, gest_day, risk_tags,
                                                  patient_data, template_id)
        agent = create_followup_generate_agent()
        response = await agent.arun(prompt)
        data = extract_structured_content(response.content)
        if not data:
            return None

        return FollowUpGenerateResponse(
            pregnant_id=pregnant.pregnant_id,
            opening_message=data.get("opening_message", ""),
            questions=data.get("questions", []),
            closing_message=data.get("closing_message", ""),
        )
    except Exception:
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
async def nurse_chat_stream(req: dict):
    """护士 AI 持续对话（SSE 流式）— 使用 Agno Agent 自动工具路由"""
    message = req.get("message", "")
    pregnant_id = req.get("pregnant_id", "")
    message_type = req.get("message_type", "TEXT")
    audio_data = req.get("audio_data")
    audio_format = req.get("audio_format", "webm")

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

    from ..core.agno_medical_agents import get_nurse_chat_agent
    from agno.agent import RunEvent
    agent = get_nurse_chat_agent()

    async def agno_event_generator():
        tool_steps: list[str] = []
        try:
            yield {"event": "thinking", "data": "小护正在思考..."}
            async for chunk in agent.arun(
                input=message,
                stream=True,
                stream_events=True,
                user_id=pregnant_id or "anonymous",
            ):
                event = chunk.event
                if event == RunEvent.tool_call_started and chunk.tool is not None:
                    tool_name = getattr(chunk.tool, "tool_name", "") or ""
                    thinking_msg = NURSE_TOOL_THINKING_MAP.get(
                        tool_name, f"正在处理（{tool_name}）..."
                    )
                    yield {"event": "thinking", "data": thinking_msg}
                elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                    tool_name = getattr(chunk.tool, "tool_name", "") or ""
                    step_desc = NURSE_TOOL_THINKING_MAP.get(tool_name, "")
                    if step_desc and step_desc not in tool_steps:
                        tool_steps.append(step_desc)
                elif event == RunEvent.run_content:
                    if chunk.content and isinstance(chunk.content, str):
                        yield {"event": "chunk", "data": chunk.content}
        except Exception as e:
            from loguru import logger
            logger.error("Nurse AI Agent run error: {}", e)
            yield {"event": "error", "data": str(e)}
            yield {"event": "chunk", "data": "\n\n抱歉，AI服务暂时不可用，请稍后再试。如果问题持续存在，请检查网络连接或联系管理员。"}
        yield {"event": "done", "data": json.dumps({"source": "NURSE_AI", "tool_steps": tool_steps})}

    return EventSourceResponse(agno_event_generator())


# ==================== 小Hu 工具函数 ====================

def tool_create_alert(db, pregnant_id: str, level: str, message: str, trigger_source: str = "MANUAL") -> dict:
    """创建预警记录"""
    alert = Alert(
        pregnant_id=pregnant_id,
        trigger_source=trigger_source,
        level=level,
        message=message,
        status="PENDING",
    )
    db.add(alert)
    db.commit()
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
    if gest_week >= 36:
        return 7
    if any(t in risk_tags for t in ("FGR高危", "高血压")):
        return 10
    if "GDM" in risk_tags:
        return 14
    return 21


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
    if "高血压" in risk_tags:
        actions.append("提醒携带血压监测记录")
    if "GDM" in risk_tags:
        actions.append("提醒携带血糖监测记录")
    if data_freq == "inactive":
        actions.append("督促孕妇加强健康数据上报")
    if gest_week >= 36:
        actions.append("确认分娩准备情况")
    return actions


def tool_recommend_followup_schedule(db, pregnant_id: str) -> dict:
    """根据历史随访和数据上报情况，生成随访排期推荐列表"""
    # 1. 查询孕妇信息
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        return {"error": "孕妇不存在", "pregnant_id": pregnant_id}

    gest_days = pregnant.gestational_age_days or 0
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []
    current_date = beijing_now().date()

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

    # 3. 查询活跃预警
    active_alerts = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "PENDING"
    ).all()
    has_critical = any(a.level in ("RED", "ORANGE") for a in active_alerts)
    alert_count = len(active_alerts)

    # 4. 查询14天健康数据量
    fourteen_days_ago = beijing_now() - timedelta(days=14)
    data_count_14d = db.query(func.count(HealthDataPoint.id)).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= fourteen_days_ago
    ).scalar() or 0

    if data_count_14d >= 7:
        data_freq = "active"
    elif data_count_14d >= 3:
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
    if interval > 0 and days_since_last is not None and days_since_last > interval * 1.5:
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": f"已超过{days_since_last}天未随访（建议间隔{interval}天），需尽快安排",
            "priority": "high",
            "is_overdue": True,
            "suggested_actions": ["尽快安排随访", "了解未随访原因"],
        })
    elif interval > 0 and days_since_last is None and gest_week >= 12:
        recommendations.append({
            "recommended_date": "immediate",
            "gestational_week": f"{gest_week}+{gest_day}",
            "template_id": template,
            "reason": "该孕妇尚无随访记录，建议尽快安排首次随访",
            "priority": "high",
            "is_overdue": True,
            "suggested_actions": ["安排首次随访", "建立随访档案"],
        })

    # 5.3 数据督促
    if data_freq == "inactive" and risk_tags:
        has_data_engagement = any(r.get("reason", "").startswith("数据不活跃") for r in recommendations)
        if not has_data_engagement:
            recommendations.append({
                "recommended_date": "immediate",
                "gestational_week": f"{gest_week}+{gest_day}",
                "template_id": template,
                "reason": f"数据不活跃：14天内仅上报{data_count_14d}条，有风险标签的孕妇需加强监测",
                "priority": "medium",
                "is_overdue": False,
                "suggested_actions": ["督促孕妇加强健康数据上报", "了解数据未上报原因"],
            })

    # 5.4 未来排期（2-3次）
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

        # 优先级
        if future_gest_week >= 36:
            priority = "high"
        elif any(t in risk_tags for t in ("FGR高危", "高血压")):
            priority = "medium"
        else:
            priority = "low"

        if data_freq == "inactive" and priority == "low":
            priority = "medium"

        future_template = _select_template(risk_tags, future_gest_week)

        reason_parts = []
        if future_gest_week >= 36:
            reason_parts.append(f"孕{future_gest_week}周已进入晚期，需每周随访")
        if any(t in risk_tags for t in ("FGR高危", "高血压")):
            reason_parts.append("高危孕妇需加密随访")
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
def get_followup_recommendations():
    """批量获取所有孕妇的随访排期推荐

    查询所有孕妇，对每人调用排期推荐算法，聚合返回 Top 10 推荐。
    按优先级排序：immediate > high > medium > low。
    """
    db = SessionLocal()
    try:
        all_pregnant = db.query(Pregnant).all()
        all_recommendations = []

        for p in all_pregnant:
            result = tool_recommend_followup_schedule(db, p.pregnant_id)
            if "error" in result:
                continue
            for rec in result.get("recommendations", []):
                # 只保留 immediate 和未来 7 天内的推荐
                if rec["recommended_date"] == "immediate":
                    all_recommendations.append({
                        "pregnant_id": p.pregnant_id,
                        "patient_name": p.display_name,
                        "gestational_week": result.get("current_gestational_week", ""),
                        **rec,
                    })
                else:
                    try:
                        from datetime import date as date_cls
                        rec_date = date_cls.fromisoformat(rec["recommended_date"])
                        if (rec_date - date.today()).days <= 7:
                            all_recommendations.append({
                                "pregnant_id": p.pregnant_id,
                                "patient_name": p.display_name,
                                "gestational_week": result.get("current_gestational_week", ""),
                                **rec,
                            })
                    except (ValueError, TypeError):
                        pass

        # 排序：immediate优先，然后按 priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        all_recommendations.sort(key=lambda r: (
            0 if r["recommended_date"] == "immediate" else 1,
            priority_order.get(r.get("priority", "low"), 2),
        ))

        return {"recommendations": all_recommendations[:10]}
    finally:
        db.close()


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
async def save_ai_analysis(req: SaveAiAnalysisRequest, db: Session = Depends(get_db)):
    """保存 AI 分析结果"""
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
async def get_ai_analysis_history(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇的 AI 分析历史"""
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
async def report_issue(req: NurseDoctorIssueCreate):
    """护士上报问题给医生"""
    from ..models import NurseDoctorIssue
    from ..core.websocket_manager import ws_manager

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        issue = NurseDoctorIssue(
            pregnant_id=req.pregnant_id,
            reported_by="current-nurse",
            issue_type=req.issue_type,
            title=req.title,
            description=req.description,
            priority=req.priority,
            status="pending",
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        # 通过 WebSocket 推送给医生端
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
        }
        await ws_manager.broadcast_alert({
            **issue_data,
            "message": f"[问题上报] {req.title}",
            "level": "ORANGE" if req.priority in ("high", "urgent") else "YELLOW",
        })

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
    finally:
        db.close()


@router.get("/issues", response_model=list[NurseDoctorIssueResponse])
async def list_issues(status: str = "pending"):
    """获取护士上报的问题列表"""
    from ..models import NurseDoctorIssue

    db = SessionLocal()
    try:
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
    finally:
        db.close()
