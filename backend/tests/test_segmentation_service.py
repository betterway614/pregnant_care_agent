"""分割服务单元测试"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np
from unittest.mock import patch, MagicMock, mock_open
from PIL import Image


class TestSegmentationServiceInit:
    """模型目录验证测试"""

    @patch("app.services.segmentation_service.os.path.isdir")
    def test_init_with_valid_model_dir(self, mock_isdir):
        mock_isdir.return_value = True
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/model/nnUNetTrainer__nnUNetPlans__2d", [], ["plans.json", "checkpoint_final.pth"]),
            ]
            from app.services.segmentation_service import SegmentationService
            svc = SegmentationService("/fake/model/Dataset001_PlacentaNT")
            assert svc.dataset_id == 1
            assert svc.folds == "all"

    @patch("app.services.segmentation_service.os.path.isdir")
    def test_init_missing_model_dir_raises(self, mock_isdir):
        mock_isdir.return_value = False
        from app.services.segmentation_service import SegmentationService, SegmentationError
        with pytest.raises(SegmentationError, match="模型目录不存在"):
            SegmentationService("/nonexistent/model_dir")

    @patch("app.services.segmentation_service.os.path.isdir")
    def test_init_missing_plans_json_raises(self, mock_isdir):
        mock_isdir.return_value = True
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [("/model/empty_dir", [], [])]
            from app.services.segmentation_service import SegmentationService, SegmentationError
            with pytest.raises(SegmentationError, match="未找到 plans.json"):
                SegmentationService("/fake/model_dir")


class TestValidateModel:
    """模型验证方法测试"""

    @patch("app.services.segmentation_service.os.path.isdir")
    def test_finds_plans_in_nested_dir(self, mock_isdir):
        mock_isdir.return_value = True
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/model/Dataset001_PlacentaNT", ["nnUNetTrainer__nnUNetPlans__2d"], []),
                ("/model/Dataset001_PlacentaNT/nnUNetTrainer__nnUNetPlans__2d", ["fold_0"], ["plans.json", "dataset.json"]),
            ]
            from app.services.segmentation_service import SegmentationService
            svc = SegmentationService("/fake/model/Dataset001_PlacentaNT")
            assert svc is not None


class TestSegment:
    """分割方法测试"""

    @pytest.fixture
    def svc(self):
        with patch("app.services.segmentation_service.os.path.isdir", return_value=True), \
             patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/model/nnUNetTrainer__2d", [], ["plans.json"]),
            ]
            from app.services.segmentation_service import SegmentationService
            return SegmentationService("/fake/model/Dataset001_PlacentaNT")

    @pytest.fixture
    def mock_img(self):
        """创建一个有效的测试图像"""
        from io import BytesIO
        buf = BytesIO()
        img = Image.new("L", (100, 100), color=128)
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_segment_input_not_found(self, svc):
        with pytest.raises(Exception, match="输入图像不存在"):
            svc.segment("/nonexistent/input.png", "/tmp/output")

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_invalid_image_format(self, mock_exists, svc, tmpdir):
        """无效图像格式抛出异常"""
        bad_path = str(tmpdir / "bad.png")
        with open(bad_path, "wb") as f:
            f.write(b"not a valid image")
        with pytest.raises(Exception, match="输入图像格式无效"):
            svc.segment(bad_path, str(tmpdir / "output"))

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_success(self, mock_exists, svc, mock_img, tmpdir):
        """成功分割场景：nnU-Net 返回0，生成掩码"""
        input_path = str(tmpdir / "input.png")
        output_dir = str(tmpdir / "output")
        with open(input_path, "wb") as f:
            f.write(mock_img)
        os.makedirs(output_dir, exist_ok=True)

        with patch("subprocess.run") as mock_run, \
             patch.object(svc, "_verify_mask", return_value=True):
            mock_run.return_value = MagicMock(returncode=0, stdout="Inference done", stderr="")

            # 预先在输出目录创建模拟掩码文件（模拟 nnU-Net 输出）
            mask_path = str(tmpdir / "output" / "image.png")
            Image.new("L", (100, 100), color=128).save(mask_path)

            result = svc.segment(input_path, output_dir)
            assert result is not None
            mock_run.assert_called_once()

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_nnunet_failure(self, mock_exists, svc, mock_img, tmpdir):
        """nnU-Net 返回非0退出码→抛出异常"""
        input_path = str(tmpdir / "input.png")
        output_dir = str(tmpdir / "output")
        with open(input_path, "wb") as f:
            f.write(mock_img)
        os.makedirs(output_dir, exist_ok=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="CUDA out of memory")
            from app.services.segmentation_service import SegmentationError
            with pytest.raises(SegmentationError, match="nnU-Net 推理失败"):
                svc.segment(input_path, output_dir)

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_timeout(self, mock_exists, svc, mock_img, tmpdir):
        """nnU-Net 超时→抛出异常"""
        import subprocess
        input_path = str(tmpdir / "input.png")
        output_dir = str(tmpdir / "output")
        with open(input_path, "wb") as f:
            f.write(mock_img)
        os.makedirs(output_dir, exist_ok=True)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300)):
            from app.services.segmentation_service import SegmentationError
            with pytest.raises(SegmentationError, match="推理超时"):
                svc.segment(input_path, output_dir)

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_nnunet_not_found(self, mock_exists, svc, mock_img, tmpdir):
        """nnUNetv2_predict 未安装→抛出异常"""
        input_path = str(tmpdir / "input.png")
        output_dir = str(tmpdir / "output")
        with open(input_path, "wb") as f:
            f.write(mock_img)
        os.makedirs(output_dir, exist_ok=True)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            from app.services.segmentation_service import SegmentationError
            with pytest.raises(SegmentationError, match="nnUNetv2_predict.*未找到"):
                svc.segment(input_path, output_dir)

    @patch("app.services.segmentation_service.os.path.exists", return_value=True)
    def test_segment_no_mask_generated(self, mock_exists, svc, mock_img, tmpdir):
        """输出目录无掩码文件→抛出异常"""
        input_path = str(tmpdir / "input.png")
        output_dir = str(tmpdir / "output")
        with open(input_path, "wb") as f:
            f.write(mock_img)
        os.makedirs(output_dir, exist_ok=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            from app.services.segmentation_service import SegmentationError
            with pytest.raises(SegmentationError, match="未生成掩码文件"):
                svc.segment(input_path, output_dir)


class TestVerifyMask:
    """掩码验证测试"""

    @pytest.fixture
    def svc(self):
        with patch("app.services.segmentation_service.os.path.isdir", return_value=True), \
             patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/model/nnUNetTrainer__2d", [], ["plans.json"]),
            ]
            from app.services.segmentation_service import SegmentationService
            return SegmentationService("/fake/model/Dataset001_PlacentaNT")

    def test_verify_with_foreground_pixels(self, svc, tmpdir):
        """有前景像素→返回True"""
        mask_path = str(tmpdir / "mask.png")
        img = Image.new("L", (100, 100), color=0)
        # 添加一些前景像素
        pixels = img.load()
        pixels[50, 50] = 255
        img.save(mask_path)
        assert svc._verify_mask(mask_path) is True

    def test_verify_empty_mask(self, svc, tmpdir):
        """全黑掩码→返回False"""
        mask_path = str(tmpdir / "empty_mask.png")
        img = Image.new("L", (100, 100), color=0)
        img.save(mask_path)
        result = svc._verify_mask(mask_path)
        assert result is False

    def test_verify_corrupt_file_returns_true(self, svc, tmpdir):
        """损坏的文件无法验证时放行→返回True"""
        bad_path = str(tmpdir / "corrupt.png")
        with open(bad_path, "wb") as f:
            f.write(b"not a valid image at all")
        result = svc._verify_mask(bad_path)
        assert result is True


class TestSegmentationError:
    """分割异常类测试"""

    def test_error_is_exception_subclass(self):
        from app.services.segmentation_service import SegmentationError
        assert issubclass(SegmentationError, Exception)

    def test_error_message(self):
        from app.services.segmentation_service import SegmentationError
        err = SegmentationError("测试错误消息")
        assert str(err) == "测试错误消息"


class TestGetSegmentationService:
    """单例工厂函数测试"""

    @patch("app.services.segmentation_service.os.path.isdir")
    def test_returns_singleton(self, mock_isdir):
        """两次调用返回同一实例"""
        mock_isdir.return_value = True
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/fake/nnUNetTrainer__2d", [], ["plans.json"]),
            ]
            from app.services.segmentation_service import (
                get_segmentation_service,
            )
            # 重置单例
            import app.services.segmentation_service as mod
            mod._segmentation_service = None

            with patch("app.config.settings") as mock_settings:
                mock_settings.nnunet_model_dir = "backend/fgr_compete/Dataset001_PlacentaNT"
                mock_settings.nnunet_dataset_id = 1
                mock_settings.nnunet_folds = "all"

                svc1 = get_segmentation_service()
                svc2 = get_segmentation_service()
                assert svc1 is svc2
