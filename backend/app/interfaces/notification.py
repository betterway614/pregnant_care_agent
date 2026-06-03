"""
通知服务接口 — 替代对 ws_manager 的直接依赖

遵循 DIP: 路由层和警报服务依赖此抽象，而非 WebSocketManager 具体实现。
"""
from __future__ import annotations

from typing import Protocol


class NotificationService(Protocol):
    """通知服务抽象"""

    async def send_alert_to_doctor(self, doctor_id: str, alert_data: dict) -> None:
        """向指定医生发送预警通知"""
        ...

    async def broadcast_alert(self, alert_data: dict) -> None:
        """向所有在线医生广播预警"""
        ...

    async def route_alert(self, level: str, alert_data: dict) -> None:
        """按预警等级路由通知"""
        ...
