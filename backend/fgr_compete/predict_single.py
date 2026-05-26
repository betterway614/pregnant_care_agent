# /media/dglguser/datadisk/workspace/swan/nnUNet/classify/predict_single.py
# 单张图片FGR预测：输入一张NT期胎盘超声图，输出FGR风险预测

import os
import sys

# 确保 backend 目录在 path 中（以便在项目根目录外也能运行）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fgr_compete.predictor import FGRPredictor


def main():
    if len(sys.argv) < 3:
        print("用法：")
        print("  python predict_single.py <image_path> <mask_path>")
        print("示例：")
        print("  python predict_single.py /path/to/image.png /path/to/mask.png")
        sys.exit(1)

    image_path = sys.argv[1]
    mask_path = sys.argv[2]

    if not os.path.exists(image_path):
        print(f"错误：图像不存在 {image_path}")
        sys.exit(1)
    if not os.path.exists(mask_path):
        print(f"错误：mask不存在 {mask_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  FGR预测系统 - 5折集成模型")
    print(f"{'='*60}")
    print(f"输入图像: {os.path.basename(image_path)}")
    print(f"输入mask: {os.path.basename(mask_path)}\n")

    # 初始化预测器
    print("初始化FGR预测器（加载ResNet + SVM）...")
    predictor = FGRPredictor()
    predictor.initialize()

    # 预测
    print(f"\n开始预测...")
    result = predictor.predict(image_path, mask_path)

    if "error" in result:
        print(f"预测失败: {result['error']}")
        return

    # 输出结果
    print(f"\n{'='*60}")
    print(f"  各折预测详情")
    print(f"{'='*60}")
    print(f"{'Fold':<6} {'ResNet概率':<12} {'SVM概率':<12} {'权重w':<8} {'融合概率':<10}")
    print("-" * 60)
    for fr in result["fold_results"]:
        print(f"  {fr['fold']:<4} {fr['p_resnet']:<12.4f} {fr['p_svm']:<12.4f} "
              f"{fr['fusion_weight']:<8.2f} {fr['p_fused']:<10.4f}")

    print(f"\n{'='*60}")
    print(f"  最终预测结果（5折集成平均）")
    print(f"{'='*60}")
    print(f"  FGR概率: {result['ensemble_fgr_probability']:.4f}")
    print(f"  预测标签: {result['predicted_label']}")
    print(f"  置信度: {result['confidence_level']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
