"""使用 AMD Quark 对 FGR ONNX 模型进行 XINT8 PTQ 量化。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fgr_compete.config import ONNX_DIR, N_FOLDS, RAW_NOR_DIR, RAW_FGR_DIR, MASK_NOR_DIR, MASK_FGR_DIR
from fgr_compete.features import build_file_pairs, load_raw_uint8, load_mask_bool
from fgr_compete.onnx_predictor import preprocess_roi_for_onnx


def _calibration_arrays() -> list[np.ndarray]:
    pairs = build_file_pairs(RAW_NOR_DIR, MASK_NOR_DIR) + build_file_pairs(RAW_FGR_DIR, MASK_FGR_DIR)
    arrays = []
    for raw_path, mask_path in pairs:
        arrays.append(preprocess_roi_for_onnx(load_raw_uint8(raw_path), load_mask_bool(mask_path)))
    if not arrays:
        raise RuntimeError("未找到量化校准图片，请检查 fgr_compete/photo/raw 与 photo/mask")
    return arrays


class CalibrationDataReader:
    def __init__(self, input_name: str, samples: list[np.ndarray]):
        self.input_name = input_name
        self._samples = list(samples)
        self._iterator = iter(self._samples)

    def get_next(self) -> dict[str, np.ndarray] | None:
        try:
            return {self.input_name: next(self._iterator)}
        except StopIteration:
            return None

    def rewind(self) -> None:
        self._iterator = iter(self._samples)


def _load_quark_quantizer():
    try:
        from quark.onnx import ModelQuantizer, get_default_config
    except Exception as exc:
        raise RuntimeError(
            "AMD Quark 未安装或版本不兼容。请按 Ryzen AI SDK 文档安装 Quark 后重试。"
        ) from exc
    return ModelQuantizer, get_default_config


def _validate_quantized(fp32_path: str, int8_path: str, samples: list[np.ndarray], max_delta: float = 0.05) -> None:
    import onnxruntime as ort

    fp32_session = ort.InferenceSession(fp32_path, providers=["CPUExecutionProvider"])
    int8_session = ort.InferenceSession(int8_path, providers=["CPUExecutionProvider"])
    fp32_input = fp32_session.get_inputs()[0].name
    int8_input = int8_session.get_inputs()[0].name
    deltas = []
    for sample in samples:
        fp32_logit = float(np.asarray(fp32_session.run(None, {fp32_input: sample})[0]).reshape(-1)[0])
        int8_logit = float(np.asarray(int8_session.run(None, {int8_input: sample})[0]).reshape(-1)[0])
        fp32_prob = 1.0 / (1.0 + np.exp(-fp32_logit))
        int8_prob = 1.0 / (1.0 + np.exp(-int8_logit))
        deltas.append(abs(fp32_prob - int8_prob))
    worst = max(deltas)
    if worst > max_delta:
        raise RuntimeError(f"INT8 量化精度下降过大: max_delta={worst:.4f} > {max_delta:.4f}")


def quantize_all() -> list[str]:
    ModelQuantizer, get_default_config = _load_quark_quantizer()
    samples = _calibration_arrays()
    quantized_paths = []

    for fold_idx in range(N_FOLDS):
        fp32_path = os.path.join(ONNX_DIR, f"resnet_v9_best_fold{fold_idx + 1}.onnx")
        int8_path = os.path.join(ONNX_DIR, f"resnet_v9_best_fold{fold_idx + 1}_int8.onnx")
        if not os.path.exists(fp32_path):
            raise FileNotFoundError(f"ONNX 模型不存在: {fp32_path}，请先运行 python -m fgr_compete.export_onnx")

        import onnxruntime as ort
        session = ort.InferenceSession(fp32_path, providers=["CPUExecutionProvider"])
        reader = CalibrationDataReader(session.get_inputs()[0].name, samples)
        config = get_default_config("XINT8")
        quantizer = ModelQuantizer(config)
        quantizer.quantize_model(fp32_path, int8_path, calibration_data_reader=reader)
        _validate_quantized(fp32_path, int8_path, samples)
        quantized_paths.append(int8_path)
        print(f"[OK] fold{fold_idx + 1}: {int8_path}")

    return quantized_paths


if __name__ == "__main__":
    quantize_all()
