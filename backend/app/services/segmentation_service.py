"""胎盘超声图像分割服务 - 基于 nnU-Net 5折集成"""
import os
import subprocess
import shutil
import numpy as np
from PIL import Image
from loguru import logger


class SegmentationError(Exception):
    """分割异常"""


class SegmentationService:
    def __init__(self, model_dir: str, dataset_id: int = 1, folds: str = "all"):
        self.model_dir = os.path.abspath(model_dir)
        self.dataset_id = dataset_id
        self.folds = folds
        self._validate_model()

    def _validate_model(self):
        if not os.path.isdir(self.model_dir):
            raise SegmentationError(f"模型目录不存在: {self.model_dir}")
        for root, _dirs, files in os.walk(self.model_dir):
            if "plans.json" in files:
                logger.info("[分割] 模型验证通过: {}", os.path.basename(root))
                return
        raise SegmentationError(f"模型目录中未找到 plans.json: {self.model_dir}")

    def segment(self, input_path: str, output_dir: str) -> str:
        """对输入图像执行分割，返回掩码文件路径"""
        # 1. 验证输入图像可读
        if not os.path.exists(input_path):
            raise SegmentationError(f"输入图像不存在: {input_path}")
        try:
            img = Image.open(input_path)
            img.verify()
        except Exception as e:
            raise SegmentationError(f"输入图像格式无效: {e}")

        os.makedirs(output_dir, exist_ok=True)

        # 2. 创建临时输入目录（nnU-Net 需要目录作为输入，必须在输出目录外）
        input_dir = output_dir + "_nnunet_input"
        os.makedirs(input_dir, exist_ok=True)
        ext = os.path.splitext(input_path)[1] or ".png"
        tmp_input = os.path.join(input_dir, f"image_0000{ext}")
        shutil.copy2(input_path, tmp_input)

        # 3. 调用 nnUNetv2_predict
        env = os.environ.copy()
        # nnUNet_results 指向 Dataset001_PlacentaNT 的父目录
        env["nnUNet_results"] = os.path.dirname(self.model_dir)
        env.setdefault("ROCR_VISIBLE_DEVICES", "0")
        env.setdefault("HIP_VISIBLE_DEVICES", env["ROCR_VISIBLE_DEVICES"])
        logger.info(
            "[分割] 推理设备配置 ROCR_VISIBLE_DEVICES={} HIP_VISIBLE_DEVICES={}",
            env.get("ROCR_VISIBLE_DEVICES"), env.get("HIP_VISIBLE_DEVICES"),
        )

        cmd = [
            "nnUNetv2_predict",
            "-i", input_dir,
            "-o", output_dir,
            "-d", "Dataset001_PlacentaNT",
            "-f", "0", "1", "2", "3", "4",
            "-tr", "nnUNetTrainer",
            "-c", "2d",
            "-p", "nnUNetPlans",
            "-device", "cpu",
        ]

        logger.info("[分割] 执行 nnU-Net 5折集成推理...")
        logger.debug("[分割] 命令: {}", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if result.returncode != 0:
                logger.error("[分割] nnU-Net stderr: {}", result.stderr)
                raise SegmentationError(f"nnU-Net 推理失败: {result.stderr[:500]}")
            logger.debug("[分割] nnU-Net stdout: {}", result.stdout[:500] if result.stdout else "(无输出)")
        except subprocess.TimeoutExpired:
            raise SegmentationError("nnU-Net 推理超时（超过5分钟）")
        except FileNotFoundError:
            raise SegmentationError("nnUNetv2_predict 命令未找到，请确认 nnunetv2 已安装并在 PATH 中")

        # 4. 找到生成的掩码文件
        # nnU-Net 命名规则：输入 image_0000.png → 输出 image.png
        mask_path = None
        expected_mask = os.path.basename(tmp_input).replace("_0000", "")
        for f in sorted(os.listdir(output_dir)):
            fp = os.path.join(output_dir, f)
            if not os.path.isfile(fp):
                continue
            if f == expected_mask or f.endswith((".nii.gz", ".png", ".jpg", ".jpeg")):
                mask_path = fp
                break

        # 清理临时输入目录
        try:
            shutil.rmtree(input_dir, ignore_errors=True)
        except Exception:
            pass

        if mask_path is None:
            # 列出 output_dir 内容帮助调试
            files_found = os.listdir(output_dir)
            logger.error("[分割] 输出目录内容: {}", files_found)
            raise SegmentationError("nnU-Net 未生成掩码文件")

        # 5. 验证掩码非空
        logger.info("[分割] 找到掩码文件: {} (size: {} bytes)", os.path.basename(mask_path), os.path.getsize(mask_path))
        if not self._verify_mask(mask_path):
            raise SegmentationError("图像质量不符合要求，请上传清晰的NT期超声图像")

        logger.info("[分割] 分割完成，掩码: {}", os.path.basename(mask_path))
        return mask_path

    def _verify_mask(self, mask_path: str) -> bool:
        """检查掩码是否包含前景像素"""
        try:
            if mask_path.endswith(".nii.gz"):
                import nibabel as nib
                data = nib.load(mask_path).get_fdata()
            else:
                data = np.array(Image.open(mask_path))
            has_foreground = bool(np.any(data > 0))
            if not has_foreground:
                logger.warning("[分割] 掩码为空（无前景像素）")
            return has_foreground
        except Exception as e:
            logger.warning("[分割] 掩码验证异常，放行: {}", e)
            return True


# 全局单例
_segmentation_service: SegmentationService | None = None


def get_segmentation_service() -> SegmentationService:
    """获取分割服务单例"""
    global _segmentation_service
    if _segmentation_service is None:
        from ..config import settings

        # 解析模型目录路径（相对路径从 backend/ 目录解析）
        model_dir = settings.nnunet_model_dir
        if not os.path.isabs(model_dir):
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_dir = os.path.normpath(os.path.join(backend_dir, "..", model_dir))

        _segmentation_service = SegmentationService(
            model_dir=model_dir,
            dataset_id=settings.nnunet_dataset_id,
            folds=settings.nnunet_folds,
        )
    return _segmentation_service
