"""随访记录 API

状态机: draft → in_progress → completed → confirmed → archived
- draft: 护士创建，等待孕妇开始
- in_progress: 孕妇已开始回答
- completed: 所有问题回答完毕
- confirmed: 护士确认审核
- archived: 长期存档
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from ..database import get_db
from ..models import FollowUpRecord, Pregnant
from ..database import SessionLocal
from ..schemas import (
    FollowUpRecordResponse, FollowUpConfirm, FollowUpTrigger,
    FOLLOWUP_ACTIVE_STATUSES, FOLLOWUP_STATUS_IN_PROGRESS,
    FOLLOWUP_STATUS_COMPLETED,
)
from ..services import followup_service

router = APIRouter(prefix="/api/v1/followup", tags=["随访管理"])


@router.post("/trigger")
def trigger_followup(trigger: FollowUpTrigger, db: Session = Depends(get_db)):
    """触发自动随访"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == trigger.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    template = followup_service.get_template(trigger.template_id or "standard")

    gest_week = f"{pregnant.gestational_age_days // 7}" if pregnant.gestational_age_days else "未知"
    gest_week_display = f"{gest_week}+{pregnant.gestational_age_days % 7}" if pregnant.gestational_age_days else "未知"

    health_education = followup_service.generate_health_education(
        int(gest_week) if gest_week != "未知" else 20,
        pregnant.risk_tags or []
    )

    # 创建随访记录
    record = FollowUpRecord(
        pregnant_id=pregnant.pregnant_id,
        gestational_week=gest_week_display,
        health_education=health_education,
        status="draft",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "message": f"已触发对 {pregnant.display_name} 的随访对话",
        "record_id": str(record.id),
        "template": template,
        "gestational_week": gest_week_display,
    }


@router.get("/records", response_model=list[FollowUpRecordResponse])
def get_records(status: Optional[str] = None,
                pregnant_id: Optional[str] = None,
                db: Session = Depends(get_db)):
    """获取随访记录列表"""
    query = db.query(FollowUpRecord)
    if status:
        query = query.filter(FollowUpRecord.status == status)
    if pregnant_id:
        query = query.filter(FollowUpRecord.pregnant_id == pregnant_id)
    records = query.order_by(FollowUpRecord.follow_up_date.desc()).limit(100).all()

    # 关联孕妇姓名
    result = []
    for r in records:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == r.pregnant_id).first()
        result.append(FollowUpRecordResponse(
            **{c.name: getattr(r, c.name) for c in r.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知"
        ))
    return result


@router.put("/records/{record_id}/confirm", response_model=FollowUpRecordResponse)
def confirm_record(record_id: str, confirm: FollowUpConfirm,
                   db: Session = Depends(get_db)):
    """确认归档随访记录"""
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    record.status = confirm.status
    db.commit()
    db.refresh(record)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    return FollowUpRecordResponse(
        **{c.name: getattr(record, c.name) for c in record.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知"
    )


@router.put("/records/{record_id}")
async def update_record(record_id: str, data: dict, db: Session = Depends(get_db)):
    """更新随访记录"""
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    for key, value in data.items():
        if hasattr(record, key):
            setattr(record, key, value)
    db.commit()
    return {"message": "更新成功"}


# ==================== 孕妇端随访对话 ====================

class FollowUpPendingResponse(BaseModel):
    record_id: str = ""
    patient_name: str = ""
    template_id: str = ""
    template_name: str = ""
    questions: list[dict] = []
    answered_count: int = 0
    total_count: int = 0
    has_pending: bool = False
    health_education: list[str] = []


class FollowUpAnswer(BaseModel):
    record_id: str
    answers: dict = {}
    total_count: int = 0  # 前端告知的总问题数，用于完成判断


@router.get("/pending/{pregnant_id}", response_model=FollowUpPendingResponse)
def get_pending_followup(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇待处理的随访（draft 或 in_progress 状态）

    根据孕妇风险标签和孕周自动选择模板，返回动态问题列表。
    """
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id,
        FollowUpRecord.status.in_(FOLLOWUP_ACTIVE_STATUSES),
    ).order_by(FollowUpRecord.created_at.desc()).first()

    if not record:
        return FollowUpPendingResponse(has_pending=False)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    patient_name = (pregnant.nickname or pregnant.display_name) if pregnant else ""

    # 根据风险标签和孕周选择模板
    gest_week = pregnant.gestational_age_days // 7 if pregnant and pregnant.gestational_age_days else 20
    risk_tags = pregnant.risk_tags if pregnant else []
    template_id, template = followup_service.select_template(risk_tags, gest_week)

    # 构建问题列表，标记已回答的
    answered_data = record.self_reported_data or {}
    questions = []
    for q in template["questions"]:
        item = {
            "key": q["key"],
            "question": q["question"],
            "type": q.get("type", "text"),
        }
        if "unit" in q:
            item["unit"] = q["unit"]
        if "format" in q:
            item["format"] = q["format"]
        if q["key"] in answered_data:
            item["answered"] = True
            item["answer"] = answered_data[q["key"]]
        else:
            item["answered"] = False
        questions.append(item)

    answered_count = sum(1 for q in questions if q["answered"])
    total_count = len(questions)

    from loguru import logger
    logger.info(
        "PENDING_DEBUG pregnant_id={} template={} questions={} answered_data_keys={} answered_count={}/{}",
        pregnant_id, template_id,
        [q["key"] for q in questions],
        sorted(answered_data.keys()),
        answered_count, total_count,
    )

    return FollowUpPendingResponse(
        record_id=str(record.id),
        patient_name=patient_name,
        template_id=template_id,
        template_name=template["name"],
        questions=questions,
        answered_count=answered_count,
        total_count=total_count,
        has_pending=True,
        health_education=record.health_education or [],
    )


@router.post("/respond")
async def respond_to_followup(req: FollowUpAnswer, db: Session = Depends(get_db)):
    """孕妇提交随访回答（支持部分提交）

    状态机：draft → in_progress → completed
    量化数据同时写入 HealthDataPoint。
    全部完成后调用 LLM 生成温馨汇总。
    """
    from datetime import datetime

    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.id == UUID(req.record_id)
    ).first()
    if not record:
        raise HTTPException(404, "随访记录不存在")

    # 合并已有数据
    reported_data = dict(record.self_reported_data) if record.self_reported_data else {}
    chief_complaint = record.chief_complaint or ""

    for key, value in req.answers.items():
        if key == "feeling" and not chief_complaint:
            chief_complaint = str(value)
        reported_data[key] = value

        # 量化数据同时写入 HealthDataPoint
        _save_health_data_point(record.pregnant_id, key, value, db)

    # 状态机转换
    if record.status == "draft":
        record.status = FOLLOWUP_STATUS_IN_PROGRESS

    record.self_reported_data = reported_data
    record.chief_complaint = chief_complaint

    # 检查是否全部完成
    pregnant = db.query(Pregnant).filter(
        Pregnant.pregnant_id == record.pregnant_id
    ).first()
    answered_keys = set(reported_data.keys())

    # 确定总问题数：优先用前端传值，回退到模板推断
    if req.total_count > 0:
        total = req.total_count
    else:
        gest_week = pregnant.gestational_age_days // 7 if pregnant and pregnant.gestational_age_days else 20
        risk_tags = pregnant.risk_tags if pregnant else []
        _, tpl = followup_service.select_template(risk_tags, gest_week)
        total = len(tpl["questions"])

    all_answered = len(answered_keys) >= total

    summary = None
    if all_answered and record.status == FOLLOWUP_STATUS_IN_PROGRESS:
        record.status = FOLLOWUP_STATUS_COMPLETED
        patient_name = (pregnant.nickname or pregnant.display_name) if pregnant else ""

        # ===== 新增：自动触发预警评估 =====
        try:
            from ..services.alert_service import alert_service

            # 构建评估上下文
            context = {}
            for key, value in reported_data.items():
                # 解析血压格式 "120/80"
                if key == "bp" and "/" in str(value):
                    parts = str(value).split("/")
                    if len(parts) == 2:
                        try:
                            context["sbp"] = float(parts[0])
                            context["dbp"] = float(parts[1])
                        except ValueError:
                            pass
                elif key in ("sbp", "dbp"):
                    try:
                        context[key] = float(value)
                    except (ValueError, TypeError):
                        pass
                elif key == "weight":
                    import re
                    match = re.search(r"(\d+\.?\d*)", str(value))
                    if match:
                        context["weight"] = float(match.group(1))
                elif key == "fetal_movement":
                    import re
                    match = re.search(r"(\d+)", str(value))
                    if match:
                        context["fetal_movement"] = float(match.group(1))
                elif key in ("blood_sugar_fasting", "blood_sugar_postprandial"):
                    import re
                    match = re.search(r"(\d+\.?\d*)", str(value))
                    if match:
                        context[key] = float(match.group(1))

            # 添加孕周
            if pregnant and pregnant.gestational_age_days:
                context["gest_week"] = pregnant.gestational_age_days // 7

            # 调用规则引擎评估
            if context:
                from ..core.rule_engine import rule_engine
                hits = rule_engine.evaluate_all(context)
                if hits:
                    alert_service.create_alerts_from_hits(db, record.pregnant_id, hits, "FOLLOWUP")
                    from loguru import logger
                    logger.info(f"FOLLOWUP_AUTO_ALERT: created {len(hits)} alerts for pregnant_id={record.pregnant_id}")

        except Exception as e:
            from loguru import logger
            logger.warning(f"FOLLOWUP_AUTO_ALERT_FAILED: {e}")
        # ===== 预警触发结束 =====

        record.summary = followup_service.generate_record_summary(
            patient_name=patient_name,
            gest_week=record.gestational_week or "?",
            answers=reported_data,
        )

        summary = await _generate_llm_summary(
            patient_name=patient_name,
            gest_week=record.gestational_week or "?",
            answers=reported_data,
            risk_tags=pregnant.risk_tags if pregnant else [],
        )

    db.commit()

    result = {
        "record_id": str(record.id),
        "status": record.status,
        "answered_count": len(answered_keys),
        "total_count": total,
    }
    if summary:
        result["summary"] = summary
    return result


def _save_health_data_point(pregnant_id: str, key: str, value, db):
    """将量化数据写入 HealthDataPoint"""
    from datetime import datetime
    from ..models import HealthDataPoint

    text = str(value)
    parsed = followup_service.extract_health_value(key, text)
    if not parsed:
        return

    source = "FOLLOWUP"
    points = []

    if key in ("bp", "bp_morning", "bp_evening"):
        if "sbp" in parsed and "dbp" in parsed:
            points.append(HealthDataPoint(
                pregnant_id=pregnant_id, metric_code="systolic",
                value=float(parsed["sbp"]), unit="mmHg", source=source,
                recorded_at=datetime.utcnow(),
            ))
            points.append(HealthDataPoint(
                pregnant_id=pregnant_id, metric_code="diastolic",
                value=float(parsed["dbp"]), unit="mmHg", source=source,
                recorded_at=datetime.utcnow(),
            ))
    elif "metric_code" in parsed:
        points.append(HealthDataPoint(
            pregnant_id=pregnant_id, metric_code=parsed["metric_code"],
            value=float(parsed["value"]), unit=parsed.get("unit", ""), source=source,
            recorded_at=datetime.utcnow(),
        ))

    for p in points:
        db.add(p)


async def _generate_llm_summary(
    patient_name: str, gest_week: str, answers: dict, risk_tags: list[str]
) -> str:
    """调用 LLM 生成温馨的随访汇总（1-2 句话）"""
    from ..core.agno_agent import get_main_agent

    # 构造答案摘要
    answer_lines = []
    for k, v in answers.items():
        answer_lines.append(f"- {k}: {v}")
    answer_text = "\n".join(answer_lines)

    risk_text = "、".join(risk_tags) if risk_tags else "无"

    prompt = (
        f"你是小安，一位温暖的孕期助手。请根据以下随访数据，生成1-2句温馨的随访总结。\n"
        f"要求：语气温和自然，对孕妇的认可+简短健康提示，不超过50字。不要用emoji。\n\n"
        f"孕妇：{patient_name}，孕{gest_week}周\n"
        f"风险标签：{risk_text}\n"
        f"随访数据：\n{answer_text}"
    )

    try:
        agent = get_main_agent()
        response = await agent.arun(input=prompt)
        return response.content or f"{patient_name}，随访已完成，感谢配合~"
    except Exception:
        return f"{patient_name}，随访已完成，感谢配合~"
