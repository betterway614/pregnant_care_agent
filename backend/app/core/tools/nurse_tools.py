"""
护士专用工具 — 患者查询、随访记录创建、问题上报

职责: 护士角色的 AI Agent 工具集。
"""
from __future__ import annotations

import asyncio
import time as _time

from agno.run import RunContext
from agno.tools import tool

from ...utils.timezone import beijing_now
from .common import _resolve_pid, truncate_tool_result, tool_metrics


@tool
async def agno_query_patient_data(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """查询孕妇详细数据，包含基本信息、近期健康数据、活跃预警、随访记录、规则引擎自动评估。
    比 agno_get_patient_context 返回更丰富（含预警+随访+规则评估），适合护士/医生端使用。
    查询结果会保存到 session_state，供后续工具使用。异步安全。"""
    _t0 = _time.perf_counter()
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _query():
        from ...database import SessionLocal
        from ...models import Pregnant, HealthDataPoint, Alert, FollowUpRecord
        from sqlalchemy import desc

        db = SessionLocal()
        try:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
            if not pregnant:
                return {"error": "孕妇不存在"}

            gest_days = pregnant.gestational_age_days or 0
            result = {
                "basic_info": {
                    "name": pregnant.display_name,
                    "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
                    "risk_tags": pregnant.risk_tags or [],
                }
            }

            recent_data = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == pid
            ).order_by(desc(HealthDataPoint.recorded_at)).limit(5).all()
            result["recent_health_data"] = [
                {"metric": d.metric_code, "value": d.value, "unit": d.unit, "time": d.recorded_at.isoformat()}
                for d in recent_data
            ]

            active_alerts = db.query(Alert).filter(
                Alert.pregnant_id == pid, Alert.status == "PENDING"
            ).limit(5).all()
            result["active_alerts"] = [
                {"level": a.level, "message": a.message, "time": a.created_at.isoformat()}
                for a in active_alerts
            ]

            recent_followups = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == pid
            ).order_by(desc(FollowUpRecord.created_at)).limit(3).all()
            result["recent_followups"] = [
                {"status": f.status, "complaint": f.chief_complaint, "time": f.created_at.isoformat()}
                for f in recent_followups
            ]

            # 自动评估规则引擎
            from ..rule_engine import rule_engine
            latest_vitals = {}
            for d in recent_data:
                code = d.metric_code
                if code not in latest_vitals:
                    latest_vitals[code] = d.value
            # 缺失数据使用 None 而非 0，避免"未测量"被误判为"测量值为0"
            # 例如：fetal_movement=0 会触发 RED "胎动极少"，但实际上只是未测量
            rule_ctx = {
                "sbp": latest_vitals.get("systolic"),  # None if not measured (was 0, caused false "血压偏低")
                "dbp": latest_vitals.get("diastolic"),  # None if not measured
                "weight": latest_vitals.get("weight"),  # None if not measured
                "fetal_movement": latest_vitals.get("fetal_movement"),  # None if not measured (was 0, triggered RED)
                "blood_sugar_fasting": latest_vitals.get("blood_sugar_fasting") or latest_vitals.get("blood_sugar"),  # None if not measured
                "heart_rate": latest_vitals.get("heart_rate"),  # None if not measured
                "gest_week": gest_days // 7 if gest_days else 0,
            }
            try:
                auto_alerts = rule_engine.evaluate_all(rule_ctx)
            except Exception:
                auto_alerts = []
            result["auto_alerts"] = [{"level": a["level"], "message": a["message"]} for a in auto_alerts[:3]]
            result["has_abnormal"] = len(auto_alerts) > 0

            # 保存到 session_state
            if run_context is not None:
                if run_context.session_state is None:
                    run_context.session_state = {}
                run_context.session_state["last_queried_patient"] = {"pregnant_id": pid, "data": result}

            return result
        finally:
            db.close()

    raw = await asyncio.to_thread(_query)
    return truncate_tool_result(raw, tool_name="agno_query_patient_data", tool_start_time=_t0)


@tool
async def agno_list_patients(run_context: RunContext | None = None) -> dict:
    """查询孕妇基本信息列表（最多返回20条，含总数）。
    当护士需要浏览当前管理的孕妇概览时使用此工具。
    不需要指定 pregnant_id，自动返回全部孕妇摘要。异步安全。"""
    _t0 = _time.perf_counter()

    def _list():
        from ...database import SessionLocal
        from ...models import Pregnant

        db = SessionLocal()
        try:
            total = db.query(Pregnant).count()
            patients = db.query(Pregnant).limit(20).all()
            result = [
                {
                    "pregnant_id": p.pregnant_id,
                    "display_name": p.display_name,
                    "gestational_age_days": p.gestational_age_days or 0,
                    "gestational_week": f"{(p.gestational_age_days or 0) // 7}+{(p.gestational_age_days or 0) % 7}",
                    "risk_tags": p.risk_tags or [],
                }
                for p in patients
            ]
            return {"patients": result, "total": total, "returned": len(result)}
        finally:
            db.close()

    raw = await asyncio.to_thread(_list)
    return truncate_tool_result(raw, tool_name="agno_list_patients", tool_start_time=_t0)


@tool
async def agno_create_followup_record(
    pregnant_id: str = "", chief_complaint: str = "", summary: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """创建随访记录草稿。
    当护士需要记录随访内容时使用此工具。异步安全。"""
    _t0 = _time.perf_counter()
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _create():
        from ...database import SessionLocal
        from ...models import Pregnant, FollowUpRecord

        db = SessionLocal()
        try:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
            if not pregnant:
                return {"error": "孕妇不存在"}
            gest_days = pregnant.gestational_age_days or 0
            record = FollowUpRecord(
                pregnant_id=pid, gestational_week=str(gest_days // 7),
                chief_complaint=chief_complaint, summary=summary, status="draft",
            )
            db.add(record)
            db.commit()
            return {"success": True, "record_id": str(record.id), "message": "随访记录已创建（草稿）"}
        finally:
            db.close()

    result = await asyncio.to_thread(_create)
    tool_metrics.record("agno_create_followup_record", (_time.perf_counter() - _t0) * 1000)
    return result


@tool
async def agno_report_issue_to_doctor(
    pregnant_id: str = "", title: str = "", description: str = "",
    priority: str = "medium", run_context: RunContext | None = None,
) -> dict:
    """上报问题给医生。
    当护士发现异常情况需要医生处理时使用此工具。
    如果之前调用过 agno_query_patient_data，可以不传 pregnant_id。异步安全。"""
    _t0 = _time.perf_counter()
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid and run_context and run_context.session_state:
        last_patient = run_context.session_state.get("last_queried_patient")
        if last_patient:
            pid = last_patient.get("pregnant_id", "")
    if not pid:
        return {
            "error": "未指定孕妇",
            "hint": "请先调用 agno_query_patient_data 获取孕妇数据，或直接传入 pregnant_id 参数",
        }

    def _report():
        from ...database import SessionLocal
        from ...models import NurseDoctorIssue

        # 从 run_context 获取实际操作护士 ID，用于审计追溯
        reporter = "nurse_ai"
        if run_context is not None and hasattr(run_context, "user_id") and run_context.user_id:
            reporter = run_context.user_id

        db = SessionLocal()
        try:
            issue = NurseDoctorIssue(
                pregnant_id=pid, reported_by=reporter, issue_type="risk_alert",
                title=title, description=description, priority=priority, status="pending",
            )
            db.add(issue)
            db.commit()
            return {"success": True, "issue_id": str(issue.id), "message": "问题已上报给医生"}
        finally:
            db.close()

    result = await asyncio.to_thread(_report)
    tool_metrics.record("agno_report_issue_to_doctor", (_time.perf_counter() - _t0) * 1000)
    if run_context and run_context.session_state:
        run_context.session_state.pop("last_queried_patient", None)
    return result
