"""
警报审核动作注册表 — 替代 review_alert 中的 9-branch if/elif 链

遵循 OCP: 新增审核动作只需定义类并调用 register_action()，
无需修改 review_alert 函数。
"""
from __future__ import annotations

from typing import Optional, Protocol
from loguru import logger


class AlertActionHandler(Protocol):
    """警报动作处理协议"""

    def execute(self, alert, payload: dict, db) -> dict:
        """执行审核动作

        Args:
            alert: Alert ORM 实例
            payload: 请求体 dict（含 action, reason, target_level 等）
            db: SQLAlchemy Session

        Returns:
            dict: {"new_status": str, "new_level": str, "message": str}
        """
        ...


_registry: dict[str, AlertActionHandler] = {}


def register_action(name: str, handler: AlertActionHandler) -> None:
    """注册警报审核动作"""
    _registry[name] = handler
    logger.debug("注册警报动作: {}", name)


def get_action(name: str) -> Optional[AlertActionHandler]:
    """获取动作处理器"""
    return _registry.get(name)


def list_actions() -> list[str]:
    """列出所有已注册的动作"""
    return list(_registry.keys())


# ==================== 内置动作实现 ====================


class ConfirmAction:
    """确认预警 — 医生/护士确认预警有效"""

    def execute(self, alert, payload: dict, db) -> dict:
        alert.status = "confirmed"
        alert.reviewed_by = payload.get("operator", "doctor")
        return {"new_status": "confirmed", "message": "预警已确认"}


class DismissAction:
    """驳回预警 — 医生/护士认为预警无效"""

    def execute(self, alert, payload: dict, db) -> dict:
        alert.status = "dismissed"
        alert.reviewed_by = payload.get("operator", "doctor")
        return {"new_status": "dismissed", "message": "预警已驳回"}


class EscalateAction:
    """升级预警 — 医生直接升级到目标等级"""

    LEVEL_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

    def execute(self, alert, payload: dict, db) -> dict:
        current = self.LEVEL_ORDER.get(alert.level, 0)
        target = payload.get("target_level", "red")
        target_ord = self.LEVEL_ORDER.get(target, 3)
        if target_ord <= current:
            return {"new_level": alert.level, "message": "目标等级需高于当前等级"}
        alert.level = target
        return {"new_level": target, "message": f"预警已升级至 {target}"}


class DowngradeAction:
    """降级预警 — 医生降低预警等级"""

    LEVEL_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

    def execute(self, alert, payload: dict, db) -> dict:
        current = self.LEVEL_ORDER.get(alert.level, 0)
        target = payload.get("target_level", "yellow")
        target_ord = self.LEVEL_ORDER.get(target, 1)
        if target_ord >= current:
            return {"new_level": alert.level, "message": "目标等级需低于当前等级"}
        alert.level = target
        return {"new_level": target, "message": f"预警已降级至 {target}"}


class SupplementAction:
    """补充预警信息"""

    def execute(self, alert, payload: dict, db) -> dict:
        supplement = payload.get("supplement", "")
        if supplement:
            if alert.details is None:
                alert.details = {}
            alert.details["supplement"] = supplement
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(alert, "details")
        return {"new_status": alert.status, "message": "已补充信息"}


class NurseConfirmAction:
    """护士确认预警"""

    def execute(self, alert, payload: dict, db) -> dict:
        alert.status = "confirmed"
        alert.reviewed_by = payload.get("operator", "nurse")
        return {"new_status": "confirmed", "message": "护士已确认预警"}


class NurseDismissAction:
    """护士驳回预警（需医生复核）"""

    def execute(self, alert, payload: dict, db) -> dict:
        alert.status = "pending_doctor_review"
        alert.reviewed_by = payload.get("operator", "nurse")
        return {"new_status": "pending_doctor_review", "message": "护士已驳回，等待医生复核"}


class NurseEscalateAction:
    """护士逐级升级（YELLOW→ORANGE→RED）"""

    LEVEL_STEPS = {"YELLOW": "ORANGE", "ORANGE": "RED"}

    def execute(self, alert, payload: dict, db) -> dict:
        next_level = self.LEVEL_STEPS.get(alert.level, "red")
        alert.level = next_level
        return {"new_level": next_level, "message": f"护士升级至 {next_level}"}


class NurseAppealAction:
    """护士申诉 — 请求医生重新评估"""

    def execute(self, alert, payload: dict, db) -> dict:
        appeal_reason = payload.get("reason", "")
        if alert.details is None:
            alert.details = {}
        alert.details["appeal_reason"] = appeal_reason
        alert.details["appealed_by"] = payload.get("operator", "nurse")
        alert.status = "pending_doctor_review"
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(alert, "details")
        return {"new_status": "pending_doctor_review", "message": "已提交申诉，等待医生处理"}


# ==================== 注册所有内置动作 ====================

register_action("confirm", ConfirmAction())
register_action("dismiss", DismissAction())
register_action("escalate", EscalateAction())
register_action("downgrade", DowngradeAction())
register_action("supplement", SupplementAction())
register_action("nurse_confirm", NurseConfirmAction())
register_action("nurse_dismiss", NurseDismissAction())
register_action("nurse_escalate", NurseEscalateAction())
register_action("nurse_appeal", NurseAppealAction())
