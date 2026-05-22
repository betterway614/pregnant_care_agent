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
        """使用护士 Agno Agent 为预警生成分析摘要"""
        from .alert_analysis_service import alert_analysis_service

        nurse_result = await alert_analysis_service.run_nurse_analysis(db, alert, pregnant)
        if not nurse_result:
            return

        details = alert.details or {}
        details["llm_analysis"] = {
            "risk_interpretation": nurse_result.get("risk_assessment") or nurse_result.get("summary", ""),
            "recommended_actions": [nurse_result.get("nursing_suggestions", "")],
            "severity_assessment": nurse_result.get("summary", ""),
            "analyzed_at": nurse_result.get("analyzed_at", datetime.utcnow().isoformat()),
            "source": "agno_nurse_agent",
        }
        alert.details = details
        db.commit()
        logger.info("Agno预警分析完成: alert_id={}", alert.id)


alert_service = AlertService()