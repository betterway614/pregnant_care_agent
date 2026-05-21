"""预警服务 - 创建和管理预警记录"""
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import and_
from loguru import logger
from ..models import Alert


# 去重时间窗口（小时）
DEDUP_WINDOW_HOURS = 24


class AlertService:
    """预警服务"""

    @staticmethod
    def _find_duplicate(db: Session, pregnant_id: str, rule_id: str) -> Alert | None:
        """查找24h内相同 rule_id 的 PENDING 预警"""
        if not rule_id:
            return None
        cutoff = datetime.utcnow() - timedelta(hours=DEDUP_WINDOW_HOURS)
        return db.query(Alert).filter(
            and_(
                Alert.pregnant_id == pregnant_id,
                Alert.rule_id == rule_id,
                Alert.status == "PENDING",
                Alert.created_at >= cutoff,
            )
        ).first()

    @staticmethod
    def create_alert(
        db: Session,
        pregnant_id: str,
        rule_id: str,
        level: str,
        message: str,
        trigger_source: str = "RULE_ENGINE",
        details: dict = None,
    ) -> Alert:
        """创建预警记录（自动去重）"""
        existing = AlertService._find_duplicate(db, pregnant_id, rule_id)
        if existing:
            logger.info(f"预警去重: {rule_id} for {pregnant_id} 已存在, 跳过创建")
            return existing

        alert = Alert(
            id=uuid4(),
            pregnant_id=pregnant_id,
            trigger_source=trigger_source,
            rule_id=rule_id,
            level=level,
            message=message,
            status="PENDING",
            details=details or {},
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def create_alerts_from_hits(
        db: Session,
        pregnant_id: str,
        hits: list[dict],
        trigger_source: str = "RULE_ENGINE",
    ) -> list[Alert]:
        """从规则命中列表批量创建预警（自动去重）"""
        alerts = []
        for hit in hits:
            alert = AlertService.create_alert(
                db=db,
                pregnant_id=pregnant_id,
                rule_id=hit.get("rule_id", "UNKNOWN"),
                level=hit.get("level", "YELLOW"),
                message=hit.get("message", ""),
                trigger_source=trigger_source,
                details={
                    "action": hit.get("action", "ALERT_NURSE"),
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            alerts.append(alert)
        return alerts


    @staticmethod
    async def enrich_alert_with_llm(db: Session, alert: Alert, pregnant):
        """异步调用 LLM 为预警生成分析摘要，存入 details.llm_analysis"""
        try:
            from ..core.llm_client import get_llm_client
            from ..core.json_parser import parse_llm_json
            from ..services.patient_context_service import get_recent_health_data

            # 收集上下文
            health_points = get_recent_health_data(db, alert.pregnant_id, limit=10)
            health_text = "\n".join(
                f"  - {h['metric']}: {h['value']}{h['unit']} ({h['recorded_at']})"
                for h in health_points
            ) or "  暂无健康数据"

            gest_week = (pregnant.gestational_age_days or 0) // 7

            prompt = f"""你是一位产科护理专家。请分析以下预警信息，返回 JSON 格式的分析结果。

## 预警信息
- 孕妇: {pregnant.display_name}
- 孕周: {gest_week}周
- 预警级别: {alert.level}
- 触发规则: {alert.rule_id}
- 预警消息: {alert.message}
- 风险标签: {', '.join(pregnant.risk_tags or [])}

## 近期健康数据
{health_text}

## 要求
请返回如下 JSON（不要输出其他内容）：
{{
  "risk_interpretation": "风险解读：为什么会触发这个预警，结合临床背景分析",
  "recommended_actions": ["建议措施1", "建议措施2", "建议措施3"],
  "severity_assessment": "严重程度评估：描述当前严重程度和可能的发展趋势"
}}"""

            client = get_llm_client()
            messages = [
                {"role": "system", "content": "你是产科护理专家，擅长分析孕妇健康预警。请用中文回答，只返回JSON。"},
                {"role": "user", "content": prompt},
            ]
            response = await client.chat(messages)
            if not response:
                return

            data = parse_llm_json(response)
            if not data:
                return

            # 更新 alert.details
            details = alert.details or {}
            details["llm_analysis"] = {
                "risk_interpretation": data.get("risk_interpretation", ""),
                "recommended_actions": data.get("recommended_actions", []),
                "severity_assessment": data.get("severity_assessment", ""),
                "analyzed_at": datetime.utcnow().isoformat(),
            }
            alert.details = details
            db.commit()
            logger.info(f"LLM分析完成: alert_id={alert.id}")
        except Exception as e:
            logger.warning(f"LLM预警分析失败 (alert_id={alert.id}): {e}")


alert_service = AlertService()