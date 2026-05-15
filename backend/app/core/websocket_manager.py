"""WebSocket 连接管理器"""
from fastapi import WebSocket
from typing import Dict
from loguru import logger


class WebSocketManager:
    """管理医生端的 WebSocket 连接"""

    def __init__(self):
        # 存储活跃的连接: {doctor_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, doctor_id: str):
        """接受新的 WebSocket 连接"""
        # 如果医生已连接，先关闭旧连接
        if doctor_id in self.active_connections:
            old_ws = self.active_connections.pop(doctor_id)  # 先从字典移除
            try:
                await old_ws.close()
                logger.info(f"医生 {doctor_id} 的旧连接已关闭")
            except Exception as e:
                logger.warning(f"关闭医生 {doctor_id} 的旧连接失败: {e}")

        await websocket.accept()
        self.active_connections[doctor_id] = websocket
        logger.info(f"医生 {doctor_id} 已连接 WebSocket")

    def disconnect(self, doctor_id: str):
        """断开 WebSocket 连接"""
        if doctor_id in self.active_connections:
            del self.active_connections[doctor_id]
            logger.info(f"医生 {doctor_id} 已断开 WebSocket")

    async def send_alert_to_doctor(self, doctor_id: str, alert_data: dict) -> bool:
        """发送预警给指定医生

        Args:
            doctor_id: 医生ID
            alert_data: 预警数据

        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        if doctor_id not in self.active_connections:
            logger.warning(f"医生 {doctor_id} 未连接，无法发送预警")
            return False

        websocket = self.active_connections[doctor_id]
        try:
            await websocket.send_json({
                "type": "NEW_ALERT",
                "data": alert_data
            })
            logger.info(f"已发送预警给医生 {doctor_id}")
            return True
        except Exception as e:
            logger.error(f"发送预警给医生 {doctor_id} 失败: {e}")
            # 清理断开的连接
            self.disconnect(doctor_id)
            return False

    async def broadcast_alert(self, alert_data: dict):
        """广播预警给所有连接的医生

        Args:
            alert_data: 预警数据
        """
        if not self.active_connections:
            logger.info("没有医生在线，跳过广播")
            return

        disconnected = []
        for doctor_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
                logger.info(f"已广播预警给医生 {doctor_id}")
            except Exception as e:
                logger.error(f"广播预警给医生 {doctor_id} 失败: {e}")
                disconnected.append(doctor_id)

        # 清理断开的连接
        for doctor_id in disconnected:
            self.disconnect(doctor_id)

        logger.info(f"预警广播完成，成功发送给 {len(self.active_connections)} 位医生")

    def get_active_connections_count(self) -> int:
        """获取活跃连接数"""
        return len(self.active_connections)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()
