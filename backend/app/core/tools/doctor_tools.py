"""
医生专用工具 — 综合分析、医嘱生成、问题处理、临床指南

职责: 医生角色的 AI Agent 工具集。
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from agno.run import RunContext
from agno.tools import tool

from ...utils.timezone import beijing_now
from .common import _resolve_pid

logger = logging.getLogger(__name__)


@tool
async def agno_analyze_patient_comprehensive(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """综合分析孕妇数据，包括健康指标趋势、风险评估、医嘱评价。
    当医生需要全面了解孕妇情况时使用此工具。
    分析结果会保存到 session_state，供后续工具使用。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _analyze():
        from ...database import SessionLocal
        from ...models import Pregnant, HealthDataPoint, Alert, FgrAssessment, MedicalOrder, FollowUpRecord
        from sqlalchemy import desc

        db = SessionLocal()
        try:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
            if not pregnant:
                return {"error": "孕妇不存在"}

            gest_days = pregnant.gestational_age_days or 0
            result = {
                "patient_info": {
                    "name": pregnant.display_name,
                    "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
                    "risk_tags": pregnant.risk_tags or [],
                }
            }

            metrics = ["weight", "systolic", "diastolic", "fetal_movement", "blood_sugar",
                        "blood_sugar_fasting", "blood_sugar_postprandial", "heart_rate"]
            all_points = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == pid,
                HealthDataPoint.metric_code.in_(metrics),
            ).order_by(desc(HealthDataPoint.recorded_at)).limit(40).all()
            trends = {}
            for p in all_points:
                m = p.metric_code
                if m not in trends:
                    trends[m] = []
                if len(trends[m]) < 5:
                    trends[m].append({"value": p.value, "unit": p.unit, "time": p.recorded_at.isoformat()})
            result["health_trends"] = trends

            alerts = db.query(Alert).filter(Alert.pregnant_id == pid).order_by(desc(Alert.created_at)).limit(5).all()
            result["alerts"] = [
                {"level": a.level, "message": a.message, "status": a.status, "time": a.created_at.isoformat()}
                for a in alerts
            ]

            fgrs = db.query(FgrAssessment).filter(
                FgrAssessment.pregnant_id == pid
            ).order_by(desc(FgrAssessment.assessed_at)).limit(5).all()
            if fgrs:
                result["fgr_assessments"] = [
                    {"risk_level": f.risk_level, "gestational_weeks": f.gestational_weeks,
                     "explanation": f.explanation, "assessed_at": f.assessed_at.isoformat() if f.assessed_at else ""}
                    for f in fgrs
                ]

            latest_followup = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == pid, FollowUpRecord.lab_results.isnot(None),
            ).order_by(desc(FollowUpRecord.created_at)).first()
            if latest_followup and latest_followup.lab_results:
                result["latest_lab_results"] = {
                    "gestational_week": latest_followup.gestational_week,
                    "follow_up_date": latest_followup.follow_up_date.isoformat() if latest_followup.follow_up_date else "",
                    "lab_results": latest_followup.lab_results,
                }

            orders = db.query(MedicalOrder).filter(
                MedicalOrder.pregnant_id == pid
            ).order_by(desc(MedicalOrder.created_at)).limit(3).all()
            result["recent_orders"] = [
                {"content": o.content, "status": o.status, "time": o.created_at.isoformat()}
                for o in orders
            ]

            return result
        finally:
            db.close()

    result = await asyncio.to_thread(_analyze)
    if not isinstance(result, dict) or "error" not in result:
        if run_context is not None:
            if run_context.session_state is None:
                run_context.session_state = {}
            run_context.session_state["last_analyzed_patient"] = {"pregnant_id": pid, "analysis": result}
    return result


@tool
async def agno_generate_medical_order(
    pregnant_id: str = "", content: str = "", order_type: str = "standard",
    run_context: RunContext | None = None,
) -> dict:
    """生成医嘱草稿。
    当医生需要开具医嘱时使用此工具。
    如果之前调用过 agno_analyze_patient_comprehensive，可以不传 pregnant_id。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid and run_context and run_context.session_state:
        last_analyzed = run_context.session_state.get("last_analyzed_patient")
        if last_analyzed:
            pid = last_analyzed.get("pregnant_id", "")
    if not pid:
        return {"error": "未指定孕妇，请先分析患者数据或指定 pregnant_id"}

    def _generate():
        from ...database import SessionLocal
        from ...models import MedicalOrder

        db = SessionLocal()
        try:
            order = MedicalOrder(
                pregnant_id=pid, content=content, order_type=order_type,
                source="AI_RECOMMENDED", status="draft",
            )
            db.add(order)
            db.commit()
            return {"success": True, "order_id": str(order.id), "message": "医嘱草稿已生成"}
        finally:
            db.close()

    result = await asyncio.to_thread(_generate)
    if run_context and run_context.session_state:
        run_context.session_state.pop("last_analyzed_patient", None)
    return result


@tool
async def agno_handle_issue(issue_id: str = "", resolution: str = "", run_context: RunContext | None = None) -> dict:
    """处理护士上报的问题。
    当医生需要处理问题时使用此工具。异步安全。"""

    def _handle():
        from ...database import SessionLocal
        from ...models import NurseDoctorIssue

        db = SessionLocal()
        try:
            try:
                issue_id_uuid = UUID(issue_id)
            except (ValueError, AttributeError):
                return {"error": "无效的问题ID"}
            issue = db.query(NurseDoctorIssue).filter(NurseDoctorIssue.id == issue_id_uuid).first()
            if not issue:
                return {"error": "问题不存在"}
            issue.status = "resolved"
            issue.resolution = resolution
            issue.resolved_at = beijing_now()
            db.commit()
            return {"success": True, "message": "问题已处理"}
        finally:
            db.close()

    return await asyncio.to_thread(_handle)


@tool
def agno_query_clinical_guideline(topic: str = "") -> dict:
    """查询临床指南和规范。优先使用知识库检索。"""
    try:
        from ..agno_knowledge import knowledge
        if knowledge is None:
            logger.warning("[RAG] clinical_guideline: knowledge 不可用，使用硬编码指南兜底。请检查 RAG_ENABLED 和 DB_TYPE。")
            raise RuntimeError("knowledge is None")
        from agno.filters import IN
        results = knowledge.search(
            query=topic, max_results=3,
            filters=[IN("audience", ["doctor", "nurse", "all"])],
        )
        if results:
            return {
                "topic": topic,
                "guidelines": [doc.content[:500] if hasattr(doc, "content") else str(doc)[:500] for doc in results],
                "source": "knowledge_base",
            }
    except Exception:
        pass

    guidelines = {
        "fgr": "ACOG Practice Bulletin No. 204: Fetal Growth Restriction (2021)",
        "gdm": "ACOG Practice Bulletin No. 190: Gestational Diabetes Mellitus (2023)",
        "hypertension": "ACOG Practice Bulletin No. 222: Gestational Hypertension and Preeclampsia (2023)",
        "prenatal": "中华医学会妇产科学分会. 孕前和孕期保健指南(2022)",
    }
    topic_lower = topic.lower()
    matched = [v for k, v in guidelines.items() if k in topic_lower]
    if not matched:
        matched = list(guidelines.values())[:3]
    return {"topic": topic, "guidelines": matched, "source": "hardcoded_fallback"}
