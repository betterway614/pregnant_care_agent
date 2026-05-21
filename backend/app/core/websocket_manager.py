"""WebSocket 连接管理器"""
from fastapi import WebSocket
from typing import Dict
from loguru import logger


class WebSocketManager:
    """管理医生端和护士端的 WebSocket 连接"""

    def __init__(self):
        # 存储活跃的连接: {doctor_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # 护士端连接: {nurse_id: websocket}
        self.nurse_connections: Dict[str, WebSocket] = {}

    # ==================== 医生端 ====================

    async def connect(self, websocket: WebSocket, doctor_id: str):
        """接受新的 WebSocket 连接"""
        if doctor_id in self.active_connections:
            old_ws = self.active_connections.pop(doctor_id)
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
        """发送预警给指定医生"""
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
            self.disconnect(doctor_id)
            return False

    # ==================== 护士端 ====================

    async def connect_nurse(self, websocket: WebSocket, nurse_id: str):
        """接受护士端 WebSocket 连接"""
        if nurse_id in self.nurse_connections:
            old_ws = self.nurse_connections.pop(nurse_id)
            try:
                await old_ws.close()
                logger.info(f"护士 {nurse_id} 的旧连接已关闭")
            except Exception as e:
                logger.warning(f"关闭护士 {nurse_id} 的旧连接失败: {e}")

        await websocket.accept()
        self.nurse_connections[nurse_id] = websocket
        logger.info(f"护士 {nurse_id} 已连接 WebSocket")

    def disconnect_nurse(self, nurse_id: str):
        """断开护士端 WebSocket 连接"""
        if nurse_id in self.nurse_connections:
            del self.nurse_connections[nurse_id]
            logger.info(f"护士 {nurse_id} 已断开 WebSocket")

    # ==================== 广播 ====================

    async def broadcast_alert(self, alert_data: dict):
        """广播预警给所有在线的医生和护士"""
        if not self.active_connections and not self.nurse_connections:
            logger.info("没有医护人员在线，跳过广播")
            return

        disconnected_doctors = []
        for doctor_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
                logger.info(f"已广播预警给医生 {doctor_id}")
            except Exception as e:
                logger.error(f"广播预警给医生 {doctor_id} 失败: {e}")
                disconnected_doctors.append(doctor_id)

        for doctor_id in disconnected_doctors:
            self.disconnect(doctor_id)

        disconnected_nurses = []
        for nurse_id, websocket in self.nurse_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
                logger.info(f"已广播预警给护士 {nurse_id}")
            except Exception as e:
                logger.error(f"广播预警给护士 {nurse_id} 失败: {e}")
                disconnected_nurses.append(nurse_id)

        for nurse_id in disconnected_nurses:
            self.disconnect_nurse(nurse_id)

        total = len(self.active_connections) + len(self.nurse_connections)
        logger.info(f"预警广播完成，成功发送给 {total} 位医护人员")

    def get_active_connections_count(self) -> int:
        """获取活跃连接数（医生+护士）"""
        return len(self.active_connections) + len(self.nurse_connections)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()
