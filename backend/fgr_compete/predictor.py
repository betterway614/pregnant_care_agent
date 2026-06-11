"""FGRPredictor 门面类：封装 5 折集成预测流程"""

import os
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from loguru import logger

from .config import (
    MODEL_DIR, DEVICE, IMG_SIZE, N_FOLDS,
)
from .model import ResNet18DualFusion
from .features import (
    load_raw_uint8, load_mask_bool, bytes_to_raw, bytes_to_mask, extract_features,
)


class FGRPredictor:
    """FGR 5 折集成预测器（纯 ResNet）"""

    def __init__(self):
        self.resnet_models: list[torch.nn.Module] = []
        self.backend_name = "pytorch"
        self.execution_provider = f"torch:{DEVICE}"
        self.hardware = self._detect_hardware_label()
        self._initialized = False

    @staticmethod
    def _detect_hardware_label() -> str:
        if DEVICE.type == "cuda":
            if getattr(torch.version, "hip", None):
                return "ROCm/PyTorch"
            return "CUDA"
        return "CPU"

    def initialize(self) -> None:
        """初始化：加载 5 个 ResNet"""
        self._load_resnet_models()
        self._initialized = True
        logger.info("FGRPredictor 初始化完成（{}折纯ResNet集成, device={}）", N_FOLDS, DEVICE)

    def _load_resnet_models(self) -> None:
        """从 MODEL_DIR 加载 5 折 ResNet 权重"""
        # 尝试多种可能的路径
        search_dirs = [
            MODEL_DIR,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "0.701_515pth"),
        ]
        model_dir = None
        for d in search_dirs:
            if os.path.isdir(d):
                model_dir = d
                break

        if model_dir is None:
            raise FileNotFoundError(f"未找到模型权重目录，搜索路径: {search_dirs}")

        for fold_idx in range(N_FOLDS):
            model_path = os.path.join(model_dir, f"resnet_v9_best_fold{fold_idx + 1}.pth")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"权重文件不存在: {model_path}")
            model = ResNet18DualFusion().to(DEVICE)
            model.load_state_dict(torch.load(model_path, map_location=DEVICE))
            model.eval()
            self.resnet_models.append(model)
            logger.debug("  Fold {} ResNet 加载完成", fold_idx + 1)

    def predict(self, image_path: str, mask_path: str) -> dict:
        """基于文件路径的预测"""
        raw = load_raw_uint8(image_path)
        mask = load_mask_bool(mask_path)
        return self._predict_arrays(raw, mask)

    def predict_from_bytes(self, image_bytes: bytes, mask_bytes: bytes) -> dict:
        """基于字节数据的预测（用于 API 上传）"""
        raw = bytes_to_raw(image_bytes)
        mask = bytes_to_mask(mask_bytes)
        return self._predict_arrays(raw, mask)

    def _predict_arrays(self, raw: np.ndarray, mask_bool: np.ndarray) -> dict:
        """核心预测逻辑"""
        assert self._initialized, "FGRPredictor.initialize() 必须先调用"

        # 提取手工特征（纯 ResNet 模式下仅用于日志，不参与预测）
        hc_feat = extract_features(raw, mask_bool)
        if hc_feat is None:
            return {"error": "mask 区域太小（<100 像素），无法提取特征"}

        # --- 日志：图像统计 & 手工特征 ---
        mask_area = int(mask_bool.sum())
        roi_area_ratio = mask_area / (raw.shape[0] * raw.shape[1])
        logger.info(
            "[FGR-特征] 图像尺寸={}x{} mask面积={}px 占比={:.2%}",
            raw.shape[1], raw.shape[0], mask_area, roi_area_ratio,
        )
        feature_names = [
            'raw_mean', 'raw_p75', 'raw_p90', 'raw_b50', 'raw_b65', 'raw_b80',
            'clahe_p75', 'clahe_p90', 'clahe_b65', 'lbp_r2_mean', 'lbp_r3_mean',
            'raw_kurt', 'lbp_r1_std', 'lbp_r1_entropy', 'lbp_r2_std',
            'raw_p50', 'raw_iqr', 'clahe_std', 'lbp_r3_std', 'clahe_mean',
        ]
        logger.info("[FGR-特征] 手工特征值: {}", {k: round(float(v), 4) for k, v in zip(feature_names, hc_feat)})

        # 准备 ResNet 输入
        img_uint8 = raw.astype(np.uint8)
        mask_f32 = mask_bool.astype(np.float32)
        roi = (img_uint8 * mask_f32).clip(0, 255).astype(np.uint8)
        roi_mean = float(roi[roi > 0].mean()) if roi[roi > 0].size > 0 else 0.0
        roi_std = float(roi[roi > 0].std()) if roi[roi > 0].size > 0 else 0.0
        logger.info("[FGR-特征] ROI 均值={:.2f} 标准差={:.2f} 非零像素={}", roi_mean, roi_std, int((roi > 0).sum()))

        img_pil = Image.fromarray(roi).convert("RGB").resize(
            (IMG_SIZE, IMG_SIZE), Image.BILINEAR
        )
        tf = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        img_tensor = tf(img_pil).unsqueeze(0).to(DEVICE)

        # 统计输入 tensor
        logger.info(
            "[FGR-特征] ResNet输入 tensor shape={} mean={:.4f} std={:.4f} min={:.4f} max={:.4f}",
            tuple(img_tensor.shape), float(img_tensor.mean()), float(img_tensor.std()),
            float(img_tensor.min()), float(img_tensor.max()),
        )

        return self._predict_resnet_only(img_tensor)

    def _predict_resnet_only(self, img_tensor: torch.Tensor) -> dict:
        """纯 ResNet 5 折集成预测"""
        resnet_probs = []
        for fold_idx in range(N_FOLDS):
            with torch.no_grad():
                logit = self.resnet_models[fold_idx](img_tensor)
                p = torch.sigmoid(logit).item()
            resnet_probs.append(p)
            logger.info("[FGR-推理] Fold{} ResNet={:.4f}", fold_idx + 1, p)

        ensemble_prob = float(np.mean(resnet_probs))
        resnet_std = float(np.std(resnet_probs))
        predicted_label = "FGR" if ensemble_prob >= 0.5 else "NOR"

        logger.info(
            "[FGR-集成] ResNet 5折均值={:.4f}±{:.4f} 各折=[{}]",
            ensemble_prob, resnet_std,
            ", ".join(f"{p:.4f}" for p in resnet_probs),
        )

        # 置信度等级
        if ensemble_prob >= 0.7 or ensemble_prob <= 0.3:
            confidence = "High"
        elif ensemble_prob >= 0.6 or ensemble_prob <= 0.4:
            confidence = "Medium"
        else:
            confidence = "Low"

        logger.info(
            "[FGR-结果] 最终预测 label={} prob={:.4f} conf={}",
            predicted_label, ensemble_prob, confidence,
        )

        fold_results = [
            {
                "fold": i + 1,
                "p_resnet": round(p, 4),
                "p_fused": round(p, 4),
            }
            for i, p in enumerate(resnet_probs)
        ]

        return {
            "fold_results": fold_results,
            "ensemble_fgr_probability": round(ensemble_prob, 4),
            "predicted_label": predicted_label,
            "confidence_level": confidence,
        }


# 模块级单例
_PREDICTOR = None


def _detect_gpu_vendor() -> str:
    """检测 GPU 厂商：nvidia / amd / unknown"""
    try:
        import torch
        if torch.cuda.is_available():
            cuda_version = torch.version.cuda or ""
            # AMD ROCm 版本格式如 "6.1"，NVIDIA CUDA 格式如 "12.1"
            if any(pat in cuda_version for pat in ["6.", "7.", "11.", "12.", "18."]):
                return "nvidia"
            # AMD ROCm torch 在 torch.version.hip 中标记
            if getattr(torch.version, "hip", None):
                return "amd"
            return "nvidia"
    except Exception:
        pass
    return "unknown"


def _probe_npu_service(backend: str = "onnx_npu") -> tuple[bool, "NPUPredictorService | None", str, str]:
    """探测 NPU 服务是否可用，返回 (success, service_or_None, hardware, provider)。

    成功时返回已初始化的 NPUPredictorService，可直接返回给调用者。
    """
    try:
        from .npu_service import NPUPredictorService
        svc = NPUPredictorService(backend)
        svc.initialize()
        return True, svc, svc.hardware, svc.execution_provider
    except Exception as e:
        logger.debug("[FGR-探测] NPU 服务不可用 ({}): {}", backend, e)
        return False, None, "", ""


def create_predictor(backend: str | None = None):
    """按配置创建 FGR predictor，支持完整的硬件 fallback 链。

    Fallback 链（自动模式，backend=None 时）：
      NVIDIA: CUDA → CPU
      AMD:    NPU → ROCm → CPU
      未知:   CPU

    显式指定 backend 时行为：
      - onnx_npu / npu: 启动 NPU 子进程；NPU 不可用时 fallback 到 ROCm → CPU
      - onnx_igpu / rocm: ONNX MIGraphX；不可用时 fallback 到 CPU
      - pytorch / cuda: PyTorch 自动检测设备
      - mock: 不加载模型
    """
    from .npu_service import NPUPredictorService

    requested = (backend or "pytorch").strip().lower()

    # ── 显式指定 backend 的 fallback 链 ──────────────────────────────
    if requested in {"onnx_npu", "npu", "vitisai"}:
        # 优先 NPU；不可用时降级 ROCm → CPU
        ok, svc, hw, ep = _probe_npu_service("onnx_npu")
        if ok:
            return svc  # 已初始化，直接返回
        logger.warning("[FGR-后端] NPU 不可用，尝试 ROCm 回退...")
        ok2, svc2, hw2, ep2 = _probe_npu_service("onnx_igpu")
        if ok2:
            logger.info("[FGR-后端] 使用 ROCm (hardware={})", hw2)
            return svc2
        logger.warning("[FGR-后端] ROCm 也不可用，使用 CPU 回退")
        _, svc_cpu, _, _ = _probe_npu_service("onnx_cpu")
        return svc_cpu

    if requested in {"onnx_igpu", "rocm", "onnx_rocm", "igpu"}:
        ok, svc, hw, ep = _probe_npu_service("onnx_igpu")
        if ok:
            return svc
        logger.warning("[FGR-后端] ROCm 不可用，使用 CPU 回退")
        _, svc_cpu, _, _ = _probe_npu_service("onnx_cpu")
        return svc_cpu

    if requested in {"onnx_cpu", "cpu"}:
        ok, svc, hw, ep = _probe_npu_service("onnx_cpu")
        return svc if ok else None

    if requested == "mock":
        return None

    # ── 自动检测最佳后端（backend=None 或 pytorch/cuda）────────────
    if requested in {"pytorch", "cuda", "torch", "pytorch_cuda", ""}:
        gpu = _detect_gpu_vendor()
        if gpu == "nvidia":
            logger.info("[FGR-后端] 检测到 NVIDIA GPU，使用 CUDA/PyTorch")
            return FGRPredictor()
        if gpu == "amd":
            # AMD: 优先 NPU，回退 ROCm → CPU
            ok, svc, hw, ep = _probe_npu_service("onnx_npu")
            if ok:
                logger.info("[FGR-后端] 检测到 AMD GPU + NPU (hardware={})，使用 NPU", hw)
                return svc
            ok2, svc2, hw2, ep2 = _probe_npu_service("onnx_igpu")
            if ok2:
                logger.info("[FGR-后端] 检测到 AMD GPU + ROCm (hardware={})，使用 ROCm", hw2)
                return svc2
            logger.warning("[FGR-后端] AMD GPU NPU/ROCm 均不可用，使用 CPU 回退")
            _, svc_cpu, _, _ = _probe_npu_service("onnx_cpu")
            return svc_cpu
        # unknown / 无 GPU 或检测失败：AMD 环境下优先尝试 NPU（VitisAI 子进程独立于 torch）
        # NVIDIA 环境下回退 CPU
        logger.info("[FGR-后端] GPU 检测结果={}，优先探测 AMD NPU...", gpu)
        ok_npu, svc_npu, hw, ep = _probe_npu_service("onnx_npu")
        if ok_npu:
            logger.info("[FGR-后端] NPU 可用 (hardware={})，使用 NPU", hw)
            return svc_npu
        ok_rocm, svc_rocm, hw2, ep2 = _probe_npu_service("onnx_igpu")
        if ok_rocm:
            logger.info("[FGR-后端] ROCm 可用 (hardware={})，使用 ROCm", hw2)
            return svc_rocm
        logger.warning("[FGR-后端] NPU/ROCm 均不可用，使用 CPU 回退")
        _, svc_cpu, _, _ = _probe_npu_service("onnx_cpu")
        return svc_cpu

    raise ValueError(f"不支持的 FGR 后端: {backend}")


def get_predictor():
    """获取全局 FGR predictor 实例。"""
    return _PREDICTOR


def initialize_predictor_for_backend(backend: str | None = None):
    """按指定后端初始化全局 FGR predictor。"""
    global _PREDICTOR
    _PREDICTOR = create_predictor(backend)
    if _PREDICTOR is None:
        logger.info("FGR predictor 使用 mock 后端，跳过模型加载")
        return None
    _PREDICTOR.initialize()
    return _PREDICTOR


def initialize_predictor() -> FGRPredictor:
    """初始化现有 PyTorch/CUDA 版 FGRPredictor，保持向后兼容。"""
    return initialize_predictor_for_backend("pytorch")
