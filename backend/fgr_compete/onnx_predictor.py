"""ONNX Runtime 版 FGR 预测器，支持 AMD NPU/iGPU 后端。"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
from PIL import Image
from loguru import logger

from .config import (
    ONNX_DIR, IMG_SIZE, N_FOLDS, FOLD_WEIGHTS, USE_SVM,
)
from .features import (
    load_raw_uint8, load_mask_bool, bytes_to_raw, bytes_to_mask, extract_features,
)
from .hardware_detect import select_backend
from .svm_trainer import generate_fold_splits, load_or_train_svms


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def preprocess_roi_for_onnx(raw: np.ndarray, mask_bool: np.ndarray) -> np.ndarray:
    """复用 PyTorch predictor 的 ROI/resize/normalize 逻辑，输出 NCHW float32。"""
    img_uint8 = raw.astype(np.uint8)
    mask_f32 = mask_bool.astype(np.float32)
    roi = (img_uint8 * mask_f32).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(roi).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)

    arr = np.asarray(img).astype(np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)
    return ((arr - mean) / std)[None, ...].astype(np.float32)


def confidence_from_probability(probability: float) -> str:
    if probability >= 0.7 or probability <= 0.3:
        return "High"
    if probability >= 0.6 or probability <= 0.4:
        return "Medium"
    return "Low"


def hardware_label_for_provider(provider: str) -> str:
    labels = {
        "VitisAIExecutionProvider": "NPU/VitisAI",
        "ROCMExecutionProvider": "ROCm",
        "MIGraphXExecutionProvider": "ROCm/MIGraphX",
        "CUDAExecutionProvider": "CUDA",
        "CPUExecutionProvider": "CPU",
    }
    return labels.get(provider, provider)


class ONNXFGRPredictor:
    """FGR 5 折 ONNX 推理器（接口与 FGRPredictor 保持一致）。"""

    def __init__(self, backend: str = "onnx_npu"):
        self.requested_backend = backend
        self.actual_backend: str | None = None
        self.execution_provider: str = "CPUExecutionProvider"
        self.hardware: str = "CPU"
        self.onnx_sessions: list[Any] = []
        self.input_names: list[str] = []
        self.model_paths: list[str] = []
        self.svm_models: list = []
        self.scalers: list = []
        self._initialized = False

    def initialize(self) -> None:
        self.actual_backend = select_backend(self.requested_backend)
        self.execution_provider = self._select_provider(self.actual_backend)
        self.hardware = hardware_label_for_provider(self.execution_provider)
        self._load_onnx_models()
        if USE_SVM:
            generate_fold_splits()
            self.svm_models, self.scalers = load_or_train_svms()
        self._initialized = True
        mode = "ResNet+SVM" if USE_SVM else "纯ResNet"
        logger.info(
            "ONNXFGRPredictor 初始化完成（{}折{}集成, backend={}, provider={}）",
            N_FOLDS, mode, self.actual_backend, self.execution_provider,
        )

    def _select_provider(self, backend: str) -> str:
        providers = self._available_providers()
        if backend == "onnx_npu" and "VitisAIExecutionProvider" in providers:
            return "VitisAIExecutionProvider"
        if backend in {"onnx_npu", "onnx_igpu"}:
            for provider in ("MIGraphXExecutionProvider", "ROCMExecutionProvider"):
                if provider in providers:
                    return provider
        return "CPUExecutionProvider"

    def _available_providers(self) -> list[str]:
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError("onnxruntime 未安装，无法使用 FGR ONNX 后端") from exc
        return list(ort.get_available_providers())

    def _provider_chain(self) -> list[str]:
        providers = self._available_providers()
        chain = [self.execution_provider]
        if self.execution_provider != "CPUExecutionProvider" and "CPUExecutionProvider" in providers:
            chain.append("CPUExecutionProvider")
        return [p for p in chain if p in providers]

    def _load_onnx_models(self) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise RuntimeError("onnxruntime 未安装，无法加载 FGR ONNX 模型") from exc

        if not os.path.isdir(ONNX_DIR):
            raise FileNotFoundError(f"ONNX 模型目录不存在: {ONNX_DIR}，请先运行 python -m fgr_compete.scripts.rocm.export_onnx 或兼容入口 python -m fgr_compete.export_onnx")

        provider_chain = self._provider_chain()
        if not provider_chain:
            raise RuntimeError("ONNX Runtime 没有可用 ExecutionProvider")

        for fold_idx in range(N_FOLDS):
            base = os.path.join(ONNX_DIR, f"resnet_v9_best_fold{fold_idx + 1}.onnx")
            int8 = os.path.join(ONNX_DIR, f"resnet_v9_best_fold{fold_idx + 1}_int8.onnx")
            model_path = int8 if os.path.exists(int8) else base
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"ONNX 模型不存在: {model_path}")

            session = ort.InferenceSession(model_path, providers=provider_chain)
            input_name = session.get_inputs()[0].name
            self.onnx_sessions.append(session)
            self.input_names.append(input_name)
            self.model_paths.append(model_path)
            logger.debug("  Fold {} ONNX 加载完成: {}", fold_idx + 1, os.path.basename(model_path))

    def predict(self, image_path: str, mask_path: str) -> dict:
        raw = load_raw_uint8(image_path)
        mask = load_mask_bool(mask_path)
        return self._predict_arrays(raw, mask)

    def predict_from_bytes(self, image_bytes: bytes, mask_bytes: bytes) -> dict:
        raw = bytes_to_raw(image_bytes)
        mask = bytes_to_mask(mask_bytes)
        return self._predict_arrays(raw, mask)

    def _predict_arrays(self, raw: np.ndarray, mask_bool: np.ndarray) -> dict:
        assert self._initialized, "ONNXFGRPredictor.initialize() 必须先调用"

        hc_feat = extract_features(raw, mask_bool)
        if hc_feat is None:
            return {"error": "mask 区域太小（<100 像素），无法提取特征"}

        mask_area = int(mask_bool.sum())
        roi_area_ratio = mask_area / (raw.shape[0] * raw.shape[1])
        logger.info(
            "[FGR-特征] 图像尺寸={}x{} mask面积={}px 占比={:.2%}",
            raw.shape[1], raw.shape[0], mask_area, roi_area_ratio,
        )

        img_input = preprocess_roi_for_onnx(raw, mask_bool)
        logger.info(
            "[FGR-特征] ONNX输入 tensor shape={} mean={:.4f} std={:.4f} min={:.4f} max={:.4f}",
            img_input.shape, float(img_input.mean()), float(img_input.std()),
            float(img_input.min()), float(img_input.max()),
        )

        if USE_SVM:
            return self._predict_with_svm(img_input, hc_feat)
        return self._predict_resnet_only(img_input)

    def _run_resnet_fold(self, fold_idx: int, img_input: np.ndarray) -> float:
        output = self.onnx_sessions[fold_idx].run(None, {self.input_names[fold_idx]: img_input})[0]
        logit = float(np.asarray(output).reshape(-1)[0])
        return _sigmoid(logit)

    def _predict_resnet_only(self, img_input: np.ndarray) -> dict:
        resnet_probs = []
        for fold_idx in range(N_FOLDS):
            p = self._run_resnet_fold(fold_idx, img_input)
            resnet_probs.append(p)
            logger.info("[FGR-推理] Fold{} ONNX-ResNet={:.4f}", fold_idx + 1, p)

        ensemble_prob = float(np.mean(resnet_probs))
        resnet_std = float(np.std(resnet_probs))
        predicted_label = "FGR" if ensemble_prob >= 0.5 else "NOR"
        confidence = confidence_from_probability(ensemble_prob)
        logger.info(
            "[FGR-集成] ONNX ResNet 5折均值={:.4f}±{:.4f} 各折=[{}]",
            ensemble_prob, resnet_std,
            ", ".join(f"{p:.4f}" for p in resnet_probs),
        )

        return {
            "fold_results": [
                {
                    "fold": i + 1,
                    "p_resnet": round(p, 4),
                    "p_svm": 0.0,
                    "fusion_weight": 1.0,
                    "p_fused": round(p, 4),
                }
                for i, p in enumerate(resnet_probs)
            ],
            "ensemble_fgr_probability": round(ensemble_prob, 4),
            "predicted_label": predicted_label,
            "confidence_level": confidence,
        }

    def _predict_with_svm(self, img_input: np.ndarray, hc_feat: np.ndarray) -> dict:
        fold_results = []
        fold_fused_probs = []
        resnet_probs = []
        svm_probs = []

        for fold_idx in range(N_FOLDS):
            p_resnet = self._run_resnet_fold(fold_idx, img_input)
            resnet_probs.append(p_resnet)
            X = self.scalers[fold_idx].transform(hc_feat.reshape(1, -1))
            p_svm = self.svm_models[fold_idx].predict_proba(X)[0, 1]
            svm_probs.append(p_svm)

            w = FOLD_WEIGHTS[fold_idx]
            p_fused = w * p_resnet + (1 - w) * p_svm
            fold_fused_probs.append(p_fused)
            logger.info(
                "[FGR-推理] Fold{} ONNX-ResNet={:.4f} SVM={:.4f} w={:.2f} Fused={:.4f}",
                fold_idx + 1, p_resnet, p_svm, w, p_fused,
            )
            fold_results.append({
                "fold": fold_idx + 1,
                "p_resnet": round(p_resnet, 4),
                "p_svm": round(float(p_svm), 4),
                "fusion_weight": w,
                "p_fused": round(float(p_fused), 4),
            })

        ensemble_prob = float(np.mean(fold_fused_probs))
        return {
            "fold_results": fold_results,
            "ensemble_fgr_probability": round(ensemble_prob, 4),
            "predicted_label": "FGR" if ensemble_prob >= 0.5 else "NOR",
            "confidence_level": confidence_from_probability(ensemble_prob),
        }
