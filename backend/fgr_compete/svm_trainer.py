"""SVM 训练：fold_splits 生成、训练、joblib 缓存"""

import json
import os
import joblib
import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from loguru import logger

from .config import (
    RAW_NOR_DIR, RAW_FGR_DIR, MASK_NOR_DIR, MASK_FGR_DIR,
    CACHE_DIR, SPLITS_PATH, N_FOLDS,
)
from .features import load_raw_uint8, load_mask_bool, extract_features, build_file_pairs


def generate_fold_splits(splits_path: str = SPLITS_PATH) -> None:
    """从本地 10 张样本生成 fold_splits.json（仅在文件不存在时生成）"""
    if os.path.exists(splits_path):
        return

    nor_pairs = build_file_pairs(RAW_NOR_DIR, MASK_NOR_DIR)
    fgr_pairs = build_file_pairs(RAW_FGR_DIR, MASK_FGR_DIR)
    all_pairs = nor_pairs + fgr_pairs
    labels = [0] * len(nor_pairs) + [1] * len(fgr_pairs)

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    splits = {}
    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(all_pairs, labels)):
        splits[fold_idx] = {
            "train": [int(i) for i in train_idx],
            "val": [int(i) for i in val_idx],
        }

    os.makedirs(os.path.dirname(splits_path), exist_ok=True)
    with open(splits_path, "w") as f:
        json.dump(splits, f, indent=2)
    logger.info("已生成 fold_splits.json（{}折，共{}个样本）", N_FOLDS, len(all_pairs))


def train_and_cache_svms() -> tuple[list[SVC], list[StandardScaler]]:
    """训练 5 折 SVM 并 joblib 缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)

    nor_pairs = build_file_pairs(RAW_NOR_DIR, MASK_NOR_DIR)
    fgr_pairs = build_file_pairs(RAW_FGR_DIR, MASK_FGR_DIR)
    all_pairs = nor_pairs + fgr_pairs
    labels = np.array([0] * len(nor_pairs) + [1] * len(fgr_pairs))

    logger.info("提取 {} 个训练样本的手工特征...", len(all_pairs))
    all_features = []
    valid_idx = []
    for i, (rp, mp) in enumerate(all_pairs):
        f = extract_features(load_raw_uint8(rp), load_mask_bool(mp))
        if f is not None:
            all_features.append(f)
            valid_idx.append(i)
    X_all = np.nan_to_num(np.array(all_features))
    idx_map = {orig: new for new, orig in enumerate(valid_idx)}

    with open(SPLITS_PATH) as f:
        splits = {int(k): v for k, v in json.load(f).items()}

    svm_models = []
    scalers = []
    for fold_idx in range(N_FOLDS):
        train_orig = splits[fold_idx]["train"]
        tr_hc = [idx_map[i] for i in train_orig if i in idx_map]
        X_tr = X_all[tr_hc]
        y_tr = labels[train_orig]

        scaler = StandardScaler()
        X_tr_norm = scaler.fit_transform(X_tr)

        svm = SVC(
            kernel="rbf", C=1.0, gamma="scale",
            class_weight="balanced", probability=True, random_state=42,
        )
        svm.fit(X_tr_norm, y_tr)

        joblib.dump(svm, os.path.join(CACHE_DIR, f"svm_fold{fold_idx}.joblib"))
        joblib.dump(scaler, os.path.join(CACHE_DIR, f"scaler_fold{fold_idx}.joblib"))
        svm_models.append(svm)
        scalers.append(scaler)

    logger.info("SVM 全部 {} 折训练完成并缓存到 {}", N_FOLDS, CACHE_DIR)
    return svm_models, scalers


def load_or_train_svms() -> tuple[list[SVC], list[StandardScaler]]:
    """优先从缓存加载 SVM，缺失时重新训练"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

    all_loaded = all(
        os.path.exists(os.path.join(CACHE_DIR, f"svm_fold{i}.joblib"))
        and os.path.exists(os.path.join(CACHE_DIR, f"scaler_fold{i}.joblib"))
        for i in range(N_FOLDS)
    )

    if all_loaded:
        svm_models = []
        scalers = []
        for i in range(N_FOLDS):
            svm_models.append(joblib.load(os.path.join(CACHE_DIR, f"svm_fold{i}.joblib")))
            scalers.append(joblib.load(os.path.join(CACHE_DIR, f"scaler_fold{i}.joblib")))
        logger.info("SVM 从缓存加载完成")
        return svm_models, scalers

    return train_and_cache_svms()
