"""Alert 分析服务 - 接入 Agno Workflow / Agent"""
from __future__ import annotations

from datetime import datetime

from loguru import logger

from ..models import Alert, Pregnant
from ..core.agno_medical_agents import get_nurse_agent, get_doctor_agent
from ..core.agno_structured import extract_structured_content
from ..core.agno_workflow import get_alert_analysis_workflow


class AlertAnalysisService:
    """预警 AI 分析：护士初筛 + 医生预分析"""

    @staticmethod
    async def run_nurse_analysis(db, alert: Alert, pregnant: Pregnant) -> dict | None:
        gest_week = (pregnant.gestational_age_days or 0) // 7
        prompt = (
            f"预警分析任务：孕妇 {pregnant.display_name}（孕{gest_week}周），"
            f"预警级别 {alert.level}，消息：{alert.message}。"
            "请先调用工具获取患者数据，再给出护理分析。"
        )
        try:
            agent = get_nurse_agent()
            response = await agent.arun(input=prompt, user_id=alert.pregnant_id)
            data = extract_structured_content(response.content)
            if data:
                return {
                    "role": "nurse",
                    "summary": data.get("summary", ""),
                    "risk_assessment": data.get("risk_assessment", ""),
                    "nursing_suggestions": data.get("nursing_suggestions", ""),
                    "analyzed_at": datetime.utcnow().isoformat(),
                }
            text = response.content if isinstance(response.content, str) else str(response.content)
            return {"role": "nurse", "summary": text, "analyzed_at": datetime.utcnow().isoformat()}
        except Exception as exc:
            logger.warning("护士预警分析失败 alert_id={}: {}", alert.id, exc)
            return None

    @staticmethod
    async def run_doctor_pre_analysis(db, alert: Alert, pregnant: Pregnant) -> dict | None:
        if alert.level not in ("RED", "ORANGE"):
            return None

        gest_week = (pregnant.gestational_age_days or 0) // 7
        prompt = (
            f"医生预分析任务：孕妇 {pregnant.display_name}（孕{gest_week}周），"
            f"预警级别 {alert.level}，消息：{alert.message}。"
            "请先调用工具获取综合数据，再给出结构化分析供医生审核。"
        )
        try:
            agent = get_doctor_agent()
            response = await agent.arun(input=prompt, user_id=alert.pregnant_id)
            data = extract_structured_content(response.content)
            if data:
                return {
                    "role": "doctor",
                    "analysis": data.get("analysis", ""),
                    "risk_summary": data.get("risk_summary", ""),
                    "suggested_orders": data.get("suggested_orders", ""),
                    "analyzed_at": datetime.utcnow().isoformat(),
                }
            text = response.content if isinstance(response.content, str) else str(response.content)
            return {"role": "doctor", "analysis": text, "analyzed_at": datetime.utcnow().isoformat()}
        except Exception as exc:
            logger.warning("医生预分析失败 alert_id={}: {}", alert.id, exc)
            return None

    @staticmethod
    async def run_alert_workflow(db, alert: Alert, pregnant: Pregnant) -> dict:
        """执行完整预警分析 Workflow，结果写入 alert.details"""
        workflow = get_alert_analysis_workflow()
        gest_week = (pregnant.gestational_age_days or 0) // 7
        input_text = (
            f"预警ID {alert.id}：孕妇 {pregnant.display_name} 孕{gest_week}周，"
            f"级别 {alert.level}，{alert.message}"
        )

        result_payload: dict = {"workflow": "alert_analysis", "steps": []}

        try:
            run = await workflow.arun(input=input_text, user_id=alert.pregnant_id)
            result_payload["workflow_output"] = run.content if hasattr(run, "content") else str(run)
        except Exception as exc:
            logger.warning("Alert Workflow 执行失败，降级单 Agent: {}", exc)
            nurse = await AlertAnalysisService.run_nurse_analysis(db, alert, pregnant)
            if nurse:
                result_payload["steps"].append(nurse)
            doctor = await AlertAnalysisService.run_doctor_pre_analysis(db, alert, pregnant)
            if doctor:
                result_payload["steps"].append(doctor)

        details = alert.details or {}
        details["ai_workflow"] = result_payload
        details["analyzed_at"] = datetime.utcnow().isoformat()
        alert.details = details
        db.commit()
        return result_payload


alert_analysis_service = AlertAnalysisService()
