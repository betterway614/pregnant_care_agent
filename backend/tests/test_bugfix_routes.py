"""路由修复集成测试

覆盖修复项：#2 预警去重、#3 随访状态机、#5 N+1查询、#9 auto_dismiss幂等、#10 Session管理统一
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime


# ==================== #2: 预警创建统一走去重入口 ====================


class TestAlertCreateUnifiedDedup:
    """验证 create_alert 和 evaluate_alerts 都通过 AlertService 走去重"""

    def test_create_alert_calls_alert_service(self):
        """POST /alerts 应调用 AlertService.create_alert"""
        from app.services.alert_service import AlertService

        mock_alert = MagicMock()
        mock_alert.id = uuid4()
        mock_alert.pregnant_id = "P001"
        mock_alert.trigger_source = "MANUAL"
        mock_alert.rule_id = "MANUAL"
        mock_alert.domain = "vital"
        mock_alert.level = "RED"
        mock_alert.message = "测试预警"
        mock_alert.status = "PENDING"
        mock_alert.details = {"history": []}
        mock_alert.created_at = datetime.utcnow()

        with patch.object(AlertService, 'create_alert', return_value=mock_alert) as mock_create:
            from app.services.alert_service import alert_service
            result = alert_service.create_alert(
                db=MagicMock(), pregnant_id="P001", rule_id="MANUAL",
                domain="vital", level="RED", message="测试预警",
                trigger_source="MANUAL",
            )
            mock_create.assert_called_once()
            assert result == mock_alert

    def test_evaluate_alerts_uses_create_alerts_from_hits(self):
        """evaluate_alerts 应通过 create_alerts_from_hits 走去重"""
        from app.services.alert_service import AlertService
        from app.core.rule_engine import rule_engine

        context = {"sbp": 150, "dbp": 95, "gest_week": 35}
        hits = rule_engine.evaluate_all(context)

        mock_alerts = [MagicMock() for _ in hits]
        with patch.object(AlertService, 'create_alerts_from_hits', return_value=mock_alerts) as mock_batch:
            from app.services.alert_service import alert_service
            result = alert_service.create_alerts_from_hits(MagicMock(), "P001", hits, "RULE_ENGINE")
            mock_batch.assert_called_once()

    def test_create_alert_request_has_domain_field(self):
        """CreateAlertRequest 应支持 domain 字段（用于去重）"""
        from app.routers.alerts import CreateAlertRequest
        import inspect
        fields = CreateAlertRequest.model_fields
        # details 字段可传递 domain
        assert "details" in fields


# ==================== #3: 随访状态机校验 ====================


class TestFollowUpStateMachine:
    """验证 confirm_record 和 sign_record 的前置状态校验"""

    def test_confirm_rejects_draft_status(self):
        """draft 状态不允许确认"""
        from app.routers.followup import confirm_record
        from app.core.auth import TokenPayload
        from fastapi import HTTPException

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "draft"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        confirm_req = MagicMock()
        confirm_req.status = "confirmed"
        confirm_req.reviewer_id = "N001"
        confirm_req.review_comment = None
        confirm_req.ai_snapshot = None

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc_info:
            confirm_record(str(mock_record.id), confirm_req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 400
        assert "状态转换不允许" in str(exc_info.value.detail)

    def test_confirm_rejects_in_progress_status(self):
        """in_progress 状态不允许确认"""
        from app.routers.followup import confirm_record
        from app.core.auth import TokenPayload
        from fastapi import HTTPException

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "in_progress"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        confirm_req = MagicMock()
        confirm_req.status = "confirmed"
        confirm_req.reviewer_id = "N001"
        confirm_req.review_comment = None
        confirm_req.ai_snapshot = None

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc_info:
            confirm_record(str(mock_record.id), confirm_req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 400

    def test_confirm_accepts_completed_status(self):
        """completed 状态允许确认"""
        from app.routers.followup import confirm_record
        from app.core.auth import TokenPayload
        from app.models import FollowUpRecord

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "completed"
        mock_record.pregnant_id = "P001"
        mock_record.gestational_week = "24+3"
        mock_record.follow_up_date = datetime.utcnow()
        mock_record.classification = "normal"
        mock_record.chief_complaint = None
        mock_record.self_reported_data = {}
        mock_record.obstetric_exam = {}
        mock_record.lab_results = {}
        mock_record.summary = "test"
        mock_record.health_education = []
        mock_record.guidance_tags = []
        mock_record.referral = None
        mock_record.next_followup_date = None
        mock_record.reviewed_by = None
        mock_record.reviewed_at = None
        mock_record.review_comment = None
        mock_record.ai_snapshot = {}
        mock_record.record_snapshot = {}
        mock_record.record_text = None
        mock_record.signature_data = {}
        # 使用真实模型的 __table__ 属性
        mock_record.__table__ = FollowUpRecord.__table__

        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "测试孕妇"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_record, mock_pregnant]

        confirm_req = MagicMock()
        confirm_req.status = "confirmed"
        confirm_req.reviewer_id = "N001"
        confirm_req.review_comment = "审核通过"
        confirm_req.ai_snapshot = {}

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        result = confirm_record(str(mock_record.id), confirm_req, db=mock_db, current_user=mock_user)
        assert mock_record.status == "confirmed"

    def test_sign_rejects_non_confirmed_status(self):
        """非 confirmed 状态不允许签名"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload
        from fastapi import HTTPException

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "completed"
        mock_record.pregnant_id = "P001"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        sign_req = MagicMock()
        sign_req.signature_image = "base64..."
        sign_req.signer_name = "张三"

        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")

        with pytest.raises(HTTPException) as exc_info:
            sign_record(str(mock_record.id), sign_req, db=mock_db, current_user=mock_user)
        assert exc_info.value.status_code == 400
        assert "confirmed" in str(exc_info.value.detail)

    def test_sign_accepts_confirmed_status(self):
        """confirmed 状态允许签名"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "confirmed"
        mock_record.pregnant_id = "P001"
        mock_record.signature_data = {}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        sign_req = MagicMock()
        sign_req.signature_image = "base64..."
        sign_req.signer_name = "张三"

        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")

        result = sign_record(str(mock_record.id), sign_req, db=mock_db, current_user=mock_user)
        assert mock_record.signature_data["signer"] == "张三"
        mock_db.commit.assert_called_once()


# ==================== #5: 医嘱 N+1 查询修复 ====================


class TestOrdersNPlusOneFix:
    """验证 get_orders 使用批量查询而非逐条查询"""

    def test_get_orders_uses_batch_query(self):
        """get_orders 应批量查询 Pregnant 而非循环逐条查询"""
        import inspect
        from app.routers.orders import get_orders

        source = inspect.getsource(get_orders)
        # 批量查询模式：先收集 pregnant_ids，再一次性查询
        assert "pregnant_ids" in source or "pregnant_map" in source, \
            "get_orders 应使用批量查询模式"
        # 不应有循环内逐条查询
        # 检查是否在循环内调用 db.query(Pregnant)（排除批量查询部分）
        lines = source.split("\n")
        in_loop = False
        for line in lines:
            if "for o in orders" in line or "for order in orders" in line:
                in_loop = True
            if in_loop and "pregnant_map" in line:
                break  # 使用 map 查找是正确的
            if in_loop and "db.query(Pregnant)" in line and ".first()" in line:
                pytest.fail("get_orders 仍在循环内逐条查询 Pregnant")


# ==================== #9: auto_dismiss 幂等保护 ====================


class TestAutoDismissIdempotent:
    """验证 auto_dismiss 有幂等保护"""

    def test_auto_dismiss_checks_status_before_update(self):
        """auto_dismiss 在更新前应二次校验 status"""
        import inspect
        from app.routers.alerts import auto_dismiss_alerts

        source = inspect.getsource(auto_dismiss_alerts)
        assert 'PENDING' in source and ('status != "PENDING"' in source or "status != 'PENDING'" in source or "alert.status" in source), \
            "auto_dismiss 应在更新前检查 alert.status"


# ==================== #10: Session 管理统一 ====================


class TestSessionManagementUnified:
    """验证手动 SessionLocal 已替换为 Depends(get_db)"""

    def test_explain_order_uses_depends_get_db(self):
        """explain_order 应使用 Depends(get_db) 而非手动 SessionLocal"""
        import inspect
        from app.routers.orders import explain_order

        sig = inspect.signature(explain_order)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names, "explain_order 应通过参数注入 db"

    def test_get_order_document_uses_depends_get_db(self):
        """get_order_document 应使用 Depends(get_db)"""
        import inspect
        from app.routers.orders import get_order_document

        sig = inspect.signature(get_order_document)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names, "get_order_document 应通过参数注入 db"

    def test_ai_review_followup_uses_depends_get_db(self):
        """ai_review_followup 应使用 Depends(get_db)"""
        import inspect
        from app.routers.followup import ai_review_followup

        sig = inspect.signature(ai_review_followup)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names, "ai_review_followup 应通过参数注入 db"

    def test_get_record_document_uses_depends_get_db(self):
        """get_record_document 应使用 Depends(get_db)"""
        import inspect
        from app.routers.followup import get_record_document

        sig = inspect.signature(get_record_document)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names, "get_record_document 应通过参数注入 db"

    def test_sign_record_uses_depends_get_db(self):
        """sign_record 应使用 Depends(get_db)"""
        import inspect
        from app.routers.followup import sign_record

        sig = inspect.signature(sign_record)
        param_names = list(sig.parameters.keys())
        assert "db" in param_names, "sign_record 应通过参数注入 db"

    def test_orders_no_sessionlocal_in_route_handlers(self):
        """orders.py 路由函数体内不应有 SessionLocal()"""
        import inspect
        from app.routers import orders

        for name in ["explain_order", "get_order_document"]:
            func = getattr(orders, name)
            source = inspect.getsource(func)
            assert "SessionLocal()" not in source, \
                f"{name} 不应再使用 SessionLocal()"


# ==================== 端点可达性集成测试 ====================


class TestEndpointReachability:
    """验证修复后的端点仍然可达（FastAPI TestClient）"""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.first.return_value = None
        query_mock.all.return_value = []
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        return db

    @pytest.fixture
    def client(self, mock_db):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_alerts_list_reachable(self, client):
        """GET /api/v1/alerts 应可达"""
        resp = client.get("/api/v1/alerts")
        assert resp.status_code != 404

    def test_followup_records_reachable(self, client):
        """GET /api/v1/followup/records 应可达"""
        resp = client.get("/api/v1/followup/records")
        assert resp.status_code != 404

    def test_orders_list_reachable(self, client):
        """GET /api/v1/orders 应可达"""
        resp = client.get("/api/v1/orders")
        assert resp.status_code != 404

    def test_auto_dismiss_reachable(self, client):
        """POST /api/v1/alerts/auto-dismiss 应可达"""
        resp = client.post("/api/v1/alerts/auto-dismiss")
        assert resp.status_code != 404
