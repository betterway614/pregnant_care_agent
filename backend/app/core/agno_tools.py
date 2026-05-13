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
7. 随访工具：get_followup_context, record_answer, complete_followup
8. 心理筛查：get_epds_result
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import UUID

from agno.tools import tool


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
    pregnant_id: str,
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
    """评估生命体征规则，返回触发的告警列表。用于检测异常指标。"""
    from ..core.rule_engine import rule_engine

    context = {
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
    alerts = rule_engine.evaluate_all(context)
    return {
        "pregnant_id": pregnant_id,
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
    pregnant_id: str,
    weight: float = 0,
    sbp: float = 0,
    dbp: float = 0,
    fetal_movement: float = 0,
    blood_sugar: float = 0,
    heart_rate: float = 0,
    sleep_hours: float = 0,
    steps: float = 0,
) -> dict:
    """保存孕妇健康数据到数据库。只传入有值的参数，0 表示未提供。异步安全，不阻塞事件循环。"""
    return await asyncio.to_thread(
        _save_health_data_sync,
        pregnant_id, weight, sbp, dbp, fetal_movement,
        blood_sugar, heart_rate, sleep_hours, steps,
    )


def _get_patient_context_sync(pregnant_id: str) -> dict:
    """同步获取患者上下文（在线程池中执行）"""
    from ..database import SessionLocal
    from ..models import Pregnant, HealthDataPoint
    from sqlalchemy import desc

    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == pregnant_id
        ).first()
        if not pregnant:
            return {"error": "孕妇不存在"}

        gest_week = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else 0
        gest_day = pregnant.gestational_age_days % 7 if pregnant.gestational_age_days else 0

        recent = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id
        ).order_by(desc(HealthDataPoint.recorded_at)).limit(10).all()

        return {
            "pregnant_id": pregnant_id,
            "display_name": pregnant.display_name,
            "nickname": pregnant.nickname,
            "gestational_week": f"{gest_week}+{gest_day}",
            "gest_week": gest_week,
            "risk_tags": pregnant.risk_tags or [],
            "recent_data": [
                {"metric": d.metric_code, "value": d.value, "unit": d.unit}
                for d in recent
            ],
        }
    finally:
        db.close()


@tool
async def agno_get_patient_context(pregnant_id: str) -> dict:
    """获取孕妇的完整上下文信息：孕周、风险标签、昵称、最近健康数据。异步安全。"""
    return await asyncio.to_thread(_get_patient_context_sync, pregnant_id)


# ==================== 记忆查询工具 ====================


@tool
def agno_should_ask_weight(pregnant_id: str) -> dict:
    """检查今天是否需要询问孕妇体重。返回是否需要询问。"""
    from ..core.memory_manager import memory_manager
    should_ask = memory_manager.should_ask_weight(pregnant_id)
    return {"pregnant_id": pregnant_id, "should_ask": should_ask}


@tool
def agno_should_ask_bp(pregnant_id: str) -> dict:
    """检查今天是否需要询问孕妇血压。返回是否需要询问。"""
    from ..core.memory_manager import memory_manager
    should_ask = memory_manager.should_ask_bp(pregnant_id)
    return {"pregnant_id": pregnant_id, "should_ask": should_ask}


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

        two_weeks_ago = datetime.now() - timedelta(days=14)
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
async def agno_analyze_health_trends(pregnant_id: str) -> dict:
    """分析孕妇近14天健康数据趋势，返回各指标的变化趋势和摘要。异步安全。"""
    return await asyncio.to_thread(_analyze_health_trends_sync, pregnant_id)


# ==================== 知识搜索工具 ====================


@tool
def agno_search_knowledge(query: str, top_k: int = 3) -> dict:
    """搜索产科知识库，返回与问题最相关的文档片段。用于回答孕期知识问题。"""
    from ..config import settings

    if not settings.rag_enabled:
        return {"results": [], "message": "RAG功能未启用"}

    try:
        from ..core.agno_knowledge import agno_knowledge
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有事件循环中，使用同步 search
            from ..core.agno_rag import agno_rag_engine
            result = agno_rag_engine.search(query, top_k=top_k)
        else:
            result = loop.run_until_complete(agno_knowledge.asearch(query, top_k=top_k))
        return {"results": result, "count": len(result)}
    except Exception as e:
        return {"results": [], "error": str(e)}


# ==================== 心理筛查工具 ====================


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


# ==================== 随访工具（已有） ====================


def _find_question_text(template: dict, key: str) -> str | None:
    """根据 key 查找问题文本"""
    for q in template.get("questions", []):
        if q["key"] == key:
            return q.get("question", key)
    return None


def _try_save_health_data(pregnant_id: str, question_key: str, text: str, db) -> bool:
    """尝试从回答文本中提取可量化的健康数据并保存"""
    from ..services import followup_service

    parsed = followup_service.extract_health_value(question_key, text)
    if not parsed:
        return False

    source = "FOLLOWUP"

    # 处理血压（拆分为 sbp/dbp）- bp, bp_morning, bp_evening
    if question_key in ("bp", "bp_morning", "bp_evening"):
        if "sbp" in parsed and "dbp" in parsed:
            _insert_health_point(db, pregnant_id, "systolic", parsed["sbp"], "mmHg", source)
            _insert_health_point(db, pregnant_id, "diastolic", parsed["dbp"], "mmHg", source)
            return True

    # 血糖指标
    if question_key in ("blood_sugar_fasting", "blood_sugar_postprandial"):
        if "metric_code" in parsed:
            _insert_health_point(
                db, pregnant_id, parsed["metric_code"], parsed["value"], parsed.get("unit", ""), source
            )
            return True

    # 其他单值指标
    if "metric_code" in parsed:
        _insert_health_point(
            db, pregnant_id, parsed["metric_code"], parsed["value"], parsed.get("unit", ""), source
        )
        return True

    return False


def _insert_health_point(
    db, pregnant_id: str, metric_code: str, value: float, unit: str, source: str
):
    """插入一条健康数据点"""
    from ..models import HealthDataPoint

    point = HealthDataPoint(
        pregnant_id=pregnant_id,
        metric_code=metric_code,
        value=float(value),
        unit=unit,
        recorded_at=datetime.utcnow(),
        source=source,
    )
    db.add(point)


async def _get_followup_context_impl(record_id: str) -> dict:
    """获取随访上下文：模板问题 + 已回答 + 孕妇信息"""
    from ..database import SessionLocal
    from ..services import followup_service
    from ..models import FollowUpRecord, Pregnant

    db = SessionLocal()
    try:
        try:
            record = db.query(FollowUpRecord).filter(
                FollowUpRecord.id == UUID(record_id)
            ).first()
        except Exception:
            return {"error": "无效的记录ID格式"}

        if not record:
            return {"error": "随访记录不存在"}

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == record.pregnant_id
        ).first()

        current_data = record.self_reported_data or {}
        template = followup_service.get_template_from_questions(current_data)
        all_questions = template["questions"]

        answered_keys = set(current_data.keys())
        pending_questions = [q for q in all_questions if q["key"] not in answered_keys]

        return {
            "record_id": str(record.id),
            "patient_name": pregnant.nickname or pregnant.display_name if pregnant else "未知",
            "gestational_week": record.gestational_week or "?",
            "risk_tags": pregnant.risk_tags if pregnant else [],
            "all_questions": [
                {"key": q["key"], "question": q["question"]} for q in all_questions
            ],
            "pending_questions": [
                {"key": q["key"], "question": q["question"]} for q in pending_questions
            ],
            "answered_questions": [
                {"key": k, "answer": v} for k, v in current_data.items()
            ],
            "answered_count": len(answered_keys),
            "total_count": len(all_questions),
            "status": record.status,
            "message": f"已回答 {len(answered_keys)}/{len(all_questions)} 个问题"
            if answered_keys
            else "随访尚未开始",
        }
    finally:
        db.close()


async def _record_answer_impl(
    record_id: str, question_key: str, answer_text: str
) -> dict:
    """记录孕妇回答，自动解析并保存健康数据

    状态机: draft → in_progress（首次回答时自动转换）
    """
    from ..database import SessionLocal
    from ..services import followup_service
    from ..models import FollowUpRecord
    from ..schemas import FOLLOWUP_STATUS_IN_PROGRESS, FOLLOWUP_ACTIVE_STATUSES

    db = SessionLocal()
    try:
        try:
            record = db.query(FollowUpRecord).filter(
                FollowUpRecord.id == UUID(record_id)
            ).first()
        except Exception:
            return {"error": "无效的记录ID格式"}

        if not record:
            return {"error": "随访记录不存在"}
        if record.status not in FOLLOWUP_ACTIVE_STATUSES:
            return {"error": f"该随访状态为 {record.status}，无法继续记录"}

        # 状态机: draft → in_progress
        if record.status == "draft":
            record.status = FOLLOWUP_STATUS_IN_PROGRESS

        current_data = dict(record.self_reported_data) if record.self_reported_data else {}
        current_data[question_key] = answer_text
        record.self_reported_data = current_data

        if question_key == "feeling" and not record.chief_complaint:
            record.chief_complaint = answer_text

        health_saved = _try_save_health_data(record.pregnant_id, question_key, answer_text, db)

        db.commit()

        template = followup_service.get_template_from_questions(current_data)
        all_keys = [q["key"] for q in template["questions"]]
        remaining = [k for k in all_keys if k not in current_data]
        answered_count = len(current_data)
        total = len(all_keys)

        return {
            "success": True,
            "record_id": record_id,
            "question_key": question_key,
            "saved": True,
            "health_data_saved": health_saved,
            "remaining_questions": remaining,
            "all_questions_answered": answered_count >= total,
            "answered_count": answered_count,
            "total_count": total,
            "status": record.status,
            "next_question": (
                _find_question_text(template, remaining[0]) if remaining else None
            ),
        }
    finally:
        db.close()


async def _complete_followup_impl(record_id: str, summary: str = "") -> dict:
    """完成随访，归档记录

    状态机: in_progress → completed（自动归档）
    """
    from ..database import SessionLocal
    from ..services import followup_service
    from ..models import FollowUpRecord, Pregnant
    from ..schemas import FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_ACTIVE_STATUSES

    db = SessionLocal()
    try:
        try:
            record = db.query(FollowUpRecord).filter(
                FollowUpRecord.id == UUID(record_id)
            ).first()
        except Exception:
            return {"error": "无效的记录ID格式"}

        if not record:
            return {"error": "随访记录不存在"}
        if record.status not in FOLLOWUP_ACTIVE_STATUSES:
            return {"error": f"该随访状态为 {record.status}，无法完成", "record_id": record_id, "status": record.status}

        pregnant = db.query(Pregnant).filter(
            Pregnant.pregnant_id == record.pregnant_id
        ).first()

        final_summary = followup_service.generate_record_summary(
            patient_name=pregnant.display_name if pregnant else "未知",
            gest_week=record.gestational_week or "?",
            answers=record.self_reported_data or {},
        )
        if summary:
            final_summary = f"{final_summary} | 小结：{summary}"

        record.summary = final_summary
        record.status = FOLLOWUP_STATUS_COMPLETED
        db.commit()

        return {
            "success": True,
            "record_id": str(record.id),
            "summary": final_summary,
            "status": FOLLOWUP_STATUS_COMPLETED,
            "follow_up_date": record.follow_up_date.isoformat()
            if record.follow_up_date
            else None,
            "health_education": record.health_education or [],
            "message": "随访已完成并归档，感谢您的配合！",
        }
    finally:
        db.close()


# ==================== 工具导出 ====================

# 主对话 Agent 工具集
MEDICAL_TOOLS = [
    agno_parse_nlu,
    agno_check_emergency,
    agno_evaluate_vital_rules,
    agno_save_health_data,
    agno_get_patient_context,
    agno_should_ask_weight,
    agno_should_ask_bp,
    agno_analyze_health_trends,
    agno_search_knowledge,
    agno_get_epds_result,
]

# 随访 Agent 工具集（保留原有 3 个 + 新增通用工具）
agno_get_followup_context = tool(_get_followup_context_impl)
agno_record_answer = tool(_record_answer_impl)
agno_complete_followup = tool(_complete_followup_impl)

AGNO_FOLLOWUP_TOOLS = [
    agno_get_followup_context,
    agno_record_answer,
    agno_complete_followup,
]
