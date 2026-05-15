"""WebSocket Manager 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.websocket_manager import WebSocketManager


@pytest.fixture
def ws_manager():
    """创建 WebSocket Manager 实例"""
    return WebSocketManager()


@pytest.mark.asyncio
async def test_connect(ws_manager):
    """测试连接注册"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    assert ws_manager.get_active_connections_count() == 1
    assert "doctor-1" in ws_manager.active_connections


@pytest.mark.asyncio
async def test_disconnect(ws_manager):
    """测试断开连接"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    ws_manager.disconnect("doctor-1")
    assert ws_manager.get_active_connections_count() == 0
    assert "doctor-1" not in ws_manager.active_connections


@pytest.mark.asyncio
async def test_disconnect_nonexistent(ws_manager):
    """测试断开不存在的连接"""
    # 不应该抛出异常
    ws_manager.disconnect("nonexistent")
    assert ws_manager.get_active_connections_count() == 0


@pytest.mark.asyncio
async def test_send_alert_to_doctor_success(ws_manager):
    """测试发送预警给指定医生成功"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")

    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("doctor-1", alert_data)

    assert result is True
    websocket.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })


@pytest.mark.asyncio
async def test_send_alert_to_doctor_not_found(ws_manager):
    """测试发送预警给不存在的医生"""
    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("nonexistent", alert_data)

    assert result is False


@pytest.mark.asyncio
async def test_send_alert_to_doctor_failure(ws_manager):
    """测试发送预警失败时清理连接"""
    websocket = AsyncMock()
    websocket.send_json.side_effect = Exception("Connection closed")
    await ws_manager.connect(websocket, "doctor-1")

    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("doctor-1", alert_data)

    assert result is False
    assert ws_manager.get_active_connections_count() == 0


@pytest.mark.asyncio
async def test_broadcast_alert(ws_manager):
    """测试广播预警给所有连接的医生"""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    await ws_manager.connect(websocket1, "doctor-1")
    await ws_manager.connect(websocket2, "doctor-2")

    alert_data = {"id": "alert-1", "message": "测试预警"}
    await ws_manager.broadcast_alert(alert_data)

    websocket1.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })
    websocket2.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })


@pytest.mark.asyncio
async def test_broadcast_alert_with_failure(ws_manager):
    """测试广播时部分连接失败"""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    websocket2.send_json.side_effect = Exception("Connection closed")
    await ws_manager.connect(websocket1, "doctor-1")
    await ws_manager.connect(websocket2, "doctor-2")

    alert_data = {"id": "alert-1", "message": "测试预警"}
    await ws_manager.broadcast_alert(alert_data)

    # doctor-1 应该收到
    websocket1.send_json.assert_called_once()
    # doctor-2 应该被清理
    assert ws_manager.get_active_connections_count() == 1
    assert "doctor-2" not in ws_manager.active_connections


@pytest.mark.asyncio
async def test_get_active_connections_count(ws_manager):
    """测试获取活跃连接数"""
    assert ws_manager.get_active_connections_count() == 0

    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    await ws_manager.connect(websocket1, "doctor-1")
    assert ws_manager.get_active_connections_count() == 1

    await ws_manager.connect(websocket2, "doctor-2")
    assert ws_manager.get_active_connections_count() == 2

    ws_manager.disconnect("doctor-1")
    assert ws_manager.get_active_connections_count() == 1
