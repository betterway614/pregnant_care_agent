"""FGR 算法诊断工具：批量运行所有样本，收集精度、特征、各折预测详情"""
import json
import os
import sys
from pathlib import Path
import time
import csv
from datetime import datetime

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_FGR_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np
from loguru import logger

from fgr_compete.predictor import FGRPredictor
from fgr_compete.features import load_raw_uint8, load_mask_bool, extract_features
from fgr_compete.config import RAW_NOR_DIR, RAW_FGR_DIR, MASK_NOR_DIR, MASK_FGR_DIR, STABLE_FEATURES
from fgr_compete.image_registry import get_image_pairs, get_patient_images, load_patient_map


def run_diagnostic(output_dir: str | None = None):
    """运行完整诊断，生成详细报告"""
    if output_dir is None:
        output_dir = os.path.join(_FGR_DIR, "diagnostic_reports")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"fgr_diagnostic_{timestamp}.json")
    csv_path = os.path.join(output_dir, f"fgr_diagnostic_{timestamp}.csv")
    log_path = os.path.join(output_dir, f"fgr_diagnostic_{timestamp}.log")

    # 配置 loguru 同时输出到文件和控制台
    logger.add(log_path, level="DEBUG", format="{time} | {level: <8} | {message}")

    logger.info("=" * 70)
    logger.info("FGR 算法诊断报告 - {}", timestamp)
    logger.info("=" * 70)

    # 初始化预测器
    logger.info("初始化 FGRPredictor...")
    t0 = time.perf_counter()
    predictor = FGRPredictor()
    predictor.initialize()
    init_time = (time.perf_counter() - t0) * 1000
    logger.info("初始化完成，耗时 {:.0f}ms", init_time)

    # 收集所有样本
    nor_pairs, fgr_pairs = get_image_pairs()
    all_samples = []
    for raw_path, mask_path in nor_pairs:
        all_samples.append(("NOR", raw_path, mask_path, os.path.basename(raw_path)))
    for raw_path, mask_path in fgr_pairs:
        all_samples.append(("FGR", raw_path, mask_path, os.path.basename(raw_path)))

    logger.info("共 {} 个样本 (NOR={}, FGR={})", len(all_samples), len(nor_pairs), len(fgr_pairs))

    # 逐样本预测
    results = []
    correct = 0
    total_elapsed = 0.0

    for idx, (true_label, raw_path, mask_path, filename) in enumerate(all_samples):
        logger.info("-" * 60)
        logger.info("[样本 {}/{}] {} (真实标签={})", idx + 1, len(all_samples), filename, true_label)

        # 加载图像并提取特征
        raw = load_raw_uint8(raw_path)
        mask = load_mask_bool(mask_path)
        hc_feat = extract_features(raw, mask)

        # 预测
        t_start = time.perf_counter()
        result = predictor.predict(raw_path, mask_path)
        elapsed = (time.perf_counter() - t_start) * 1000
        total_elapsed += elapsed

        if "error" in result:
            logger.error("  预测失败: {}", result["error"])
            results.append({
                "filename": filename,
                "true_label": true_label,
                "predicted_label": "ERROR",
                "fgr_probability": None,
                "confidence_level": "ERROR",
                "elapsed_ms": elapsed,
                "error": result["error"],
            })
            continue

        # 判断是否正确
        is_correct = result["predicted_label"] == true_label
        if is_correct:
            correct += 1

        logger.info(
            "  预测结果: {} (prob={:.4f}) 真实: {} {} conf={} 耗时={:.0f}ms",
            result["predicted_label"], result["ensemble_fgr_probability"],
            true_label, "✓" if is_correct else "✗",
            result["confidence_level"], elapsed,
        )

        # 各折详情
        for fr in result["fold_results"]:
            logger.info(
                "    Fold{}: ResNet={:.4f} SVM={:.4f} w={:.2f} Fused={:.4f}",
                fr["fold"], fr["p_resnet"], fr["p_svm"],
                fr["fusion_weight"], fr["p_fused"],
            )

        # ResNet 和 SVM 分别平均
        r_mean = np.mean([f["p_resnet"] for f in result["fold_results"]])
        s_mean = np.mean([f["p_svm"] for f in result["fold_results"]])
        r_label = "FGR" if r_mean >= 0.5 else "NOR"
        s_label = "FGR" if s_mean >= 0.5 else "NOR"
        logger.info(
            "  汇总: ResNet平均={:.4f}→{} | SVM平均={:.4f}→{} | 集成={:.4f}→{}",
            r_mean, r_label, s_mean, s_label,
            result["ensemble_fgr_probability"], result["predicted_label"],
        )

        # 构建结果条目
        entry = {
            "filename": filename,
            "true_label": true_label,
            "predicted_label": result["predicted_label"],
            "fgr_probability": result["ensemble_fgr_probability"],
            "confidence_level": result["confidence_level"],
            "is_correct": is_correct,
            "elapsed_ms": elapsed,
            "resnet_mean": round(r_mean, 4),
            "svm_mean": round(s_mean, 4),
            "fold_details": result["fold_results"],
            "features": {k: round(float(v), 4) for k, v in zip(STABLE_FEATURES, hc_feat)} if hc_feat is not None else None,
        }
        results.append(entry)

    # ========== 汇总统计 ==========
    accuracy = correct / len(all_samples) if all_samples else 0
    avg_time = total_elapsed / len(all_samples) if all_samples else 0

    logger.info("=" * 70)
    logger.info("诊断汇总")
    logger.info("=" * 70)
    logger.info("总样本数: {}", len(all_samples))
    logger.info("正确数: {}/{}", correct, len(all_samples))
    logger.info("准确率: {:.2%}", accuracy)
    logger.info("平均推理时间: {:.0f}ms", avg_time)

    # 按类别统计
    for label in ["NOR", "FGR"]:
        subset = [r for r in results if r.get("true_label") == label and r.get("fgr_probability") is not None]
        if subset:
            subset_correct = sum(1 for r in subset if r["is_correct"])
            probs = [r["fgr_probability"] for r in subset]
            logger.info(
                "  {}: 准确率={}/{}={:.2%} 平均FGR概率={:.4f}±{:.4f} 概率范围=[{:.4f}, {:.4f}]",
                label, subset_correct, len(subset), subset_correct / len(subset),
                np.mean(probs), np.std(probs), min(probs), max(probs),
            )

    # 混淆矩阵
    logger.info("混淆矩阵:")
    nor_as_nor = sum(1 for r in results if r.get("true_label") == "NOR" and r.get("predicted_label") == "NOR")
    nor_as_fgr = sum(1 for r in results if r.get("true_label") == "NOR" and r.get("predicted_label") == "FGR")
    fgr_as_nor = sum(1 for r in results if r.get("true_label") == "FGR" and r.get("predicted_label") == "NOR")
    fgr_as_fgr = sum(1 for r in results if r.get("true_label") == "FGR" and r.get("predicted_label") == "FGR")
    logger.info("           预测NOR  预测FGR")
    logger.info("  真实NOR    {}        {}", nor_as_nor, nor_as_fgr)
    logger.info("  真实FGR    {}        {}", fgr_as_nor, fgr_as_fgr)

    # 错误分析
    errors = [r for r in results if not r.get("is_correct") and r.get("fgr_probability") is not None]
    if errors:
        logger.info("错误样本详情:")
        for e in errors:
            logger.info(
                "  {} 真实={} 预测={} prob={:.4f} conf={}",
                e["filename"], e["true_label"], e["predicted_label"],
                e["fgr_probability"], e["confidence_level"],
            )

    # ResNet vs SVM 分歧分析
    r_correct = sum(1 for r in results if r.get("resnet_mean", 0) >= 0.5 and r.get("true_label") == "FGR"
                    or r.get("resnet_mean", 0) < 0.5 and r.get("true_label") == "NOR")
    s_correct = sum(1 for r in results if r.get("svm_mean", 0) >= 0.5 and r.get("true_label") == "FGR"
                    or r.get("svm_mean", 0) < 0.5 and r.get("true_label") == "NOR")
    logger.info("单独模型准确率（基于均值判定）: ResNet={:.2%} SVM={:.2%}",
                r_correct / len(all_samples), s_correct / len(all_samples))

    # 保存 JSON 报告
    report = {
        "timestamp": timestamp,
        "total_samples": len(all_samples),
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "avg_inference_ms": round(avg_time, 1),
        "init_time_ms": round(init_time, 1),
        "confusion_matrix": {
            "nor_pred_nor": nor_as_nor, "nor_pred_fgr": nor_as_fgr,
            "fgr_pred_nor": fgr_as_nor, "fgr_pred_fgr": fgr_as_fgr,
        },
        "resnet_accuracy": round(r_correct / len(all_samples), 4),
        "svm_accuracy": round(s_correct / len(all_samples), 4),
        "class_breakdown": {},
        "errors": errors,
        "results": results,
    }
    for label in ["NOR", "FGR"]:
        subset = [r for r in results if r.get("true_label") == label and r.get("fgr_probability") is not None]
        if subset:
            probs = [r["fgr_probability"] for r in subset]
            report["class_breakdown"][label] = {
                "count": len(subset),
                "correct": sum(1 for r in subset if r["is_correct"]),
                "accuracy": round(sum(1 for r in subset if r["is_correct"]) / len(subset), 4),
                "mean_prob": round(np.mean(probs), 4),
                "std_prob": round(np.std(probs), 4),
                "min_prob": round(min(probs), 4),
                "max_prob": round(max(probs), 4),
            }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("JSON 报告已保存到 {}", report_path)

    # 保存 CSV（每折一行）
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "filename", "true_label", "predicted_label", "fgr_probability",
            "confidence", "is_correct", "elapsed_ms",
            "resnet_mean", "svm_mean",
            "fold1_resnet", "fold1_svm", "fold1_fused",
            "fold2_resnet", "fold2_svm", "fold2_fused",
            "fold3_resnet", "fold3_svm", "fold3_fused",
            "fold4_resnet", "fold4_svm", "fold4_fused",
            "fold5_resnet", "fold5_svm", "fold5_fused",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = {
                "filename": r.get("filename"),
                "true_label": r.get("true_label"),
                "predicted_label": r.get("predicted_label"),
                "fgr_probability": r.get("fgr_probability"),
                "confidence": r.get("confidence_level"),
                "is_correct": r.get("is_correct"),
                "elapsed_ms": r.get("elapsed_ms"),
                "resnet_mean": r.get("resnet_mean"),
                "svm_mean": r.get("svm_mean"),
            }
            # 各折详情
            if r.get("fold_details"):
                for i, fd in enumerate(r["fold_details"]):
                    row[f"fold{i+1}_resnet"] = fd["p_resnet"]
                    row[f"fold{i+1}_svm"] = fd["p_svm"]
                    row[f"fold{i+1}_fused"] = fd["p_fused"]
            writer.writerow(row)
    logger.info("CSV 报告已保存到 {}", csv_path)

    logger.info("诊断日志已保存到 {}", log_path)
    logger.info("=" * 70)

    return report


if __name__ == "__main__":
    run_diagnostic()
