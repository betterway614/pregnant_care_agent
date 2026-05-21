"""FGR上传端点集成测试 - 线性流水线：上传→分割→预测"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date

from app.database import Base, get_db
from app.models import Pregnant, FgrAssessment, Alert
from app.main import app

# ── 测试数据库 ──
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_fgr_upload.db")
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _seed_pregnant(db):
    p = Pregnant(
        pregnant_id="PT_TEST001",
        display_name="测试孕妇",
        gestational_age_days=196,  # 28周
        lmp_date=date.today(),
    )
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()
    yield db
    db.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session):
    """FastAPI 测试客户端，注入测试数据库"""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_segmentation():
    """模拟分割服务：生成一张简单的掩码图"""
    def _create_mask(raw_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        mask_path = os.path.join(output_dir, "image.nii.gz")
        # 生成带前景像素的掩码 PNG
        img = Image.new("L", (224, 224), color=0)
        pixels = img.load()
        for x in range(80, 140):
            for y in range(80, 140):
                pixels[x, y] = 255
        # 输出为 PNG（nnU-Net 对 PNG 输入输出 PNG）
        mask_png = os.path.join(output_dir, "image.png")
        img.save(mask_png)
        return mask_png

    return _create_mask


@pytest.fixture
def mock_fgr_predictor():
    """模拟 FGR 预测器，返回预定义结果"""
    def _predict(image_path, mask_path):
        return {
            "ensemble_fgr_probability": 0.62,
            "predicted_label": "FGR",
            "confidence_level": "High",
            "fold_results": [
                {"fold": 0, "p_resnet": 0.55, "p_svm": 0.60, "fusion_weight": 0.55, "p_fused": 0.58},
                {"fold": 1, "p_resnet": 0.60, "p_svm": 0.65, "fusion_weight": 0.70, "p_fused": 0.63},
                {"fold": 2, "p_resnet": 0.50, "p_svm": 0.55, "fusion_weight": 0.20, "p_fused": 0.52},
                {"fold": 3, "p_resnet": 0.65, "p_svm": 0.70, "fusion_weight": 0.85, "p_fused": 0.68},
                {"fold": 4, "p_resnet": 0.58, "p_svm": 0.62, "fusion_weight": 0.65, "p_fused": 0.61},
            ],
        }
    return _predict


def _make_test_image():
    """生成模拟超声图像"""
    buf = BytesIO()
    img = Image.new("L", (224, 224), color=100)
    # 模拟胎盘区域
    pixels = img.load()
    for x in range(70, 150):
        for y in range(70, 150):
            pixels[x, y] = 180
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════
# 线性流水线集成测试
# ═══════════════════════════════════════════

class TestFgrUploadPipeline:
    """上传→分割→预测 线性流水线"""

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_full_pipeline_success(
        self, mock_settings, mock_get_seg, client, db_session, mock_segmentation,
    ):
        """端到端：上传原图 → 自动分割 → FGR预测 → 返回结果"""
        # 种子数据
        _seed_pregnant(db_session)

        # 配置 mock
        mock_settings.fgr_mode = True
        mock_svc = MagicMock()
        mock_svc.segment.side_effect = mock_segmentation
        mock_get_seg.return_value = mock_svc

        # mock register_uploaded_images
        with patch("fgr_compete.image_registry.register_uploaded_images") as mock_reg:
            fake_raw = os.path.join(
                os.path.dirname(__file__),
                "../fgr_compete/uploads/PT_TEST001/image.png",
            )
            fake_mask = os.path.join(
                os.path.dirname(__file__),
                "../fgr_compete/uploads/PT_TEST001/mask.png",
            )
            os.makedirs(os.path.dirname(fake_raw), exist_ok=True)
            mock_reg.return_value = (fake_raw, fake_mask)

            # mock FGR predictor
            with patch("app.routers.fgr._run_fgr_model") as mock_fgr:
                mock_fgr.return_value = {
                    "case_id": "CASE_AABBCCDD",
                    "risk_level": "high",
                    "risk_label": "高风险",
                    "fgr_probability": 0.62,
                    "predicted_label": "FGR",
                    "model_confidence": "High",
                    "confidence_interval": {"lower_bound": 0.55, "upper_bound": 0.69},
                    "explanation": "基于胎盘超声图像的5折ResNet集成模型预测。FGR概率=62%。",
                    "processing_time": 3500,
                    "fold_details": [],
                }

                img_file = _make_test_image()
                response = client.post(
                    "/api/v1/fgr/upload/PT_TEST001",
                    data={"gestational_weeks": 28, "image_type": "AC"},
                    files={"image": ("ultrasound.png", img_file, "image/png")},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["case_id"] == "CASE_AABBCCDD"
        assert data["risk_level"] == "high"
        assert data["risk_label"] == "高风险"
        assert data["fgr_probability"] == 0.62
        assert data["hardware"] == "NPU"

        # 验证数据库写入
        assessment = db_session.query(FgrAssessment).filter_by(case_id="CASE_AABBCCDD").first()
        assert assessment is not None
        assert assessment.pregnant_id == "PT_TEST001"
        assert assessment.risk_level == "high"

        # 验证预警生成
        alerts = db_session.query(Alert).filter_by(pregnant_id="PT_TEST001").all()
        assert len(alerts) > 0

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_segmentation_failure_returns_400(
        self, mock_settings, mock_get_seg, client, db_session,
    ):
        """分割失败 → 400"""
        _seed_pregnant(db_session)
        mock_settings.fgr_mode = True

        mock_svc = MagicMock()
        from app.services.segmentation_service import SegmentationError
        mock_svc.segment.side_effect = SegmentationError("图像质量不符合要求，请上传清晰的NT期超声图像")
        mock_get_seg.return_value = mock_svc

        img_file = _make_test_image()
        response = client.post(
            "/api/v1/fgr/upload/PT_TEST001",
            data={"gestational_weeks": 28},
            files={"image": ("bad.png", img_file, "image/png")},
        )

        assert response.status_code == 400
        assert "图像质量不符合要求" in response.json()["detail"]

    def test_upload_missing_image(self, client):
        """未上传图像 → 400"""
        response = client.post(
            "/api/v1/fgr/upload/PT_TEST001",
            data={"gestational_weeks": 28},
        )
        assert response.status_code == 422  # FastAPI 校验失败

    def test_upload_pregnant_not_found(self, client, db_session):
        """孕妇不存在 → 404"""
        img_file = _make_test_image()
        response = client.post(
            "/api/v1/fgr/upload/NONEXISTENT",
            data={"gestational_weeks": 28},
            files={"image": ("ultrasound.png", img_file, "image/png")},
        )
        assert response.status_code == 404
        assert "孕妇不存在" in response.json()["detail"]

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_empty_image_bytes(
        self, mock_settings, mock_get_seg, client, db_session,
    ):
        """上传空文件 → 400"""
        _seed_pregnant(db_session)
        mock_settings.fgr_mode = True

        response = client.post(
            "/api/v1/fgr/upload/PT_TEST001",
            data={"gestational_weeks": 28},
            files={"image": ("empty.png", BytesIO(b""), "image/png")},
        )
        assert response.status_code == 400
        assert "不能为空" in response.json()["detail"]

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_mock_mode(
        self, mock_settings, mock_get_seg, client, db_session, mock_segmentation,
    ):
        """fgr_mode=False 使用 mock 评估"""
        _seed_pregnant(db_session)
        mock_settings.fgr_mode = False

        mock_svc = MagicMock()
        mock_svc.segment.side_effect = mock_segmentation
        mock_get_seg.return_value = mock_svc

        with patch("fgr_compete.image_registry.register_uploaded_images") as mock_reg:
            fake_raw = os.path.join(
                os.path.dirname(__file__),
                "../fgr_compete/uploads/PT_TEST001/image.png",
            )
            fake_mask = os.path.join(
                os.path.dirname(__file__),
                "../fgr_compete/uploads/PT_TEST001/mask.png",
            )
            os.makedirs(os.path.dirname(fake_raw), exist_ok=True)
            mock_reg.return_value = (fake_raw, fake_mask)

            img_file = _make_test_image()
            response = client.post(
                "/api/v1/fgr/upload/PT_TEST001",
                data={"gestational_weeks": 28},
                files={"image": ("ultrasound.png", img_file, "image/png")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["hardware"] == "CPU"
        assert "fgr_probability" in data
        assert "risk_level" in data

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_segmentation_server_error_returns_500(
        self, mock_settings, mock_get_seg, client, db_session,
    ):
        """分割时意外异常 → 500"""
        _seed_pregnant(db_session)
        mock_settings.fgr_mode = True

        mock_svc = MagicMock()
        mock_svc.segment.side_effect = RuntimeError("GPU 内存不足")
        mock_get_seg.return_value = mock_svc

        img_file = _make_test_image()
        response = client.post(
            "/api/v1/fgr/upload/PT_TEST001",
            data={"gestational_weeks": 28},
            files={"image": ("ultrasound.png", img_file, "image/png")},
        )

        assert response.status_code == 500
        assert "服务端分割错误" in response.json()["detail"]

    @patch("app.routers.fgr.get_segmentation_service")
    @patch("app.routers.fgr.settings")
    def test_upload_empty_mask_returns_400(
        self, mock_settings, mock_get_seg, client, db_session,
    ):
        """分割结果为空掩码 → 400"""
        _seed_pregnant(db_session)
        mock_settings.fgr_mode = True

        # 生成空掩码（全黑）
        def _create_empty_mask(raw_path, output_dir):
            os.makedirs(output_dir, exist_ok=True)
            mask_path = os.path.join(output_dir, "empty_mask.png")
            img = Image.new("L", (224, 224), color=0)
            img.save(mask_path)
            return mask_path

        mock_svc = MagicMock()
        mock_svc.segment.side_effect = _create_empty_mask
        mock_get_seg.return_value = mock_svc

        with patch("fgr_compete.image_registry.register_uploaded_images") as mock_reg:
            img_file = _make_test_image()
            response = client.post(
                "/api/v1/fgr/upload/PT_TEST001",
                data={"gestational_weeks": 28},
                files={"image": ("ultrasound.png", img_file, "image/png")},
            )

        assert response.status_code == 400
        assert "图像质量不符合要求" in response.json()["detail"]


# ═══════════════════════════════════════════
# 组装端点测试
# ═══════════════════════════════════════════

class TestFgrAssessEndpoint:
    """已有图片的评估端点"""

    def test_assess_patient_not_found(self, client):
        response = client.post(
            "/api/v1/fgr/assess/NONEXISTENT",
            json={"gestational_weeks": 28, "image_type": "AC"},
        )
        assert response.status_code == 404

    def test_assess_no_bound_images(self, client, db_session):
        """无绑定图片 → 400"""
        _seed_pregnant(db_session)
        with patch("app.routers.fgr.settings") as mock_settings:
            mock_settings.fgr_mode = True
            with patch("app.routers.fgr._get_patient_images", return_value=None):
                response = client.post(
                    "/api/v1/fgr/assess/PT_TEST001",
                    json={"gestational_weeks": 28, "image_type": "AC"},
                )
                assert response.status_code == 400
                assert "暂无绑定超声图像" in response.json()["detail"]


class TestFgrPatientImages:
    """患者图片信息端点"""

    def test_no_images(self, client):
        response = client.get("/api/v1/fgr/patient-images/NONEXISTENT")
        assert response.status_code == 200
        data = response.json()
        assert data["has_image"] is False

    def test_image_not_found_returns_404(self, client):
        """无绑定图片请求原图 → 404"""
        with patch("app.routers.fgr._get_patient_images", return_value=None):
            response = client.get("/api/v1/fgr/image/NONEXISTENT")
            assert response.status_code == 404


# ── 清理测试数据库 ──
def teardown_module():
    test_engine.dispose()
    import gc
    gc.collect()
    try:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    except PermissionError:
        pass  # Windows 文件锁，下次测试前会被覆盖
