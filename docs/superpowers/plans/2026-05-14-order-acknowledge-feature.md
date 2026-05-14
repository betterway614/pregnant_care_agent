# 医嘱已读确认功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现孕妇端医嘱已读确认功能，让医生知道孕妇是否已阅读医嘱

**Architecture:** 在 MedicalOrder 模型新增 acknowledged_at 字段，后端提供 acknowledge API，前端在医嘱详情页增加已读按钮

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, Element Plus

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `backend/app/models/models.py` | 数据模型 - 新增 acknowledged_at 字段 |
| `backend/app/schemas/schemas.py` | 响应模型 - OrderResponse 增加 acknowledged_at |
| `backend/app/routers/orders.py` | API 端点 - 新增 acknowledge 接口 |
| `frontend/src/api/endpoints.ts` | 前端 API - 新增 acknowledge 调用 |
| `frontend/src/views/pregnant/PregnantHome.vue` | 孕妇端 - 医嘱通知跳转逻辑 |

---

### Task 1: 数据模型 - 新增 acknowledged_at 字段

**Files:**
- Modify: `backend/app/models/models.py:154-168`

- [ ] **Step 1: 修改 MedicalOrder 模型**

在 MedicalOrder 类中新增 acknowledged_at 字段：

```python
class MedicalOrder(Base):
    """医嘱记录"""
    __tablename__ = "medical_orders"

    id = Column(UUIDColumn(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pregnant_id = Column(String(64), ForeignKey("pregnant.pregnant_id"), nullable=False)
    alert_id = Column(UUIDColumn(as_uuid=True), ForeignKey("alerts.id"), nullable=True)
    content = Column(Text, nullable=False, comment="医嘱内容")
    order_type = Column(String(32), default="standard", comment="standard/custom")
    source = Column(String(32), default="AI_RECOMMENDED", comment="AI_RECOMMENDED/DOCTOR_WRITTEN")
    status = Column(String(16), default="draft", comment="draft/signed/executed")
    created_by = Column(String(64), nullable=True, comment="医生ID")
    signed_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True, comment="孕妇确认阅读时间")
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: 验证模型修改**

Run: `cd backend && python -c "from app.models.models import MedicalOrder; print('acknowledged_at' in [c.name for c in MedicalOrder.__table__.columns])"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/models.py
git commit -m "feat: add acknowledged_at field to MedicalOrder model"
```

---

### Task 2: 响应模型 - OrderResponse 增加 acknowledged_at

**Files:**
- Modify: `backend/app/schemas/schemas.py`

- [ ] **Step 1: 查找 OrderResponse 定义**

在 schemas.py 中找到 OrderResponse 类定义。

- [ ] **Step 2: 添加 acknowledged_at 字段**

```python
class OrderResponse(BaseModel):
    # ... 现有字段 ...
    acknowledged_at: Optional[datetime] = None

    class Config:
        from_attributes = True
```

- [ ] **Step 3: 验证 schema 修改**

Run: `cd backend && python -c "from app.schemas import OrderResponse; print('acknowledged_at' in OrderResponse.model_fields)"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: add acknowledged_at to OrderResponse schema"
```

---

### Task 3: 后端 API - 新增 acknowledge 接口

**Files:**
- Modify: `backend/app/routers/orders.py`

- [ ] **Step 1: 添加 acknowledge API 端点**

在 orders.py 中添加：

```python
@router.put("/{order_id}/acknowledge")
def acknowledge_order(order_id: str, db: Session = Depends(get_db)):
    """孕妇确认阅读医嘱"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    if order.acknowledged_at:
        return {"success": True, "message": "已确认阅读"}
    order.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "已确认阅读"}
```

- [ ] **Step 2: 验证 API 注册**

Run: `cd backend && python -c "from app.routers.orders import router; print([r.path for r in router.routes])"`
Expected: 包含 `/{order_id}/acknowledge`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/orders.py
git commit -m "feat: add acknowledge order API endpoint"
```

---

### Task 4: 前端 API - 新增 acknowledge 调用

**Files:**
- Modify: `frontend/src/api/endpoints.ts`

- [ ] **Step 1: 添加 acknowledge API**

在 orderApi 对象中添加：

```typescript
export const orderApi = {
  // ... 现有 API ...
  acknowledge: (orderId: string) =>
    client.put(`/orders/${orderId}/acknowledge`),
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/endpoints.ts
git commit -m "feat: add acknowledge order API to frontend"
```

---

### Task 5: 孕妇端 - 医嘱详情页增加已读按钮

**Files:**
- Create: `frontend/src/views/pregnant/OrderDetail.vue` (如果不存在)
- 或 Modify: `frontend/src/views/pregnant/PregnantHome.vue`

- [ ] **Step 1: 创建医嘱详情页组件**

```vue
<template>
  <div class="order-detail">
    <div class="order-header">
      <h3>医嘱详情</h3>
      <el-tag :type="getStatusType(order.status)">{{ getStatusText(order.status) }}</el-tag>
    </div>

    <div class="order-content">
      <div class="content-label">医嘱内容</div>
      <div class="content-text">{{ order.content }}</div>
    </div>

    <div class="order-meta">
      <div class="meta-item">
        <span class="meta-label">开具时间</span>
        <span class="meta-value">{{ formatTime(order.created_at) }}</span>
      </div>
      <div class="meta-item" v-if="order.signed_at">
        <span class="meta-label">签署时间</span>
        <span class="meta-value">{{ formatTime(order.signed_at) }}</span>
      </div>
    </div>

    <div class="order-actions" v-if="!order.acknowledged_at">
      <el-button type="primary" @click="handleAcknowledge" :loading="loading">
        我已阅读
      </el-button>
    </div>

    <div class="acknowledged-info" v-else>
      <el-icon><CircleCheck /></el-icon>
      <span>已于 {{ formatTime(order.acknowledged_at) }} 确认阅读</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheck } from '@element-plus/icons-vue'
import { orderApi } from '@/api/endpoints'

const props = defineProps<{
  order: any
}>()

const emit = defineEmits<{
  (e: 'acknowledged'): void
}>()

const loading = ref(false)

function getStatusType(status: string): string {
  const map: Record<string, string> = {
    draft: 'info',
    signed: 'success',
    executed: 'primary',
  }
  return map[status] || 'info'
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    signed: '已签署',
    executed: '已执行',
  }
  return map[status] || status
}

function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function handleAcknowledge() {
  loading.value = true
  try {
    await orderApi.acknowledge(props.order.id)
    emit('acknowledged')
  } catch (err) {
    console.error('确认阅读失败:', err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.order-detail {
  padding: 16px;
}

.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.order-content {
  margin-bottom: 16px;
}

.content-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.content-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 8px;
}

.order-meta {
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.meta-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.meta-value {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.order-actions {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.acknowledged-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--el-color-success);
  font-size: 14px;
  margin-top: 16px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/OrderDetail.vue
git commit -m "feat: add order detail page with acknowledge button"
```

---

### Task 6: 集成 - 孕妇端首页医嘱通知跳转

**Files:**
- Modify: `frontend/src/views/pregnant/PregnantHome.vue`

- [ ] **Step 1: 修改医嘱通知点击事件**

在 PregnantHome.vue 中，修改医嘱通知的点击事件：

```vue
<!-- 医嘱通知 -->
<div 
  v-if="pendingOrders.length > 0" 
  class="compact-notice order-notice interactive-card"
  @click="goToOrder(pendingOrders[0].id)"
>
  <!-- ... 现有内容 ... -->
</div>
```

- [ ] **Step 2: 添加跳转方法**

```typescript
function goToOrder(orderId: string) {
  router.push(`/pregnant/orders/${orderId}`)
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/pregnant/PregnantHome.vue
git commit -m "feat: add order notification click navigation"
```

---

## 自审清单

**1. Spec 覆盖:**
- ✓ MedicalOrder 模型新增 acknowledged_at 字段
- ✓ 后端新增 acknowledge API
- ✓ 前端新增 acknowledge API 调用
- ✓ 孕妇端医嘱详情页增加已读按钮

**2. Placeholder 扫描:**
- 无 TBD/TODO ✓
- 所有代码完整 ✓

**3. 类型一致性:**
- acknowledged_at 类型一致 (DateTime/Optional[datetime]) ✓
- API 路径一致 ✓

---

## 执行选项

**计划已保存到 `docs/superpowers/plans/2026-05-14-order-acknowledge-feature.md`**

两种执行方式：

**1. Subagent-Driven (推荐)** - 每个任务分发一个新的 subagent，任务间进行 review，快速迭代

**2. Inline Execution** - 在当前会话中执行任务，批量执行并设置检查点

选择哪种方式？
