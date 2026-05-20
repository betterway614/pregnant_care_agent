# FGR 线性流水线：自动分割 + 预测

**日期:** 2026-05-20
**状态:** 待实施

## 问题

当前 FGR 上传流程要求用户同时上传**原图**和**掩码图片**两个文件。实际上 nnU-Net 胎盘分割模型（Dataset001_PlacentaNT，5折 Dice 0.72）已经存在于项目中，但未被集成到 API 流程中。掩码应该由系统自动生成，不应由用户手动提供。

## 目标

将流程改为线性链路：

```
上传原图 → nnU-Net 5折集成自动分割 → 原图+掩码 → FGRPredictor → 输出结果
```

## 设计

### 1. 新增：分割服务 `backend/app/services/segmentation_service.py`

```python
class SegmentationService:
    def __init__(self, model_dir: str):
        # 加载 nnU-Net 配置，验证模型目录和 plans.json 存在

    def segment(self, input_path: str, output_dir: str) -> str:
        # 1. 验证输入图像可读
        # 2. 调用 nnUNetv2_predict -i input_dir -o output_dir -d 1 -f all -c 2d
        # 3. 找到生成的 mask 文件
        # 4. 验证掩码非空（有前景像素）
        # 5. 失败时抛出 SegmentationError
        # 返回 mask 文件路径

    def _verify_mask(self, mask_path: str) -> bool:
        # 检查掩码图片是否包含前景像素（像素值>0）
```

关键决策：
- 使用 **5 折集成**（-f all），推理约 10-15 秒
- 分割失败返回 400，提示用户重新上传合格图像
- 依赖 `nnunetv2` 包

### 2. 修改：后端路由 `backend/app/routers/fgr.py`

**上传端点变更：**

| 项目 | 改前 | 改后 |
|------|------|------|
| 文件参数 | `image` + `mask` | 仅 `image` |
| 处理流程 | 直接保存两文件 → 注册 → 预测 | 保存原图 → 分割 → 保存掩码 → 注册 → 预测 |

**新处理流程：**
```
POST /api/v1/fgr/upload/{pregnant_id}
  1. 接收原图 → 保存到 uploads/{pregnant_id}/image.png
  2. segmentation_service.segment() → 生成 uploads/{pregnant_id}/mask.png
  3. 验证掩码非空，空则 400
  4. image_registry.register_uploaded_images()
  5. fgr_predictor.predict() → 结果
  6. _save_assessment() → 数据库
  7. _evaluate_rules() → 触发预警
  8. 返回 FgrAssessResponse
```

### 3. 修改：配置 `backend/app/config.py` / `backend/fgr_compete/config.py`

新增：
```python
NNUNET_MODEL_DIR = "backend/fgr_compete/Dataset001_PlacentaNT"
NNUNET_DATASET_ID = 1
NNUNET_FOLDS = "all"  # 5折集成
```

### 4. 修改：前端上传 `frontend/src/views/doctor/FGRBoard.vue`

- 上传弹窗：两个文件选择器 → 一个（标注"超声图像 NT期B超"）
- 去掉掩膜相关的校验提示
- FormData 移除 `mask` 字段
- 上传期间显示加载动画，文案提示"正在进行图像分割分析..."

### 5. 修改：前端 API `frontend/src/api/endpoints.ts`

- `fgrApi.upload()` 签名中移除 `mask` 参数
- 对应 TypeScript 类型更新

### 6. 依赖 `backend/requirements.txt`

新增 `nnunetv2`。

## 错误处理

| 场景 | 响应 |
|------|------|
| 图像格式无效 | 400 文件格式不支持 |
| 分割结果为空掩码 | 400 "图像质量不符合要求，请上传清晰的NT期超声图像" |
| nnU-Net 推理异常 | 500 服务端分割错误 |
| FGR 模型推理异常 | 500 已有兜底 |

## 影响范围

| 文件 | 改动类型 |
|------|----------|
| `backend/app/services/segmentation_service.py` | **新增** |
| `backend/app/routers/fgr.py` | 修改上传端点 |
| `backend/app/config.py` | 新增配置项 |
| `frontend/src/views/doctor/FGRBoard.vue` | 修改上传弹窗 |
| `frontend/src/api/endpoints.ts` | 修改 API 签名 |
| `backend/requirements.txt` | 新增依赖 |
