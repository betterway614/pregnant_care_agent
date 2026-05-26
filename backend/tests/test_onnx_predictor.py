"""ONNX FGR predictor 轻量单元测试。"""
import os
import sys
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("torch")

from fgr_compete import hardware_detect
from fgr_compete.onnx_predictor import ONNXFGRPredictor


class _FakeInput:
    name = "input"


class _FakeSession:
    def __init__(self, logit: float):
        self.logit = logit

    def get_inputs(self):
        return [_FakeInput()]

    def run(self, _outputs, feed):
        assert "input" in feed
        assert feed["input"].shape == (1, 3, 224, 224)
        return [np.asarray([[self.logit]], dtype=np.float32)]


def _make_raw_mask_arrays():
    raw = np.full((512, 512), 100, dtype=np.uint8)
    raw[160:360, 180:340] = 180
    mask = np.zeros((512, 512), dtype=bool)
    mask[160:360, 180:340] = True
    return raw, mask


def _png_bytes(array: np.ndarray) -> bytes:
    buf = BytesIO()
    Image.fromarray(array.astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def _initialized_predictor() -> ONNXFGRPredictor:
    predictor = ONNXFGRPredictor("onnx_cpu")
    predictor.onnx_sessions = [_FakeSession(v) for v in [-1.0, -0.5, 0.0, 0.5, 1.0]]
    predictor.input_names = ["input"] * 5
    predictor.execution_provider = "CPUExecutionProvider"
    predictor.hardware = "CPU"
    predictor._initialized = True
    return predictor


def test_onnx_predictor_predict_returns_required_keys():
    raw, mask = _make_raw_mask_arrays()
    result = _initialized_predictor()._predict_arrays(raw, mask)

    assert set(result) >= {
        "fold_results",
        "ensemble_fgr_probability",
        "predicted_label",
        "confidence_level",
    }
    assert len(result["fold_results"]) == 5
    assert result["predicted_label"] in {"FGR", "NOR"}


def test_onnx_predictor_predict_from_bytes_matches_arrays():
    raw, mask = _make_raw_mask_arrays()
    mask_uint8 = (mask.astype(np.uint8) * 255)
    predictor = _initialized_predictor()

    from_arrays = predictor._predict_arrays(raw, mask)
    from_bytes = predictor.predict_from_bytes(_png_bytes(raw), _png_bytes(mask_uint8))

    assert from_bytes["ensemble_fgr_probability"] == from_arrays["ensemble_fgr_probability"]
    assert from_bytes["fold_results"] == from_arrays["fold_results"]


def test_select_backend_npu_falls_back_to_cpu(monkeypatch):
    hardware_detect._available_onnx_providers.cache_clear()
    monkeypatch.setattr(hardware_detect, "_available_onnx_providers", lambda: ("CPUExecutionProvider",))

    assert hardware_detect.select_backend("onnx_npu") == "onnx_cpu"


def test_select_backend_rocm_alias(monkeypatch):
    hardware_detect._available_onnx_providers.cache_clear()
    monkeypatch.setattr(
        hardware_detect,
        "_available_onnx_providers",
        lambda: ("MIGraphXExecutionProvider", "CPUExecutionProvider"),
    )

    assert hardware_detect.select_backend("rocm") == "onnx_igpu"
