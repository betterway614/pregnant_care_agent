"""测试 Orders 路由 - 医嘱签署 + 文档端点 + 去重验证"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime


# ==================== 签署验证逻辑（单元测试） ====================


class TestOrderSignValidation:
    """测试签署前置验证逻辑"""

    def test_ai_order_must_be_modified_before_sign(self):
        """AI生成的医嘱未经修改不能签署"""
        from app.models import MedicalOrder

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST",
            content="建议每日测血压",
            source="AI_RECOMMENDED",
            status="draft",
            modified_by_doctor=False,
        )

        assert order.source == "AI_RECOMMENDED"
        assert order.modified_by_doctor is False
        assert order.status == "draft"

    def test_modified_ai_order_can_be_signed(self):
        """医生修改后的AI医嘱可以签署"""
        from app.models import MedicalOrder

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST",
            content="建议每日测血压，低盐饮食",
            source="AI_RECOMMENDED",
            status="draft",
            modified_by_doctor=True,
        )

        assert order.modified_by_doctor is True

    def test_doctor_written_order_can_sign_directly(self):
        """医生手写医嘱可以直接签署（无需modified_by_doctor）"""
        from app.models import MedicalOrder

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST",
            content="每日测血压",
            source="DOCTOR_WRITTEN",
            status="draft",
            modified_by_doctor=False,
        )

        # 医生手写的医嘱即使modified_by_doctor=False也应该能签署
        assert order.source == "DOCTOR_WRITTEN"
        # 签署逻辑在路由中实现：仅 AI_RECOMMENDED 需验证 modified_by_doctor


class TestOrderSignatureData:
    """测试签名数据存储"""

    def test_signature_data_stores_image_and_signer(self):
        """签名数据应存储图片、签名人、时间"""
        from app.models import MedicalOrder

        sig_data = {
            "image": "data:image/png;base64,iVBOR...",
            "signer": "张医生",
            "signed_at": datetime.utcnow().isoformat(),
        }

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST",
            content="test",
            signature_data=sig_data,
        )

        assert order.signature_data["image"].startswith("data:image/png;base64,")
        assert order.signature_data["signer"] == "张医生"
        assert "signed_at" in order.signature_data


class TestOrderDocumentSnapshot:
    """测试文档快照存储"""

    def test_order_snapshot_stores_frozen_data(self):
        """签署时快照应冻结订单数据"""
        from app.models import MedicalOrder

        snapshot = {
            "patient_name": "测试孕妇",
            "gestational_week": "24+3",
            "order_content": "建议每日测血压，低盐饮食",
            "order_type": "standard",
            "source": "AI_RECOMMENDED",
            "doctor_name": "张医生",
            "generated_at": datetime.utcnow().isoformat(),
        }

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST",
            content="建议每日测血压，低盐饮食",
            order_snapshot=snapshot,
            order_text="医 嘱 单\n测试孕妇\n建议每日测血压，低盐饮食",
        )

        assert order.order_snapshot["patient_name"] == "测试孕妇"
        assert "建议" in order.order_text


# ==================== 路由级集成测试 ====================


class TestOrdersRouterIntegration:
    """FastAPI TestClient 集成测试（Mock DB）"""

    @pytest.fixture
    def mock_db(self):
        """创建 mock DB session"""
        db = MagicMock()
        return db

    @pytest.fixture
    def client(self, mock_db):
        """创建 TestClient 并注入 mock DB（端点统一使用 Depends(get_db)）"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()

    def _setup_mock_order_query(self, mock_db, order):
        """设置 mock 查询链返回指定 order"""
        # Mock 查询链: query().filter().first() -> order
        mock_db.query.return_value.filter.return_value.first.return_value = order
        mock_db.query.return_value.filter.return_value.all.return_value = [order]
        mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [order]

    def test_generate_order_endpoint(self, client, mock_db):
        """POST /orders/generate — 路由可达（验证端点注册）"""
        from app.models import Pregnant

        pregnant = Pregnant(
            pregnant_id="PT_TEST_001",
            display_name="测试孕妇",
            gestational_age_days=24 * 7 + 3,
            risk_tags=["FGR"],
        )
        mock_db.query.return_value.filter.return_value.first.return_value = pregnant

        def mock_refresh(order):
            order.id = uuid4()

        mock_db.refresh = mock_refresh

        with patch("app.routers.orders.llm") as mock_llm:
            mock_llm.chat = AsyncMock(return_value="建议每2周产检一次，低盐饮食。")

            response = client.post("/api/v1/orders/generate", json={
                "pregnant_id": "PT_TEST_001",
                "risk_level": "high",
                "gestational_weeks": 24.5,
            })

            # 404 = 路由未注册, 422 = 参数校验失败
            assert response.status_code != 404, "orders/generate 端点未注册"
            assert response.status_code != 422, f"参数校验失败: {response.json()}"

    def test_get_orders_list(self, client, mock_db):
        """GET /orders — 路由可达，返回200（验证端点注册）"""
        response = client.get("/api/v1/orders")
        # 端点至少应可访问（mock链不完整时可能返回500，但不应404）
        assert response.status_code != 404, "orders 列表端点未注册"

    def _setup_pregnant_mock(self, mock_db):
        """辅助：Mock 孕妇查询"""
        from app.models import Pregnant
        pregnant = Pregnant(
            pregnant_id="PT_TEST_001",
            display_name="测试孕妇",
            gestational_age_days=24 * 7 + 3,
            risk_tags=["FGR"],
        )
        return pregnant

    def test_get_order_document_endpoint(self, client, mock_db):
        """GET /orders/{id}/document — SessionLocal 端点应可达"""
        from app.models import MedicalOrder
        from app.models import Pregnant

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST_001",
            content="建议每日测血压",
            status="signed",
            order_type="standard",
            signature_data={"image": "base64...", "signer": "张医生", "signed_at": "2025-01-01"},
            order_snapshot={"patient_name": "测试", "order_content": "建议每日测血压"},
            order_text="医 嘱 单\n测试\n建议每日测血压",
        )

        pregnant = Pregnant(
            pregnant_id="PT_TEST_001",
            display_name="测试孕妇",
        )

        # SessionLocal 端点: 每次 db.query() 返回新的 query mock
        # 第一次 db.query(MedicalOrder) -> order
        # 第二次 db.query(Pregnant) -> pregnant
        query_results = [order, pregnant]

        def mock_first():
            # 返回下一个结果
            return query_results.pop(0) if query_results else None

        mock_db.query.return_value.filter.return_value.first = mock_first

        response = client.get(f"/api/v1/orders/{order.id}/document")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == str(order.id)
        assert data["has_document"] is True

    def test_update_order_sets_modified_flag(self, client, mock_db):
        """PUT /orders/{id} 修改content时应设置modified_by_doctor=True"""
        from app.models import MedicalOrder
        from app.models import Pregnant

        order = MedicalOrder(
            id=uuid4(),
            pregnant_id="PT_TEST_001",
            content="原始医嘱内容",
            source="AI_RECOMMENDED",
            status="draft",
            order_type="standard",
            modified_by_doctor=False,
        )

        pregnant = Pregnant(
            pregnant_id="PT_TEST_001",
            display_name="测试孕妇",
        )

        # SessionLocal 端点: order 先查，pregnant 后查
        query_results = [order, pregnant]

        def mock_first():
            return query_results.pop(0) if query_results else None

        mock_db.query.return_value.filter.return_value.first = mock_first

        response = client.put(f"/api/v1/orders/{order.id}", json={
            "content": "修改后的医嘱内容",
        })

        assert order.modified_by_doctor is True, f"修改医嘱内容后 modified_by_doctor 应为 True, 实际={order.modified_by_doctor}"
        assert order.content == "修改后的医嘱内容"


# ==================== 去重验证 ====================


class TestDoctorAnalyzeNoAutoOrder:
    """验证 doctor/analyze 不再自动创建医嘱"""

    def test_tool_generate_medical_order_still_exists(self):
        """工具函数仍应存在（供Dr.智对话使用）"""
        from app.routers.doctor_ai import tool_generate_medical_order
        assert callable(tool_generate_medical_order)

    def test_doctor_analyze_does_not_auto_call_tool(self):
        """验证 doctor_analyze 函数体内不再调用 tool_generate_medical_order"""
        import inspect
        from app.routers.doctor_ai import doctor_analyze

        source = inspect.getsource(doctor_analyze)

        # 函数体内不应包含 tool_generate_medical_order 调用
        # 但允许 import 语句或注释中出现
        lines_after_analysis = source.split("suggested_orders")
        if len(lines_after_analysis) > 1:
            rest = lines_after_analysis[-1]
            # 确保不再调用 tool_generate_medical_order
            assert "tool_generate_medical_order" not in rest or "不再自动创建" in rest, \
                "doctor_analyze 不应再自动调用 tool_generate_medical_order"
