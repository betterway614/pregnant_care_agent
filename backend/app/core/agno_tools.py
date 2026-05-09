"""Agno @tool 随访工具

将 followup_tools.py 的业务逻辑包装为 Agno 框架的 @tool 装饰器，
供 Agno Agent 直接调用。

工具列表：
1. agno_get_followup_context — 获取当前随访进度
2. agno_record_answer — 记录孕妇回答 + 保存健康数据
3. agno_complete_followup — 归档随访记录
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agno.tools import tool


# ==================== 辅助函数 ====================


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


# ==================== 业务逻辑函数（可直接调用用于测试） ====================


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
    """记录孕妇回答，自动解析并保存健康数据"""
    from ..database import SessionLocal
    from ..services import followup_service
    from ..models import FollowUpRecord

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
    finally:
        db.close()


async def _complete_followup_impl(record_id: str, summary: str = "") -> dict:
    """完成随访，归档记录"""
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
    finally:
        db.close()


# ==================== Agno @tool 包装 ====================


agno_get_followup_context = tool(_get_followup_context_impl)
agno_record_answer = tool(_record_answer_impl)
agno_complete_followup = tool(_complete_followup_impl)


# ==================== 工具导出 ====================

AGNO_FOLLOWUP_TOOLS = [
    agno_get_followup_context,
    agno_record_answer,
    agno_complete_followup,
]
