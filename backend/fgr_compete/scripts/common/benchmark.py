"""FGR 后端初始化与单次推理延迟基准。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fgr_compete.features import build_file_pairs
from fgr_compete.config import RAW_NOR_DIR, MASK_NOR_DIR
from fgr_compete.predictor import create_predictor


def benchmark_backend(backend: str, image_path: str, mask_path: str) -> dict:
    t0 = time.perf_counter()
    predictor = create_predictor(backend)
    if predictor is None:
        raise RuntimeError("mock 后端不执行真实 benchmark")
    predictor.initialize()
    init_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    result = predictor.predict(image_path, mask_path)
    infer_ms = (time.perf_counter() - t1) * 1000

    return {
        "backend": backend,
        "hardware": getattr(predictor, "hardware", "unknown"),
        "init_ms": round(init_ms, 2),
        "infer_ms": round(infer_ms, 2),
        "probability": result.get("ensemble_fgr_probability"),
    }


def main(default_backend: str = "pytorch") -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=default_backend, help="pytorch/cuda/rocm/onnx_npu/onnx_igpu/onnx_cpu")
    parser.add_argument("--image")
    parser.add_argument("--mask")
    args = parser.parse_args()

    image_path = args.image
    mask_path = args.mask
    if not image_path or not mask_path:
        pairs = build_file_pairs(RAW_NOR_DIR, MASK_NOR_DIR)
        if not pairs:
            raise RuntimeError("未找到默认 benchmark 样本，请通过 --image/--mask 指定")
        image_path, mask_path = pairs[0]

    print(benchmark_backend(args.backend, image_path, mask_path))


if __name__ == "__main__":
    main()
