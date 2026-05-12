"""随访智能体工具定义

为 LLM 提供三个可调用的工具函数，完成结构化随访问询：
1. get_followup_context — 获取当前随访进度
2. record_answer — 记录孕妇回答 + 保存健康数据
3. complete_followup — 归档随访记录
"""
import json
import re
from uuid import UUID
from sqlalchemy.orm import Session
from ..models import Alert, FollowUpRecord, Pregnant, HealthDataPoint
from ..services import followup_service
from .rule_engine import rule_engine
from datetime import datetime

# ==================== Tool Schemas (OpenAI Function Calling 格式) ====================

GET_FOLLOWUP_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "get_followup_context",
        "description": "获取当前随访的上下文信息，包括模板问题列表、已记录的答案、孕妇基本信息",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "随访记录ID"}
            },
            "required": ["record_id"],
        },
    },
}

RECORD_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "record_answer",
        "description": "记录孕妇对随访问题的回答。该工具会自动将可量化的健康数据（体重、血压等）保存到健康档案。调用后返回已答数量和剩余问题列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "随访记录ID"},
                "question_key": {
                    "type": "string",
                    "description": "问题标识符，如 feeling/weight/bp/fetal_movement/diet/medication/wound",
                },
                "answer_text": {"type": "string", "description": "孕妇的原始回答文本"},
            },
            "required": ["record_id", "question_key", "answer_text"],
        },
    },
}

COMPLETE_FOLLOWUP_TOOL = {
    "type": "function",
    "function": {
        "name": "complete_followup",
        "description": "完成随访并归档记录。当所有随访问题都回答完毕后调用此函数。会自动生成随访摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "随访记录ID"},
                "summary": {
                    "type": "string",
                    "description": "本次随访的简要总结，包含孕妇关键状况和注意事项",
                },
            },
            "required": ["record_id", "summary"],
        },
    },
}

FOLLOWUP_TOOLS = [
    GET_FOLLOWUP_CONTEXT_TOOL,
    RECORD_ANSWER_TOOL,
    COMPLETE_FOLLOWUP_TOOL,
]

TOOL_NAME_MAP = {t["function"]["name"]: t for t in FOLLOWUP_TOOLS}


# ==================== Tool Execution Functions ====================


async def execute_get_followup_context(record_id: str, db: Session) -> dict:
    """获取随访上下文：模板问题 + 已回答 + 孕妇信息"""
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


async def execute_record_answer(
    record_id: str, question_key: str, answer_text: str, db: Session
) -> dict:
    """记录孕妇回答，自动解析并保存健康数据"""
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
    except Exception:
        return {"error": "无效的记录ID格式"}

    if not record:
        return {"error": "随访记录不存在"}
    if record.status == "confirmed":
        return {"error": "该随访已归档，无法继续记录"}

    # 1. 保存到 self_reported_data
    current_data = dict(record.self_reported_data) if record.self_reported_data else {}
    current_data[question_key] = answer_text
    record.self_reported_data = current_data

    # 2. 如果是主诉，更新 chief_complaint
    if question_key == "feeling" and not record.chief_complaint:
        record.chief_complaint = answer_text

    # 3. 解析可量化健康数据并保存
    health_saved = _try_save_health_data(record.pregnant_id, question_key, answer_text, db)

    db.commit()

    # 3.5 保存健康数据后触发规则引擎评估
    _evaluate_rules_after_answer(record.pregnant_id, db)

    # 4. 计算剩余问题
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
        "next_question": (
            _find_question_text(template, remaining[0]) if remaining else None
        ),
    }


async def execute_complete_followup(
    record_id: str, summary: str, db: Session
) -> dict:
    """完成随访，归档记录"""
    try:
        record = db.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(record_id)
        ).first()
    except Exception:
        return {"error": "无效的记录ID格式"}

    if not record:
        return {"error": "随访记录不存在"}
    if record.status == "confirmed":
        return {"error": "该随访已归档", "record_id": record_id, "status": "confirmed"}

    pregnant = db.query(Pregnant).filter(
        Pregnant.pregnant_id == record.pregnant_id
    ).first()

    # 生成结构化摘要
    final_summary = followup_service.generate_record_summary(
        patient_name=pregnant.display_name if pregnant else "未知",
        gest_week=record.gestational_week or "?",
        answers=record.self_reported_data or {},
    )
    if summary:
        final_summary = f"{final_summary} | 小结：{summary}"

    record.summary = final_summary
    record.status = "confirmed"
    db.commit()

    return {
        "success": True,
        "record_id": str(record.id),
        "summary": final_summary,
        "status": "confirmed",
        "follow_up_date": record.follow_up_date.isoformat()
        if record.follow_up_date
        else None,
        "health_education": record.health_education or [],
        "message": "随访已完成并归档，感谢您的配合！",
    }


# ==================== 辅助函数 ====================


def _find_question_text(template: dict, key: str) -> str | None:
    """根据 key 查找问题文本"""
    for q in template.get("questions", []):
        if q["key"] == key:
            return q.get("question", key)
    return None


def _try_save_health_data(pregnant_id: str, question_key: str, text: str, db: Session) -> bool:
    """尝试从回答文本中提取可量化的健康数据并保存"""
    parsed = followup_service.extract_health_value(question_key, text)
    if not parsed:
        return False

    source = "FOLLOWUP"

    # 处理血压（拆分为 sbp/dbp）
    if question_key == "bp":
        if "sbp" in parsed and "dbp" in parsed:
            _insert_health_point(db, pregnant_id, "sbp", parsed["sbp"], "mmHg", source)
            _insert_health_point(db, pregnant_id, "dbp", parsed["dbp"], "mmHg", source)
            return True

    # 其他单值指标
    if "metric_code" in parsed:
        _insert_health_point(
            db, pregnant_id, parsed["metric_code"], parsed["value"], parsed.get("unit", ""), source
        )
        return True

    return False


def _insert_health_point(
    db: Session, pregnant_id: str, metric_code: str, value: float, unit: str, source: str
):
    """插入一条健康数据点"""
    point = HealthDataPoint(
        pregnant_id=pregnant_id,
        metric_code=metric_code,
        value=float(value),
        unit=unit,
        recorded_at=datetime.utcnow(),
        source=source,
    )
    db.add(point)


async def dispatch_tool(tool_call: dict, db: Session) -> dict:
    """根据 LLM 返回的 tool_call 分发到对应的执行函数"""
    func_name = tool_call["function"]["name"]
    try:
        args = json.loads(tool_call["function"]["arguments"])
    except (json.JSONDecodeError, KeyError):
        return {"error": "工具参数解析失败"}

    if func_name == "get_followup_context":
        return await execute_get_followup_context(args["record_id"], db)
    elif func_name == "record_answer":
        return await execute_record_answer(
            args["record_id"], args["question_key"], args["answer_text"], db
        )
    elif func_name == "complete_followup":
        return await execute_complete_followup(
            args["record_id"], args.get("summary", ""), db
        )
    return {"error": f"未知工具: {func_name}"}


def _evaluate_rules_after_answer(pregnant_id: str, db: Session):
    """随访回答后触发规则引擎评估，自动创建预警"""
    from sqlalchemy import desc
    from datetime import timedelta

    # 收集该孕妇最近7天的健康数据
    recent_points = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == pregnant_id,
        HealthDataPoint.recorded_at >= datetime.utcnow() - timedelta(days=7),
    ).order_by(desc(HealthDataPoint.recorded_at)).all()

    if not recent_points:
        return

    # 构建规则引擎上下文：取每种指标的最新值
    context = {}
    metric_values = {}
    for point in recent_points:
        if point.metric_code not in metric_values:
            metric_values[point.metric_code] = []
        metric_values[point.metric_code].append(point.value)

    for metric, values in metric_values.items():
        if metric in ("sbp", "dbp", "weight", "fetal_movement", "blood_sugar",
                       "emotion_score", "sleep_hours"):
            context[metric] = values[0]  # 最新值

    # 获取孕周
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if pregnant and pregnant.gestational_age_days:
        context["gest_week"] = pregnant.gestational_age_days // 7

    # 计算胎动平均值（排除最新一条）
    fm_values = metric_values.get("fetal_movement", [])
    if len(fm_values) > 1:
        context["fetal_movement_avg"] = sum(fm_values[1:]) / len(fm_values[1:])

    # 评估规则
    hits = rule_engine.evaluate_all(context)
    for hit in hits:
        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="RULE_ENGINE",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details=hit,
            status="PENDING",
        )
        db.add(alert)
    if hits:
        db.commit()
