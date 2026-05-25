# FGR 模块迁移到 AMD Ryzen AI MAX+ 395 NPU/iGPU 实施方案

## Context

FGR（胎儿生长受限）预测模块当前使用纯 PyTorch 运行在 CPU/GPU 上，需要迁移到 AMD Ryzen AI MAX+ 395 (Strix Halo) 平台，利用其 NPU (XDNA2, 50 TOPS) 和 iGPU (Radeon 8060S, RDNA 3.5) 进行混合推理加速。

**硬件**: Ryzen AI MAX+ 395, 128GB LPDDR5X UMA, Linux, ROCm + Ryzen AI SDK 已搭建  
**策略**: ResNet18 分类 → NPU (INT8), nnU-Net 分割 → iGPU (ROCm), SVM+预处理 → CPU  
**范围**: 仅 FGR 模块，不涉及 NLU BERT / Embedding 等其他模块

已有设计文档 `docs/design/2026-04-29-hardware-adaptation.md` 描述了目标架构，但代码层面零实现——无 ONNX 文件、无 ONNX Runtime 代码、无 Ryzen AI SDK 依赖。

---

## 实施步骤（按执行顺序）

### Step 1: ONNX 导出脚本 — Gate 1，必须先通过

**新建** `backend/fgr_compete/export_onnx.py`

- 导出 5 个 ResNet18DualFusion `.pth` → `.onnx` (opset 17)
- 使用 `ONNXExportWrapper` 包装模型，避免 `forward()` 末尾的 `.squeeze(1)` 导致 0D 张量问题
- 输出到 `fgr_compete/onnx_resnet/resnet_v9_best_fold{1..5}.onnx`
- 每个模型做 round-trip 验证: PyTorch CPU vs ONNX Runtime CPU，`atol=1e-5`
- `onnx.checker.check_model()` 校验

**关键**: 导出 wrapper 不含 squeeze，输出形状 `[1, 1]`，推理端手动 `.flatten()[0]` 取标量

### Step 2: 量化脚本

**新建** `backend/fgr_compete/quantize_onnx.py`

- 使用 AMD Quark 对 5 个 ONNX 模型做 XINT8 PTQ 量化
- 校准集: 现有 10 张训练图片 (`photo/raw/{nor,fgr}` + `photo/mask/{nor,fgr}`)，走与 predictor 相同的预处理
- Quark API: `get_default_config("XINT8")` → `ModelQuantizer.quantize_model()`
- 输出: `fgr_compete/onnx_resnet/resnet_v9_best_fold{1..5}_int8.onnx`
- 量化后验证: 10 样本 FP32 ONNX vs INT8 ONNX，概率差 < 0.05

### Step 3: 硬件检测工具

**新建** `backend/fgr_compete/hardware_detect.py`

```python
def detect_npu() -> bool:
    """检查 VitisAIExecutionProvider 是否可用"""
    
def detect_rocm() -> bool:
    """检查 ROCm GPU 是否可用"""
    
def select_backend(configured: str) -> str:
    """解析配置 → 实际后端，含回退链: NPU → iGPU → CPU"""
```

### Step 4: 配置扩展

**修改** `backend/app/config.py` (line 63 附近)

```python
fgr_backend: Literal["pytorch", "onnx_npu", "onnx_igpu", "mock"] = "pytorch"
```

**修改** `backend/fgr_compete/config.py`

```python
ONNX_DIR = os.path.join(MODULE_DIR, "onnx_resnet")
```

### Step 5: ONNX Predictor — 核心新类

**新建** `backend/fgr_compete/onnx_predictor.py`

`ONNXFGRPredictor` 类，与 `FGRPredictor` 完全相同的接口:

- `initialize()`: 检测硬件 → 选 EP → 加载 5 个 ONNX session → 可选加载 SVM
- `_select_provider()`: `VitisAIExecutionProvider` → `ROCMExecutionProvider` → `CPUExecutionProvider`
- `_load_onnx_models()`: 优先加载 `_int8.onnx`，不存在则加载 `.onnx`
- `predict()` / `predict_from_bytes()`: 与原 predictor 完全一致的输入输出
- `_predict_arrays()`: 复用 `features.py` 的 `extract_features()`，ROI 预处理转 numpy，ONNX `session.run()` 推理，手动 sigmoid，返回相同 dict
- 返回值合约: `{fold_results, ensemble_fgr_probability, predicted_label, confidence_level}`

### Step 6: 工厂函数 + 集成

**修改** `backend/fgr_compete/predictor.py`

- 添加 `create_predictor(backend)` 工厂函数
- 添加 `initialize_predictor_for_backend(backend)` 函数，使用 `select_backend()` 解析后端
- 保留原 `initialize_predictor()` 向后兼容

**修改** `backend/fgr_compete/__init__.py`

- 导出 `ONNXFGRPredictor`

**修改** `backend/app/main.py` (lines 170-177)

```python
# 替换: from fgr_compete import initialize_predictor; initialize_predictor()
# 改为: from fgr_compete.predictor import initialize_predictor_for_backend
#        initialize_predictor_for_backend(settings.fgr_backend)
```

**修改** `backend/app/routers/fgr.py` (line 265, 351)

- `hardware=` 字段改为从 predictor 实例动态获取实际 EP 名称

### Step 7: Segmentation Service — 最小改动

**修改** `backend/app/services/segmentation_service.py`

- subprocess 环境变量加 `ROCR_VISIBLE_DEVICES=0` 确保 iGPU 可见
- 添加日志行报告推理设备
- nnU-Net 仍以 subprocess 方式调用，ROCm 加速对 PyTorch 透明

### Step 8: 依赖更新

**修改** `backend/requirements.txt`

```
onnx>=1.16.0
onnxruntime>=1.18.0
# AMD Quark 量化工具（需按 Ryzen AI SDK 文档安装）
# onnxruntime-vitisai（需从 Ryzen AI SDK 获取）
```

### Step 9: 测试与验证

**新建** `backend/tests/test_onnx_predictor.py`

- `ONNXFGRPredictor.predict()` 返回 dict 包含所有必需 key
- 与 `FGRPredictor.predict()` 同输入结果对比 (atol=0.05)
- `predict_from_bytes()` 一致性测试
- EP 回退测试: mock 无 VitisAI EP → 自动降级

**新建** `backend/fgr_compete/benchmark.py`

- 延迟基准: PyTorch CPU / ONNX CPU / ONNX ROCM / ONNX VitisAI
- 测量: 初始化时间 + 单次推理时间

**扩展现有测试** `backend/tests/test_fgr_upload.py`

- 参数化 `fgr_backend="pytorch"` 和 `"onnx_npu"` 两组

---

## 文件清单

### 新建 (7 个)

| 文件 | 用途 |
|------|------|
| `fgr_compete/export_onnx.py` | ONNX 导出脚本 |
| `fgr_compete/quantize_onnx.py` | INT8 量化脚本 (AMD Quark) |
| `fgr_compete/onnx_predictor.py` | ONNX 推理器 (NPU/iGPU/CPU) |
| `fgr_compete/hardware_detect.py` | 硬件检测与后端选择 |
| `fgr_compete/benchmark.py` | 延迟基准测试 |
| `tests/test_onnx_predictor.py` | ONNX predictor 单元测试 |
| `fgr_compete/onnx_resnet/` | 目录（放导出的 .onnx 文件） |

### 修改 (7 个)

| 文件 | 改动 |
|------|------|
| `fgr_compete/config.py` | 添加 `ONNX_DIR` 常量 |
| `fgr_compete/predictor.py` | 添加 `create_predictor()` / `initialize_predictor_for_backend()` 工厂函数 |
| `fgr_compete/__init__.py` | 导出 `ONNXFGRPredictor` |
| `app/config.py` | 添加 `fgr_backend` 配置项 |
| `app/main.py` | lifespan 使用 `initialize_predictor_for_backend(settings.fgr_backend)` |
| `app/routers/fgr.py` | `hardware=` 字段动态化 |
| `app/services/segmentation_service.py` | ROCm 环境变量 + 日志 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| VitisAI EP 不可用 | `ONNXFGRPredictor._select_provider()` 自动回退到 ROCM → CPU |
| INT8 量化精度下降 >5% | 校准验证，超阈值则用 FP32 ONNX 跑 iGPU |
| ONNX 导出失败 | 模型是标准 ResNet18 变体，wrapper 避免 squeeze 问题 |
| 现有测试回归 | 默认 `fgr_backend="pytorch"` 保持现有行为不变 |

---

## 验证方式

1. **Step 1 验证**: 运行 `python -m fgr_compete.export_onnx`，5 个 .onnx 文件生成且 round-trip `atol<1e-5`
2. **Step 5 验证**: 在 `fgr_backend=onnx_npu` 下启动 FastAPI，调用 `/api/v1/fgr/assess/{id}`，返回正常结果
3. **Step 9 验证**: `pytest tests/test_onnx_predictor.py -v` 全通过，benchmark 显示 NPU 推理 < 100ms
4. **回归验证**: `fgr_backend=pytorch` 模式下所有现有测试 `pytest tests/ -v` 全通过
