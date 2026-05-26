"""FGR评估 API（模拟 HIS 集成：图片预绑定到患者）"""
import os
import random
import time
import uuid as uuid_lib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from loguru import logger
from ..database import get_db
from ..models import FgrAssessment, Pregnant, Alert
from ..schemas import FgrAssessRequest, FgrAssessResponse, FgrTrendPoint, PatientImageResponse
from ..core import rule_engine
from ..config import settings
from ..services.segmentation_service import SegmentationError, get_segmentation_service
import numpy as np

router = APIRouter(prefix="/api/v1/fgr", tags=["FGR评估"])


# ==================== 患者图片查找（模拟 HIS） ====================

def _get_patient_images(pregnant_id: str) -> tuple[str, str] | None:
    """从 patient_image_map.json 查找患者的超声原图和 mask 路径"""
    try:
        from fgr_compete.image_registry import get_patient_images
        return get_patient_images(pregnant_id)
    except ImportError:
        return None


# ==================== Mock 评估 ====================

def _mock_fgr_assess(gestational_weeks: float, pregnant_id: str = "") -> dict:
    """Mock FGR评估（fgr_mode=False 时使用）。使用确定性随机种子保证同一输入产生相同结果。"""
    rng = random.Random(int(gestational_weeks * 1000) + hash(pregnant_id) % 10000)
    base_risk = min(0.8, max(0.05, (gestational_weeks - 20) / 50))
    risk_score = base_risk + rng.uniform(-0.15, 0.15)
    risk_score = max(0.01, min(0.95, risk_score))

    risk_level, risk_label = _prob_to_risk(risk_score)
    ci_width = rng.uniform(0.04, 0.08)
    return {
        "case_id": f"MOCK_{int(gestational_weeks):03d}",
        "risk_level": risk_level,
        "risk_label": risk_label,
        "fgr_probability": round(risk_score, 4),
        "predicted_label": "FGR" if risk_score >= 0.5 else "NOR",
        "model_confidence": None,
        "confidence_interval": {
            "lower_bound": round(max(0, risk_score - ci_width), 2),
            "upper_bound": round(min(0.99, risk_score + ci_width), 2),
        },
        "explanation": {
            "critical": "基于多项生长指标严重滞后及血流阻力指数显著升高",
            "high": "基于腹围增长滞后及血流阻力指数升高",
            "medium": "部分生长指标偏低，需要持续监测",
            "low": "各项生长指标在正常范围内",
        }.get(risk_level, "评估完成，各项指标正常"),
        "processing_time": rng.randint(500, 1500),
        "fold_details": None,
    }


# ==================== 模型评估 ====================

def _run_fgr_model(image_path: str, mask_path: str, pregnant_id: str = "") -> dict:
    """调用真实 FGR 算法（读取本地文件）"""
    import os
    logger.info("[FGR-模型] 开始推理 raw={} mask={} 患者={}", os.path.basename(image_path), os.path.basename(mask_path), pregnant_id)
    if not os.path.exists(image_path) or not os.path.exists(mask_path):
        raise HTTPException(400, f"图像文件不存在: {image_path}")

    from fgr_compete import get_predictor
    predictor = get_predictor()
    if predictor is None:
        raise RuntimeError("FGR predictor 未初始化（fgr_mode=False）")

    t0 = time.perf_counter()
    algo_result = predictor.predict(image_path, mask_path)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if "error" in algo_result:
        logger.error("[FGR-模型] 推理失败: {}", algo_result["error"])
        raise HTTPException(400, algo_result["error"])

    prob = algo_result["ensemble_fgr_probability"]
    logger.info("[FGR-模型] 推理完成 prob={:.4f} label={} conf={} time={}ms",
                prob, algo_result["predicted_label"], algo_result["confidence_level"], elapsed_ms)

    # 获取真实标签对比（仅限已绑定的已知样本）
    try:
        from fgr_compete.image_registry import get_patient_group
        true_group = get_patient_group(pregnant_id) if pregnant_id else None
        if true_group and true_group in ("NOR", "FGR"):
            is_correct = algo_result["predicted_label"] == true_group
            tag = "✓" if is_correct else "✗ 错误!"
            logger.warning(
                "[FGR-精度] 真实={} 预测={} prob={:.4f} {}",
                true_group, algo_result["predicted_label"], prob, tag,
            )
            if not is_correct:
                r_mean = sum(f["p_resnet"] for f in algo_result["fold_results"]) / len(algo_result["fold_results"])
                s_mean = sum(f["p_svm"] for f in algo_result["fold_results"]) / len(algo_result["fold_results"])
                if s_mean > 0:
                    logger.error(
                        "[FGR-精度] 误判详情: 患者={} 真实={} 预测={} prob={:.4f} conf={} "
                        "ResNet均值={:.4f} SVM均值={:.4f}",
                        pregnant_id, true_group, algo_result["predicted_label"],
                        prob, algo_result["confidence_level"], r_mean, s_mean,
                    )
                else:
                    logger.error(
                        "[FGR-精度] 误判详情: 患者={} 真实={} 预测={} prob={:.4f} conf={} "
                        "ResNet均值={:.4f} (纯ResNet模式)",
                        pregnant_id, true_group, algo_result["predicted_label"],
                        prob, algo_result["confidence_level"], r_mean,
                    )
    except Exception:
        pass  # 非关键路径，忽略错误
    risk_level, risk_label = _prob_to_risk(prob)

    fold_probs = [f["p_fused"] for f in algo_result["fold_results"]]
    mu = float(np.mean(fold_probs))
    sigma = float(np.std(fold_probs))
    ci_lower = round(max(0.0, mu - sigma), 4)
    ci_upper = round(min(1.0, mu + sigma), 4)

    explanation = (
        f"基于胎盘超声图像的5折ResNet集成模型预测。"
        f"FGR概率={prob:.1%}，置信度={algo_result['confidence_level']}。"
    )

    return {
        "case_id": f"CASE_{uuid_lib.uuid4().hex[:8].upper()}",
        "risk_level": risk_level,
        "risk_label": risk_label,
        "fgr_probability": prob,
        "predicted_label": algo_result["predicted_label"],
        "model_confidence": algo_result["confidence_level"],
        "confidence_interval": {"lower_bound": ci_lower, "upper_bound": ci_upper},
        "explanation": explanation,
        "processing_time": elapsed_ms,
        "fold_details": algo_result["fold_results"],
    }


# ==================== 工具函数 ====================


def _get_fgr_hardware() -> str:
    """返回当前 FGR predictor 实际硬件/EP 名称。"""
    if not settings.fgr_mode:
        return "CPU"
    try:
        from fgr_compete import get_predictor
        predictor = get_predictor()
    except Exception:
        predictor = None
    if predictor is None:
        return "NPU"
    return str(getattr(predictor, "hardware", getattr(predictor, "execution_provider", "NPU")))

def _prob_to_risk(prob: float) -> tuple[str, str]:
    if prob >= 0.7:
        return "critical", "极高风险"
    elif prob >= 0.5:
        return "high", "高风险"
    elif prob >= 0.25:
        return "medium", "中风险"
    else:
        return "low", "低风险"


def _save_assessment(db: Session, pregnant_id: str, gestational_weeks: float,
                     image_type: str, result: dict) -> FgrAssessment:
    assessment = FgrAssessment(
        pregnant_id=pregnant_id,
        case_id=result["case_id"],
        image_type=image_type,
        gestational_weeks=gestational_weeks,
        risk_level=result["risk_level"],
        confidence_lower=result["confidence_interval"].get("lower_bound"),
        confidence_upper=result["confidence_interval"].get("upper_bound"),
        explanation=result["explanation"],
        processing_time_ms=result["processing_time"],
        fgr_probability=result.get("fgr_probability"),
        predicted_label=result.get("predicted_label"),
        model_confidence=result.get("model_confidence"),
    )
    db.add(assessment)
    return assessment


def _evaluate_rules(db: Session, pregnant_id: str, result: dict) -> None:
    rule_hits = rule_engine.evaluate_fgr_risk(result["risk_level"])
    for hit in rule_hits:
        alert = Alert(
            pregnant_id=pregnant_id,
            trigger_source="FGR_ALGORITHM",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details={"case_id": result["case_id"], "risk_level": result["risk_level"]},
        )
        db.add(alert)


# ==================== API 端点 ====================


@router.get("/patient-images/{pregnant_id}", response_model=PatientImageResponse)
def get_patient_images(pregnant_id: str):
    """获取患者绑定的超声图像信息（前端展示用）"""
    images = _get_patient_images(pregnant_id)
    if not images:
        # 无图片的返回空信息
        return PatientImageResponse(
            pregnant_id=pregnant_id,
            has_image=False,
            image_url="",
            display_name="",
        )

    raw_path, _ = images
    from fgr_compete.image_registry import load_patient_map
    mapping = load_patient_map()
    entry = mapping.get(pregnant_id, {})
    return PatientImageResponse(
        pregnant_id=pregnant_id,
        has_image=True,
        image_url=f"/api/v1/fgr/image/{pregnant_id}",
        display_name=entry.get("display_name", ""),
    )


@router.get("/image/{pregnant_id}")
def get_fgr_image(pregnant_id: str):
    """返回患者的超声原图（FileResponse）"""
    images = _get_patient_images(pregnant_id)
    if not images:
        raise HTTPException(404, "该患者暂无绑定超声图像")
    raw_path, _ = images
    return FileResponse(raw_path, media_type="image/png")


@router.post("/assess/{pregnant_id}", response_model=FgrAssessResponse)
async def assess_fgr(pregnant_id: str, req: FgrAssessRequest, db: Session = Depends(get_db)):
    """FGR风险评估：前端无需上传图片，系统从 HIS 绑定数据中获取"""
    # 所有阻塞操作（DB + 模型推理）放到线程池，避免阻塞事件循环
    return await run_in_threadpool(_assess_fgr_sync, pregnant_id, req, db)


def _assess_fgr_sync(pregnant_id: str, req: FgrAssessRequest, db: Session):
    """同步的 FGR 评估逻辑，在线程池中运行"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    if settings.fgr_mode:
        logger.info("[FGR-Assess] fgr_mode=TRUE 患者={} 孕周={}", pregnant_id, req.gestational_weeks)
        images = _get_patient_images(pregnant_id)
        if not images:
            logger.warning("[FGR-Assess] 患者 {} 暂无绑定图像", pregnant_id)
            raise HTTPException(400, "该患者暂无绑定超声图像，无法进行 FGR 算法评估")
        raw_path, mask_path = images
        logger.info("[FGR-Assess] 图片路径 raw={} mask={}", raw_path, mask_path)
        result = _run_fgr_model(raw_path, mask_path, pregnant_id)
    else:
        logger.info("[FGR-Assess] fgr_mode=FALSE 患者={} 使用mock", pregnant_id)
        result = _mock_fgr_assess(req.gestational_weeks)

    _save_assessment(db, pregnant_id, req.gestational_weeks, req.image_type, result)
    _evaluate_rules(db, pregnant_id, result)
    db.commit()

    return FgrAssessResponse(**result, hardware=_get_fgr_hardware())


@router.post("/upload/{pregnant_id}", response_model=FgrAssessResponse)
async def upload_and_assess(
    pregnant_id: str,
    gestational_weeks: float = Form(...),
    image_type: str = Form("AC"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传超声图像 + 自动分割 + FGR分析入库"""
    logger.info("[FGR-上传] 收到请求: pregnant_id={}", pregnant_id)
    # 先异步读取文件（I/O 密集，不阻塞）
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "上传图像不能为空")

    # 后续阻塞操作（DB + 分割 + 模型推理）放到线程池
    return await run_in_threadpool(
        _upload_assess_sync, pregnant_id, gestational_weeks, image_type,
        image_bytes, db,
    )


def _upload_assess_sync(
    pregnant_id: str, gestational_weeks: float, image_type: str,
    image_bytes: bytes, db: Session,
):
    """同步的上传+分割+评估逻辑，在线程池中运行"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    # 1. 保存原图到 uploads/{pregnant_id}/image.png
    from fgr_compete.image_registry import UPLOAD_DIR, register_uploaded_images
    patient_dir = os.path.join(UPLOAD_DIR, pregnant_id)
    os.makedirs(patient_dir, exist_ok=True)
    raw_path = os.path.join(patient_dir, "image.png")
    with open(raw_path, "wb") as f:
        f.write(image_bytes)
    logger.info("[FGR-上传] 原图已保存: {}", raw_path)

    # 2. nnU-Net 5折集成自动分割
    seg_service = get_segmentation_service()
    seg_output_dir = os.path.join(patient_dir, "_seg_output")
    try:
        mask_path = seg_service.segment(raw_path, seg_output_dir)
    except SegmentationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("[FGR-上传] 分割异常: {}", e)
        raise HTTPException(500, "服务端分割错误，请稍后重试")

    # 3. 验证掩码非空，空则 400
    try:
        from PIL import Image
        import numpy as np
        mask_data = np.array(Image.open(mask_path) if not mask_path.endswith(".nii.gz") else None)
        if mask_data is None:
            import nibabel as nib
            mask_data = nib.load(mask_path).get_fdata()
        if not np.any(mask_data > 0):
            raise HTTPException(400, "图像质量不符合要求，请上传清晰的NT期超声图像")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[FGR-上传] 掩码验证跳过: {}", e)

    # 4. 注册到映射表
    with open(mask_path, "rb") as f:
        mask_bytes = f.read()
    raw_path_reg, mask_path_reg = register_uploaded_images(
        pregnant_id, pregnant.display_name, image_bytes, mask_bytes
    )

    # 5. 执行 FGR 评估
    if settings.fgr_mode:
        result = _run_fgr_model(raw_path_reg, mask_path_reg, pregnant_id)
    else:
        result = _mock_fgr_assess(gestational_weeks)

    _save_assessment(db, pregnant_id, gestational_weeks, image_type, result)
    _evaluate_rules(db, pregnant_id, result)
    db.commit()

    return FgrAssessResponse(**result, hardware=_get_fgr_hardware())


@router.get("/trend/{pregnant_id}", response_model=list[FgrTrendPoint])
def get_fgr_trend(pregnant_id: str, db: Session = Depends(get_db)):
    """获取FGR趋势数据"""
    assessments = db.query(FgrAssessment).filter(
        FgrAssessment.pregnant_id == pregnant_id
    ).order_by(FgrAssessment.gestational_weeks).all()

    if not assessments:
        from datetime import timedelta
        base_date = datetime.now() - timedelta(days=56)
        mock_trend = []
        for i in range(6):
            gw = 24 + i * 2
            result = _mock_fgr_assess(gw, pregnant_id)
            mock_trend.append(FgrTrendPoint(
                gestational_weeks=float(gw),
                risk_score=result["fgr_probability"] or 0.1,
                confidence_lower=result["confidence_interval"].get("lower_bound", 0),
                confidence_upper=result["confidence_interval"].get("upper_bound", 0),
                assessed_at=(base_date + timedelta(days=i * 14)).isoformat(),
            ))
        return mock_trend

    return [
        FgrTrendPoint(
            gestational_weeks=a.gestational_weeks,
            risk_score=a.fgr_probability or 0.1,
            confidence_lower=a.confidence_lower or 0,
            confidence_upper=a.confidence_upper or 0,
            assessed_at=a.assessed_at.isoformat() if a.assessed_at else "",
        )
        for a in assessments
    ]
