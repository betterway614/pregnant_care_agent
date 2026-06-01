# FGR 后端脚本分类

API 运行时的核心代码仍在 `fgr_compete` 根目录，脚本入口按硬件后端放在 `scripts/` 下。

## ROCm 相关

- 分割服务代码：`backend/app/services/segmentation_service.py`
  - 调用 `nnUNetv2_predict`
  - 使用 `ROCR_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES` 选择 AMD GPU/iGPU
- 分类服务代码：`backend/fgr_compete/predictor.py` + `backend/fgr_compete/onnx_predictor.py`
  - `.env` 设置 `FGR_BACKEND=rocm` 时会选择 ONNX Runtime `MIGraphXExecutionProvider` / `ROCMExecutionProvider`
- 脚本入口：
  - `python -m fgr_compete.scripts.rocm.export_onnx`
  - `python -m fgr_compete.scripts.rocm.classify_single <image> <mask>`
  - `python -m fgr_compete.scripts.rocm.segment_single <image> --output-dir <dir>`
  - `python -m fgr_compete.scripts.rocm.benchmark --image <image> --mask <mask>`

## CUDA/PyTorch 相关

- 分类服务代码：`backend/fgr_compete/predictor.py`
- 脚本入口：
  - `python -m fgr_compete.scripts.cuda.predict_single <image> <mask>`
  - `python -m fgr_compete.scripts.cuda.diagnostic`
  - `python -m fgr_compete.scripts.cuda.benchmark --image <image> --mask <mask>`

## Ryzen AI/NPU 相关

- 分类服务代码：`backend/fgr_compete/onnx_predictor.py`
  - `.env` 设置 `FGR_BACKEND=onnx_npu` 时优先选择 `VitisAIExecutionProvider`
  - 当前机器需要先保证 Ryzen AI `quicktest.py` 跑出 `Test Finished`
  - 如果 `xrt-smi validate` 或 quicktest 失败，先运行 `python -m fgr_compete.scripts.ryzen_ai.check_npu_runtime`
- 脚本入口：
  - `python -m fgr_compete.scripts.ryzen_ai.check_npu_runtime`
  - `python -m fgr_compete.scripts.ryzen_ai.quantize_onnx`
  - `python -m fgr_compete.scripts.ryzen_ai.classify_single <image> <mask>`
  - `python -m fgr_compete.scripts.ryzen_ai.benchmark --image <image> --mask <mask>`

## 兼容入口

以下旧命令仍保留，用于兼容已有文档和自动化脚本：

- `python -m fgr_compete.export_onnx`
- `python -m fgr_compete.quantize_onnx`
- `python -m fgr_compete.benchmark`
- `python -m fgr_compete.predict_single`
- `python -m fgr_compete.diagnostic`
