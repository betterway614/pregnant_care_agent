"""Alert 分析服务 - 接入 Agno Workflow / Agent"""
from __future__ import annotations

import time
from loguru import logger

from ..utils.timezone import beijing_now

from ..models import Alert, Pregnant, FollowUpRecord, AgentAuditLog
from ..database import SessionLocal
from ..core.agno_medical_agents import get_nurse_agent, get_doctor_agent
from ..core.agno_structured import extract_structured_content
from ..core.agno_workflow import get_alert_analysis_workflow
from ..core.agno_team import get_alert_team
from ..services.patient_context_service import get_recent_health_data


def _alert_quick_audit(
    session_id: str,
    user_id: str,
    agent_variant: str,
    intent: str,
    run_response,
    elapsed_ms: int,
    agent_role: str = "nurse",
) -> int | None:
    """预警分析的轻量审计日志"""
    if elapsed_ms < 10:
        return None
    try:
        content = getattr(run_response, "content", "") or ""
        db = SessionLocal()
        try:
            log = AgentAuditLog(
                session_id=session_id,
                user_id=user_id,
                agent_role=agent_role,
                agent_variant=agent_variant,
                intent_classification=intent,
                routed_agent=f"{'小护' if agent_role == 'nurse' else '智医'}-{agent_variant}",
                input_tokens=0, output_tokens=0, total_tokens=0,
                model_id=getattr(run_response, "model", "") or "unknown",
                provider="openai",
                total_latency_ms=elapsed_ms,
                response_preview=content[:200],
            )
            db.add(log)
            db.commit()
            return log.id
        finally:
            db.close()
    except Exception:
        return None


def _build_data_snapshot(db, pregnant_id: str) -> str:
    """构建健康数据快照，注入 Agent prompt 减少工具调用"""
    parts = []
    recent = get_recent_health_data(db, pregnant_id, limit=5)
    if recent:
        items = [f"{d['metric']}={d['value']}{d['unit']}" for d in recent[:5]]
        parts.append(f"最近健康数据: {', '.join(items)}")

    latest_followup = db.query(FollowUpRecord).filter(
        FollowUpRecord.pregnant_id == pregnant_id,
        FollowUpRecord.lab_results.isnot(None),
    ).order_by(FollowUpRecord.created_at.desc()).first()
    if latest_followup and latest_followup.lab_results:
        lr = latest_followup.lab_results
        items = [f"{k}={v}" for k, v in lr.items()]
        parts.append(f"最新化验(孕{latest_followup.gestational_week or '?'}周): {', '.join(items)}")

    return "\n".join(parts) if parts else ""


class AlertAnalysisService:
    """预警 AI 分析：护士初筛 + 医生预分析"""

    @staticmethod
    async def run_nurse_analysis(db, alert: Alert, pregnant: Pregnant) -> dict | None:
        gest_week = (pregnant.gestational_age_days or 0) // 7
        snapshot = _build_data_snapshot(db, alert.pregnant_id)
        snapshot_block = f"\n\n患者数据快照：\n{snapshot}" if snapshot else ""
        prompt = (
            f"预警分析任务：孕妇 {pregnant.display_name}（孕{gest_week}周），"
            f"预警级别 {alert.level}，消息：{alert.message}。"
            f"{snapshot_block}"
            "请基于以上数据给出护理分析。"
        )
        try:
            agent = get_nurse_agent()
            t0 = time.time()
            response = await agent.arun(input=prompt, user_id=alert.pregnant_id)
            _alert_quick_audit(
                session_id=f"alert_nurse_{alert.id}",
                user_id=alert.pregnant_id,
                agent_variant="analyze",
                intent="ALERT_ANALYZE",
                run_response=response,
                elapsed_ms=int((time.time() - t0) * 1000),
            )
            data = extract_structured_content(response.content)
            if data:
                return {
                    "role": "nurse",
                    "summary": data.get("summary", ""),
                    "risk_assessment": data.get("risk_assessment", ""),
                    "nursing_suggestions": data.get("nursing_suggestions", ""),
                    "analyzed_at": beijing_now().isoformat(),
                }
            text = response.content if isinstance(response.content, str) else str(response.content)
            return {"role": "nurse", "summary": text, "analyzed_at": beijing_now().isoformat()}
        except Exception as exc:
            logger.warning("护士预警分析失败 alert_id={}: {}", alert.id, exc)
            return None

    @staticmethod
    async def run_doctor_pre_analysis(db, alert: Alert, pregnant: Pregnant) -> dict | None:
        if alert.level not in ("RED", "ORANGE"):
            return None

        gest_week = (pregnant.gestational_age_days or 0) // 7
        snapshot = _build_data_snapshot(db, alert.pregnant_id)
        snapshot_block = f"\n\n患者数据快照：\n{snapshot}" if snapshot else ""
        prompt = (
            f"医生预分析任务：孕妇 {pregnant.display_name}（孕{gest_week}周），"
            f"预警级别 {alert.level}，消息：{alert.message}。"
            f"{snapshot_block}"
            "请基于以上数据给出结构化分析供医生审核。"
        )
        try:
            agent = get_doctor_agent()
            t0 = time.time()
            response = await agent.arun(input=prompt, user_id=alert.pregnant_id)
            _alert_quick_audit(
                session_id=f"alert_doctor_{alert.id}",
                user_id=alert.pregnant_id,
                agent_variant="analyze",
                intent="ALERT_ANALYZE",
                run_response=response,
                elapsed_ms=int((time.time() - t0) * 1000),
                agent_role="doctor",
            )
            data = extract_structured_content(response.content)
            if data:
                return {
                    "role": "doctor",
                    "analysis": data.get("analysis", ""),
                    "risk_summary": data.get("risk_summary", ""),
                    "suggested_orders": data.get("suggested_orders", ""),
                    "analyzed_at": beijing_now().isoformat(),
                }
            text = response.content if isinstance(response.content, str) else str(response.content)
            return {"role": "doctor", "analysis": text, "analyzed_at": beijing_now().isoformat()}
        except Exception as exc:
            logger.warning("医生预分析失败 alert_id={}: {}", alert.id, exc)
            return None

    @staticmethod
    async def run_alert_workflow(db, alert: Alert, pregnant: Pregnant) -> dict:
        """执行完整预警分析 — 优先 Team 并行，降级串行 Workflow，最终降级单 Agent"""
        gest_week = (pregnant.gestational_age_days or 0) // 7
        input_text = (
            f"预警ID {alert.id}：孕妇 {pregnant.display_name} 孕{gest_week}周，"
            f"级别 {alert.level}，{alert.message}"
        )

        result_payload: dict = {"workflow": "alert_analysis", "steps": []}

        # 优先使用 Team 并行分析（护士+医生同时分析）
        try:
            team = get_alert_team()
            t0_team = time.time()
            run = await team.arun(input=input_text, user_id=alert.pregnant_id)
            _alert_quick_audit(
                session_id=f"alert_team_{alert.id}",
                user_id=alert.pregnant_id,
                agent_variant="team",
                intent="ALERT_ANALYZE",
                run_response=run,
                elapsed_ms=int((time.time() - t0_team) * 1000),
                agent_role="nurse",
            )
            result_payload["workflow_output"] = run.content if hasattr(run, "content") else str(run)
            result_payload["mode"] = "team_parallel"
        except Exception as exc:
            logger.warning("Alert Team 并行分析失败，降级串行 Workflow: {}", exc)
            try:
                workflow = get_alert_analysis_workflow()
                t0_wf = time.time()
                run = await workflow.arun(input=input_text, user_id=alert.pregnant_id)
                _alert_quick_audit(
                    session_id=f"alert_wf_{alert.id}",
                    user_id=alert.pregnant_id,
                    agent_variant="workflow",
                    intent="ALERT_ANALYZE",
                    run_response=run,
                    elapsed_ms=int((time.time() - t0_wf) * 1000),
                    agent_role="nurse",
                )
                result_payload["workflow_output"] = run.content if hasattr(run, "content") else str(run)
                result_payload["mode"] = "workflow_sequential"
            except Exception as exc2:
                logger.warning("Alert Workflow 也失败，降级单 Agent: {}", exc2)
                nurse = await AlertAnalysisService.run_nurse_analysis(db, alert, pregnant)
                if nurse:
                    result_payload["steps"].append(nurse)
                doctor = await AlertAnalysisService.run_doctor_pre_analysis(db, alert, pregnant)
                if doctor:
                    result_payload["steps"].append(doctor)
                result_payload["mode"] = "single_agent_fallback"

        details = alert.details or {}
        details["ai_workflow"] = result_payload
        details["analyzed_at"] = beijing_now().isoformat()
        alert.details = details
        db.commit()
        return result_payload


alert_analysis_service = AlertAnalysisService()
