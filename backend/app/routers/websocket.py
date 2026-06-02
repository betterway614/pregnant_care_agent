"""WebSocket API 端点"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.websocket_manager import ws_manager
from ..core.auth import decode_token
from loguru import logger

router = APIRouter(tags=["WebSocket"])


def _verify_ws_token(websocket: WebSocket) -> bool:
    """从 query param 校验 WebSocket 的 JWT token"""
    token = websocket.query_params.get("token", "")
    if not token:
        return False
    payload = decode_token(token)
    return payload is not None


@router.websocket("/ws/alerts/{doctor_id}")
async def websocket_alerts(websocket: WebSocket, doctor_id: str):
    """
    医生端 WebSocket 连接端点

    用于接收实时预警推送
    """
    if not _verify_ws_token(websocket):
        await websocket.close(code=4001, reason="认证失败")
        return
    await ws_manager.connect(websocket, doctor_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                logger.debug(f"收到来自医生 {doctor_id} 的心跳")
            else:
                logger.debug(f"收到医生 {doctor_id} 的未知消息: {data}")
    except WebSocketDisconnect:
        logger.info(f"医生 {doctor_id} 主动断开 WebSocket 连接")
        ws_manager.disconnect(doctor_id)
    except Exception as e:
        logger.error(f"医生 {doctor_id} WebSocket 连接异常: {e}")
        ws_manager.disconnect(doctor_id)


@router.websocket("/ws/nurse-alerts/{nurse_id}")
async def websocket_nurse_alerts(websocket: WebSocket, nurse_id: str):
    """
    护士端 WebSocket 连接端点

    用于接收实时预警推送
    """
    if not _verify_ws_token(websocket):
        await websocket.close(code=4001, reason="认证失败")
        return
    await ws_manager.connect_nurse(websocket, nurse_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                logger.debug(f"收到来自护士 {nurse_id} 的心跳")
            else:
                logger.debug(f"收到护士 {nurse_id} 的未知消息: {data}")
    except WebSocketDisconnect:
        logger.info(f"护士 {nurse_id} 主动断开 WebSocket 连接")
        ws_manager.disconnect_nurse(nurse_id)
    except Exception as e:
        logger.error(f"护士 {nurse_id} WebSocket 连接异常: {e}")
        ws_manager.disconnect_nurse(nurse_id)
