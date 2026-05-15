"""WebSocket API 端点"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.websocket_manager import ws_manager
from loguru import logger

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/alerts/{doctor_id}")
async def websocket_alerts(websocket: WebSocket, doctor_id: str):
    """
    医生端 WebSocket 连接端点

    用于接收实时预警推送

    Args:
        websocket: WebSocket 连接
        doctor_id: 医生ID
    """
    await ws_manager.connect(websocket, doctor_id)
    try:
        while True:
            # 保持连接活跃，接收客户端消息
            data = await websocket.receive_text()

            # 处理心跳消息
            if data == "ping":
                await websocket.send_text("pong")
                logger.debug(f"收到来自医生 {doctor_id} 的心跳")

            # 可以处理其他客户端消息
            # 例如：确认收到预警、标记已读等

    except WebSocketDisconnect:
        logger.info(f"医生 {doctor_id} 主动断开 WebSocket 连接")
        ws_manager.disconnect(doctor_id)
    except Exception as e:
        logger.error(f"医生 {doctor_id} WebSocket 连接异常: {e}")
        ws_manager.disconnect(doctor_id)
