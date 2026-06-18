"""
SQLAlchemy 仓储实现 — 将 ORM 操作封装在仓储接口之后

遵循 DIP: 这些实现对接 interfaces/ 中定义的 Protocol，
工具模块通过 run_context.dependencies 获取仓储实例，
而非直接导入 SessionLocal 和 ORM 模型。
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from loguru import logger

from ...utils.timezone import beijing_now


class SqlAlchemyPatientRepo:
    """患者仓储 — SQLAlchemy 实现"""

    def get_by_id(self, patient_id: str) -> Optional[dict]:
        from ...database import SessionLocal
        from ...models import Pregnant

        db = SessionLocal()
        try:
            p = db.query(Pregnant).filter(Pregnant.pregnant_id == patient_id).first()
            if not p:
                return None
            from ..patient_context_service import compute_gestational_days
            gest_days = compute_gestational_days(p)
            return {
                "pregnant_id": p.pregnant_id,
                "display_name": p.display_name,
                "nickname": p.nickname,
                "gestational_week": f"{gest_days // 7}+{gest_days % 7}",
                "gest_week": gest_days // 7,
                "risk_tags": p.risk_tags or [],
            }
        finally:
            db.close()

    def get_recent_health_data(self, patient_id: str, days: int = 7) -> list[dict]:
        from ...database import SessionLocal
        from ...models import HealthDataPoint

        db = SessionLocal()
        try:
            cutoff = beijing_now() - timedelta(days=days)
            records = db.query(HealthDataPoint).filter(
                HealthDataPoint.pregnant_id == patient_id,
                HealthDataPoint.recorded_at >= cutoff,
            ).order_by(HealthDataPoint.recorded_at.desc()).limit(20).all()
            return [
                {"metric": r.metric_code, "value": r.value, "unit": r.unit,
                 "recorded_at": str(r.recorded_at)}
                for r in records
            ]
        finally:
            db.close()

    def get_active_alerts(self, patient_id: str) -> list[dict]:
        from ...database import SessionLocal
        from ...models import Alert

        db = SessionLocal()
        try:
            alerts = db.query(Alert).filter(
                Alert.pregnant_id == patient_id,
                Alert.status.in_(["PENDING", "ESCALATED"]),
            ).all()
            return [
                {"level": a.level, "message": a.message, "status": a.status}
                for a in alerts
            ]
        finally:
            db.close()

    def save_health_metrics(self, pregnant_id: str, metrics: dict[str, float], source: str = "CHAT") -> list[str]:
        from ...database import SessionLocal
        from ...models import HealthDataPoint

        metric_map = {
            "weight": ("weight", "kg"), "sbp": ("systolic", "mmHg"),
            "dbp": ("diastolic", "mmHg"), "fetal_movement": ("fetal_movement", "次/小时"),
            "blood_sugar": ("blood_sugar", "mmol/L"), "heart_rate": ("heart_rate", "bpm"),
            "sleep_hours": ("sleep_hours", "小时"), "steps": ("steps", "步"),
        }
        saved = []
        db = SessionLocal()
        try:
            for key, value in metrics.items():
                if value and value > 0 and key in metric_map:
                    code, unit = metric_map[key]
                    point = HealthDataPoint(
                        pregnant_id=pregnant_id, metric_code=code,
                        value=float(value), unit=unit, source="AGENT_REPORT",
                    )
                    db.add(point)
                    saved.append(key)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("健康数据保存失败 pregnant_id=%s metrics=%s", pregnant_id, saved, exc_info=True)
        finally:
            db.close()
        return saved


class SqlAlchemyAlertRepo:
    """预警仓储 — SQLAlchemy 实现"""

    def create(self, pregnant_id: str, rule_id: str, domain: str,
               level: str, message: str, trigger_source: str = "RULE_ENGINE",
               details: Optional[dict] = None) -> dict:
        from ...database import SessionLocal
        from ...models import Alert
        from uuid import uuid4

        db = SessionLocal()
        try:
            existing = db.query(Alert).filter(
                Alert.pregnant_id == pregnant_id,
                Alert.domain == domain,
                Alert.status.in_(["PENDING", "ESCALATED"]),
            ).first()
            if existing:
                return {"id": str(existing.id), "status": "duplicate_skipped"}

            alert = Alert(
                id=uuid4(), pregnant_id=pregnant_id, rule_id=rule_id,
                domain=domain, level=level, message=message,
                trigger_source=trigger_source, details=details or {},
                status="PENDING",
            )
            db.add(alert)
            db.commit()
            return {"id": str(alert.id), "status": "created"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def find_duplicate(self, pregnant_id: str, domain: str) -> Optional[dict]:
        from ...database import SessionLocal
        from ...models import Alert

        db = SessionLocal()
        try:
            existing = db.query(Alert).filter(
                Alert.pregnant_id == pregnant_id,
                Alert.domain == domain,
                Alert.status.in_(["PENDING", "ESCALATED"]),
            ).first()
            if existing:
                return {"id": str(existing.id), "level": existing.level, "status": existing.status}
            return None
        finally:
            db.close()

    def update_details(self, alert_id: str, details: dict) -> bool:
        from ...database import SessionLocal
        from ...models import Alert
        from sqlalchemy.orm.attributes import flag_modified

        db = SessionLocal()
        try:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if not alert:
                return False
            alert.details = details
            flag_modified(alert, "details")
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()


class SqlAlchemyFollowUpRepo:
    """随访记录仓储 — SQLAlchemy 实现"""

    def get_by_id(self, record_id: str) -> Optional[dict]:
        from ...database import SessionLocal
        from ...models import FollowUpRecord

        db = SessionLocal()
        try:
            r = db.query(FollowUpRecord).filter(FollowUpRecord.id == record_id).first()
            if not r:
                return None
            return {
                "id": str(r.id), "pregnant_id": r.pregnant_id,
                "status": r.status, "gestational_week": r.gestational_week,
                "chief_complaint": r.chief_complaint, "summary": r.summary,
            }
        finally:
            db.close()

    def update_status(self, record_id: str, new_status: str) -> bool:
        from ...database import SessionLocal
        from ...models import FollowUpRecord

        db = SessionLocal()
        try:
            r = db.query(FollowUpRecord).filter(FollowUpRecord.id == record_id).first()
            if not r:
                return False
            r.status = new_status
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def save_answers(self, record_id: str, answers: dict) -> bool:
        from ...database import SessionLocal
        from ...models import FollowUpRecord
        from sqlalchemy.orm.attributes import flag_modified

        db = SessionLocal()
        try:
            r = db.query(FollowUpRecord).filter(FollowUpRecord.id == record_id).first()
            if not r:
                return False
            if r.answers is None:
                r.answers = {}
            r.answers.update(answers)
            flag_modified(r, "answers")
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()
