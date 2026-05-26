"""单张 FGR 分类推理脚本，共用于 CUDA/ROCm/Ryzen AI 包装入口。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fgr_compete.predictor import create_predictor


def _print_result(result: dict) -> None:
    if "error" in result:
        print(f"预测失败: {result['error']}")
        return

    print()
    print("=" * 60)
    print("  各折预测详情")
    print("=" * 60)
    print(f"{'Fold':<6} {'ResNet概率':<12} {'SVM概率':<12} {'权重w':<8} {'融合概率':<10}")
    print("-" * 60)
    for fr in result["fold_results"]:
        print(
            f"  {fr['fold']:<4} {fr['p_resnet']:<12.4f} {fr['p_svm']:<12.4f} "
            f"{fr['fusion_weight']:<8.2f} {fr['p_fused']:<10.4f}"
        )

    print()
    print("=" * 60)
    print("  最终预测结果（5折集成平均）")
    print("=" * 60)
    print(f"  FGR概率: {result['ensemble_fgr_probability']:.4f}")
    print(f"  预测标签: {result['predicted_label']}")
    print(f"  置信度: {result['confidence_level']}")
    print("=" * 60)
    print()


def predict_single(backend: str, image_path: str, mask_path: str) -> dict:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图像不存在: {image_path}")
    if not os.path.exists(mask_path):
        raise FileNotFoundError(f"mask 不存在: {mask_path}")

    print()
    print("=" * 60)
    print("  FGR预测系统 - 5折集成模型")
    print("=" * 60)
    print(f"后端: {backend}")
    print(f"输入图像: {os.path.basename(image_path)}")
    print(f"输入mask: {os.path.basename(mask_path)}")
    print()

    predictor = create_predictor(backend)
    if predictor is None:
        raise RuntimeError("mock 后端不执行真实图片推理")
    print(f"初始化FGR预测器（backend={backend}）...")
    predictor.initialize()
    print(f"实际硬件: {getattr(predictor, 'hardware', 'unknown')}")

    print()
    print("开始预测...")
    result = predictor.predict(image_path, mask_path)
    _print_result(result)
    return result


def main(default_backend: str = "pytorch") -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="原始超声图像路径")
    parser.add_argument("mask", help="胎盘分割 mask 路径")
    parser.add_argument("--backend", default=default_backend, help="pytorch/cuda/rocm/onnx_npu/onnx_igpu/onnx_cpu")
    args = parser.parse_args()
    predict_single(args.backend, args.image, args.mask)


if __name__ == "__main__":
    main()
