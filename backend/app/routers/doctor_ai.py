"""医生AI辅助 API"""
import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment, MedicalOrder
from ..schemas import DoctorAnalyzeRequest, DoctorAnalyzeResponse
from ..core import get_llm_client
from ..core.json_parser import parse_llm_json
from ..core.prompts import get_doctor_system_prompt, get_doctor_chat_system_prompt
from ..config import settings

# 医生端工具调用 → 用户友好的中文描述
DOCTOR_TOOL_THINKING_MAP: dict[str, str] = {
    "agno_analyze_patient_comprehensive": "正在综合分析患者数据...",
    "agno_generate_medical_order": "正在生成医嘱草稿...",
    "agno_handle_issue": "正在处理协作问题...",
    "agno_query_clinical_guideline": "正在查阅临床指南...",
    "agno_analyze_health_trends": "正在分析健康趋势...",
    "agno_evaluate_vital_rules": "正在评估生命体征...",
    "agno_search_knowledge": "正在查阅医学知识库...",
    "agno_query_patient_data": "正在查询患者数据...",
}

router = APIRouter(prefix="/api/v1/doctor", tags=["医生AI辅助"])


@router.post("/analyze/{pregnant_id}", response_model=DoctorAnalyzeResponse)
async def doctor_analyze(pregnant_id: str, req: DoctorAnalyzeRequest = None):
    """AI综合分析孕妇数据，返回含证据引用的分析结果"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7
        risk_tags = pregnant.risk_tags or []
        query = req.query if req else ""

        # 收集综合分析所需数据
        analysis_context = _collect_doctor_analysis_context(db, pregnant_id, gest_week, gest_day)

        # 尝试LLM综合分析
        llm_result = await _try_llm_doctor_analyze(pregnant, gest_week, gest_day, risk_tags,
                                                    analysis_context, query)
        if llm_result:
            result = llm_result
        else:
            # 模板兜底
            result = _fallback_doctor_analyze(pregnant, gest_week, gest_day, risk_tags,
                                              analysis_context, query)

        # 应用医生草稿安全后处理：拦截确定性诊断结论
        from ..core.agno_guardrails import apply_doctor_draft_safety
        result.analysis = apply_doctor_draft_safety(result.analysis or "")
        result.risk_summary = apply_doctor_draft_safety(result.risk_summary or "")
        result.suggested_orders = apply_doctor_draft_safety(result.suggested_orders or "")

        # 分析完成后自动生成医嘱草稿
        if result.suggested_orders:
            tool_generate_medical_order(
                db, pregnant_id, result.suggested_orders,
                order_type="standard"
            )
        return result
    finally:
        db.close()


def _collect_doctor_analysis_context(db, pregnant_id: str, gest_week: int, gest_day: int) -> dict:
    """收集医生综合分析所需的上下文数据"""
    from sqlalchemy import desc
    from ..services.patient_context_service import get_recent_health_data

    context = {
        "gestational_week": f"{gest_week}+{gest_day}",
        "health_data_summary": {},
        "alerts_history": [],
        "fgr_assessments": [],
        "recent_followups": [],
        "recent_orders": [],
    }

    # 健康数据摘要：按指标类型汇总最近数据
    metrics = ["weight", "systolic", "diastolic", "fetal_movement", "blood_sugar"]
    for metric in metrics:
        all_recent = get_recent_health_data(db, pregnant_id, limit=20, days=30)
        metric_points = [p for p in all_recent if p["metric"] == metric][:5]
        if metric_points:
            context["health_data_summary"][metric] = [
                {"value": p["value"], "unit": p["unit"], "recorded_at": p["recorded_at"]}
                for p in metric_points
            ]

    # 预警历史（含已处理）
    all_alerts = db.query(Alert).filter(
        Alert.pregnant_id == pregnant_id
    ).order_by(desc(Alert.created_at)).limit(10).all()
    for a in all_alerts:
        context["alerts_history"].append({
            "id": str(a.id),
            "level": a.level,
            "message": a.message,
            "trigger_source": a.trigger_source,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        })

    # FGR评估历史
    fgrs = db.query(FgrAssessment).filter(
        FgrAssessment.pregnant_id == pregnant_id
    ).order_by(desc(FgrAssessment.assessed_at)).limit(5).all()
    for f in fgrs:
        context["fgr_assessments"].append({
            "case_id": f.case_id,
            "gestational_weeks": f.gestational_weeks,
            "risk_level": f.risk_level,
            "confidence_lower": f.confidence_lower,
            "confidence_upper": f.confidence_upper,
            "explanation": f.explanation,
            "image_type": f.image_type,
            "assessed_at": f.assessed_at.isoformat() if f.assessed_at else ""
        })

    # 最近随访记录
    followups = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(desc(FollowUpRecord.created_at)).limit(5).all()
    for f in followups:
        context["recent_followups"].append({
            "id": str(f.id),
            "gestational_week": f.gestational_week,
            "chief_complaint": f.chief_complaint,
            "status": f.status,
            "summary": f.summary,
            "created_at": f.created_at.isoformat() if f.created_at else ""
        })

    # 最近医嘱
    orders = db.query(MedicalOrder).filter(
        MedicalOrder.pregnant_id == pregnant_id
    ).order_by(desc(MedicalOrder.created_at)).limit(5).all()
    for o in orders:
        context["recent_orders"].append({
            "id": str(o.id),
            "content": o.content,
            "order_type": o.order_type,
            "source": o.source,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else ""
        })

    return context


async def _try_llm_doctor_analyze(pregnant: Pregnant, gest_week: int, gest_day: int,
                                   risk_tags: list, context: dict,
                                   query: str) -> DoctorAnalyzeResponse | None:
    """尝试通过LLM综合分析孕妇数据，失败返回None"""
    try:
        prompt = _build_doctor_analyze_prompt(pregnant, gest_week, gest_day, risk_tags, context, query)

        if settings.agno_enabled:
            from ..core.agno_medical_agents import create_doctor_agent
            agent = create_doctor_agent()
            response = await agent.arun(input=prompt, user_id=pregnant.pregnant_id)
            content = response.content or ""
            import json
            try:
                data = json.loads(content) if isinstance(content, str) else content
            except json.JSONDecodeError:
                return None
        else:
            client = get_llm_client()
            messages = [
                {"role": "system", "content": get_doctor_system_prompt()},
                {"role": "user", "content": prompt}
            ]
            response = await client.chat(messages)
            if not response or not response.strip():
                return None
            data = parse_llm_json(response)
            if not data:
                return None

        return DoctorAnalyzeResponse(
            pregnant_id=pregnant.pregnant_id,
            analysis=data.get("analysis", ""),
            evidence_references=data.get("evidence_references", []),
            suggested_orders=data.get("suggested_orders", ""),
            risk_summary=data.get("risk_summary", ""),
            differential_diagnosis=data.get("differential_diagnosis", []),
            reasoning_chain=data.get("reasoning_chain", []),
        )
    except Exception:
        return None


def _build_doctor_analyze_prompt(pregnant: Pregnant, gest_week: int, gest_day: int,
                                  risk_tags: list, context: dict, query: str) -> str:
    """构建医生分析提示词"""
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"

    # 健康数据
    health_lines = []
    for metric, points in context.get("health_data_summary", {}).items():
        latest = points[0] if points else None
        if latest:
            health_lines.append(f"  - {metric}: 最近值 {latest['value']}{latest['unit']} (记录于 {latest['recorded_at']})")

    # 预警历史
    alert_lines = []
    for a in context.get("alerts_history", [])[:5]:
        alert_lines.append(f"  - [{a['level']}] {a['message']} (状态: {a['status']}, 时间: {a['created_at']})")

    # FGR评估
    fgr_lines = []
    for f in context.get("fgr_assessments", []):
        confidence = f" 置信区间 [{f.get('confidence_lower', '')}, {f.get('confidence_upper', '')}]" if f.get('confidence_lower') else ""
        fgr_lines.append(f"  - 孕{f['gestational_weeks']}周 风险等级: {f['risk_level']}{confidence} | {f.get('explanation', '')}")

    # 医嘱
    order_lines = []
    for o in context.get("recent_orders", [])[:3]:
        order_lines.append(f"  - [{o['status']}] {o['content']}")

    extra_query = f"\n医生特别关注：{query}" if query else ""

    return f"""请为以下孕妇提供综合分析：

孕妇：{pregnant.display_name} (ID: {pregnant.pregnant_id})
孕周：{gest_week}周+{gest_day}天
风险标签：{risk_text}
末次月经：{pregnant.lmp_date.isoformat() if pregnant.lmp_date else '未知'}
预产期：{pregnant.edd.isoformat() if pregnant.edd else '未知'}
{extra_query}

【健康数据摘要】
{chr(10).join(health_lines) if health_lines else '  暂无健康数据'}

【预警历史】
{chr(10).join(alert_lines) if alert_lines else '  暂无预警记录'}

【FGR评估记录】
{chr(10).join(fgr_lines) if fgr_lines else '  暂无FGR评估'}

【最近医嘱】
{chr(10).join(order_lines) if order_lines else '  暂无医嘱记录'}

请提供：
1. analysis: 综合分析（300-500字），涵盖：孕妇基本情况、关键健康指标趋势、风险评估、现有医嘱评价
2. evidence_references: 证据引用（字符串数组，3-5条），引用相关临床指南（如ACOG、RCOG、中华医学会妇产科学分会指南）
3. suggested_orders: 医嘱草稿建议（100-300字，需医生审核签署），包括检查项目、转诊建议等，不做具体用药方案
4. risk_summary: 风险摘要（50-100字），一句话总结当前核心风险和建议

请以JSON格式返回，键名使用英文，值使用中文。"""


def _fallback_doctor_analyze(pregnant: Pregnant, gest_week: int, gest_day: int,
                              risk_tags: list, context: dict,
                              query: str) -> DoctorAnalyzeResponse:
    """模板兜底医生综合分析"""
    gest_week_str = f"{gest_week}+{gest_day}"
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"

    # 综合分析
    analysis_parts = [
        f"## 孕妇概述\n孕妇{pregnant.display_name}，孕{gest_week_str}，孕周计算依据末次月经{pregnant.lmp_date.isoformat() if pregnant.lmp_date else '未知'}，预估预产期{pregnant.edd.isoformat() if pregnant.edd else '未知'}。当前风险标签：{risk_text}。",
    ]

    # 健康指标分析
    health_summary = context.get("health_data_summary", {})
    if health_summary:
        analysis_parts.append("## 健康指标趋势")
        for metric, points in health_summary.items():
            metric_names = {"weight": "体重", "systolic": "收缩压", "diastolic": "舒张压",
                           "fetal_movement": "胎动", "blood_sugar": "血糖"}
            name = metric_names.get(metric, metric)
            latest = points[0]
            if metric == "weight":
                analysis_parts.append(f"- {name}：最近记录 {latest['value']}{latest['unit']}，建议每周增重0.3-0.5kg")
            elif metric in ("systolic", "diastolic"):
                analysis_parts.append(f"- {name}：最近值 {latest['value']}{latest['unit']}")
                if latest['value'] >= 140 and metric == "systolic":
                    analysis_parts.append("  **关注：收缩压≥140mmHg，需警惕妊娠期高血压**")
            elif metric == "fetal_movement":
                analysis_parts.append(f"- {name}：最近记录 {latest['value']}次/小时，正常范围3-5次/小时")
            elif metric == "blood_sugar":
                analysis_parts.append(f"- {name}：最近值 {latest['value']}{latest['unit']}")

    # FGR评估分析
    fgr_list = context.get("fgr_assessments", [])
    if fgr_list:
        analysis_parts.append("## FGR评估结果")
        latest_fgr = fgr_list[0]
        risk_level_map = {"low": "低风险", "medium": "中风险", "high": "高风险", "critical": "危重"}
        risk_label = risk_level_map.get(latest_fgr["risk_level"], latest_fgr["risk_level"])
        analysis_parts.append(f"- 最近评估（孕{latest_fgr['gestational_weeks']}周）：{risk_label}")
        if latest_fgr.get("explanation"):
            analysis_parts.append(f"- AI判读：{latest_fgr['explanation']}")
        if len(fgr_list) > 1:
            analysis_parts.append("- 历史评估趋势：")
            for f in fgr_list:
                analysis_parts.append(f"  - 孕{f['gestational_weeks']}周：{risk_level_map.get(f['risk_level'], f['risk_level'])}")

    # 预警总结
    alerts = context.get("alerts_history", [])
    if alerts:
        analysis_parts.append("## 预警记录概要")
        pending = [a for a in alerts if a["status"] == "PENDING"]
        if pending:
            analysis_parts.append(f"- 当前活跃预警 {len(pending)} 条，需优先处理")
            for a in pending[:3]:
                analysis_parts.append(f"  - {a['level']}级：{a['message']}")

    analysis = "\n\n".join(analysis_parts)

    # 证据引用
    evidence_references = [
        "ACOG Practice Bulletin No. 204: Fetal Growth Restriction (2021)",
        "中华医学会妇产科学分会. 孕前和孕期保健指南(2022)",
        "ACOG Committee Opinion No. 700: Obesity in Pregnancy (2023)",
        "RCOG Green-top Guideline No. 31: The Investigation and Management of the Small-for-Gestational-Age Fetus",
    ]
    if "GDM" in risk_tags:
        evidence_references.insert(1, "ACOG Practice Bulletin No. 190: Gestational Diabetes Mellitus (2023)")
    if "高血压" in risk_tags:
        evidence_references.insert(1, "ACOG Practice Bulletin No. 222: Gestational Hypertension and Preeclampsia (2023)")

    # 建议医嘱（草稿，需医生审核签署）
    order_items = [
        f"1. 孕{gest_week_str}常规产检项目：体重、血压、宫高腹围、尿常规（需医生确认）",
    ]
    if "FGR高危" in risk_tags:
        order_items.append("2. 建议每2周行胎儿B超监测（包括AC、HC、FL、EFW、脐动脉血流S/D比值）")
        order_items.append("3. 孕妇每日自数胎动，如每小时<3次或每日<10次及时就诊")
    if "GDM" in risk_tags:
        order_items.append("2. 建议监测空腹及三餐后2小时血糖，具体控制目标由医生制定")
        order_items.append("3. 医学营养治疗+运动指导，必要时由医生评估药物干预")
    if "高血压" in risk_tags:
        order_items.append("2. 建议每日早晚各测血压一次，具体控制目标由医生制定")
        order_items.append("3. 建议查尿蛋白（尿常规+24小时尿蛋白定量），由医生评估子痫前期风险")
    order_items.append("定期随访：建议每2-4周一次产检，根据风险等级调整频率。以上均为草稿建议，需医生审核签署。")

    suggested_orders = "\n".join(order_items)

    # 风险摘要
    risk_summary_parts = [f"风险标签：{risk_text}"]
    if alerts:
        pending_alerts = [a for a in alerts if a["status"] == "PENDING"]
        if pending_alerts:
            risk_summary_parts.append(f"；活跃预警 {len(pending_alerts)} 条")
    if fgr_list:
        latest_fgr = fgr_list[0]
        if latest_fgr["risk_level"] in ("high", "critical"):
            risk_summary_parts.append("；FGR评估结果需紧急关注")
    risk_summary = "".join(risk_summary_parts) + "。建议严格按医嘱随访，关注异常体征变化。"

    return DoctorAnalyzeResponse(
        pregnant_id=pregnant.pregnant_id,
        analysis=analysis,
        evidence_references=evidence_references[:5],
        suggested_orders=suggested_orders,
        risk_summary=risk_summary,
    )


# ==================== Dr.智 工具函数 ====================

def tool_generate_medical_order(db, pregnant_id: str, content: str, order_type: str = "standard", alert_id: str = None) -> dict:
    """生成医嘱草稿"""
    from uuid import UUID as _UUID
    order = MedicalOrder(
        pregnant_id=pregnant_id,
        alert_id=_UUID(alert_id) if alert_id else None,
        content=content,
        order_type=order_type,
        source="AI_RECOMMENDED",
        status="draft",
    )
    db.add(order)
    db.commit()
    return {"success": True, "order_id": str(order.id), "message": "医嘱草稿已生成"}


def tool_update_alert_review(db, alert_id: str, action: str, reason: str = "") -> dict:
    """更新预警审核状态"""
    from uuid import UUID as _UUID
    alert = db.query(Alert).filter(Alert.id == _UUID(alert_id)).first()
    if not alert:
        return {"error": "预警不存在"}
    if action == "confirm":
        alert.status = "CONFIRMED"
    elif action == "dismiss":
        alert.status = "DISMISSED"
    alert.reviewed_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": f"预警已{'确认' if action == 'confirm' else 'dismiss'}"}


def tool_record_clinical_note(db, pregnant_id: str, content: str) -> dict:
    """记录临床笔记（写入最新随访记录的summary）"""
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id
    ).order_by(FollowUpRecord.created_at.desc()).first()
    if record:
        record.summary = (record.summary or "") + f"\n\n【临床笔记】{content}"
        db.commit()
        return {"success": True, "message": "临床笔记已记录"}
    return {"error": "未找到该孕妇的随访记录"}


# ==================== Dr.智 持续对话 ====================


@router.post("/chat/stream")
async def doctor_chat_stream(req: dict):
    """医生 AI 持续对话（SSE 流式）— 使用 Agno Agent 自动工具路由"""
    message = req.get("message", "")
    pregnant_id = req.get("pregnant_id", "")

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # 使用 Agno Agent 处理（如果启用）
    if settings.agno_enabled:
        from ..core.agno_medical_agents import create_doctor_chat_agent
        from agno.agent import RunEvent
        agent = create_doctor_chat_agent()

        async def agno_event_generator():
            tool_steps: list[str] = []
            try:
                yield {"event": "thinking", "data": "Dr.智正在思考..."}
                async for chunk in agent.arun(
                    input=message,
                    stream=True,
                    stream_events=True,
                    user_id=pregnant_id or "anonymous",
                ):
                    event = chunk.event
                    # 工具调用开始 → 发送 thinking 事件
                    if event == RunEvent.tool_call_started and chunk.tool is not None:
                        tool_name = getattr(chunk.tool, "tool_name", "") or ""
                        thinking_msg = DOCTOR_TOOL_THINKING_MAP.get(
                            tool_name, f"正在处理（{tool_name}）..."
                        )
                        yield {"event": "thinking", "data": thinking_msg}
                    # 工具调用完成 → 记录步骤
                    elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                        tool_name = getattr(chunk.tool, "tool_name", "") or ""
                        step_desc = DOCTOR_TOOL_THINKING_MAP.get(tool_name, "")
                        if step_desc and step_desc not in tool_steps:
                            tool_steps.append(step_desc)
                    # 流式内容输出
                    elif event == RunEvent.run_content:
                        if chunk.content and isinstance(chunk.content, str):
                            yield {"event": "chunk", "data": chunk.content}
            except Exception as e:
                yield {"event": "error", "data": str(e)}
            yield {"event": "done", "data": json.dumps({"source": "DOCTOR_AI", "tool_steps": tool_steps})}

        return EventSourceResponse(agno_event_generator())

    # 降级到普通 LLM 处理
    db = SessionLocal()
    patient_summary = ""
    try:
        if pregnant_id:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
            if pregnant:
                gw = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0
                risk_text = "、".join(pregnant.risk_tags) if pregnant.risk_tags else "无"
                patient_summary = f"当前查看的孕妇: {pregnant.display_name}, 孕{gw}周, 风险: {risk_text}"

                from datetime import datetime, timedelta
                recent = db.query(HealthDataPoint).filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.recorded_at >= datetime.now() - timedelta(days=7)
                ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()
                if recent:
                    data_lines = [f"  - {r.metric_code}: {r.value}{r.unit}" for r in recent]
                    patient_summary += "\n近7日数据:\n" + "\n".join(data_lines)

                alerts = db.query(Alert).filter(
                    Alert.pregnant_id == pregnant_id,
                    Alert.status == "PENDING"
                ).all()
                if alerts:
                    alert_lines = [f"  - [{a.level}] {a.message}" for a in alerts]
                    patient_summary += "\n活跃告警:\n" + "\n".join(alert_lines)

                orders = db.query(MedicalOrder).filter(
                    MedicalOrder.pregnant_id == pregnant_id
                ).order_by(MedicalOrder.created_at.desc()).limit(3).all()
                if orders:
                    order_lines = [f"  - [{o.status}] {o.content[:50]}..." for o in orders]
                    patient_summary += "\n最近医嘱:\n" + "\n".join(order_lines)
    finally:
        db.close()

    system_prompt = get_doctor_chat_system_prompt(patient_summary)

    async def fallback_event_generator():
        try:
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
        yield {"event": "done", "data": json.dumps({"source": "DOCTOR_AI"})}

    return EventSourceResponse(fallback_event_generator())


# ==================== 医生端 - 问题处理 ====================

from ..schemas import NurseDoctorIssueResponse


@router.get("/issues", response_model=list[NurseDoctorIssueResponse])
async def list_issues(status: str = "pending"):
    """获取待处理的问题列表"""
    from ..models import NurseDoctorIssue

    db = SessionLocal()
    try:
        issues = db.query(NurseDoctorIssue).filter(
            NurseDoctorIssue.status == status
        ).order_by(
            NurseDoctorIssue.priority.desc(),
            NurseDoctorIssue.created_at.desc()
        ).limit(20).all()

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


@router.put("/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: str, resolution: str = ""):
    """处理问题"""
    from uuid import UUID
    from ..models import NurseDoctorIssue

    db = SessionLocal()
    try:
        issue = db.query(NurseDoctorIssue).filter(NurseDoctorIssue.id == UUID(issue_id)).first()
        if not issue:
            raise HTTPException(404, "问题不存在")

        issue.status = "resolved"
        issue.resolution = resolution or "已处理"
        issue.resolved_at = datetime.utcnow()
        issue.assigned_to = "current-doctor"
        db.commit()

        return {"success": True, "message": "问题已处理"}
    finally:
        db.close()


# ==================== 医生端 - 报告生成 ====================

@router.post("/report/{pregnant_id}")
async def generate_report(pregnant_id: str):
    """生成孕期健康报告"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7

        # 收集数据
        patient_summary = f"""孕妇：{pregnant.display_name}
孕周：{gest_week}周+{gest_day}天
风险标签：{', '.join(pregnant.risk_tags) if pregnant.risk_tags else '无'}
管理时间：{pregnant.created_at.strftime('%Y-%m-%d') if pregnant.created_at else '未知'}"""

        # 健康数据
        from ..services.patient_context_service import get_recent_health_data
        health_points = get_recent_health_data(db, pregnant_id, limit=20, days=30)
        health_lines = []
        for point in health_points[:10]:
            health_lines.append(f"- {point['metric']}: {point['value']}{point['unit']} ({point['recorded_at'][:10]})")
        health_data = "\n".join(health_lines) if health_lines else "暂无健康数据"

        # 预警记录
        alerts = db.query(Alert).filter(
            Alert.pregnant_id == pregnant_id
        ).order_by(Alert.created_at.desc()).limit(5).all()
        alert_lines = []
        for alert in alerts:
            alert_lines.append(f"- [{alert.level}] {alert.message} ({alert.created_at.strftime('%Y-%m-%d')})")
        alerts_text = "\n".join(alert_lines) if alert_lines else "暂无预警记录"

        # 生成报告
        prompt = f"""请根据以下信息生成一份结构化的孕期健康报告：

{patient_summary}

【健康数据趋势】
{health_data}

【预警记录】
{alerts_text}

请使用Markdown格式输出，包含以下部分：
1. 基本情况摘要
2. 关键指标分析
3. 风险评估
4. 建议"""

        if settings.agno_enabled:
            from ..core.agno_medical_agents import create_doctor_chat_agent
            agent = create_doctor_chat_agent()
            response = await agent.arun(input=prompt, user_id=pregnant_id)
            report_content = response.content or ""
        else:
            client = get_llm_client()
            messages = [
                {"role": "system", "content": "你是一位资深的产科医生，擅长撰写孕期健康报告。"},
                {"role": "user", "content": prompt},
            ]
            report_content = await client.chat(messages)

        return {
            "pregnant_id": pregnant_id,
            "patient_name": pregnant.display_name,
            "report": report_content,
            "generated_at": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()
