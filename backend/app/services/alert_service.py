"""预警服务 - 创建和管理预警记录"""
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import and_
from loguru import logger
from ..utils.timezone import beijing_now
from ..models import Alert


class AlertService:
    """预警服务"""

    @staticmethod
    def _find_duplicate(db: Session, pregnant_id: str, domain: str) -> Alert | None:
        """同一孕妇同一领域已有 PENDING 预警时视为重复"""
        if not domain:
            return None
        return db.query(Alert).filter(
            and_(
                Alert.pregnant_id == pregnant_id,
                Alert.domain == domain,
                Alert.status == "PENDING",
            )
        ).first()

    @staticmethod
    def create_alert(
        db: Session,
        pregnant_id: str,
        rule_id: str,
        domain: str,
        level: str,
        message: str,
        trigger_source: str = "RULE_ENGINE",
        details: dict = None,
    ) -> Alert:
        """创建预警记录（领域级去重）"""
        existing = AlertService._find_duplicate(db, pregnant_id, domain)
        if existing:
            logger.info(f"预警去重: domain={domain} for {pregnant_id} 已有 PENDING 预警, 跳过创建")
            return existing

        base_details = details or {}
        base_details["history"] = [{
            "seq": 1,
            "action": "created",
            "source_role": "system",
            "level": level,
            "operator": None,
            "reason": None,
            "timestamp": beijing_now().isoformat(),
        }]
        base_details["source_role"] = "system"

        alert = Alert(
            id=uuid4(),
            pregnant_id=pregnant_id,
            trigger_source=trigger_source,
            rule_id=rule_id,
            domain=domain,
            level=level,
            message=message,
            status="PENDING",
            details=base_details,
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
        """从领域分组命中列表批量创建预警（领域级去重）"""
        alerts = []
        for hit in hits:
            alert = AlertService.create_alert(
                db=db,
                pregnant_id=pregnant_id,
                rule_id=hit.get("rule_id", "UNKNOWN"),
                domain=hit.get("domain", ""),
                level=hit.get("level", "YELLOW"),
                message=hit.get("message", ""),
                trigger_source=trigger_source,
                details={
                    "action": hit.get("action", "ALERT_NURSE"),
                    "triggered_rules": hit.get("triggered_rules", []),
                    "created_at": beijing_now().isoformat(),
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
            "analyzed_at": nurse_result.get("analyzed_at", beijing_now().isoformat()),
            "source": "agno_nurse_agent",
        }
        alert.details = details
        db.commit()
        logger.info("Agno预警分析完成: alert_id={}", alert.id)


    @staticmethod
    def repair_details(db: Session) -> int:
        """修复 details 字段格式，使所有预警的 details 结构一致，返回修复条数"""
        from sqlalchemy.orm.attributes import flag_modified

        repaired = 0
        alerts = db.query(Alert).all()
        for alert in alerts:
            details = dict(alert.details or {})  # 拷贝一份，确保 SQLAlchemy 检测变更
            changed = False

            # 补充 source_role
            if "source_role" not in details:
                details["source_role"] = "system"
                changed = True

            # 补充 created_at
            if "created_at" not in details:
                details["created_at"] = alert.created_at.isoformat() if alert.created_at else beijing_now().isoformat()
                changed = True

            # 补充 triggered_rules
            if "triggered_rules" not in details:
                details["triggered_rules"] = [alert.rule_id] if alert.rule_id else []
                changed = True

            # 补充 action（FGR 预警根据 risk_level 推断）
            if "action" not in details:
                risk_level = details.get("risk_level", "")
                action_map = {
                    "critical": "ALERT_DOCTOR",
                    "high": "ALERT_DOCTOR",
                    "medium": "ALERT_NURSE",
                }
                details["action"] = action_map.get(risk_level, "ALERT_NURSE")
                changed = True

            # 初始化 history（如果不存在）
            if "history" not in details:
                details["history"] = [{
                    "seq": 1,
                    "action": "created",
                    "source_role": "system",
                    "level": alert.level,
                    "operator": None,
                    "reason": None,
                    "timestamp": alert.created_at.isoformat() if alert.created_at else beijing_now().isoformat(),
                }]
                changed = True

            if changed:
                alert.details = details
                flag_modified(alert, "details")
                repaired += 1

        if repaired:
            db.commit()
            logger.info(f"共修复 {repaired} 条预警的 details 字段")
        return repaired

    @staticmethod
    def repair_mismatched_alerts(db: Session) -> int:
        """修复 rule_id 与 message/level 不匹配的预警记录，返回修复条数"""
        from ..core.rule_engine import get_rule_message, get_rule_level

        repaired = 0
        alerts = db.query(Alert).all()
        for alert in alerts:
            changed = False
            correct_message = get_rule_message(alert.rule_id)
            correct_level = get_rule_level(alert.rule_id)

            if correct_message and alert.message != correct_message:
                old_msg = alert.message
                alert.message = correct_message
                changed = True
                logger.info(
                    f"修复预警 {alert.id}: rule_id={alert.rule_id}, "
                    f"消息 '{old_msg}' → '{correct_message}'"
                )

            if correct_level and alert.level != correct_level:
                old_level = alert.level
                alert.level = correct_level
                changed = True
                logger.info(
                    f"修复预警 {alert.id}: rule_id={alert.rule_id}, "
                    f"级别 '{old_level}' → '{correct_level}'"
                )

            if changed:
                repaired += 1

        if repaired:
            db.commit()
            logger.info(f"共修复 {repaired} 条不匹配的预警记录")
        return repaired


alert_service = AlertService()
