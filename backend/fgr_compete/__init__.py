"""FGR 预测算法包"""
from .predictor import (
    FGRPredictor,
    create_predictor,
    get_predictor,
    initialize_predictor,
    initialize_predictor_for_backend,
)
from .onnx_predictor import ONNXFGRPredictor
from .npu_service import NPUPredictorService, shutdown_npu_service
from .model import ResNet18DualFusion
