"""医生AI辅助 API"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment, MedicalOrder
from ..schemas import DoctorAnalyzeRequest, DoctorAnalyzeResponse
from ..core import get_llm_client

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
            return llm_result

        # 模板兜底
        return _fallback_doctor_analyze(pregnant, gest_week, gest_day, risk_tags,
                                        analysis_context, query)
    finally:
        db.close()


def _collect_doctor_analysis_context(db, pregnant_id: str, gest_week: int, gest_day: int) -> dict:
    """收集医生综合分析所需的上下文数据"""
    from sqlalchemy import desc

    context = {
        "gestational_week": f"{gest_week}+{gest_day}",
        "health_data_summary": {},
        "alerts_history": [],
        "fgr_assessments": [],
        "recent_followups": [],
        "recent_orders": [],
    }

    # 健康数据摘要：按指标类型汇总最近数据
    metrics = ["weight", "sbp", "dbp", "fetal_movement", "blood_sugar"]
    for metric in metrics:
        points = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.metric_code == metric
        ).order_by(desc(HealthDataPoint.recorded_at)).limit(5).all()
        if points:
            context["health_data_summary"][metric] = [
                {"value": p.value, "unit": p.unit, "recorded_at": p.recorded_at.isoformat() if p.recorded_at else ""}
                for p in points
            ]

    # 预警历史
    alerts = db.query(Alert).filter(
        Alert.pregnant_id == patient_id
    ).order_by(desc(Alert.created_at)).limit(10).all()
    for a in alerts:
        context["alerts_history"].append({
            "id": str(a.id),
            "level": a.level,
            "message": a.message,
            "trigger_source": a.trigger_source,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else ""
        })

    # FGR评估历史
    fgrs = db.query(FgrAssessment).filter(
        FgrAssessment.pregnant_id == patient_id
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
        FollowUpRecord.pregnant_id == patient_id
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
        MedicalOrder.pregnant_id == patient_id
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
        client = get_llm_client()
        prompt = _build_doctor_analyze_prompt(pregnant, gest_week, gest_day, risk_tags, context, query)
        messages = [
            {"role": "system", "content": "你是一位资深的产科医生，擅长高危妊娠管理和循证医学。请基于孕妇数据提供专业的综合分析，引用权威医学指南。请严格按JSON格式返回，不要包含markdown代码块标记。返回字段：analysis(综合分析), evidence_references(证据引用，字符串数组), suggested_orders(建议医嘱), risk_summary(风险摘要)"},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat(messages)
        if not response or not response.strip():
            return None

        data = _parse_llm_json(response)
        if not data:
            return None

        return DoctorAnalyzeResponse(
            pregnant_id=pregnant.pregnant_id,
            analysis=data.get("analysis", ""),
            evidence_references=data.get("evidence_references", []),
            suggested_orders=data.get("suggested_orders", ""),
            risk_summary=data.get("risk_summary", ""),
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
3. suggested_orders: 建议医嘱（100-300字），具体的下一步处理建议，包括检查项目、药物治疗、转诊建议等
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
            metric_names = {"weight": "体重", "sbp": "收缩压", "dbp": "舒张压",
                           "fetal_movement": "胎动", "blood_sugar": "血糖"}
            name = metric_names.get(metric, metric)
            latest = points[0]
            if metric == "weight":
                analysis_parts.append(f"- {name}：最近记录 {latest['value']}{latest['unit']}，建议每周增重0.3-0.5kg")
            elif metric in ("sbp", "dbp"):
                analysis_parts.append(f"- {name}：最近值 {latest['value']}{latest['unit']}")
                if latest['value'] >= 140 and metric == "sbp":
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

    # 建议医嘱
    order_items = [
        f"1. 孕{gest_week_str}常规产检项目：体重、血压、宫高腹围、尿常规",
    ]
    if "FGR高危" in risk_tags:
        order_items.append("2. 建议每2周行胎儿B超监测（包括AC、HC、FL、EFW、脐动脉血流S/D比值）")
        order_items.append("3. 孕妇每日自数胎动，如每小时<3次或每日<10次及时就诊")
    if "GDM" in risk_tags:
        order_items.append("2. 每日监测空腹及三餐后2小时血糖，目标空腹<5.3mmol/L，餐后2h<6.7mmol/L")
        order_items.append("3. 医学营养治疗+运动指导，必要时胰岛素治疗")
    if "高血压" in risk_tags:
        order_items.append("2. 每日早晚各测血压一次，目标<140/90mmHg")
        order_items.append("3. 查尿蛋白（尿常规+24小时尿蛋白定量），监测子痫前期")
    order_items.append("定期随访：建议每2-4周一次产检，根据风险等级调整频率")

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
