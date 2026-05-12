"""护士AI辅助 API"""
import json
from datetime import date
from fastapi import APIRouter, HTTPException
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment
from ..schemas import NurseAnalyzeRequest, NurseAnalyzeResponse, FollowUpGenerateRequest, FollowUpGenerateResponse
from ..core import get_llm_client
from ..core.prompts import get_nurse_system_prompt
from ..config import settings

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

        # 分析完成后自动创建预警（如果检测到高风险）
        if "高风险" in (result.risk_assessment or "") or "异常" in (result.risk_assessment or ""):
            tool_create_alert(
                db, req.pregnant_id, "ORANGE",
                f"护士AI分析提示：{result.risk_assessment[:100]}",
                "MANUAL"
            )
        return result
    finally:
        db.close()


def _collect_patient_data_for_nurse(db, pregnant_id: str, gest_week: int, gest_day: int) -> dict:
    """收集孕妇数据用于护士分析"""
    from sqlalchemy import desc

    data = {
        "gestational_week": f"{gest_week}+{gest_day}",
        "recent_health": [],
        "active_alerts": [],
        "recent_fgr": None,
        "recent_followup": None,
    }

    # 最近健康数据（最近5条）
    health_points = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id
    ).order_by(desc(HealthDataPoint.recorded_at)).limit(10).all()
    for hp in health_points:
        data["recent_health"].append({
            "metric": hp.metric_code,
            "value": hp.value,
            "unit": hp.unit,
            "recorded_at": hp.recorded_at.isoformat() if hp.recorded_at else ""
        })

    # 活跃预警
    alerts = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id,
        Alert.status == "PENDING"
    ).order_by(desc(Alert.created_at)).limit(5).all()
    for a in alerts:
        data["active_alerts"].append({
            "level": a.level,
            "message": a.message,
            "source": a.trigger_source,
            "created_at": a.created_at.isoformat() if a.created_at else ""
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
    """尝试通过LLM分析孕妇数据，失败返回None"""
    try:
        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            client = get_agno_client()
        else:
            client = get_llm_client()
        prompt = _build_nurse_analyze_prompt(pregnant, gest_week, gest_day, risk_tags, patient_data)
        messages = [
            {"role": "system", "content": get_nurse_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat(messages)
        if not response or not response.strip():
            return None

        data = _parse_llm_json(response)
        if not data:
            return None

        return NurseAnalyzeResponse(
            pregnant_id=pregnant.pregnant_id,
            patient_name=pregnant.display_name,
            summary=data.get("summary", ""),
            risk_assessment=data.get("risk_assessment", ""),
            nursing_suggestions=data.get("nursing_suggestions", ""),
            followup_focus=data.get("followup_focus", []),
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
    """尝试通过LLM生成随访对话脚本，失败返回None"""
    try:
        if settings.agno_enabled:
            from ..core.agno_client import get_agno_client
            client = get_agno_client()
        else:
            client = get_llm_client()
        prompt = _build_followup_generate_prompt(pregnant, gest_week, gest_day, risk_tags,
                                                  patient_data, template_id)
        messages = [
            {"role": "system", "content": "你是一位经验丰富的产科随访护士，擅长与孕妇进行有效的电话/微信随访沟通。请严格按JSON格式返回，不要包含markdown代码块标记。返回字段：opening_message(开场白), questions(问题列表，每项含question和purpose字段), closing_message(结束语)"},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat(messages)
        if not response or not response.strip():
            return None

        data = _parse_llm_json(response)
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


def _parse_llm_json(response: str) -> dict | None:
    """解析LLM返回的JSON，支持多种格式"""
    import re
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    # 尝试提取代码块中的JSON
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, KeyError):
            pass
    # 尝试提取花括号包裹的JSON
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ==================== 护士 AI 持续对话 ====================

from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from ..core.prompts import get_nurse_chat_system_prompt


@router.post("/chat/stream")
async def nurse_chat_stream(req: dict):
    """护士 AI 持续对话（SSE 流式）"""
    message = req.get("message", "")
    pregnant_id = req.get("pregnant_id", "")

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # 构建护士 AI 上下文
    db = SessionLocal()
    patient_summary = ""
    try:
        if pregnant_id:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
            if pregnant:
                gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0
                risk_text = "、".join(pregnant.risk_tags) if pregnant.risk_tags else "无"
                patient_summary = f"当前查看的孕妇: {pregnant.display_name}, 孕{gw}周, 风险: {risk_text}"

                # 获取最近健康数据
                from datetime import datetime, timedelta
                recent = db.query(HealthDataPoint).filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.recorded_at >= datetime.now() - timedelta(days=7)
                ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()
                if recent:
                    data_lines = [f"  - {r.metric_code}: {r.value}{r.unit}" for r in recent]
                    patient_summary += "\n近7日数据:\n" + "\n".join(data_lines)

                # 获取活跃告警
                alerts = db.query(Alert).filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status == "pending"
                ).all()
                if alerts:
                    alert_lines = [f"  - [{a.level}] {a.message}" for a in alerts]
                    patient_summary += "\n活跃告警:\n" + "\n".join(alert_lines)
    finally:
        db.close()

    system_prompt = get_nurse_chat_system_prompt(patient_summary)

    async def event_generator():
        try:
            if settings.agno_enabled:
                from ..core.agno_client import get_agno_client
                client = get_agno_client()
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]
                async for chunk in client.chat_stream(messages):
                    yield {"event": "chunk", "data": chunk}
            else:
                client = get_llm_client()
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]
                async for chunk in client.chat_stream(messages, max_tokens=1024):
                    yield {"event": "chunk", "data": chunk}
        except Exception:
            from ..core.llm_client import MockLLMClient
            mock = MockLLMClient()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            async for chunk in mock.chat_stream(messages):
                yield {"event": "chunk", "data": chunk}

        yield {"event": "done", "data": json.dumps({"source": "NURSE_AI"})}

    return EventSourceResponse(event_generator())


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
