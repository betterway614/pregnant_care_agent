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
from datetime import datetime
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
    """确认审核随访记录

    写入审核追溯信息：审核人、审核时间、审核意见、AI快照。
    """
    record = db.query(FollowUpRecord).filter(FollowUpRecord.id == UUID(record_id)).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    record.status = confirm.status
    record.reviewed_by = confirm.reviewer_id
    record.reviewed_at = datetime.utcnow()
    if confirm.review_comment:
        record.review_comment = confirm.review_comment
    if confirm.ai_snapshot:
        record.ai_snapshot = confirm.ai_snapshot
    db.commit()
    db.refresh(record)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == record.pregnant_id).first()
    return FollowUpRecordResponse(
        **{c.name: getattr(record, c.name) for c in record.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知"
    )


@router.get("/records/{record_id}/ai-review")
async def ai_review_followup(record_id: str):
    """护士审核随访时的 AI 辅助分析

    收集该次随访数据 + 历史记录 + 健康数据，调用 LLM 生成审核建议。
    三层降级：Agno Agent → 普通 LLM → 模板兜底。
    """
    from ..config import settings
    from ..models import HealthDataPoint, Alert
    from ..schemas import FollowUpAiReviewResponse
    from datetime import timedelta

    db = SessionLocal()
    try:
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
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
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

        # 尝试1: Agno Agent
        if settings.agno_enabled:
            try:
                from ..core.agno_medical_agents import create_followup_review_agent
                import json
                agent = create_followup_review_agent()
                response = await agent.arun(input=f"请审核以下随访记录，给出审核建议。\n\n{context}")
                content = response.content or ""
                data = json.loads(content) if isinstance(content, str) else content
                return FollowUpAiReviewResponse(
                    summary=data.get("summary", ""),
                    abnormal_flags=data.get("abnormal_flags", []),
                    action_needed=data.get("action_needed", False),
                    recommendation=data.get("recommendation", "确认通过"),
                    detail_analysis=data.get("detail_analysis", ""),
                )
            except Exception:
                pass

        # 尝试2: 普通 LLM
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
        except Exception:
            pass

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
    finally:
        db.close()


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
            pregnant_id=record.pregnant_id,
        )

        # LLM 个性化健康教育
        try:
            gest_week_int = int(record.gestational_week.split("+")[0]) if record.gestational_week and "+" in record.gestational_week else 20
            personalized_edu = await followup_service.generate_health_education_with_llm(
                gest_week=gest_week_int,
                risk_tags=pregnant.risk_tags if pregnant else [],
                answers=reported_data,
            )
            if personalized_edu:
                record.health_education = personalized_edu
        except Exception:
            pass  # 保留原有模板健康教育

    db.commit()

    result = {
        "record_id": str(record.id),
        "status": record.status,
        "answered_count": len(answered_keys),
        "total_count": total,
    }
    if summary:
        result["summary"] = summary.get("warm_summary", "")
        result["analysis_report"] = summary
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
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
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
    except Exception:
        pass
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
    if settings.agno_enabled:
        try:
            from ..core.agno_medical_agents import create_followup_analysis_agent
            agent = create_followup_analysis_agent()
            prompt = (
                f"请分析以下孕妇的随访数据，生成结构化分析报告。\n\n"
                f"孕妇：{patient_name}，孕{gest_week}周\n"
                f"风险标签：{risk_text}\n"
                f"本次随访数据：\n{answer_text}"
                f"{context_section}"
            )
            response = await agent.arun(input=prompt)
            content = response.content or ""
            import json
            try:
                data = json.loads(content) if isinstance(content, str) else content
                return {
                    "warm_summary": data.get("warm_summary", ""),
                    "abnormal_indicators": data.get("abnormal_indicators", []),
                    "trend_analysis": data.get("trend_analysis", ""),
                    "personalized_advice": data.get("personalized_advice", ""),
                    "nurse_action_suggestion": data.get("nurse_action_suggestion", "确认通过"),
                }
            except (json.JSONDecodeError, AttributeError):
                pass
        except Exception:
            pass

    # 尝试2: 普通 LLM
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
    except Exception:
        pass

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
