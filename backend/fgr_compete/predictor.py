"""FGRPredictor 门面类：封装 5 折集成预测流程"""

import os
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from loguru import logger

from .config import (
    MODEL_DIR, DEVICE, IMG_SIZE, N_FOLDS, FOLD_WEIGHTS, USE_SVM,
)
from .model import ResNet18DualFusion
from .features import (
    load_raw_uint8, load_mask_bool, bytes_to_raw, bytes_to_mask, extract_features,
)
from .svm_trainer import generate_fold_splits, load_or_train_svms


class FGRPredictor:
    """FGR 5 折集成预测器（ResNet + SVM）"""

    def __init__(self):
        self.resnet_models: list[torch.nn.Module] = []
        self.svm_models: list = []
        self.scalers: list = []
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
        """完整初始化：加载 5 个 ResNet，可选 SVM"""
        self._load_resnet_models()
        if USE_SVM:
            generate_fold_splits()
            self.svm_models, self.scalers = load_or_train_svms()
        self._initialized = True
        mode = "ResNet+SVM" if USE_SVM else "纯ResNet"
        logger.info("FGRPredictor 初始化完成（{}折{}集成, device={}）", N_FOLDS, mode, DEVICE)

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

        if USE_SVM:
            return self._predict_with_svm(img_tensor, hc_feat)
        else:
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
                "p_svm": 0.0,
                "fusion_weight": 1.0,
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

    def _predict_with_svm(self, img_tensor: torch.Tensor, hc_feat: np.ndarray) -> dict:
        """ResNet + SVM 融合 5 折集成预测"""
        fold_results = []
        fold_fused_probs = []
        resnet_probs = []
        svm_probs = []
        for fold_idx in range(N_FOLDS):
            with torch.no_grad():
                logit = self.resnet_models[fold_idx](img_tensor)
                p_resnet = torch.sigmoid(logit).item()
            resnet_probs.append(p_resnet)

            X = self.scalers[fold_idx].transform(hc_feat.reshape(1, -1))
            logger.debug(
                "[FGR-推理] Fold{} Scaler变换后前5维: {}",
                fold_idx + 1, [round(float(v), 4) for v in X[0, :5]],
            )
            p_svm = self.svm_models[fold_idx].predict_proba(X)[0, 1]
            svm_probs.append(p_svm)

            w = FOLD_WEIGHTS[fold_idx]
            p_fused = w * p_resnet + (1 - w) * p_svm
            fold_fused_probs.append(p_fused)

            logger.info(
                "[FGR-推理] Fold{} ResNet={:.4f} SVM={:.4f} w={:.2f} Fused={:.4f}",
                fold_idx + 1, p_resnet, p_svm, w, p_fused,
            )

            fold_results.append({
                "fold": fold_idx + 1,
                "p_resnet": round(p_resnet, 4),
                "p_svm": round(p_svm, 4),
                "fusion_weight": w,
                "p_fused": round(p_fused, 4),
            })

        ensemble_prob = float(np.mean(fold_fused_probs))
        predicted_label = "FGR" if ensemble_prob >= 0.5 else "NOR"

        resnet_mean = float(np.mean(resnet_probs))
        resnet_std = float(np.std(resnet_probs))
        svm_mean = float(np.mean(svm_probs))
        svm_std = float(np.std(svm_probs))
        logger.info(
            "[FGR-集成] ResNet均值={:.4f}±{:.4f} SVM均值={:.4f}±{:.4f} 集成概率={:.4f}",
            resnet_mean, resnet_std, svm_mean, svm_std, ensemble_prob,
        )

        resnet_label = "FGR" if resnet_mean >= 0.5 else "NOR"
        svm_label = "FGR" if svm_mean >= 0.5 else "NOR"
        if resnet_label != svm_label:
            logger.warning(
                "[FGR-分歧] ResNet倾向={} ({:.4f}) SVM倾向={} ({:.4f}) 两模型意见不一致!",
                resnet_label, resnet_mean, svm_label, svm_mean,
            )

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

        return {
            "fold_results": fold_results,
            "ensemble_fgr_probability": round(ensemble_prob, 4),
            "predicted_label": predicted_label,
            "confidence_level": confidence,
        }


# 模块级单例
_PREDICTOR = None


def create_predictor(backend: str | None = None):
    """按配置创建 FGR predictor，保留 PyTorch/CUDA 路径并扩展 ONNX ROCm/NPU。"""
    from .hardware_detect import select_backend

    actual_backend = select_backend(backend or "pytorch")
    if actual_backend == "pytorch":
        return FGRPredictor()
    if actual_backend in {"onnx_npu", "onnx_igpu", "onnx_cpu"}:
        from .onnx_predictor import ONNXFGRPredictor
        return ONNXFGRPredictor(actual_backend)
    if actual_backend == "mock":
        return None
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
