"""预警服务单元测试 - 去重机制、LLM增强、WebSocket护士端"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4


# ==================== 去重机制测试 ====================

class TestAlertDeduplication:
    """测试预警去重逻辑 — domain-based"""

    def _make_alert(self, **kwargs):
        alert = MagicMock()
        alert.id = kwargs.get("id", uuid4())
        alert.pregnant_id = kwargs.get("pregnant_id", "P001")
        alert.rule_id = kwargs.get("rule_id", "RULE_BP_HIGH")
        alert.domain = kwargs.get("domain", "vital")
        alert.level = kwargs.get("level", "RED")
        alert.message = kwargs.get("message", "血压异常升高")
        alert.status = kwargs.get("status", "PENDING")
        alert.trigger_source = kwargs.get("trigger_source", "RULE_ENGINE")
        alert.details = kwargs.get("details", {})
        alert.created_at = kwargs.get("created_at", datetime.utcnow())
        return alert

    def test_find_duplicate_by_domain_returns_existing(self):
        from app.services.alert_service import AlertService
        existing_alert = self._make_alert()
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = existing_alert
        result = AlertService._find_duplicate(db, "P001", "vital")
        assert result == existing_alert

    def test_find_duplicate_different_domain_returns_none(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = None
        result = AlertService._find_duplicate(db, "P001", "fetal")
        assert result is None

    def test_find_duplicate_returns_none_for_no_domain(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        result = AlertService._find_duplicate(db, "P001", None)
        assert result is None
        db.query.assert_not_called()

    def test_create_alert_skips_domain_duplicate(self):
        from app.services.alert_service import AlertService
        existing_alert = self._make_alert(id=uuid4())
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=existing_alert):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            assert result == existing_alert
            db.add.assert_not_called()

    def test_create_alert_creates_new_when_no_duplicate(self):
        from app.services.alert_service import AlertService
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=None):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            db.add.assert_called_once()
            db.commit.assert_called_once()
            assert result.pregnant_id == "P001"
            assert result.level == "RED"

    def test_create_alert_initializes_history(self):
        """创建预警时初始化 history 时间线"""
        from app.services.alert_service import AlertService
        db = MagicMock()
        with patch.object(AlertService, '_find_duplicate', return_value=None):
            result = AlertService.create_alert(
                db=db, pregnant_id="P001", rule_id="RULE_BP_HIGH",
                domain="vital", level="RED", message="血压异常升高",
            )
            assert "history" in result.details
            assert result.details["history"][0]["action"] == "created"
            assert result.details["history"][0]["source_role"] == "system"
            assert result.details["source_role"] == "system"

    def test_create_alerts_from_hits_uses_domain(self):
        from app.services.alert_service import AlertService
        hits = [
            {"rule_id": "RULE_BP_HIGH", "domain": "vital", "level": "RED",
             "message": "血压异常", "action": "ALERT_NURSE_AND_DOCTOR",
             "triggered_rules": ["RULE_BP_HIGH"], "priority": 3},
            {"rule_id": "RULE_FETAL_DROP", "domain": "fetal", "level": "RED",
             "message": "胎动减少", "action": "ALERT_NURSE_AND_DOCTOR",
             "triggered_rules": ["RULE_FETAL_DROP"], "priority": 3},
        ]
        db = MagicMock()
        existing = self._make_alert()

        def mock_find_dup(db, pid, domain):
            return existing if domain == "vital" else None

        with patch.object(AlertService, '_find_duplicate', side_effect=mock_find_dup):
            results = AlertService.create_alerts_from_hits(db, "P001", hits)
            assert len(results) == 2
            assert results[0] == existing
            assert results[1].rule_id == "RULE_FETAL_DROP"


# ==================== WebSocket 护士端测试 ====================

class TestWebSocketManagerNurse:

    @pytest.fixture
    def ws_manager(self):
        from app.core.websocket_manager import WebSocketManager
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_connect_nurse(self, ws_manager):
        websocket = AsyncMock()
        await ws_manager.connect_nurse(websocket, "nurse-1")
        assert "nurse-1" in ws_manager.nurse_connections
        assert ws_manager.get_active_connections_count() == 1

    @pytest.mark.asyncio
    async def test_disconnect_nurse(self, ws_manager):
        websocket = AsyncMock()
        await ws_manager.connect_nurse(websocket, "nurse-1")
        ws_manager.disconnect_nurse("nurse-1")
        assert "nurse-1" not in ws_manager.nurse_connections
        assert ws_manager.get_active_connections_count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_nurse_nonexistent(self, ws_manager):
        ws_manager.disconnect_nurse("nonexistent")
        assert ws_manager.get_active_connections_count() == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_both_doctor_and_nurse(self, ws_manager):
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        alert_data = {"id": "alert-1", "message": "测试预警"}
        await ws_manager.broadcast_alert(alert_data)

        doctor_ws.send_json.assert_called_once_with({"type": "NEW_ALERT", "data": alert_data})
        nurse_ws.send_json.assert_called_once_with({"type": "NEW_ALERT", "data": alert_data})

    @pytest.mark.asyncio
    async def test_broadcast_nurse_failure_cleans_up(self, ws_manager):
        doctor_ws = AsyncMock()
        nurse_ws = AsyncMock()
        nurse_ws.send_json.side_effect = Exception("Connection closed")
        await ws_manager.connect(doctor_ws, "doctor-1")
        await ws_manager.connect_nurse(nurse_ws, "nurse-1")

        await ws_manager.broadcast_alert({"id": "a1"})

        assert "nurse-1" not in ws_manager.nurse_connections
        assert "doctor-1" in ws_manager.active_connections
        assert ws_manager.get_active_connections_count() == 1

    @pytest.mark.asyncio
    async def test_connect_nurse_replaces_old_connection(self, ws_manager):
        old_ws = AsyncMock()
        new_ws = AsyncMock()
        await ws_manager.connect_nurse(old_ws, "nurse-1")
        await ws_manager.connect_nurse(new_ws, "nurse-1")
        assert ws_manager.nurse_connections["nurse-1"] == new_ws
        old_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_total_connections_count(self, ws_manager):
        await ws_manager.connect(AsyncMock(), "doctor-1")
        await ws_manager.connect_nurse(AsyncMock(), "nurse-1")
        await ws_manager.connect_nurse(AsyncMock(), "nurse-2")
        assert ws_manager.get_active_connections_count() == 3


# ==================== LLM 预警分析测试 ====================

class TestAlertLLMEnrichment:

    @pytest.mark.asyncio
    async def test_enrich_alert_stores_workflow_analysis(self):
        from app.services.alert_service import AlertService

        alert = MagicMock()
        alert.id = uuid4()
        alert.pregnant_id = "P001"
        alert.rule_id = "RULE_BP_HIGH"
        alert.level = "RED"
        alert.message = "血压异常升高"
        alert.details = {}

        pregnant = MagicMock()
        pregnant.display_name = "测试孕妇"
        pregnant.gestational_age_days = 224
        pregnant.risk_tags = ["高血压"]

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [alert, pregnant]

        workflow_result = {
            "workflow": "alert_analysis",
            "workflow_output": "综合分析结果",
            "steps": [
                {"role": "nurse", "summary": "血压持续升高", "nursing_suggestions": "立即测量血压", "analyzed_at": "2026-01-01T00:00:00"},
            ],
        }

        with patch("app.database.SessionLocal", return_value=mock_session), \
             patch(
                "app.services.alert_analysis_service.alert_analysis_service.run_alert_workflow",
                new=AsyncMock(return_value=workflow_result),
             ):
            await AlertService.enrich_alert_with_llm(alert.id, "P001")

            assert "llm_analysis" in alert.details
            assert alert.details["llm_analysis"]["source"] == "agno_workflow"
            assert "血压持续升高" in alert.details["llm_analysis"]["risk_interpretation"]
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_alert_handles_workflow_failure(self):
        from app.services.alert_service import AlertService

        alert = MagicMock()
        alert.id = uuid4()
        alert.details = {}

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [alert, MagicMock()]

        with patch("app.database.SessionLocal", return_value=mock_session), \
             patch(
                "app.services.alert_analysis_service.alert_analysis_service.run_alert_workflow",
                new=AsyncMock(side_effect=Exception("Workflow failed")),
             ):
            await AlertService.enrich_alert_with_llm(alert.id, "P001")
            assert "llm_analysis" not in alert.details
            mock_session.close.assert_called_once()
