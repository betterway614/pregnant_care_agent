"""路径常量与超参数配置（所有路径相对于本模块目录解析）"""
import os
import torch

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# 模型权重目录
MODEL_DIR = os.path.join(MODULE_DIR, "0.701_515pth")

# ONNX 模型目录（由 scripts/rocm/export_onnx.py / scripts/ryzen_ai/quantize_onnx.py 生成）
ONNX_DIR = os.path.join(MODULE_DIR, "onnx_resnet")

# 设备
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 图像与模型参数
IMG_SIZE = 224
N_FOLDS = 5

