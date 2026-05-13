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

class FollowUpChatResponse(BaseModel):
    record_id: str = ""
    patient_name: str = ""
    opening: str = ""
    questions: list[dict] = []
    closing: str = ""
    has_pending: bool = False


class FollowUpAnswer(BaseModel):
    record_id: str
    answers: dict = {}


@router.get("/pending/{pregnant_id}", response_model=FollowUpChatResponse)
def get_pending_followup(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇待处理的随访对话（draft 或 in_progress 状态）"""
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id,
        FollowUpRecord.status.in_(FOLLOWUP_ACTIVE_STATUSES),
    ).order_by(FollowUpRecord.created_at.desc()).first()

    if not record:
        # 检查是否有已确认但未读的
        recent = db.query(FollowUpRecord).filter(
            FollowUpRecord.pregnant_id == pregnant_id,
            FollowUpRecord.status.in_(["confirmed", "archived"]),
        ).order_by(FollowUpRecord.created_at.desc()).first()

        return FollowUpChatResponse(
            record_id=recent.id if recent else "",
            patient_name="",
            opening="",
            questions=[],
            closing="",
            has_pending=False,
        )

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    patient_name = pregnant.nickname or pregnant.display_name if pregnant else ""

    # 构建随访对话
    gw = record.gestational_week or "?"
    opening = f"{patient_name}妈妈您好，我是您的孕产助手小护。今天到了我们约定的随访时间（孕{gw}周），占用您2分钟问几个问题可以吗？"

    questions = [
        {"key": "feeling", "question": "最近感觉怎么样？有没有不舒服的地方？"},
        {"key": "weight", "question": "今天的体重是多少？"},
        {"key": "bp", "question": "有测量血压吗？数值是多少呢？"},
        {"key": "fetal_movement", "question": "最近胎动感觉如何？每小时大概几次？"},
    ]

    closing = "感谢您的配合，信息已记录。您本月还有一次B超检查，小安会提前提醒您。祝您孕期愉快！"

    return FollowUpChatResponse(
        record_id=str(record.id),
        patient_name=patient_name,
        opening=opening,
        questions=questions,
        closing=closing,
        has_pending=True,
    )


@router.post("/respond")
def respond_to_followup(req: FollowUpAnswer, db: Session = Depends(get_db)):
    """孕妇提交随访回答

    状态机转换：
    - draft → in_progress（首次回答）
    - in_progress → completed（所有问题回答完毕）
    """
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.id == UUID(req.record_id)
    ).first()
    if not record:
        raise HTTPException(404, "随访记录不存在")

    # 解析回答
    reported_data = dict(record.self_reported_data) if record.self_reported_data else {}
    chief_complaint = record.chief_complaint or ""
    for key, value in req.answers.items():
        if key == "feeling" and not chief_complaint:
            chief_complaint = str(value)
        reported_data[key] = value

    # 状态机转换：draft → in_progress
    if record.status == "draft":
        record.status = FOLLOWUP_STATUS_IN_PROGRESS

    # 更新随访记录
    record.self_reported_data = reported_data
    record.chief_complaint = chief_complaint

    # 检查是否所有问题都已回答
    template = followup_service.get_template_from_questions(reported_data)
    all_keys = [q["key"] for q in template["questions"]]
    answered_keys = set(reported_data.keys())
    all_answered = all(k in answered_keys for k in all_keys)

    if all_answered and record.status == FOLLOWUP_STATUS_IN_PROGRESS:
        # 所有问题回答完毕 → completed
        record.status = FOLLOWUP_STATUS_COMPLETED
        record.summary = followup_service.generate_record_summary(
            patient_name="",
            gest_week=record.gestational_week or "?",
            answers=reported_data,
        )

    db.commit()

    return {
        "message": "随访回答已提交",
        "record_id": str(record.id),
        "status": record.status,
        "answered_count": len(answered_keys),
        "total_count": len(all_keys),
        "all_answered": all_answered,
    }
