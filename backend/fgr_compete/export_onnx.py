"""导出 FGR ResNet18DualFusion 权重到 ONNX。"""

from __future__ import annotations

import os

import numpy as np
import torch

from .config import MODEL_DIR, ONNX_DIR, IMG_SIZE, N_FOLDS
from .model import ResNet18DualFusion


class ONNXExportWrapper(torch.nn.Module):
    """避免原 forward 末尾 squeeze(1)，保持输出形状为 [N, 1]。"""

    def __init__(self, model: ResNet18DualFusion):
        super().__init__()
        self.model = model

    def forward(self, x):
        x = self.model.stem(x)
        x = self.model.layer1(x)
        x = self.model.layer2(x)
        shallow = self.model.gap(x).flatten(1)
        x = self.model.layer3(x)
        x = self.model.layer4(x)
        deep = self.model.gap(x).flatten(1)
        return self.model.classifier(torch.cat([shallow, deep], dim=1))


def _load_model(fold_idx: int) -> ONNXExportWrapper:
    model_path = os.path.join(MODEL_DIR, f"resnet_v9_best_fold{fold_idx + 1}.pth")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"权重文件不存在: {model_path}")
    model = ResNet18DualFusion()
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    wrapper = ONNXExportWrapper(model)
    wrapper.eval()
    return wrapper


def _validate_onnx(onnx_path: str, wrapper: ONNXExportWrapper, dummy: torch.Tensor) -> None:
    import onnx
    import onnxruntime as ort

    onnx.checker.check_model(onnx.load(onnx_path))
    with torch.no_grad():
        torch_out = wrapper(dummy).detach().cpu().numpy()
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    ort_out = session.run(None, {session.get_inputs()[0].name: dummy.numpy()})[0]
    np.testing.assert_allclose(torch_out, ort_out, rtol=1e-5, atol=1e-5)


def export_all() -> list[str]:
    os.makedirs(ONNX_DIR, exist_ok=True)
    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE, dtype=torch.float32)
    exported = []

    for fold_idx in range(N_FOLDS):
        wrapper = _load_model(fold_idx)
        onnx_path = os.path.join(ONNX_DIR, f"resnet_v9_best_fold{fold_idx + 1}.onnx")
        torch.onnx.export(
            wrapper,
            dummy,
            onnx_path,
            input_names=["input"],
            output_names=["logit"],
            opset_version=17,
            dynamic_axes={"input": {0: "batch"}, "logit": {0: "batch"}},
            dynamo=False,
        )
        _validate_onnx(onnx_path, wrapper, dummy)
        exported.append(onnx_path)
        print(f"[OK] fold{fold_idx + 1}: {onnx_path}")

    return exported


if __name__ == "__main__":
    export_all()
