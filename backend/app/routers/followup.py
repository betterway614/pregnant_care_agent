"""随访记录 API

状态机: draft → in_progress → completed → confirmed → archived
- draft: 护士创建，等待孕妇开始
- in_progress: 孕妇已开始回答
- completed: 所有问题回答完毕
- confirmed: 护士确认审核
- archived: 长期存档
"""
import json
import re
import time
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from sse_starlette.sse import EventSourceResponse

from ..database import get_db
from ..utils.timezone import beijing_now
from ..models import FollowUpRecord, Pregnant, AgentAuditLog
from ..database import SessionLocal
from ..schemas import (
    FollowUpRecordResponse, FollowUpConfirm, FollowUpTrigger,
    FollowUpSignatureRequest, FollowUpRecordUpdateRequest,
    FollowUpArchiveSummaryRequest, FollowUpArchiveSummaryResponse,
    FOLLOWUP_ACTIVE_STATUSES, FOLLOWUP_STATUS_DRAFT,
    FOLLOWUP_STATUS_IN_PROGRESS, FOLLOWUP_STATUS_COMPLETED,
)
from ..services import followup_service
from ..core.auth import get_current_user, TokenPayload
from ..core.state_machine import followup_fsm, FollowUpStatus, InvalidTransition
from loguru import logger

def _quick_audit(
    session_id: str,
    user_id: str,
    agent_variant: str,
    intent_classification: str,
    run_response,
    total_latency_ms: int,
    agent_role: str = "nurse",
) -> int | None:
    """随访/分析场景的轻量审计日志（同步写入，可靠优先）"""
    if total_latency_ms < 10:
        return None
    metrics = getattr(run_response, "metrics", None) if run_response else None
    input_tok = getattr(metrics, "input_tokens", None) if metrics else None
    output_tok = getattr(metrics, "output_tokens", None) if metrics else None
    if (input_tok is None or input_tok == 0) and (output_tok is None or output_tok == 0):
        return None
    try:
        db = SessionLocal()
        try:
            log = AgentAuditLog(
                session_id=session_id,
                user_id=user_id,
                agent_role=agent_role,
                agent_variant=agent_variant,
                intent_classification=intent_classification,
                routed_agent=f"小护-{agent_variant}",
                input_tokens=input_tok or 0,
                output_tokens=output_tok or 0,
                total_tokens=(input_tok or 0) + (output_tok or 0),
                model_id=getattr(run_response, "model", "") or "unknown",
                provider="openai",
                total_latency_ms=total_latency_ms,
                response_preview=(getattr(run_response, "content", "") or "")[:200],
            )
            db.add(log)
            db.commit()
            return log.id
        except Exception as e:
            db.rollback()
            logger.warning("随访审计日志DB写入失败: {}", e)
            return None
        finally:
            db.close()
    except Exception as e:
        logger.warning("随访审计日志会话创建失败: {}", e)
        return None


router = APIRouter(prefix="/api/v1/followup", tags=["随访管理"])


def _normalize_archive_summary_text(text: str) -> str:
    """Compare clinical text while ignoring whitespace-only edits."""
    return re.sub(r"\s+", "", str(text or ""))


def _format_archive_summary_text(summary: dict | str | None) -> str:
    """Render AI structured archive summary into editable plain text."""
    if not summary:
        return ""
    if isinstance(summary, str):
        return summary.strip()
    lines: list[str] = []
    if summary.get("warm_summary"):
        lines.append(f"温馨总结：{summary.get('warm_summary', '')}")
    abnormal = summary.get("abnormal_indicators") or summary.get("abnormal_flags") or []
    if abnormal:
        lines.append(f"需关注指标：{'、'.join(str(item) for item in abnormal)}")
    if summary.get("trend_analysis"):
        lines.append(f"趋势分析：{summary.get('trend_analysis', '')}")
    if summary.get("personalized_advice"):
        lines.append(f"个性化建议：{summary.get('personalized_advice', '')}")
    if summary.get("nurse_action_suggestion"):
        lines.append(f"护士建议：{summary.get('nurse_action_suggestion', '')}")
    return "\n\n".join(line for line in lines if line).strip()


def _archive_summary_parts(record: FollowUpRecord) -> tuple[dict, str, str, bool]:
    snapshot = dict(record.ai_snapshot or {})
    draft = snapshot.get("archive_summary_draft") or snapshot.get("archive_summary") or {}
    draft_text = (snapshot.get("archive_summary_draft_text") or _format_archive_summary_text(draft)).strip()
    final = snapshot.get("archive_summary_final") or {}
    final_text = (snapshot.get("archive_summary_final_text") or final.get("text") or "").strip()
    modified = bool(
        draft_text
        and final_text
        and _normalize_archive_summary_text(draft_text) != _normalize_archive_summary_text(final_text)
    )
    return draft, draft_text, final_text, modified


def _archive_summary_response(record: FollowUpRecord) -> FollowUpArchiveSummaryResponse:
    draft, draft_text, final_text, modified = _archive_summary_parts(record)
    snapshot = dict(record.ai_snapshot or {})
    return FollowUpArchiveSummaryResponse(
        record_id=str(record.id),
        ai_draft=draft if isinstance(draft, dict) else {},
        ai_draft_text=draft_text,
        nurse_final_text=final_text,
        modified=modified,
        generated_at=snapshot.get("archive_summary_generated_at"),
        modified_at=snapshot.get("archive_summary_modified_at"),
    )


def _require_modified_archive_summary(record: FollowUpRecord) -> str:
    _, draft_text, final_text, modified = _archive_summary_parts(record)
    if not draft_text:
        raise HTTPException(400, "请先生成 AI 归档总结原稿")
    if not final_text:
        raise HTTPException(400, "请先修改并保存归档总结")
    if not modified:
        raise HTTPException(400, "护士提交的归档总结必须和 AI 原稿不同")
    return final_text


def _document_payload(record: FollowUpRecord) -> dict:
    _, draft_text, final_text, modified = _archive_summary_parts(record)
    return {
        "record_id": str(record.id),
        "status": record.status,
        "classification": record.classification or "normal",
        "chief_complaint": record.chief_complaint,
        "self_reported_data": record.self_reported_data or {},
        "obstetric_exam": record.obstetric_exam or {},
        "lab_results": record.lab_results or {},
        "summary": record.summary,
        "health_education": record.health_education or [],
        "guidance_tags": record.guidance_tags or [],
        "referral": record.referral,
        "next_followup_date": str(record.next_followup_date) if record.next_followup_date else "",
        "reviewed_by": record.reviewed_by,
        "reviewed_at": str(record.reviewed_at) if record.reviewed_at else "",
        "review_comment": record.review_comment,
        "ai_snapshot": record.ai_snapshot or {},
        "archive_summary_draft_text": draft_text,
        "archive_summary_final_text": final_text,
        "archive_summary_modified": modified,
    }


def _generate_record_document_for(record: FollowUpRecord, patient_name: str) -> tuple[dict, str]:
    gest_week = record.gestational_week or "?"
    follow_up_date = record.follow_up_date.strftime("%Y-%m-%d") if record.follow_up_date else "?"
    return followup_service.generate_record_document(
        patient_name=patient_name,
        gest_week=gest_week,
        follow_up_date=follow_up_date,
        record=_document_payload(record),
    )


@router.post("/trigger")
def trigger_followup(trigger: FollowUpTrigger, db: Session = Depends(get_db), current_user: TokenPayload = Depends(get_current_user)):
    """触发自动随访

    去重逻辑：同一孕妇仅保留最新一条活跃随访。若已存在 draft/in_progress
    状态的随访记录，自动归档旧记录后再创建新记录。
    """
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == trigger.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    # ── 去重：归档该孕妇所有活跃的旧随访记录 ──
    active_records = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == trigger.pregnant_id,
        FollowUpRecord.status.in_(FOLLOWUP_ACTIVE_STATUSES),
    ).all()

    archived_count = 0
    for old in active_records:
        old.status = "archived"
        old.review_comment = (
            f"[自动归档] 护士重新触发随访（{beijing_now().strftime('%Y-%m-%d %H:%M')}），"
            f"原状态 {old.status if old.status != 'archived' else 'draft'} 的记录被新记录取代。"
        )
        archived_count += 1

    if archived_count > 0:
        db.flush()
        logger.info(
            "随访去重：归档孕妇 {} 的 {} 条旧记录，创建最新记录",
            trigger.pregnant_id, archived_count,
        )

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
        follow_up_date=beijing_now(),
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
        "archived_previous": archived_count,
    }


@router.get("/records", response_model=list[FollowUpRecordResponse])
def get_records(status: Optional[str] = None,
                pregnant_id: Optional[str] = None,
                today_only: bool = False,
                db: Session = Depends(get_db),
                current_user: TokenPayload = Depends(get_current_user)):
    """获取随访记录列表

    Args:
        status: 逗号分隔的状态筛选
        pregnant_id: 按孕妇ID筛选
        today_only: 仅返回 follow_up_date 为今天的记录（用于工作台"今日随访"卡片对齐）
    """
    query = db.query(FollowUpRecord)
    if status:
        statuses = [s.strip() for s in status.split(",")]
        query = query.filter(FollowUpRecord.status.in_(statuses))
    if pregnant_id:
        query = query.filter(FollowUpRecord.pregnant_id == pregnant_id)
    if today_only:
        today = beijing_now().date()
        query = query.filter(func.date(FollowUpRecord.follow_up_date) == today)
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


@router.get("/records/{record_id}", response_model=FollowUpRecordResponse)
def get_record(record_id: str, db: Session = Depends(get_db),
               current_user: TokenPayload = Depends(get_current_user)):
    """获取单条随访记录详情（孕妇仅可查看本人记录）"""
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    if current_user.role == "pregnant":
        if not current_user.pregnant_id or record.pregnant_id != current_user.pregnant_id:
            raise HTTPException(403, "无权访问此记录")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    return FollowUpRecordResponse(
        **{c.name: getattr(record, c.name) for c in record.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知"
    )


@router.put("/records/{record_id}/confirm", response_model=FollowUpRecordResponse)
def confirm_record(record_id: str, confirm: FollowUpConfirm,
                   db: Session = Depends(get_db),
                   current_user: TokenPayload = Depends(get_current_user)):
    """确认审核随访记录

    写入审核追溯信息 + 生成归档文档快照。
    使用状态机校验转换合法性，从JWT提取审核者身份。
    仅护士/管理员可以确认审核。
    """
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以审核确认随访记录")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    # 使用状态机校验：仅 completed -> confirmed 转换合法
    try:
        current_status = FollowUpStatus(record.status)
        new_status = followup_fsm.transition(current_status, "confirm")
    except InvalidTransition as e:
        raise HTTPException(400, f"状态转换不允许: {e}")

    # 审核追溯 — 从JWT token提取审核者身份（不信任客户端传值）
    record.status = new_status.value
    record.reviewed_by = current_user.sub
    record.reviewed_at = beijing_now()
    if confirm.review_comment:
        record.review_comment = confirm.review_comment
    if confirm.ai_snapshot:
        record.ai_snapshot = confirm.ai_snapshot

    # 生成确认阶段文档快照 + 纯文本。归档时会重新冻结护士定稿后的最终快照。
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    patient_name = (pregnant.display_name if pregnant else "未知")
    try:
        snapshot, text = _generate_record_document_for(record, patient_name)
        record.record_snapshot = snapshot
        record.record_text = text
    except Exception as e:
        logger.warning("归档文档生成失败: {}", e)

    db.commit()
    db.refresh(record)

    return FollowUpRecordResponse(
        **{c.name: getattr(record, c.name) for c in record.__table__.columns},
        patient_name=patient_name,
    )


@router.post("/records/{record_id}/archive", response_model=FollowUpRecordResponse)
async def archive_record(record_id: str, db: Session = Depends(get_db),
                   current_user: TokenPayload = Depends(get_current_user)):
    """归档已确认的随访记录（confirmed → archived）

    1. 校验护士签名已存在（签名是归档前置条件）
    2. 校验护士定稿已保存且不同于 AI 原稿
    3. 状态机转换 confirmed → archived，并冻结最终文档
    """
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以归档随访记录")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    # 状态机校验（优先于签名检查，给出明确错误信息）
    try:
        current_status = FollowUpStatus(record.status)
        new_status = followup_fsm.transition(current_status, "archive")
    except InvalidTransition as e:
        raise HTTPException(400, f"状态转换不允许: {e}")

    sig = record.signature_data or {}
    if not sig.get("image"):
        raise HTTPException(400, "请先完成护士签名后再归档")

    # 护士定稿必须不同于 AI 原稿，归档前再次后端校验。
    _require_modified_archive_summary(record)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    patient_name = (pregnant.display_name if pregnant else "未知")

    record.status = new_status.value
    try:
        snapshot, text = _generate_record_document_for(record, patient_name)
        record.record_snapshot = snapshot
        record.record_text = text
    except Exception as e:
        logger.warning("归档最终文档生成失败: {}", e)

    db.commit()
    db.refresh(record)

    return FollowUpRecordResponse(
        **{c.name: getattr(record, c.name) for c in record.__table__.columns},
        patient_name=patient_name,
    )


@router.post("/records/{record_id}/archive-summary/generate", response_model=FollowUpArchiveSummaryResponse)
async def generate_archive_summary(record_id: str, db: Session = Depends(get_db),
                                   current_user: TokenPayload = Depends(get_current_user)):
    """生成或读取 AI 归档总结原稿。

    AI 原稿只负责起草；护士必须另存一版不同的定稿后才允许签名和归档。
    """
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以生成归档总结")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    if record.status not in ("confirmed", "archived"):
        raise HTTPException(400, "仅已确认的随访记录可以生成归档总结")

    snapshot = dict(record.ai_snapshot or {})
    _, draft_text, _, _ = _archive_summary_parts(record)
    if not draft_text:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
        patient_name = (pregnant.nickname or pregnant.display_name) if pregnant else "未知"
        ai_report = await _generate_llm_summary(
            patient_name=patient_name,
            gest_week=record.gestational_week or "?",
            answers=record.self_reported_data or {},
            risk_tags=pregnant.risk_tags if pregnant else [],
            pregnant_id=record.pregnant_id,
        )
        draft_text = _format_archive_summary_text(ai_report)
        snapshot["archive_summary_draft"] = ai_report
        snapshot["archive_summary_draft_text"] = draft_text
        snapshot["archive_summary_generated_at"] = beijing_now().isoformat()
        snapshot.setdefault("archive_summary_final_text", "")
        snapshot["archive_summary_modified"] = False
        record.ai_snapshot = snapshot
        db.commit()
        db.refresh(record)

    return _archive_summary_response(record)


@router.put("/records/{record_id}/archive-summary", response_model=FollowUpArchiveSummaryResponse)
def update_archive_summary(record_id: str, req: FollowUpArchiveSummaryRequest,
                           db: Session = Depends(get_db),
                           current_user: TokenPayload = Depends(get_current_user)):
    """保存护士修改后的归档总结定稿。"""
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以修改归档总结")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    if record.status != "confirmed":
        raise HTTPException(400, "仅已确认且未归档的随访记录可以修改归档总结")

    snapshot = dict(record.ai_snapshot or {})
    _, draft_text, _, _ = _archive_summary_parts(record)
    if not draft_text:
        raise HTTPException(400, "请先生成 AI 归档总结原稿")

    final_text = req.summary_text.strip()
    if not final_text:
        raise HTTPException(400, "归档总结不能为空")
    if _normalize_archive_summary_text(final_text) == _normalize_archive_summary_text(draft_text):
        raise HTTPException(400, "护士提交的归档总结必须和 AI 原稿不同")

    now = beijing_now().isoformat()
    snapshot["archive_summary_final_text"] = final_text
    snapshot["archive_summary_final"] = {
        "text": final_text,
        "modified_by": current_user.sub,
        "modified_at": now,
    }
    snapshot["archive_summary_modified"] = True
    snapshot["archive_summary_modified_by"] = current_user.sub
    snapshot["archive_summary_modified_at"] = now
    record.ai_snapshot = snapshot
    db.commit()
    return _archive_summary_response(record)


@router.get("/records/{record_id}/ai-review")
async def ai_review_followup(record_id: str, db: Session = Depends(get_db),
                             current_user: TokenPayload = Depends(get_current_user)):
    """护士审核随访时的 AI 辅助分析

    收集该次随访数据 + 历史记录 + 健康数据，调用 LLM 生成审核建议。
    三层降级：Agno Agent → 普通 LLM → 模板兜底。
    """
    from ..config import settings
    from ..models import HealthDataPoint, Alert
    from ..schemas import FollowUpAiReviewResponse
    from datetime import timedelta

    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "随访记录不存在")

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    patient_name = (pregnant.display_name if pregnant else "未知")
    gest_week = record.gestational_week or "未知"
    risk_tags = pregnant.risk_tags if pregnant else []
    answers = record.self_reported_data or {}

    # 收集历史随访记录（不含当前）
    prev_records = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == record.pregnant_id,
        FollowUpRecord.id != record.id,
    ).order_by(FollowUpRecord.created_at.desc()).limit(5).all()

    history_text = ""
    if prev_records:
        lines = []
        for pr in prev_records:
            pr_data = pr.self_reported_data or {}
            pr_date = pr.created_at.strftime("%Y-%m-%d") if pr.created_at else "?"
            items = "; ".join(f"{k}={v}" for k, v in pr_data.items() if v)
            lines.append(f"  [{pr_date}] {items}")
        history_text = "\n".join(lines)

    # 最近健康数据
    seven_days_ago = beijing_now() - timedelta(days=7)
    recent_points = db.query(HealthDataPoint).filter(
        HealthDataPoint.pregnant_id == record.pregnant_id,
        HealthDataPoint.recorded_at >= seven_days_ago,
    ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()

    health_text = ""
    if recent_points:
        health_text = "\n".join(
            f"  {hp.metric_code}: {hp.value}{hp.unit} ({hp.recorded_at.strftime('%m-%d')})"
            for hp in recent_points
        )

    # 活跃预警
    active_alerts = db.query(Alert).filter(
        Alert.pregnant_id == record.pregnant_id,
        Alert.status == "PENDING",
    ).all()
    alert_text = ""
    if active_alerts:
        alert_text = "\n".join(f"  [{a.level}] {a.message}" for a in active_alerts)

    # 构造答案文本
    answer_lines = [f"- {k}: {v}" for k, v in answers.items()]
    answer_text = "\n".join(answer_lines)
    risk_text = "、".join(risk_tags) if risk_tags else "无"

    # 拼接上下文
    context = f"孕妇：{patient_name}，孕{gest_week}周，风险标签：{risk_text}\n\n本次随访数据：\n{answer_text}"
    if history_text:
        context += f"\n\n最近随访历史：\n{history_text}"
    if health_text:
        context += f"\n\n最近7天健康数据：\n{health_text}"
    if alert_text:
        context += f"\n\n活跃预警：\n{alert_text}"

    # 尝试1: Agno Agent（120s 超时保护）
    try:
        import asyncio as _asyncio
        from ..core.agno_medical_agents import get_followup_review_agent
        from ..core.agno_structured import extract_structured_content
        agent = get_followup_review_agent()
        t0 = time.time()
        response = await _asyncio.wait_for(
            agent.arun(input=f"请审核以下随访记录，给出审核建议。\n\n{context}"),
            timeout=120,
        )
        _quick_audit(
            session_id=f"followup_review_{record_id}",
            user_id=record.pregnant_id,
            agent_variant="review",
            intent_classification="FOLLOWUP_REVIEW",
            run_response=response,
            total_latency_ms=int((time.time() - t0) * 1000),
        )
        data = extract_structured_content(response.content)
        if data:
            return FollowUpAiReviewResponse(
                summary=data.get("summary", ""),
                abnormal_flags=data.get("abnormal_flags", []),
                action_needed=data.get("action_needed", False),
                recommendation=data.get("recommendation", "确认通过"),
                detail_analysis=data.get("detail_analysis", ""),
            )
    except Exception as e:
        logger.warning("随访审核Agno Agent降级: %s", e)

    # 尝试2: 普通 LLM（容错降级）
    try:
        from ..core import get_llm_client
        from ..core.json_parser import parse_llm_json
        client = get_llm_client()
        system_prompt = (
            "你是一位专业的产科护理AI助手，帮助护士审核随访记录。请以JSON格式返回：\n"
            "- summary: 随访要点摘要（100-200字）\n"
            "- abnormal_flags: 异常指标列表\n"
            "- action_needed: 是否需要上报医生（布尔值）\n"
            "- recommendation: 审核建议（确认通过/需进一步沟通/紧急上报）\n"
            "- detail_analysis: 详细分析（100-200字）\n"
            "不要包含markdown代码块标记。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请审核以下随访记录：\n\n{context}"},
        ]
        response = await client.chat(messages)
        if response and response.strip():
            data = parse_llm_json(response)
            if data:
                return FollowUpAiReviewResponse(
                    summary=data.get("summary", ""),
                    abnormal_flags=data.get("abnormal_flags", []),
                    action_needed=data.get("action_needed", False),
                    recommendation=data.get("recommendation", "确认通过"),
                    detail_analysis=data.get("detail_analysis", ""),
                )
    except Exception as e:
        logger.warning("随访审核普通LLM降级: %s", e)

    # 降级: 模板兜底
    abnormal = []
    bp = answers.get("bp", "")
    if bp and "/" in str(bp):
        try:
            parts = str(bp).split("/")
            sbp, dbp = float(parts[0]), float(parts[1])
            if sbp >= 140 or dbp >= 90:
                abnormal.append(f"血压偏高（{bp}mmHg）")
        except (ValueError, IndexError):
            pass

    return FollowUpAiReviewResponse(
        summary=f"孕妇{patient_name}孕{gest_week}周随访记录，共回答{len(answers)}项。",
        abnormal_flags=abnormal,
        action_needed=len(abnormal) > 0,
        recommendation="需进一步沟通" if abnormal else "确认通过",
        detail_analysis="建议护士核实各项指标，如有异常需及时与医生沟通。",
    )


@router.put("/records/{record_id}")
async def update_record(record_id: str, data: FollowUpRecordUpdateRequest, db: Session = Depends(get_db),
                        current_user: TokenPayload = Depends(get_current_user)):
    """更新随访记录（仅允许更新安全字段）

    仅 draft/in_progress 状态允许修改，已归档记录不可篡改。
    仅护士/管理员可以更新随访记录。
    """
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以编辑随访记录")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    # 状态机校验：仅 draft/in_progress 状态允许编辑
    try:
        current_status = FollowUpStatus(record.status)
    except ValueError:
        raise HTTPException(400, f"未知状态 '{record.status}'")
    if not followup_fsm.can_transition(current_status, "edit"):
        raise HTTPException(400, f"当前状态 '{record.status}' 不允许修改，仅 'draft' 或 'in_progress' 状态可修改")

    if data.summary is not None:
        record.summary = data.summary
    if data.chief_complaint is not None:
        record.chief_complaint = data.chief_complaint
    if data.classification is not None:
        record.classification = data.classification
    if data.health_education is not None:
        record.health_education = data.health_education
    if data.self_reported_data is not None:
        record.self_reported_data = data.self_reported_data
    # nurse_notes 字段在 FollowUpRecord 模型中不存在，使用 review_comment 替代
    if data.nurse_notes is not None:
        record.review_comment = data.nurse_notes
    db.commit()
    return {"message": "更新成功"}


@router.get("/records/{record_id}/document")
def get_record_document(record_id: str, db: Session = Depends(get_db),
                        current_user: TokenPayload = Depends(get_current_user)):
    """获取随访记录的归档文档。

    confirmed 阶段返回实时预览；archived 阶段返回最终冻结快照。
    """
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    patient_name = pregnant.display_name if pregnant else "未知"

    generated_snapshot, generated_text = _generate_record_document_for(record, patient_name)
    if record.status == "archived" and record.record_snapshot:
        snapshot = dict(record.record_snapshot or {})
        snapshot.setdefault("record_id", str(record.id))
        if not snapshot.get("archive_summary_final_text"):
            snapshot["archive_summary_final_text"] = generated_snapshot.get("archive_summary_final_text", "")
            snapshot["archive_summary_modified"] = generated_snapshot.get("archive_summary_modified", False)
            snapshot["ai_snapshot"] = generated_snapshot.get("ai_snapshot", {})
        text = record.record_text or generated_text
    else:
        snapshot = generated_snapshot
        text = generated_text

    return {
        "record_id": str(record.id),
        "patient_name": patient_name,
        "status": record.status,
        "snapshot": snapshot,
        "text": text,
        "signature": record.signature_data or {},
        "ai_snapshot": record.ai_snapshot or {},
        "archive_summary": _archive_summary_response(record).model_dump(),
        "has_document": bool(snapshot),
        "can_print": record.status == "archived",
    }


@router.post("/records/{record_id}/sign")
def sign_record(record_id: str, req: FollowUpSignatureRequest, db: Session = Depends(get_db),
                current_user: TokenPayload = Depends(get_current_user)):
    """护士签署归档文档

    将手写签名 base64 PNG 存入 signature_data，附带签名者姓名和时间。
    仅护士/管理员可以签署。签名后记录才可归档。
    """
    if current_user.role not in ("nurse", "admin"):
        raise HTTPException(403, "仅护士或管理员可以签署随访记录")
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    # 状态机校验：仅 confirmed 状态允许签名
    if record.status != "confirmed":
        raise HTTPException(400, f"当前状态 '{record.status}' 不允许签名，仅 'confirmed' 状态可签名")
    _require_modified_archive_summary(record)
    record.signature_data = {
        "image": req.signature_image,
        "signer": req.signer_name,
        "signed_at": beijing_now().isoformat(),
    }
    db.commit()
    return {"message": "签名已保存", "signed_at": record.signature_data["signed_at"]}


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
def get_pending_followup(pregnant_id: str, db: Session = Depends(get_db),
                         current_user: TokenPayload = Depends(get_current_user)):
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
async def respond_to_followup(req: FollowUpAnswer, db: Session = Depends(get_db),
                              current_user: TokenPayload = Depends(get_current_user)):
    """孕妇提交随访回答（支持部分提交）

    状态机：draft → in_progress → completed
    量化数据同时写入 HealthDataPoint。
    全部完成后调用 LLM 生成温馨汇总。
    已完成/已确认/已归档的记录不允许再提交。
    """
    from datetime import datetime

    # SELECT ... FOR UPDATE 防止并发提交时的读-改-写竞争
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.id == UUID(req.record_id)
    ).with_for_update().first()
    if not record:
        raise HTTPException(404, "随访记录不存在")

    # 状态机校验：已完成/已确认/已归档的记录不允许再提交
    try:
        current_status = FollowUpStatus(record.status)
    except ValueError:
        raise HTTPException(400, f"未知状态 '{record.status}'")
    if not followup_fsm.can_transition(current_status, "start") and not followup_fsm.can_transition(current_status, "complete"):
        raise HTTPException(400, f"当前状态 '{record.status}' 不允许提交回答")

    # 合并已有数据
    reported_data = dict(record.self_reported_data) if record.self_reported_data else {}
    chief_complaint = record.chief_complaint or ""

    for key, value in req.answers.items():
        if key == "feeling" and not chief_complaint:
            chief_complaint = str(value)
        reported_data[key] = value

        # 量化数据同时写入 HealthDataPoint
        _save_health_data_point(record.pregnant_id, key, value, db)

    # 状态机转换: draft → in_progress（孕妇首次提交回答）
    if record.status == FOLLOWUP_STATUS_DRAFT:
        try:
            followup_fsm.transition(current_status, "start")
            record.status = FOLLOWUP_STATUS_IN_PROGRESS
        except InvalidTransition as e:
            raise HTTPException(400, f"状态转换不允许: {e}")

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
        # 状态机转换: in_progress → completed（全部回答完毕）
        try:
            followup_fsm.transition(FollowUpStatus(record.status), "complete")
            record.status = FOLLOWUP_STATUS_COMPLETED
        except InvalidTransition as e:
            raise HTTPException(400, f"状态转换不允许: {e}")
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

            # 补充查询聚合字段（规则引擎依赖这些历史数据）
            if context:
                from sqlalchemy import func
                from datetime import timedelta
                from ..utils.timezone import beijing_now
                now = beijing_now()
                week_ago = now - timedelta(days=7)
                two_weeks_ago = now - timedelta(days=14)

                # 补充当前随访未采集但规则引擎需要的指标
                existing_keys = set(context.keys())

                # 胎动平均值（近7天）
                if "fetal_movement_avg" not in existing_keys:
                    from ..models import HealthDataPoint
                    fm_avg = db.query(func.avg(HealthDataPoint.value)).filter(
                        HealthDataPoint.pregnant_id == record.pregnant_id,
                        HealthDataPoint.metric_code == "fetal_movement",
                        HealthDataPoint.recorded_at >= week_ago,
                    ).scalar()
                    if fm_avg:
                        context["fetal_movement_avg"] = float(fm_avg)

                # 体重周增长
                if "weight_gain_weekly" not in existing_keys and "weight" in context:
                    weight_prev = db.query(HealthDataPoint).filter(
                        HealthDataPoint.pregnant_id == record.pregnant_id,
                        HealthDataPoint.metric_code == "weight",
                        HealthDataPoint.recorded_at <= two_weeks_ago,
                    ).order_by(HealthDataPoint.recorded_at.desc()).first()
                    if weight_prev and weight_prev.value > 0:
                        context["weight_gain_weekly"] = (context["weight"] - weight_prev.value) / 2.0

                # 情绪评分平均值（近7天）
                if "emotion_score_avg_7d" not in existing_keys:
                    emotion_avg = db.query(func.avg(HealthDataPoint.value)).filter(
                        HealthDataPoint.pregnant_id == record.pregnant_id,
                        HealthDataPoint.metric_code == "emotion_score",
                        HealthDataPoint.recorded_at >= week_ago,
                    ).scalar()
                    if emotion_avg:
                        context["emotion_score_avg_7d"] = float(emotion_avg)

                # 睡眠时长
                if "sleep_hours" not in existing_keys:
                    sleep = db.query(HealthDataPoint).filter(
                        HealthDataPoint.pregnant_id == record.pregnant_id,
                        HealthDataPoint.metric_code == "sleep_hours",
                    ).order_by(HealthDataPoint.recorded_at.desc()).first()
                    if sleep:
                        context["sleep_hours"] = sleep.value

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

        # LLM 分析和健康教育改为按需触发（通过 /respond/analyze/stream 端点）
        # 规则引擎已执行，模板健康教育兜底
        if not record.health_education:
            gest_week_int = int(record.gestational_week.split("+")[0]) if record.gestational_week and "+" in record.gestational_week else 20
            record.health_education = followup_service.generate_health_education(
                gest_week_int,
                pregnant.risk_tags if pregnant else [],
            )

    db.commit()

    result = {
        "record_id": str(record.id),
        "status": record.status,
        "answered_count": len(answered_keys),
        "total_count": total,
    }
    if all_answered and record.status == FOLLOWUP_STATUS_COMPLETED:
        result["summary"] = record.summary or ""
        result["analysis_available"] = True
        result["health_education"] = record.health_education or []
    return result


class FollowUpAnalyzeRequest(BaseModel):
    record_id: str


@router.post("/respond/analyze/stream")
async def respond_analyze_stream(req: FollowUpAnalyzeRequest, db: Session = Depends(get_db),
                                 current_user: TokenPayload = Depends(get_current_user)):
    """SSE 流式端点：对已完成的随访记录进行 AI 分析

    事件类型：
    - phase:  分析阶段提示（data 为阶段描述字符串）
    - chunk:  分析文本流式片段
    - done:   分析完成（data 为 JSON，包含 analysis_report 和 health_education）
    - error:  分析失败（data 为错误信息）
    """
    record = db.query(FollowUpRecord).filter(
        FollowUpRecord.id == UUID(req.record_id)
    ).first()
    if not record:
        raise HTTPException(404, "随访记录不存在")
    if record.status != FOLLOWUP_STATUS_COMPLETED:
        raise HTTPException(400, "随访尚未完成，无法进行分析")

    answers = dict(record.self_reported_data) if record.self_reported_data else {}
    pregnant = db.query(Pregnant).filter(
        Pregnant.pregnant_id == record.pregnant_id
    ).first()
    patient_name = (pregnant.nickname or pregnant.display_name) if pregnant else ""
    risk_tags = pregnant.risk_tags if pregnant else []
    gest_week = record.gestational_week or "?"

    return EventSourceResponse(
        _stream_followup_analysis(
            patient_name=patient_name,
            gest_week=gest_week,
            answers=answers,
            risk_tags=risk_tags,
            pregnant_id=record.pregnant_id,
            db=db,
            record=record,
            pregnant=pregnant,
        )
    )


async def _stream_followup_analysis(
    patient_name: str,
    gest_week: str,
    answers: dict,
    risk_tags: list[str],
    pregnant_id: str,
    db: Session,
    record: FollowUpRecord,
    pregnant,
) -> AsyncGenerator[dict, None]:
    """流式生成随访分析报告的 SSE 事件生成器"""
    from loguru import logger

    # Phase 1: 收集历史数据
    yield {"event": "phase", "data": "正在收集历史健康数据..."}

    history_text = ""
    recent_health_text = ""
    try:
        prev_records = db.query(FollowUpRecord).filter(
            FollowUpRecord.pregnant_id == pregnant_id,
            FollowUpRecord.status.in_(["completed", "confirmed", "archived"]),
        ).order_by(FollowUpRecord.created_at.desc()).limit(3).all()

        if prev_records:
            history_lines = []
            for pr in prev_records:
                pr_data = pr.self_reported_data or {}
                pr_date = pr.created_at.strftime("%Y-%m-%d") if pr.created_at else "未知"
                pr_items = [f"{k}={v}" for k, v in pr_data.items() if v]
                history_lines.append(f"  [{pr_date}] {'; '.join(pr_items)}")
            history_text = "\n".join(history_lines)

        from datetime import timedelta
        from ..models import HealthDataPoint
        seven_days_ago = beijing_now() - timedelta(days=7)
        recent_points = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= seven_days_ago,
        ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()

        if recent_points:
            health_lines = [
                f"  {hp.metric_code}: {hp.value}{hp.unit} ({hp.recorded_at.strftime('%m-%d')})"
                for hp in recent_points
            ]
            recent_health_text = "\n".join(health_lines)
    except Exception as e:
        logger.warning("随访分析历史数据收集失败: %s", e)

    # Phase 2: 开始 AI 分析
    yield {"event": "phase", "data": "正在分析您的健康趋势..."}

    answer_lines = [f"- {k}: {v}" for k, v in answers.items()]
    answer_text = "\n".join(answer_lines)
    risk_text = "、".join(risk_tags) if risk_tags else "无"

    context_section = ""
    if history_text:
        context_section += f"\n\n最近随访历史：\n{history_text}"
    if recent_health_text:
        context_section += f"\n\n最近7天健康数据：\n{recent_health_text}"

    analysis_report = None
    health_education_list = []

    # 尝试1: Agno Agent 流式输出
    agno_success = False
    try:
        from ..core.agno_medical_agents import get_followup_analysis_agent
        agent = get_followup_analysis_agent()
        prompt = (
            f"请分析以下孕妇的随访数据，生成结构化分析报告。\n\n"
            f"孕妇：{patient_name}，孕{gest_week}周\n"
            f"风险标签：{risk_text}\n"
            f"本次随访数据：\n{answer_text}"
            f"{context_section}"
        )
        t0 = time.time()
        full_response = ""
        run_response = None
        async for chunk in agent.arun(input=prompt, stream=True):
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                full_response += content
                yield {"event": "chunk", "data": content}

        if full_response.strip():
            from ..core.agno_structured import extract_structured_content
            data = extract_structured_content(full_response)
            if data:
                analysis_report = {
                    "warm_summary": data.get("warm_summary", ""),
                    "abnormal_indicators": data.get("abnormal_indicators", []),
                    "trend_analysis": data.get("trend_analysis", ""),
                    "personalized_advice": data.get("personalized_advice", ""),
                    "nurse_action_suggestion": data.get("nurse_action_suggestion", "确认通过"),
                }
                agno_success = True
        _quick_audit(
            session_id=f"followup_stream_{pregnant_id or 'anon'}",
            user_id=pregnant_id or "anonymous",
            agent_variant="analyze",
            intent_classification="FOLLOWUP_ANALYZE",
            run_response=run_response,
            total_latency_ms=int((time.time() - t0) * 1000),
        )
    except Exception:
        logger.warning("Agno stream analysis failed, falling back to standard LLM")

    # 尝试2: 普通 LLM + 最终兜底
    if not agno_success:
        try:
            from ..core import get_llm_client
            client = get_llm_client()
            system_prompt = (
                "你是一位专业的孕期健康分析助手。请根据随访数据生成JSON格式的分析报告。\n"
                "返回字段：\n"
                "- warm_summary: 温馨总结（30-50字）\n"
                "- abnormal_indicators: 异常指标列表（字符串数组）\n"
                "- trend_analysis: 趋势分析（50-100字）\n"
                "- personalized_advice: 个性化建议（50-100字）\n"
                "- nurse_action_suggestion: 护士行动建议（确认通过/需进一步沟通/紧急上报）\n"
                "不要包含markdown代码块标记，直接返回JSON。"
            )
            user_msg = (
                f"孕妇：{patient_name}，孕{gest_week}周，风险标签：{risk_text}\n"
                f"本次随访：\n{answer_text}"
                f"{context_section}"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
            response = await client.chat(messages)
            if response and response.strip():
                from ..core.json_parser import parse_llm_json
                data = parse_llm_json(response)
                if data:
                    analysis_report = {
                        "warm_summary": data.get("warm_summary", ""),
                        "abnormal_indicators": data.get("abnormal_indicators", []),
                        "trend_analysis": data.get("trend_analysis", ""),
                        "personalized_advice": data.get("personalized_advice", ""),
                        "nurse_action_suggestion": data.get("nurse_action_suggestion", "确认通过"),
                    }
                    warm = data.get("warm_summary", "")
                    trend = data.get("trend_analysis", "")
                    advice = data.get("personalized_advice", "")
                    if warm:
                        yield {"event": "chunk", "data": warm + "\n\n"}
                    if trend:
                        yield {"event": "chunk", "data": "📊 " + trend + "\n\n"}
                    if advice:
                        yield {"event": "chunk", "data": "💡 " + advice}
        except Exception:
            logger.warning("Standard LLM analysis failed, using fallback template")

    # 降级: 模板兜底
    if not analysis_report:
        analysis_report = _fallback_analysis_report(patient_name, gest_week, answers, risk_tags)
        yield {"event": "chunk", "data": analysis_report.get("warm_summary", "")}

    # Phase 3: 生成个性化健康教育
    yield {"event": "phase", "data": "正在生成个性化健康建议..."}

    try:
        gest_week_int = int(gest_week.split("+")[0]) if gest_week and "+" in gest_week else 20
        personalized_edu = await followup_service.generate_health_education_with_llm(
            gest_week=gest_week_int,
            risk_tags=risk_tags,
            answers=answers,
        )
        if personalized_edu:
            health_education_list = personalized_edu
            record.health_education = personalized_edu
        else:
            health_education_list = record.health_education or []
    except Exception:
        logger.warning("Health education generation failed")
        health_education_list = record.health_education or []

    # 写入 LLM 分析结果到记录
    if analysis_report:
        record.summary = analysis_report.get("warm_summary", record.summary)
    db.commit()

    # Phase 4: 完成
    yield {
        "event": "done",
        "data": json.dumps({
            "record_id": str(record.id),
            "status": record.status,
            "analysis_report": analysis_report,
            "health_education": health_education_list,
        }),
    }


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
                recorded_at=beijing_now(),
            ))
            points.append(HealthDataPoint(
                pregnant_id=pregnant_id, metric_code="diastolic",
                value=float(parsed["dbp"]), unit="mmHg", source=source,
                recorded_at=beijing_now(),
            ))
    elif "metric_code" in parsed:
        points.append(HealthDataPoint(
            pregnant_id=pregnant_id, metric_code=parsed["metric_code"],
            value=float(parsed["value"]), unit=parsed.get("unit", ""), source=source,
            recorded_at=beijing_now(),
        ))

    for p in points:
        db.add(p)


async def _generate_llm_summary(
    patient_name: str, gest_week: str, answers: dict, risk_tags: list[str],
    pregnant_id: str = "",
) -> dict:
    """调用 LLM 生成结构化的随访分析报告

    返回 FollowUpAnalysisReport 字典，包含温馨总结、异常指标、趋势分析、
    个性化建议和护士行动建议。

    三层降级：Agno Agent → 普通 LLM → 模板兜底
    """
    from ..config import settings

    # 收集历史随访数据和最近健康数据
    history_text = ""
    recent_health_text = ""
    db = SessionLocal()
    try:
        # 最近 3 次随访记录
        prev_records = db.query(FollowUpRecord).filter(
            FollowUpRecord.pregnant_id == pregnant_id,
            FollowUpRecord.status.in_(["completed", "confirmed", "archived"]),
        ).order_by(FollowUpRecord.created_at.desc()).limit(3).all()

        if prev_records:
            history_lines = []
            for pr in prev_records:
                pr_data = pr.self_reported_data or {}
                pr_date = pr.created_at.strftime("%Y-%m-%d") if pr.created_at else "未知"
                pr_items = [f"{k}={v}" for k, v in pr_data.items() if v]
                history_lines.append(f"  [{pr_date}] {'; '.join(pr_items)}")
            history_text = "\n".join(history_lines)

        # 最近 7 天健康数据
        from datetime import timedelta
        from ..models import HealthDataPoint
        seven_days_ago = beijing_now() - timedelta(days=7)
        recent_points = db.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == pregnant_id,
            HealthDataPoint.recorded_at >= seven_days_ago,
        ).order_by(HealthDataPoint.recorded_at.desc()).limit(10).all()

        if recent_points:
            health_lines = [
                f"  {hp.metric_code}: {hp.value}{hp.unit} ({hp.recorded_at.strftime('%m-%d')})"
                for hp in recent_points
            ]
            recent_health_text = "\n".join(health_lines)
    except Exception as e:
        logger.warning("LLM摘要历史数据收集失败: %s", e)
    finally:
        db.close()

    # 构造答案摘要
    answer_lines = []
    for k, v in answers.items():
        answer_lines.append(f"- {k}: {v}")
    answer_text = "\n".join(answer_lines)
    risk_text = "、".join(risk_tags) if risk_tags else "无"

    context_section = ""
    if history_text:
        context_section += f"\n\n最近随访历史：\n{history_text}"
    if recent_health_text:
        context_section += f"\n\n最近7天健康数据：\n{recent_health_text}"

    # 尝试1: Agno Agent 结构化输出
    try:
        from ..core.agno_medical_agents import get_followup_analysis_agent
        from ..core.agno_structured import extract_structured_content
        agent = get_followup_analysis_agent()
        prompt = (
            f"请分析以下孕妇的随访数据，生成结构化分析报告。\n\n"
            f"孕妇：{patient_name}，孕{gest_week}周\n"
            f"风险标签：{risk_text}\n"
            f"本次随访数据：\n{answer_text}"
            f"{context_section}"
        )
        t0 = time.time()
        response = await agent.arun(input=prompt)
        _quick_audit(
            session_id=f"followup_analyze_{pregnant_id or 'anon'}",
            user_id=pregnant_id or "anonymous",
            agent_variant="analyze",
            intent_classification="FOLLOWUP_ANALYZE",
            run_response=response,
            total_latency_ms=int((time.time() - t0) * 1000),
        )
        data = extract_structured_content(response.content)
        if data:
            return {
                "warm_summary": data.get("warm_summary", ""),
                "abnormal_indicators": data.get("abnormal_indicators", []),
                "trend_analysis": data.get("trend_analysis", ""),
                "personalized_advice": data.get("personalized_advice", ""),
                "nurse_action_suggestion": data.get("nurse_action_suggestion", "确认通过"),
            }
    except Exception as e:
        logger.warning("随访分析Agno Agent降级: %s", e)

    # 尝试2: 普通 LLM（容错降级）
    try:
        from ..core import get_llm_client
        client = get_llm_client()
        system_prompt = (
            "你是一位专业的孕期健康分析助手。请根据随访数据生成JSON格式的分析报告。\n"
            "返回字段：\n"
            "- warm_summary: 温馨总结（30-50字）\n"
            "- abnormal_indicators: 异常指标列表（字符串数组）\n"
            "- trend_analysis: 趋势分析（50-100字）\n"
            "- personalized_advice: 个性化建议（50-100字）\n"
            "- nurse_action_suggestion: 护士行动建议（确认通过/需进一步沟通/紧急上报）\n"
            "不要包含markdown代码块标记，直接返回JSON。"
        )
        user_msg = (
            f"孕妇：{patient_name}，孕{gest_week}周，风险标签：{risk_text}\n"
            f"本次随访：\n{answer_text}"
            f"{context_section}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        response = await client.chat(messages)
        if response and response.strip():
            from ..core.json_parser import parse_llm_json
            data = parse_llm_json(response)
            if data:
                return {
                    "warm_summary": data.get("warm_summary", ""),
                    "abnormal_indicators": data.get("abnormal_indicators", []),
                    "trend_analysis": data.get("trend_analysis", ""),
                    "personalized_advice": data.get("personalized_advice", ""),
                    "nurse_action_suggestion": data.get("nurse_action_suggestion", "确认通过"),
                }
    except Exception as e:
        logger.warning("随访分析普通LLM降级: %s", e)

    # 降级: 模板兜底
    return _fallback_analysis_report(patient_name, gest_week, answers, risk_tags)


def _fallback_analysis_report(
    patient_name: str, gest_week: str, answers: dict, risk_tags: list[str]
) -> dict:
    """模板兜底的随访分析报告"""
    # 检测异常指标
    abnormal = []

    # 血压检查
    bp_value = answers.get("bp", "")
    if bp_value and "/" in str(bp_value):
        try:
            parts = str(bp_value).split("/")
            sbp, dbp = float(parts[0]), float(parts[1])
            if sbp >= 140 or dbp >= 90:
                abnormal.append(f"血压偏高（{bp_value}mmHg），正常值<140/90")
            elif sbp >= 135 or dbp >= 85:
                abnormal.append(f"血压临界（{bp_value}mmHg），需关注")
        except (ValueError, IndexError):
            pass

    # 血糖检查
    bs_fasting = answers.get("blood_sugar_fasting")
    if bs_fasting:
        try:
            val = float(bs_fasting)
            if val > 5.3:
                abnormal.append(f"空腹血糖偏高（{val}mmol/L），目标≤5.3")
        except (ValueError, TypeError):
            pass

    # 胎动检查
    fm = answers.get("fetal_movement")
    if fm:
        try:
            val = float(fm)
            if val < 3:
                abnormal.append(f"胎动偏少（{val}次/小时），正常≥3次/小时")
        except (ValueError, TypeError):
            pass

    # 生成温馨总结
    if abnormal:
        warm = f"{patient_name}，感谢您完成本次随访。有{len(abnormal)}项指标需要特别关注，请留意下方详情。"
        recommendation = "需进一步沟通"
        action_needed = True
    else:
        warm = f"{patient_name}，本次随访各项指标均在正常范围内，继续保持良好的生活习惯哦~"
        recommendation = "确认通过"
        action_needed = False

    return {
        "warm_summary": warm,
        "abnormal_indicators": abnormal,
        "trend_analysis": f"本次为孕{gest_week}周随访。建议持续关注各项指标变化趋势。" if not abnormal else f"本次为孕{gest_week}周随访，检测到异常指标，建议密切关注。",
        "personalized_advice": "请继续保持规律作息和均衡饮食，按时产检。如有不适请及时就医。",
        "nurse_action_suggestion": recommendation,
    }
