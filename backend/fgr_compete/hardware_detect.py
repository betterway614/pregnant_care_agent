"""FGR 硬件后端检测与选择。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from loguru import logger

FGRBackend = Literal["pytorch", "onnx_npu", "onnx_igpu", "onnx_cpu", "mock"]


@lru_cache(maxsize=1)
def _available_onnx_providers() -> tuple[str, ...]:
    try:
        import onnxruntime as ort
    except Exception as exc:
        logger.debug("[FGR-硬件] onnxruntime 不可用: {}", exc)
        return ()
    providers = tuple(ort.get_available_providers())
    logger.debug("[FGR-硬件] ONNX Runtime providers: {}", providers)
    return providers


def detect_npu() -> bool:
    """检查 VitisAIExecutionProvider 是否可用。"""
    return "VitisAIExecutionProvider" in _available_onnx_providers()


def detect_rocm() -> bool:
    """检查 ONNX Runtime AMD GPU provider 是否可用。"""
    providers = _available_onnx_providers()
    return "ROCMExecutionProvider" in providers or "MIGraphXExecutionProvider" in providers


def select_backend(configured: str) -> FGRBackend:
    """解析配置并选择实际后端。

    回退链:
    - onnx_npu/npu: VitisAI -> ROCm -> CPU
    - rocm/onnx_igpu: MIGraphX/ROCm -> CPU
    - cuda/pytorch: 现有 PyTorch 路径
    """
    value = (configured or "pytorch").strip().lower()

    if value in {"pytorch", "cuda", "torch", "pytorch_cuda"}:
        return "pytorch"
    if value == "mock":
        return "mock"
    if value in {"onnx_cpu", "cpu"}:
        return "onnx_cpu"
    if value in {"onnx_igpu", "rocm", "onnx_rocm", "igpu"}:
        if detect_rocm():
            return "onnx_igpu"
        logger.warning("[FGR-硬件] ROCm provider 不可用，FGR ONNX 后端回退到 CPU")
        return "onnx_cpu"
    if value in {"onnx_npu", "npu", "vitisai"}:
        if detect_npu():
            return "onnx_npu"
        if detect_rocm():
            logger.warning("[FGR-硬件] VitisAI provider 不可用，FGR 后端回退到 ROCm")
            return "onnx_igpu"
        logger.warning("[FGR-硬件] VitisAI/ROCm provider 均不可用，FGR ONNX 后端回退到 CPU")
        return "onnx_cpu"

    raise ValueError(f"不支持的 FGR 后端: {configured}")
