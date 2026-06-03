"""
数据仓储接口 — 替代工具函数中对 ORM 模型的直接依赖

遵循 DIP: 高层模块（工具、服务）依赖这些抽象，
而非直接依赖 SQLAlchemy Session 和 ORM 模型。
"""
from __future__ import annotations

from typing import Optional, Protocol


class PatientRepository(Protocol):
    """患者数据仓储抽象"""

    def get_by_id(self, patient_id: str) -> Optional[dict]:
        """获取患者基本信息，返回 dict 或 None"""
        ...

    def get_recent_health_data(self, patient_id: str, days: int = 7) -> list[dict]:
        """获取近 N 天健康数据"""
        ...

    def get_active_alerts(self, patient_id: str) -> list[dict]:
        """获取活跃预警列表"""
        ...

    def save_health_metrics(self, pregnant_id: str, metrics: dict[str, float], source: str = "CHAT") -> list[str]:
        """保存健康指标，返回已保存的指标名列表"""
        ...


class AlertRepository(Protocol):
    """预警数据仓储抽象"""

    def create(
        self,
        pregnant_id: str,
        rule_id: str,
        domain: str,
        level: str,
        message: str,
        trigger_source: str = "RULE_ENGINE",
        details: Optional[dict] = None,
    ) -> dict:
        """创建预警（含去重），返回预警 dict"""
        ...

    def find_duplicate(self, pregnant_id: str, domain: str) -> Optional[dict]:
        """查找同域重复预警"""
        ...

    def update_details(self, alert_id: str, details: dict) -> bool:
        """更新预警详情"""
        ...


class FollowUpRepository(Protocol):
    """随访记录仓储抽象"""

    def get_by_id(self, record_id: str) -> Optional[dict]:
        """获取随访记录"""
        ...

    def update_status(self, record_id: str, new_status: str) -> bool:
        """更新随访状态"""
        ...

    def save_answers(self, record_id: str, answers: dict) -> bool:
        """保存随访回答"""
        ...
