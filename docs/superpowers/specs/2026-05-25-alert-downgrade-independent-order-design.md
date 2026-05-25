# 异常审核工作台降级逻辑 & 独立生成医嘱 — 设计方案

**日期**: 2026-05-25
**状态**: 待评审

---

## 1. 异常审核工作台降级逻辑

### 1.1 当前状态

- 前端 ReviewWorkbench.vue 已实现降级 UI（降级按钮 + 弹窗：选择目标等级 + 理由），调用 `alertApi.review(id, 'downgrade', reason)`
- 后端 `AlertReviewRequest` Schema 正则只允许 `confirm|dismiss|escalate`，不支持 `downgrade`
- 系统级降级（Workflow→单Agent容错）已在 `alert_analysis_service.py` 实现，本次不改动

### 1.2 目标

实现业务层面的预警降级分流：医生可将预警降级，ORANGE/YELLOW 转护士端关注，GREEN 直接关闭。

### 1.3 后端改动

#### Schema 扩展 (`backend/app/schemas/schemas.py`)

`AlertReviewRequest`:
- `action` 正则增加 `downgrade`
- 新增 `target_level: Optional[str]` 字段（ORANGE/YELLOW/GREEN）

#### 降级 API 逻辑 (`backend/app/routers/alerts.py` — `review_alert`)

降级分流规则：
- `target_level = GREEN` → `alert.status = "dismissed"`，预警关闭
- `target_level = ORANGE/YELLOW` → `alert.level = target_level`，`status` 保持 `pending`，WebSocket 广播给护士端
- 记录 `reviewed_by`、`reviewed_at`，`reason` 存入 `details` 或新字段

#### WebSocket 通知 (`backend/app/core/websocket_manager.py`)

- 降级到 ORANGE/YELLOW 时调用 `broadcast_to_nurse(alert_data)` 通知护士端
- 护士端收到后可刷新预警列表

### 1.4 前端改动

#### ReviewWorkbench.vue

- `confirmDowngrade()` 调用参数对齐新接口（增加 `target_level`）
- 降级 GREEN → 从列表移除
- 降级 ORANGE/YELLOW → 保留在列表，更新等级徽章显示

---

## 2. 独立生成医嘱

### 2.1 当前状态

- `POST /orders/generate` 接口的 `alert_id` 已是 Optional，技术上支持无预警生成
- 但前端所有 `orderApi.generate()` 调用都在 ReviewWorkbench.vue 中，强绑定预警流程
- 医生无法脱离预警为某个孕妇生成医嘱

### 2.2 目标

提供两条独立入口让医生直接为孕妇生成医嘱。

### 2.3 医嘱管理页入口 (`OrderManage.vue`)

- 新增"新建医嘱"按钮（页面顶部操作栏）
- 点击弹出对话框，包含：
  - 孕妇选择（el-select 下拉搜索，数据源 `GET /api/v1/dashboard/pregnant`）
  - 孕周（自动带出 `gestational_age_days` 换算，可手动调整）
  - 风险等级选择（RED/ORANGE/YELLOW/GREEN/无风险）
  - 可选备注
- 确认后调用 `orderApi.generate({ pregnant_id, risk_level, gestational_weeks })`（不传 `alert_id`）
- 生成成功后跳转到 `OrderSignPage` 进行编辑签署

### 2.4 医生仪表盘入口 (`DoctorDashboard.vue`)

- 孕妇列表中每行增加"生成医嘱"操作按钮
- 点击后弹出简化版对话框（自动填充孕妇信息，确认孕周和风险等级即可）
- 后续流程同 OrderManage 入口

### 2.5 后端适配

- `POST /orders/generate`：当 `alert_id` 为空且 `risk_level` 为空（或"无风险"）时，`order_service.get_recommendation()` 返回常规诊疗建议模板
- 需增加一个通用/默认医嘱模板，覆盖"无风险"或纯保健场景

---

## 3. 不变更范围

- 审核工作台"确认高危 → 生成医嘱 → 签署"路径保持不变
- 签署页本身的交互逻辑不变
- Workflow→单Agent 系统级降级逻辑不变

---

## 4. 涉及文件

| 文件 | 改动类型 |
|------|----------|
| `backend/app/schemas/schemas.py` | AlertReviewRequest 增加 downgrade + target_level |
| `backend/app/routers/alerts.py` | review_alert 增加降级分流逻辑 |
| `backend/app/core/websocket_manager.py` | 增加 broadcast_to_nurse（如缺失） |
| `backend/app/services/order_service.py` | 增加通用/默认医嘱模板 |
| `frontend/src/views/doctor/ReviewWorkbench.vue` | 降级逻辑对齐新接口 |
| `frontend/src/views/doctor/OrderManage.vue` | 新增"新建医嘱"按钮+对话框 |
| `frontend/src/views/doctor/DoctorDashboard.vue` | 孕妇列表增加"生成医嘱"按钮 |
| `frontend/src/api/endpoints.ts` | 如需要，调整 review 参数签名 |
