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

    alert_data = {"id": "alert-1", "message": "测试预警", "action": "created"}
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


class TestRouteAlert:
    """route_alert 分级路由测试"""

    @pytest.fixture
    def ws_manager(self):
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_red_alert_broadcasts_to_all(self, ws_manager):
        """RED 预警广播给医生和护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "RED", "source_role": "system", "message": "血压异常"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_orange_alert_only_nurses(self, ws_manager):
        """ORANGE 预警仅推送给护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "ORANGE", "source_role": "system", "message": "血压偏高"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_yellow_alert_only_nurses(self, ws_manager):
        """YELLOW 预警仅推送给护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "YELLOW", "source_role": "system", "message": "体重缓慢"}
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_doctor_downgrade_only_nurses(self, ws_manager):
        """医生降级仅推护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "YELLOW", "source_role": "doctor", "action": "downgrade",
            "message": "[医生降级] 血压偏高",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_not_called()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_nurse_escalate_broadcasts_all(self, ws_manager):
        """护士升级推全部"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "ORANGE", "source_role": "nurse", "action": "nurse_escalate",
            "message": "[护士升级] 血压偏高需要医生关注",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_nurse_appeal_sends_to_target_doctor(self, ws_manager):
        """护士复议推给目标医生"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "YELLOW", "source_role": "nurse", "action": "nurse_appeal",
            "target_doctor_id": "doctor-1", "message": "[复议] 请重新评估",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_fgr_doctor_alert_only_doctors(self, ws_manager):
        """FGR_ALGORITHM + ALERT_DOCTOR 仅推医生，不推护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "RED",
            "trigger_source": "FGR_ALGORITHM",
            "source_role": "system",
            "action": "created",
            "details": {"action": "ALERT_DOCTOR"},
            "message": "FGR极高风险",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_not_called(), (
            "FGR ALERT_DOCTOR 预警不应推送给护士端"
        )

    @pytest.mark.asyncio
    async def test_fgr_nurse_alert_goes_to_nurses(self, ws_manager):
        """FGR_ALGORITHM + ALERT_NURSE（中风险）正常推给护士"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "YELLOW",
            "trigger_source": "FGR_ALGORITHM",
            "source_role": "system",
            "action": "created",
            "details": {"action": "ALERT_NURSE"},
            "message": "FGR中风险",
        }
        await ws_manager.route_alert(alert_data)

        # FGR ALERT_NURSE 走默认路由：非 RED → 仅推护士
        nurse_ws.send_json.assert_called_once()
        doctor_ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_nurse_confirm_broadcasts_all(self, ws_manager):
        """护士确认 → 通知全员（医生 + 护士）"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "ORANGE",
            "source_role": "nurse",
            "action": "nurse_confirm",
            "message": "血压偏高已确认",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once(), (
            "护士确认后必须通知医生端刷新审核列表"
        )
        nurse_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_nurse_confirm_sends_status_change_type(self, ws_manager):
        """护士确认的消息类型应为 ALERT_STATUS_CHANGE"""
        doctor_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")

        alert_data = {
            "level": "RED",
            "source_role": "nurse",
            "action": "nurse_confirm",
            "message": "高危已确认",
        }
        await ws_manager.route_alert(alert_data)

        call_args = doctor_ws.send_json.call_args[0][0]
        assert call_args["type"] == "ALERT_STATUS_CHANGE", (
            "护士确认应发送 ALERT_STATUS_CHANGE，"
            "医生端据此更新预警状态而非当作新预警"
        )

    @pytest.mark.asyncio
    async def test_broadcast_to_doctors_only(self, ws_manager):
        """_broadcast_to_doctors_only 仅推医生"""
        doctor_ws1 = AsyncMock()
        doctor_ws2 = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws1, "doctor-1")
        await ws_manager.connect(doctor_ws2, "doctor-2")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"level": "RED", "message": "医生专属预警"}
        await ws_manager._broadcast_to_doctors_only(alert_data)

        doctor_ws1.send_json.assert_called_once()
        doctor_ws2.send_json.assert_called_once()
        nurse_ws.send_json.assert_not_called(), (
            "_broadcast_to_doctors_only 不应推送给护士"
        )

    @pytest.mark.asyncio
    async def test_fgr_alert_details_not_dict_still_routes_safely(self, ws_manager):
        """FGR 预警 details 为非 dict 时（异常数据）不崩溃"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "RED",
            "trigger_source": "FGR_ALGORITHM",
            "source_role": "system",
            "action": "created",
            "details": "invalid_string_details",
            "message": "FGR极高风险",
        }
        # 不应抛出异常
        await ws_manager.route_alert(alert_data)

    @pytest.mark.asyncio
    async def test_non_fgr_red_alert_still_broadcasts_all(self, ws_manager):
        """非 FGR 的 RED 预警仍广播全员（回归验证）"""
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {
            "level": "RED",
            "trigger_source": "RULE_ENGINE",
            "source_role": "system",
            "action": "created",
            "details": {"action": "ALERT_NURSE_AND_DOCTOR"},
            "message": "血压异常升高",
        }
        await ws_manager.route_alert(alert_data)

        doctor_ws.send_json.assert_called_once()
        nurse_ws.send_json.assert_called_once(), (
            "非 FGR 的 RED 预警必须仍广播全员"
        )
