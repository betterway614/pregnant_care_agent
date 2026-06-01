"""Agno @tool 医疗工具集合

将确定性医疗逻辑包装为 Agno 框架的 @tool 装饰器，
供 Agno Agent 自主调用，替代命令式 if/else 管道。

工具分组：
1. NLU：parse_nlu, check_emergency
2. 规则引擎：evaluate_vital_rules
3. 健康数据：save_health_data, get_patient_context
4. 记忆查询：should_ask_weight, should_ask_bp
5. 趋势分析：analyze_health_trends
6. 知识搜索：search_knowledge
7. 心理筛查：get_epds_result

上下文自动注入：
- 通过 Agno 原生 RunContext 自动获取当前 user_id（即 pregnant_id）
- 工具函数可通过 run_context.user_id 获取当前登录用户
- Agent 无需手动传递 pregnant_id，RunContext 由框架自动注入
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import UUID

from agno.run import RunContext
from ..utils.timezone import beijing_now
from agno.tools import tool
from ..config import settings

# NLU 结果上下文：由路由层注入，供 agno_get_nlu_result 工具读取
# key: session_id, value: NLU result dict
_nlu_context: dict[str, dict] = {}


def _resolve_pid(pregnant_id: str, run_context: RunContext | None) -> str:
    """解析孕妇ID：优先使用传入值，为空时从 RunContext.user_id 获取"""
    if pregnant_id:
        return pregnant_id
    if run_context is not None and hasattr(run_context, "user_id") and run_context.user_id:
        return run_context.user_id
    return ""


# ==================== NLU 工具 ====================


@tool(stop_after_tool_call=False)
def agno_parse_nlu(text: str) -> dict:
    """解析用户输入，提取意图、实体和情绪。用于理解用户想做什么。"""
    from ..core.nlu_engine import nlu_engine
    result = nlu_engine.parse(text)
    return {
        "intent": result.intent,
        "entities": result.entities,
        "emotion": result.emotion,
        "is_emergency": result.is_emergency,
    }


@tool
def agno_get_nlu_result(run_context: RunContext | None = None) -> dict:
    """获取当前消息的已解析 NLU 结果（意图、实体、情绪）。
    结果由系统在路由阶段预计算并注入，无需再次解析。"""
    # 从 session_state 读取（如果 Agno 支持注入）
    if run_context is not None and hasattr(run_context, "session_state"):
        nlu = run_context.session_state.get("nlu_result")
        if nlu:
            return nlu
    # 从模块级上下文读取（按 session_id 查找）
    if run_context is not None and hasattr(run_context, "session_id"):
        nlu = _nlu_context.get(run_context.session_id)
        if nlu:
            return nlu
    return {
        "intent": "UNKNOWN",
        "entities": {},
        "emotion": {"level": "neutral", "score": 0},
        "is_emergency": False,
        "note": "NLU结果未注入，使用默认值",
    }


@tool(stop_after_tool_call=True)
def agno_check_emergency(text: str) -> dict:
    """紧急情况检测 - 检查用户消息是否包含紧急医疗状况。
    如果检测到紧急情况，应立即引导就医，不再继续对话。"""
    from ..core.nlu_engine import nlu_engine
    result = nlu_engine.parse(text)
    if not result.is_emergency:
        return {"is_emergency": False, "message": ""}

    if result.intent == "SUICIDE_RISK":
        return {
            "is_emergency": True,
            "intent": "SUICIDE_RISK",
            "message": "⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。",
        }
    return {
        "is_emergency": True,
        "intent": result.intent,
        "message": "⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。如果情况紧急，请拨打120急救电话！",
    }


# ==================== 规则引擎工具 ====================


@tool
def agno_evaluate_vital_rules(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
    sbp: float = 0,
    dbp: float = 0,
    weight: float = 0,
    fetal_movement: float = 0,
    fetal_movement_avg: float = 0,
    weight_gain_weekly: float = 0,
    emotion_score_avg_7d: float = 0,
    blood_sugar_fasting: float = 0,
    blood_sugar_postprandial: float = 0,
    sleep_hours: float = 8,
    gest_week: float = 0,
) -> dict:
    """评估生命体征规则，返回触发的告警列表。用于检测异常指标。
    pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..core.rule_engine import rule_engine

    ctx = {
        "sbp": sbp, "dbp": dbp,
        "weight": weight,
        "fetal_movement": fetal_movement,
        "fetal_movement_avg": fetal_movement_avg,
        "weight_gain_weekly": weight_gain_weekly,
        "emotion_score_avg_7d": emotion_score_avg_7d,
        "blood_sugar_fasting": blood_sugar_fasting,
        "blood_sugar_postprandial": blood_sugar_postprandial,
        "sleep_hours": sleep_hours,
        "gest_week": gest_week,
    }
    alerts = rule_engine.evaluate_all(ctx)
    return {
        "pregnant_id": pid,
        "alerts": alerts,
        "alert_count": len(alerts),
        "has_critical": any(a["level"] == "RED" for a in alerts),
    }


# ==================== 健康数据工具 ====================


def _save_health_data_sync(
    pregnant_id: str,
    weight: float,
    sbp: float,
    dbp: float,
    fetal_movement: float,
    blood_sugar: float,
    heart_rate: float,
    sleep_hours: float,
    steps: float,
) -> dict:
    """同步保存健康数据（在线程池中执行）"""
    from ..database import SessionLocal
    from ..models import HealthDataPoint

    metric_map = {
        "weight": ("weight", "kg"),
        "sbp": ("systolic", "mmHg"),
        "dbp": ("diastolic", "mmHg"),
        "fetal_movement": ("fetal_movement", "次/小时"),
        "blood_sugar": ("blood_sugar", "mmol/L"),
        "heart_rate": ("heart_rate", "bpm"),
        "sleep_hours": ("sleep_hours", "小时"),
        "steps": ("steps", "步"),
    }
    values = {
        "weight": weight, "sbp": sbp, "dbp": dbp,
        "fetal_movement": fetal_movement, "blood_sugar": blood_sugar,
        "heart_rate": heart_rate, "sleep_hours": sleep_hours, "steps": steps,
    }

    saved = []
    db = SessionLocal()
    try:
        for key, value in values.items():
            if value and value > 0:
                code, unit = metric_map[key]
                point = HealthDataPoint(
                    pregnant_id=pregnant_id,
                    metric_code=code,
                    value=float(value),
                    unit=unit,
                    source="AGENT_REPORT",
                )
                db.add(point)
                saved.append(key)
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.warning("健康数据保存失败 pregnant_id=%s metrics=%s", pregnant_id, saved, exc_info=True)
    finally:
        db.close()

    return {"saved_metrics": saved, "count": len(saved)}


@tool
async def agno_save_health_data(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
    weight: float = 0,
    sbp: float = 0,
    dbp: float = 0,
    fetal_movement: float = 0,
    blood_sugar: float = 0,
    heart_rate: float = 0,
    sleep_hours: float = 0,
    steps: float = 0,
) -> dict:
    """保存孕妇健康数据到数据库。只传入有值的参数，0 表示未提供。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    return await asyncio.to_thread(
        _save_health_data_sync,
        pid, weight, sbp, dbp, fetal_movement,
        blood_sugar, heart_rate, sleep_hours, steps,
    )


def _get_patient_context_sync(pregnant_id: str) -> dict:
    """同步获取患者上下文（在线程池中执行）"""
    from ..database import SessionLocal
    from ..services.patient_context_service import get_patient_basic, get_recent_health_data

    db = SessionLocal()
    try:
        basic = get_patient_basic(db, pregnant_id)
        if not basic:
            return {"error": "孕妇不存在"}

        recent = get_recent_health_data(db, pregnant_id, limit=10)

        return {
            "pregnant_id": pregnant_id,
            "display_name": basic["display_name"],
            "nickname": basic["nickname"],
            "gestational_week": basic["gestational_week"],
            "gest_week": basic["gest_week"],
            "risk_tags": basic["risk_tags"],
            "recent_data": [
                {"metric": d["metric"], "value": d["value"], "unit": d["unit"]}
                for d in recent
            ],
        }
    finally:
        db.close()


@tool
async def agno_get_patient_context(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """获取孕妇的完整上下文信息：孕周、风险标签、昵称、最近健康数据。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    return await asyncio.to_thread(_get_patient_context_sync, pid)


# ==================== 记忆查询工具 ====================


@tool
def agno_should_ask_weight(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """检查今天是否需要询问孕妇体重。pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..core.memory_manager import memory_manager
    should_ask = memory_manager.should_ask_weight(pid)
    return {"pregnant_id": pid, "should_ask": should_ask}


@tool
def agno_should_ask_bp(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """检查今天是否需要询问孕妇血压。pregnant_id 可选，留空时自动使用当前登录用户。"""
    pid = _resolve_pid(pregnant_id, run_context)
    from ..core.memory_manager import memory_manager
    should_ask = memory_manager.should_ask_bp(pid)
    return {"pregnant_id": pid, "should_ask": should_ask}


# ==================== 趋势分析工具 ====================


def _analyze_health_trends_sync(pregnant_id: str) -> dict:
    """同步分析健康趋势（在线程池中执行）"""
    from datetime import timedelta
    from ..database import SessionLocal
    from ..models import Pregnant, HealthDataPoint
    from ..core.trend_engine import trend_engine

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()
        gest_week = (pregnant.gestational_age_days // 7) if pregnant and pregnant.gestational_age_days else 0

        two_weeks_ago = beijing_now() - timedelta(days=14)
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
            "data_count": len(records_data),
            "trends": [
                {"metric": t.metric, "current_value": t.current_value, "trend": t.trend, "summary": t.summary, "is_normal": t.is_normal}
                for t in trends
            ],
        }
    finally:
        db.close()


@tool
async def agno_analyze_health_trends(
    pregnant_id: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """分析孕妇近14天健康数据趋势，返回各指标的变化趋势和摘要。
    pregnant_id 可选，留空时自动使用当前登录用户。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    return await asyncio.to_thread(_analyze_health_trends_sync, pid)


# ==================== 心理筛查工具 ====================

# 注意：知识搜索工具由 Agno 框架自动注入 (search_knowledge_base)
# 当 Agent 设置 search_knowledge=True 时，框架会自动创建该工具


@tool
def agno_get_epds_result(total_score: int) -> dict:
    """根据EPDS量表总分返回心理健康筛查结果和建议。分数范围0-30。"""
    if total_score <= 9:
        return {
            "total_score": total_score,
            "risk_level": "low",
            "risk_description": "正常范围，心理健康状况良好",
            "recommendations": ["保持良好的生活习惯", "继续定期产检"],
        }
    elif total_score <= 12:
        return {
            "total_score": total_score,
            "risk_level": "moderate",
            "risk_description": "轻度抑郁倾向，建议关注",
            "recommendations": [
                "建议与家人多沟通，寻求支持",
                "适当增加户外活动和运动",
                "如症状持续2周以上，建议咨询心理医生",
            ],
        }
    elif total_score <= 15:
        return {
            "total_score": total_score,
            "risk_level": "high",
            "risk_description": "中度抑郁风险，建议专业评估",
            "recommendations": [
                "强烈建议咨询专业心理医生",
                "告知家人您的感受，获得支持",
                "保持规律作息，避免独处",
            ],
        }
    else:
        return {
            "total_score": total_score,
            "risk_level": "severe",
            "risk_description": "重度抑郁风险，需要立即关注",
            "recommendations": [
                "请立即联系心理医生或前往医院",
                "拨打心理援助热线：400-161-9995",
                "不要独处，确保身边有人陪伴",
            ],
        }


# ==================== 工具导出 ====================

# 主对话 Agent 工具集
MEDICAL_TOOLS = [
    agno_get_nlu_result,
    agno_check_emergency,
    agno_evaluate_vital_rules,
    agno_save_health_data,
    agno_get_patient_context,
    agno_should_ask_weight,
    agno_should_ask_bp,
    agno_analyze_health_trends,
    agno_get_epds_result,
]


# ==================== 护士端专用工具 ====================


@tool
async def agno_query_patient_data(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """查询孕妇完整数据，包括基本信息、健康数据、预警、随访记录。
    当护士需要了解孕妇整体情况时使用此工具。
    查询结果会保存到 session_state，供后续工具使用。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _query():
        from ..database import SessionLocal
        from ..models import Pregnant, HealthDataPoint, Alert, FollowUpRecord
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
            ).order_by(desc(HealthDataPoint.recorded_at)).limit(10).all()
            result["recent_health_data"] = [
                {"metric": d.metric_code, "value": d.value, "unit": d.unit, "time": d.recorded_at.isoformat()}
                for d in recent_data
            ]

            active_alerts = db.query(Alert).filter(
                Alert.pregnant_id == pid, Alert.status == "PENDING"
            ).all()
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

        # 自动评估规则引擎：将最近数据喂入规则引擎检测异常
        from .rule_engine import rule_engine
        latest_vitals = {}
        for d in recent_data:
            code = d.metric_code
            if code not in latest_vitals:
                latest_vitals[code] = d.value
        rule_ctx = {
            "sbp": latest_vitals.get("systolic", 0),
            "dbp": latest_vitals.get("diastolic", 0),
            "weight": latest_vitals.get("weight", 0),
            "fetal_movement": latest_vitals.get("fetal_movement", 0),
            "blood_sugar_fasting": latest_vitals.get("blood_sugar_fasting", 0) or latest_vitals.get("blood_sugar", 0),
            "heart_rate": latest_vitals.get("heart_rate", 0),
            "gest_week": gest_days // 7 if gest_days else 0,
        }
        try:
            auto_alerts = rule_engine.evaluate_all(rule_ctx)
        except Exception:
            auto_alerts = []
        result["auto_alerts"] = [
            {"level": a["level"], "message": a["message"]}
            for a in auto_alerts
        ]
        result["has_abnormal"] = len(auto_alerts) > 0

        # 保存到 session_state，供后续工具使用
        if run_context is not None:
            if run_context.session_state is None:
                run_context.session_state = {}
            run_context.session_state["last_queried_patient"] = {
                "pregnant_id": pid,
                "data": result,
            }

    return result


@tool
async def agno_create_followup_record(
    pregnant_id: str = "",
    chief_complaint: str = "",
    summary: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """创建随访记录草稿。
    当护士需要记录随访内容时使用此工具。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _create():
        from ..database import SessionLocal
        from ..models import Pregnant, FollowUpRecord

        db = SessionLocal()
        try:
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pid).first()
            if not pregnant:
                return {"error": "孕妇不存在"}

            gest_days = pregnant.gestational_age_days or 0
            record = FollowUpRecord(
                pregnant_id=pid,
                gestational_week=str(gest_days // 7),
                chief_complaint=chief_complaint,
                summary=summary,
                status="draft",
            )
            db.add(record)
            db.commit()

            return {"success": True, "record_id": str(record.id), "message": "随访记录已创建（草稿）"}
        finally:
            db.close()

    return await asyncio.to_thread(_create)


@tool
async def agno_report_issue_to_doctor(
    pregnant_id: str = "",
    title: str = "",
    description: str = "",
    priority: str = "medium",
    run_context: RunContext | None = None,
) -> dict:
    """上报问题给医生。
    当护士发现异常情况需要医生处理时使用此工具。
    如果之前调用过 agno_query_patient_data，可以不传 pregnant_id，自动使用上次查询的孕妇。异步安全。"""
    # 从 session_state 获取上次查询的孕妇 ID
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid and run_context and run_context.session_state:
        last_patient = run_context.session_state.get("last_queried_patient")
        if last_patient:
            pid = last_patient.get("pregnant_id", "")

    if not pid:
        return {"error": "未指定孕妇，请先查询孕妇数据或指定 pregnant_id"}

    def _report():
        from ..database import SessionLocal
        from ..models import NurseDoctorIssue

        db = SessionLocal()
        try:
            issue = NurseDoctorIssue(
                pregnant_id=pid,
                reported_by="nurse_ai",
                issue_type="risk_alert",
                title=title,
                description=description,
                priority=priority,
                status="pending",
            )
            db.add(issue)
            db.commit()

            return {"success": True, "issue_id": str(issue.id), "message": "问题已上报给医生"}
        finally:
            db.close()

    result = await asyncio.to_thread(_report)

    # 清除 session_state 中的查询记录
    if run_context and run_context.session_state:
        run_context.session_state.pop("last_queried_patient", None)

    return result


# ==================== 医生端专用工具 ====================


@tool
async def agno_analyze_patient_comprehensive(pregnant_id: str = "", run_context: RunContext | None = None) -> dict:
    """综合分析孕妇数据，包括健康指标趋势、风险评估、医嘱评价。
    当医生需要全面了解孕妇情况时使用此工具。
    分析结果会保存到 session_state，供后续工具（如生成医嘱）使用。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "未指定孕妇"}

    def _analyze():
        from ..database import SessionLocal
        from ..models import Pregnant, HealthDataPoint, Alert, FgrAssessment, MedicalOrder, FollowUpRecord
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

            # 一次查询所有指标，再在内存中分组（避免 N 次查询）
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

            alerts = db.query(Alert).filter(
                Alert.pregnant_id == pid
            ).order_by(desc(Alert.created_at)).limit(5).all()
            result["alerts"] = [
                {"level": a.level, "message": a.message, "status": a.status, "time": a.created_at.isoformat()}
                for a in alerts
            ]

            # FGR 取最近 5 条（含趋势）
            fgrs = db.query(FgrAssessment).filter(
                FgrAssessment.pregnant_id == pid
            ).order_by(desc(FgrAssessment.assessed_at)).limit(5).all()
            if fgrs:
                result["fgr_assessments"] = [
                    {
                        "risk_level": f.risk_level,
                        "gestational_weeks": f.gestational_weeks,
                        "explanation": f.explanation,
                        "assessed_at": f.assessed_at.isoformat() if f.assessed_at else "",
                    }
                    for f in fgrs
                ]

            # 最新生化检验结果
            latest_followup = db.query(FollowUpRecord).filter(
                FollowUpRecord.pregnant_id == pid,
                FollowUpRecord.lab_results.isnot(None),
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

    # 保存到 session_state，供后续工具使用
    if not isinstance(result, dict) or "error" not in result:
        if run_context is not None:
            if run_context.session_state is None:
                run_context.session_state = {}
            run_context.session_state["last_analyzed_patient"] = {
                "pregnant_id": pid,
                "analysis": result,
            }

    return result


@tool
async def agno_generate_medical_order(
    pregnant_id: str = "",
    content: str = "",
    order_type: str = "standard",
    run_context: RunContext | None = None,
) -> dict:
    """生成医嘱草稿。
    当医生需要开具医嘱时使用此工具。
    如果之前调用过 agno_analyze_patient_comprehensive，可以不传 pregnant_id，自动使用上次分析的孕妇。异步安全。"""
    pid = _resolve_pid(pregnant_id, run_context)
    if not pid and run_context and run_context.session_state:
        last_analyzed = run_context.session_state.get("last_analyzed_patient")
        if last_analyzed:
            pid = last_analyzed.get("pregnant_id", "")

    if not pid:
        return {"error": "未指定孕妇，请先分析患者数据或指定 pregnant_id"}

    def _generate():
        from ..database import SessionLocal
        from ..models import MedicalOrder

        db = SessionLocal()
        try:
            order = MedicalOrder(
                pregnant_id=pid,
                content=content,
                order_type=order_type,
                source="AI_RECOMMENDED",
                status="draft",
            )
            db.add(order)
            db.commit()

            return {"success": True, "order_id": str(order.id), "message": "医嘱草稿已生成"}
        finally:
            db.close()

    result = await asyncio.to_thread(_generate)

    # 清除 session_state 中的分析记录
    if run_context and run_context.session_state:
        run_context.session_state.pop("last_analyzed_patient", None)

    return result


@tool
async def agno_handle_issue(
    issue_id: str = "",
    resolution: str = "",
    run_context: RunContext | None = None,
) -> dict:
    """处理护士上报的问题。
    当医生需要处理问题时使用此工具。异步安全。"""

    def _handle():
        from ..database import SessionLocal
        from ..models import NurseDoctorIssue

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
        from .agno_knowledge import knowledge
        results = knowledge.search(query=topic, max_results=3)
        if results:
            return {
                "topic": topic,
                "guidelines": [
                    doc.content[:500] if hasattr(doc, "content") else str(doc)[:500]
                    for doc in results
                ],
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


# 护士端 Agent 工具集
NURSE_TOOLS = [
    agno_query_patient_data,
    agno_create_followup_record,
    agno_report_issue_to_doctor,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
]

# 医生端 Agent 工具集
DOCTOR_TOOLS = [
    agno_analyze_patient_comprehensive,
    agno_generate_medical_order,
    agno_handle_issue,
    agno_query_clinical_guideline,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
]

# ==================== 工具子集分组（工具路由） ====================

TOOL_GROUPS: dict[str, list] = {
    "chat": [
        # agno_parse_nlu 移除 — 意图已由 chat_handler NLU 预分析注入
        agno_check_emergency,
        agno_get_patient_context,
        agno_get_epds_result,       # 情绪评估
        agno_save_health_data,      # 记录情绪评分
    ],
    "record": [
        agno_get_nlu_result,
        agno_save_health_data,
        agno_evaluate_vital_rules,
        agno_get_patient_context,
    ],
    "qa": [
            agno_get_patient_context,
        agno_analyze_health_trends,
    ],
    "emergency": [
        agno_check_emergency,
        agno_get_patient_context,
    ],
    "complex": MEDICAL_TOOLS,
}

# 意图 → 工具组路由映射
# NLU 返回的意图 → TOOL_GROUPS 的组名
INTENT_TO_GROUP: dict[str, str] = {
    # NLU 引擎意图映射
    "health_data_report": "record",
    "emotion_express": "chat",
    "knowledge_query": "qa",
    "schedule_inquiry": "complex",
    "emergency": "emergency",
    "suicide_risk": "emergency",
    "greeting": "chat",
    "unknown": "complex",
    # 保留旧的直接映射（向后兼容）
    "chat": "chat",
    "emotion": "chat",
    "record_weight": "record",
    "record_bp": "record",
    "record_glucose": "record",
    "record_fetal_movement": "record",
    "ask_knowledge": "qa",
    "ask_symptom": "qa",
    "ask_exam": "qa",
    "emergency": "emergency",
    "health_data_report": "record",
    "schedule_inquiry": "qa",
}


def resolve_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回工具子集和 variant 名称。

    Returns:
        (tools_list, variant_name)
        variant_name: "chat" | "record" | "qa" | "emergency" | "complex"
    """
    if nlu_result is None or not nlu_result.get("intent"):
        return (MEDICAL_TOOLS, "complex")

    intent = nlu_result.get("intent", "").lower()
    group_name = INTENT_TO_GROUP.get(intent)

    if group_name and group_name in TOOL_GROUPS:
        return (TOOL_GROUPS[group_name], group_name)

    return (MEDICAL_TOOLS, "complex")


# ==================== 护士端工具子集分组（工具路由） ====================

NURSE_TOOL_GROUPS: dict[str, list] = {
    "analyze": [
        agno_query_patient_data,
        agno_analyze_health_trends,
        agno_evaluate_vital_rules,
        ],
    "followup": [
        agno_create_followup_record,
        agno_query_patient_data,
    ],
    "report": [
        agno_report_issue_to_doctor,
        agno_query_patient_data,
    ],
    "chat": [
        agno_query_patient_data,
            agno_analyze_health_trends,
    ],
}


def resolve_nurse_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回护士工具子集和 variant 名称。

    Returns:
        (tools_list, variant_name)
        variant_name: "analyze" | "followup" | "report" | "chat" | "complex"
    """
    if nlu_result is None or not nlu_result.get("intent"):
        return (NURSE_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
    nurse_intent_map = {
        "analyze": "analyze", "nurse_analyze": "analyze",
        "followup": "followup", "create_followup": "followup",
        "report": "report", "report_issue": "report",
        "chat": "chat", "greeting": "chat", "emotion": "chat",
        "ask_knowledge": "chat", "ask_symptom": "chat",
    }
    group_name = nurse_intent_map.get(intent)
    if group_name and group_name in NURSE_TOOL_GROUPS:
        return (NURSE_TOOL_GROUPS[group_name], group_name)
    return (NURSE_TOOLS, "complex")


# ==================== 医生端工具子集分组（工具路由） ====================

DOCTOR_TOOL_GROUPS: dict[str, list] = {
    "analyze": [
        agno_analyze_patient_comprehensive,
        agno_analyze_health_trends,
        agno_evaluate_vital_rules,
            agno_query_clinical_guideline,
    ],
    "order": [
        agno_generate_medical_order,
        agno_analyze_patient_comprehensive,
    ],
    "issue": [
        agno_handle_issue,
        agno_analyze_patient_comprehensive,
    ],
    "chat": [
            agno_analyze_health_trends,
        agno_evaluate_vital_rules,
    ],
}


def resolve_doctor_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回医生工具子集和 variant 名称。

    Returns:
        (tools_list, variant_name)
        variant_name: "analyze" | "order" | "issue" | "chat" | "complex"
    """
    if nlu_result is None or not nlu_result.get("intent"):
        return (DOCTOR_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
    doctor_intent_map = {
        "analyze": "analyze", "doctor_analyze": "analyze",
        "order": "order", "generate_order": "order",
        "handle_issue": "issue", "resolve_issue": "issue",
        "chat": "chat", "greeting": "chat",
        "ask_knowledge": "chat", "guideline": "analyze",
    }
    group_name = doctor_intent_map.get(intent)
    if group_name and group_name in DOCTOR_TOOL_GROUPS:
        return (DOCTOR_TOOL_GROUPS[group_name], group_name)
    return (DOCTOR_TOOLS, "complex")
