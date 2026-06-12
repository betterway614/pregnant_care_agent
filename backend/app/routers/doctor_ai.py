"""医生AI辅助 API"""
import asyncio
import time
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from ..utils.timezone import beijing_now
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from ..database import SessionLocal, get_db
from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord, FgrAssessment, MedicalOrder
from ..schemas import DoctorAnalyzeRequest, DoctorAnalyzeResponse, ChatStreamRequest
from ..core import get_llm_client
from ..core.json_parser import parse_llm_json
from ..core.auth import extract_user_from_header, get_current_user, TokenPayload
from ..config import settings
from ..services.audit_service import AuditService
from loguru import logger

# 医生端工具调用 → 用户友好的中文描述
DOCTOR_TOOL_THINKING_MAP: dict[str, str] = {
    "agno_analyze_patient_comprehensive": "正在综合分析患者数据...",
    "agno_generate_medical_order": "正在生成医嘱草稿...",
    "agno_handle_issue": "正在处理协作问题...",
    "agno_query_clinical_guideline": "正在查阅临床指南...",
    "agno_analyze_health_trends": "正在分析健康趋势...",
    "agno_evaluate_vital_rules": "正在评估生命体征...",
    "search_knowledge_base": "正在查阅医学知识库...",
    "agno_query_patient_data": "正在查询患者数据...",
}

# _save_doctor_audit_log 已迁移到 app/services/audit_service.py → AuditService.save_log()

# 保持后台审计任务引用，防止 fire-and-forget 被 GC 回收
_audit_tasks: set = set()

router = APIRouter(prefix="/api/v1/doctor", tags=["医生AI辅助"])


@router.post("/analyze/{pregnant_id}", response_model=DoctorAnalyzeResponse)
async def doctor_analyze(pregnant_id: str, req: DoctorAnalyzeRequest = None, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI综合分析孕妇数据，返回含证据引用的分析结果"""
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="需要医生权限")

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

    # 分析完成后不再自动创建医嘱草稿（去重：统一由 POST /orders/generate 负责）
    # suggested_orders 仅作为分析结果中的文本建议展示
    return result


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
        "lab_results_history": [],
    }

    # 健康数据摘要：一次查询全部，再按指标分组（避免 N 次查询）
    metrics = ["weight", "systolic", "diastolic", "fetal_movement", "blood_sugar",
                "blood_sugar_fasting", "blood_sugar_postprandial", "heart_rate"]
    all_recent = get_recent_health_data(db, pregnant_id, limit=50, days=30)
    for metric in metrics:
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

    # 最近随访记录 + 提取生化检验结果
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
        lr = f.lab_results or {}
        if lr:
            context["lab_results_history"].append({
                "gestational_week": f.gestational_week,
                "follow_up_date": f.follow_up_date.isoformat() if f.follow_up_date else "",
                "lab_results": lr,
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
    """通过 Agno 医生 Agent 综合分析（工具驱动 + 结构化输出）"""
    from loguru import logger

    try:
        from ..core.agno_medical_agents import get_doctor_analyze_agent
        from ..core.agno_structured import extract_structured_content

        risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"

        # 提取活跃预警信息，传递给 LLM
        active_alerts = [a for a in context.get("alerts_history", []) if a.get("status") == "PENDING"]
        alert_context = ""
        if active_alerts:
            alert_lines = [
                f"- [{a['level']}] {a['message']}（来源: {a.get('trigger_source', 'N/A')}）"
                for a in active_alerts[:5]
            ]
            alert_context = (
                f"\n\n【重要】该孕妇当前有 {len(active_alerts)} 条活跃预警：\n"
                + "\n".join(alert_lines)
                + "\n请在分析时重点关注这些预警涉及的指标。如果健康数据显示正常但与预警矛盾，"
                  "请明确指出数据与预警的不一致之处，帮助医生判断预警是否仍然有效。"
            )

        extra = f"\n\n医生关注点：{query}" if query else ""
        prompt = (
            f"请为孕妇 {pregnant.display_name}（孕{gest_week}周+{gest_day}天，风险：{risk_text}）"
            f"提供综合分析。请先调用工具获取数据，再输出结构化结果。"
            f"注意：本系统不提供诊断意见，无需输出鉴别诊断。请基于数据提供风险分析和建议。"
            f"{alert_context}{extra}"
        )

        agent = get_doctor_analyze_agent()
        t0 = time.time()
        response = await asyncio.wait_for(
            agent.arun(input=prompt, user_id=pregnant.pregnant_id),
            timeout=120,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        await asyncio.to_thread(
            AuditService.save_log,
            session_id=f"doctor_analyze_{pregnant.pregnant_id}",
            user_id=pregnant.pregnant_id,
            agent_role="doctor",
            agent_variant="analyze",
            intent_classification="ANALYZE",
            user_message=None,
            run_response=response,
            total_latency_ms=elapsed_ms,
        )
        data = extract_structured_content(response.content)
        if not data:
            return None

        return DoctorAnalyzeResponse(
            pregnant_id=pregnant.pregnant_id,
            analysis=data.get("analysis", ""),
            evidence_references=data.get("evidence_references", []),
            suggested_orders=data.get("suggested_orders", ""),
            risk_summary=data.get("risk_summary", ""),
            reasoning_chain=data.get("reasoning_chain", []),
            source="llm",
        )
    except Exception as e:
        logger.error("LLM医生分析异常: {}", e)
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

    # 生化检验结果
    lab_lines = []
    LAB_KEY_NAMES = {
        "hemoglobin": "血红蛋白", "urine_protein": "尿蛋白",
        "alt": "ALT", "ast": "AST", "creatinine": "肌酐",
        "uric_acid": "尿酸", "albumin": "白蛋白",
        "wbc": "白细胞", "platelet": "血小板", "hct": "红细胞压积",
    }
    for lr_entry in context.get("lab_results_history", [])[:3]:
        gw = lr_entry.get("gestational_week", "?")
        lr = lr_entry.get("lab_results", {})
        items = [f"{LAB_KEY_NAMES.get(k, k)}={v}" for k, v in lr.items()]
        lab_lines.append(f"  - 孕{gw}周: {', '.join(items)}")

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

【生化检验结果】
{chr(10).join(lab_lines) if lab_lines else '  暂无化验结果'}

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
                           "fetal_movement": "胎动", "blood_sugar": "血糖",
                           "blood_sugar_fasting": "空腹血糖", "blood_sugar_postprandial": "餐后血糖",
                           "heart_rate": "心率"}
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
    risk_level_map = {"low": "低风险", "medium": "中风险", "high": "高风险", "critical": "危重"}
    if fgr_list:
        analysis_parts.append("## FGR评估结果")
        latest_fgr = fgr_list[0]
        risk_label = risk_level_map.get(latest_fgr["risk_level"], latest_fgr["risk_level"])
        analysis_parts.append(f"- 最近评估（孕{latest_fgr['gestational_weeks']}周）：{risk_label}")
        if latest_fgr.get("explanation"):
            analysis_parts.append(f"- AI判读：{latest_fgr['explanation']}")
        if len(fgr_list) > 1:
            analysis_parts.append("- 历史评估趋势：")
            for f in fgr_list:
                analysis_parts.append(f"  - 孕{f['gestational_weeks']}周：{risk_level_map.get(f['risk_level'], f['risk_level'])}")

    # 生化检验结果
    lab_list = context.get("lab_results_history", [])
    if lab_list:
        analysis_parts.append("## 生化检验结果")
        LAB_KEY_NAMES = {
            "hemoglobin": "血红蛋白", "urine_protein": "尿蛋白",
            "alt": "ALT", "ast": "AST", "creatinine": "肌酐",
            "uric_acid": "尿酸", "albumin": "白蛋白",
            "wbc": "白细胞", "platelet": "血小板", "hct": "红细胞压积",
        }
        for lr_entry in lab_list[:3]:
            gw = lr_entry.get("gestational_week", "?")
            lr = lr_entry.get("lab_results", {})
            items = [f"{LAB_KEY_NAMES.get(k, k)}={v}" for k, v in lr.items()]
            analysis_parts.append(f"- 孕{gw}周：{', '.join(items)}")

    # 预警总结 — 与健康数据交叉对比
    alerts = context.get("alerts_history", [])
    if alerts:
        analysis_parts.append("## 预警与健康数据交叉分析")
        pending = [a for a in alerts if a["status"] == "PENDING"]
        if pending:
            analysis_parts.append(f"- 当前活跃预警 {len(pending)} 条：")
            for a in pending[:5]:
                analysis_parts.append(f"  - [{a['level']}] {a['message']}")
            # 检查是否存在健康数据与预警的矛盾
            high_alerts = [a for a in pending if a.get("level") in ("RED", "ORANGE")]
            if high_alerts and not risk_tags:
                analysis_parts.append(
                    "- ⚠️ 注意：存在高级别预警但无对应风险标签，建议医生复核预警的有效性，"
                    "确认是否需要更新预警状态或重新评估风险等级"
                )

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
    # 提取活跃预警（在推理链中也会用到，提前定义）
    pending_alerts = [a for a in alerts if a.get("status") == "PENDING"]
    high_alerts = [a for a in pending_alerts if a.get("level") in ("RED", "ORANGE")]

    risk_summary_parts = [f"风险标签：{risk_text}"]
    if pending_alerts:
        risk_summary_parts.append(f"；活跃预警 {len(pending_alerts)} 条（其中高级别 {len(high_alerts)} 条）")
    if fgr_list:
        latest_fgr = fgr_list[0]
        if latest_fgr["risk_level"] in ("high", "critical"):
            risk_summary_parts.append("；FGR评估结果需紧急关注")
    if not risk_tags and not high_alerts:
        risk_summary = "".join(risk_summary_parts) + "。建议常规产检随访。"
    else:
        risk_summary = "".join(risk_summary_parts) + "。建议严格按医嘱随访，关注异常体征变化。"

    # 推理链
    reasoning_chain = [
        f"1. 孕妇处于孕{gest_week_str}，风险标签：{risk_text}",
        f"2. 已收集健康数据{len(health_summary)}项指标、FGR评估{len(fgr_list)}次、检验结果{len(lab_list)}次",
    ]
    if fgr_list:
        latest_fgr = fgr_list[0]
        reasoning_chain.append(f"3. FGR评估显示{risk_level_map.get(latest_fgr['risk_level'], latest_fgr['risk_level'])}，需关注胎儿生长趋势")

    # 活跃预警检查 — 与健康数据交叉验证
    if high_alerts:
        alert_summary = "；".join(f"{a['level']}级: {a['message']}" for a in high_alerts[:3])
        reasoning_chain.append(
            f"4. 存在 {len(high_alerts)} 条高级别活跃预警：{alert_summary}"
        )
        reasoning_chain.append(
            "5. 综合判断：请医生结合预警信息和当前健康数据进行复核。"
            "若健康数据正常但预警仍存在，需评估预警是否已失效或需重新评估风险等级"
        )
    elif pending_alerts:
        reasoning_chain.append(
            f"4. 存在 {len(pending_alerts)} 条活跃预警（均为低级别），需持续关注"
        )
        if not risk_tags:
            reasoning_chain.append("5. 综合以上信息，无高风险标签，建议常规产检随访，并关注预警变化")
        else:
            reasoning_chain.append("5. 综合以上信息，存在风险因素需关注，请结合临床综合判断")
    else:
        if not risk_tags:
            reasoning_chain.append("5. 综合以上信息，孕妇当前各项指标在正常范围内，无特殊风险，建议常规产检随访")
        else:
            reasoning_chain.append("5. 综合以上信息，存在风险因素需关注，请结合临床综合判断")

    return DoctorAnalyzeResponse(
        pregnant_id=pregnant.pregnant_id,
        analysis=analysis,
        evidence_references=evidence_references[:5],
        suggested_orders=suggested_orders,
        risk_summary=risk_summary,
        reasoning_chain=reasoning_chain,
        source="template",
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
    alert.reviewed_at = beijing_now()
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


async def _transcribe_audio_with_llm(audio_data: str, audio_format: str, role: str) -> str:
    """已移除：LLM 不适合做 ASR，请使用 cloud 或 local 模式的专用 ASR 服务。"""
    return "（语音识别服务不可用，请使用文字输入）"


@router.post("/chat/stream")
async def doctor_chat_stream(req: ChatStreamRequest, user: TokenPayload = Depends(get_current_user)):
    """医生 AI 持续对话（SSE 流式）— 使用 Agno Agent 自动工具路由"""
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="需要医生权限")
    message = req.message
    pregnant_id = req.pregnant_id
    message_type = req.message_type
    audio_data = req.audio_data
    audio_format = req.audio_format

    # ASR 预处理：音频输入转文本（使用专用 ASR 服务）
    if message_type == "AUDIO" and audio_data:
        from ..services.asr_service import asr_service

        transcribed = await asr_service.transcribe(audio_data, audio_format, "doctor")
        if transcribed:
            message = transcribed
        else:
            message = "（语音识别失败，请重试或使用文字输入）"

    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    from ..core.agno_medical_agents import get_doctor_chat_agent, DOCTOR_AGENT_VARIANT_MAP
    from ..core.agno_tools import resolve_doctor_tools_by_intent
    from ..core.agno_sse import AgnoSseConfig, AgnoSseState, agno_sse_event_generator

    # 意图分类（chat 端点）
    # 注意：chat/stream 端点必须使用无 output_schema 的 Agent，否则 agno 的
    # RunEvent.run_content 不会触发，导致前端无法收到流式内容。
    _STREAMING_SAFE_VARIANTS = {"chat"}
    intent_variant = "chat"
    intent_classification = None
    if message.strip():
        try:
            from ..core.nlu_engine import nlu_engine
            nlu_result = nlu_engine.parse(message.strip())
            intent_classification = nlu_result.intent
            _, resolved_variant = resolve_doctor_tools_by_intent({
                "intent": nlu_result.intent,
                "entities": nlu_result.entities,
            })
            # 只有已知流式安全的变体才直接使用；其余（analyze/order/issue/complex）
            # 均回退到 "chat" 变体，因为那些变体启用了 output_schema，会阻止 SSE 流式输出。
            if resolved_variant in _STREAMING_SAFE_VARIANTS:
                intent_variant = resolved_variant
        except Exception as e:
            logger.warning("医生端chat意图分类降级: %s", e)

    agent_factory = DOCTOR_AGENT_VARIANT_MAP.get(intent_variant, get_doctor_chat_agent)
    agent = agent_factory()

    # 会话 ID：前端传入或自动生成
    # 安全校验：前端传入的 session_id 必须匹配当前 pregnant_id
    if req.session_id:
        expected_prefix = f"doctor_{pregnant_id[:8]}" if pregnant_id else "doctor_anon"
        if not req.session_id.startswith(expected_prefix):
            logger.warning("doctor session_id 归属校验失败: {} vs expected prefix {}", req.session_id[:20], expected_prefix)
            req.session_id = None
    session_id = req.session_id or f"doctor_{pregnant_id[:8] if pregnant_id else 'anon'}_{uuid.uuid4().hex[:6]}"

    async def agno_event_generator():
        state = AgnoSseState()
        config = AgnoSseConfig(
            agent=agent,
            input_text=message,
            user_id=pregnant_id or "anonymous",
            session_id=session_id,
            thinking_map=DOCTOR_TOOL_THINKING_MAP,
            initial_thinking="Dr.智正在思考...",
            error_log_message="Doctor chat stream error",
            error_chunk_content="\n\n抱歉，AI服务暂时不可用，请稍后再试。",
            done_source="DOCTOR_AI",
        )

        async for event in agno_sse_event_generator(config, state):
            yield event

        # 审计日志（后台异步写入，不阻塞响应）
        import asyncio
        _bg_task = asyncio.create_task(asyncio.to_thread(
            AuditService.save_log,
            session_id=session_id,
            user_id=pregnant_id or "anonymous",
            agent_role="doctor",
            agent_variant=intent_variant,
            intent_classification=intent_classification,
            user_message=message,
            run_response=state.run_response,
            total_latency_ms=state.elapsed_ms,
        ))
        _bg_task.add_done_callback(_audit_tasks.discard)
        _audit_tasks.add(_bg_task)

    return EventSourceResponse(agno_event_generator(), ping=15)


# ==================== 医生端 - 问题处理 ====================

from ..schemas import NurseDoctorIssueResponse


@router.get("/issues", response_model=list[NurseDoctorIssueResponse])
async def list_issues(status: str = "pending", user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取待处理的问题列表"""
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="需要医生权限")
    from ..models import NurseDoctorIssue

    issues = db.query(NurseDoctorIssue).filter(
        NurseDoctorIssue.status == status
    ).order_by(
        NurseDoctorIssue.priority.desc(),
        NurseDoctorIssue.created_at.desc()
    ).limit(20).all()

    # 批量查询孕妇信息，避免 N+1 查询
    pregnant_ids = list(set(i.pregnant_id for i in issues))
    pregnant_map = {}
    if pregnant_ids:
        pregnants = db.query(Pregnant).filter(Pregnant.pregnant_id.in_(pregnant_ids)).all()
        pregnant_map = {p.pregnant_id: p for p in pregnants}

    result = []
    for issue in issues:
        pregnant = pregnant_map.get(issue.pregnant_id)
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


@router.put("/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: str, resolution: str = "", user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """处理问题"""
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="需要医生权限")
    from uuid import UUID
    from ..models import NurseDoctorIssue

    doctor_id = user.sub

    issue = db.query(NurseDoctorIssue).filter(NurseDoctorIssue.id == UUID(issue_id)).first()
    if not issue:
        raise HTTPException(404, "问题不存在")

    issue.status = "resolved"
    issue.resolution = resolution or "已处理"
    issue.resolved_at = beijing_now()
    issue.assigned_to = doctor_id
    db.commit()

    return {"success": True, "message": "问题已处理"}


# ==================== 医生端 - 报告生成 ====================

@router.post("/report/{pregnant_id}")
async def generate_report(pregnant_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """生成孕期健康报告"""
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="需要医生权限")

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

    from ..core.agno_medical_agents import get_doctor_chat_agent, DOCTOR_AGENT_VARIANT_MAP
    from ..core.agno_tools import resolve_doctor_tools_by_intent

    # 意图分类（report 端点）
    intent_variant = "analyze"
    intent_classification = "ANALYZE"
    if prompt.strip():
        try:
            from ..core.nlu_engine import nlu_engine
            nlu_result = nlu_engine.parse(prompt.strip())
            intent_classification = nlu_result.intent
            _, intent_variant = resolve_doctor_tools_by_intent({
                "intent": nlu_result.intent,
                "entities": nlu_result.entities,
            })
        except Exception as e:
            logger.warning("医生端报告意图分类降级: %s", e)

    agent_factory = DOCTOR_AGENT_VARIANT_MAP.get(intent_variant, get_doctor_chat_agent)
    agent = agent_factory()
    t0 = time.time()
    response = await agent.arun(input=prompt, user_id=pregnant_id)
    elapsed_ms = int((time.time() - t0) * 1000)
    await asyncio.to_thread(
        AuditService.save_log,
        session_id=f"doctor_report_{pregnant_id}",
        user_id=pregnant_id,
        agent_role="doctor",
        agent_variant=intent_variant,
        intent_classification=intent_classification,
        user_message=None,
        run_response=response,
        total_latency_ms=elapsed_ms,
    )
    report_content = response.content or ""

    return {
        "pregnant_id": pregnant_id,
        "patient_name": pregnant.display_name,
        "report": report_content,
        "generated_at": beijing_now().isoformat(),
    }
