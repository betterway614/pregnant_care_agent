"""路径常量与超参数配置（所有路径相对于本模块目录解析）"""
import os
import torch

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# 模型权重目录
MODEL_DIR = os.path.join(MODULE_DIR, "0.701_515pth")

# ONNX 模型目录（由 scripts/rocm/export_onnx.py / scripts/ryzen_ai/quantize_onnx.py 生成）
ONNX_DIR = os.path.join(MODULE_DIR, "onnx_resnet")

# SVM 训练数据
RAW_NOR_DIR = os.path.join(MODULE_DIR, "photo", "raw", "nor")
RAW_FGR_DIR = os.path.join(MODULE_DIR, "photo", "raw", "fgr")
MASK_NOR_DIR = os.path.join(MODULE_DIR, "photo", "mask", "nor")
MASK_FGR_DIR = os.path.join(MODULE_DIR, "photo", "mask", "fgr")

# SVM 缓存
CACHE_DIR = os.path.join(MODULE_DIR, "cache")

# fold_splits.json 路径
SPLITS_PATH = os.path.join(MODULE_DIR, "fold_splits.json")

# 设备
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 图像与模型参数
IMG_SIZE = 224
N_FOLDS = 5

# 是否启用 SVM 融合（当前 SVM 训练数据不足，关闭后纯用 ResNet 5折集成）
USE_SVM = False

# 各折融合权重（来自最优运行的 w 值）
FOLD_WEIGHTS = [0.55, 0.70, 0.20, 0.85, 0.65]

# 20 个稳定手工特征名称
STABLE_FEATURES = [
    'raw_mean', 'raw_p75', 'raw_p90', 'raw_b50', 'raw_b65', 'raw_b80',
    'clahe_p75', 'clahe_p90', 'clahe_b65', 'lbp_r2_mean', 'lbp_r3_mean',
    'raw_kurt', 'lbp_r1_std', 'lbp_r1_entropy', 'lbp_r2_std',
    'raw_p50', 'raw_iqr', 'clahe_std', 'lbp_r3_std', 'clahe_mean',
]
