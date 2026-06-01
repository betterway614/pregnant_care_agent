"""FGR ONNX推理延迟基准测试"""
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np

def benchmark_fgr():
    from fgr_compete.onnx_predictor import ONNXFGRPredictor
    from fgr_compete.config import ONNX_DIR

    print(f"ONNX模型目录: {ONNX_DIR}")
    print(f"模型文件: {os.listdir(ONNX_DIR) if os.path.isdir(ONNX_DIR) else 'NOT FOUND'}")

    try:
        predictor = ONNXFGRPredictor(backend="onnx_cpu")
        predictor.initialize()
    except Exception as e:
        print(f"初始化失败: {e}")
        print("请先运行: python -m fgr_compete.quantize_onnx 生成INT8模型")
        return

    dummy_raw = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
    dummy_mask = np.ones((256, 256), dtype=bool)

    N, WARMUP = 20, 3
    # Warmup
    for _ in range(WARMUP):
        predictor.predict(dummy_raw, dummy_mask)

    times = []
    for _ in range(N):
        t0 = time.perf_counter()
        predictor.predict(dummy_raw, dummy_mask)
        times.append(time.perf_counter() - t0)

    avg = np.mean(times) * 1000
    p50 = np.percentile(times, 50) * 1000
    p95 = np.percentile(times, 95) * 1000
    print(f"\nFGR ONNX推理 ({predictor.model_paths[0].split('/')[-1]}):")
    print(f"  avg={avg:.1f}ms  p50={p50:.1f}ms  p95={p95:.1f}ms  ({N} runs)")

if __name__ == "__main__":
    benchmark_fgr()
