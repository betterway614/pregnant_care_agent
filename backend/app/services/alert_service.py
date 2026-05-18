"""预警服务 - 创建和管理预警记录"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from ..models import Alert


class AlertService:
    """预警服务"""

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
        """创建预警记录"""
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
        """从规则命中列表批量创建预警"""
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


alert_service = AlertService()