"""图像加载与手工特征提取"""

import io
import os
import numpy as np
from PIL import Image
import cv2
from scipy import stats
from skimage.feature import local_binary_pattern

# 20 个稳定手工特征名称（特征提取顺序）
STABLE_FEATURES = [
    'raw_mean', 'raw_p75', 'raw_p90', 'raw_b50', 'raw_b65', 'raw_b80',
    'clahe_p75', 'clahe_p90', 'clahe_b65', 'lbp_r2_mean', 'lbp_r3_mean',
    'raw_kurt', 'lbp_r1_std', 'lbp_r1_entropy', 'lbp_r2_std',
    'raw_p50', 'raw_iqr', 'clahe_std', 'lbp_r3_std', 'clahe_mean',
]


def load_raw_uint8(path: str) -> np.ndarray:
    """加载灰度图，resize 到 512x512，返回 uint8 数组"""
    return np.array(
        Image.open(path).convert("L").resize((512, 512), Image.BILINEAR)
    ).astype(np.uint8)


def load_mask_bool(path: str) -> np.ndarray:
    """加载 mask，resize 到 512x512，二值化，返回 bool 数组"""
    arr = np.array(
        Image.open(path).convert("L").resize((512, 512), Image.NEAREST)
    ).astype(np.float32)
    if arr.max() <= 1.0:
        arr *= 255.0
    return (arr > 127).astype(bool)


def bytes_to_raw(data: bytes) -> np.ndarray:
    """从字节数据加载灰度图，返回 uint8 数组"""
    return np.array(
        Image.open(io.BytesIO(data)).convert("L").resize((512, 512), Image.BILINEAR)
    ).astype(np.uint8)


def bytes_to_mask(data: bytes) -> np.ndarray:
    """从字节数据加载 mask，返回 bool 数组"""
    arr = np.array(
        Image.open(io.BytesIO(data)).convert("L").resize((512, 512), Image.NEAREST)
    ).astype(np.float32)
    if arr.max() <= 1.0:
        arr *= 255.0
    return (arr > 127).astype(bool)


def extract_features(img_uint8: np.ndarray, mask_bool: np.ndarray) -> np.ndarray | None:
    """提取 20 维手工特征向量，若 mask 区域 <100 像素则返回 None"""
    mask_area = int(mask_bool.sum())
    if mask_area < 100:
        return None

    img_roi = img_uint8.copy()
    img_roi[~mask_bool] = 0

    # CLAHE 增强
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_clahe = clahe.apply(img_roi)

    # 前景像素
    fg_raw = img_uint8.astype(np.float32)[mask_bool] / 255.0
    fg_clahe = img_clahe.astype(np.float32)[mask_bool] / 255.0

    # 前景像素统计摘要
    from loguru import logger
    logger.debug(
        "[FGR-特征提取] mask面积={} 前景raw均值={:.4f}±{:.4f} clahe均值={:.4f}±{:.4f} "
        "raw中位数={:.4f} raw_p90={:.4f}",
        mask_area,
        float(fg_raw.mean()), float(fg_raw.std()),
        float(fg_clahe.mean()), float(fg_clahe.std()),
        float(np.percentile(fg_raw, 50)), float(np.percentile(fg_raw, 90)),
    )

    # LBP 特征（半径 1, 2, 3）
    lbp_feats = {}
    for r in [1, 2, 3]:
        lbp = local_binary_pattern(img_clahe, 8 * r, r, method='uniform')
        fg_lbp = lbp[mask_bool]
        lbp_feats[f'lbp_r{r}_mean'] = float(fg_lbp.mean())
        lbp_feats[f'lbp_r{r}_std'] = float(fg_lbp.std())
        lbp_feats[f'lbp_r{r}_entropy'] = float(
            stats.entropy(np.histogram(fg_lbp, bins=20)[0] + 1e-8)
        )

    all_f = {
        'raw_mean': float(fg_raw.mean()),
        'raw_p50': float(np.percentile(fg_raw, 50)),
        'raw_p75': float(np.percentile(fg_raw, 75)),
        'raw_p90': float(np.percentile(fg_raw, 90)),
        'raw_kurt': float(stats.kurtosis(fg_raw)),
        'raw_iqr': float(np.percentile(fg_raw, 75) - np.percentile(fg_raw, 25)),
        'raw_b50': float((fg_raw > 0.50).mean()),
        'raw_b65': float((fg_raw > 0.65).mean()),
        'raw_b80': float((fg_raw > 0.80).mean()),
        'clahe_mean': float(fg_clahe.mean()),
        'clahe_std': float(fg_clahe.std()),
        'clahe_p75': float(np.percentile(fg_clahe, 75)),
        'clahe_p90': float(np.percentile(fg_clahe, 90)),
        'clahe_b65': float((fg_clahe > 0.65).mean()),
        **lbp_feats,
    }
    return np.array([all_f[k] for k in STABLE_FEATURES], dtype=np.float32)


def build_file_pairs(raw_dir: str, mask_dir: str) -> list[tuple[str, str]]:
    """构建 (raw_path, mask_path) 配对列表"""
    mask_files = {
        f.replace('.png', ''): os.path.join(mask_dir, f)
        for f in os.listdir(mask_dir) if f.endswith('.png')
    }
    pairs = []
    for raw_f in sorted(os.listdir(raw_dir)):
        if not raw_f.endswith('.png'):
            continue
        key = raw_f.replace('_0000.png', '') if raw_f.endswith('_0000.png') else raw_f.replace('.png', '')
        if key in mask_files:
            pairs.append((os.path.join(raw_dir, raw_f), mask_files[key]))
    return pairs
