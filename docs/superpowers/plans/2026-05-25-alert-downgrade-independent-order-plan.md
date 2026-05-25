# 异常审核降级 & 独立生成医嘱 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现预警降级分流（ORANGE/YELLOW转护士端，GREEN关闭）和医生独立生成医嘱能力（脱离预警流程）

**Architecture:** 后端扩展 AlertReviewRequest schema 支持 downgrade action + target_level，review_alert 增加降级分流逻辑与 WebSocket 护士端通知；前端 OrderManage 和 DoctorDashboard 各增加"新建医嘱"入口，复用 orderApi.generate 接口

**Tech Stack:** Python/FastAPI/SQLAlchemy (后端), Vue 3/TypeScript/Element Plus (前端)

---

### Task 1: 扩展 AlertReviewRequest Schema

**Files:**
- Modify: `backend/app/schemas/schemas.py:301-303`

- [ ] **Step 1: 扩展 AlertReviewRequest，增加 downgrade action 和 target_level 字段**

```python
class AlertReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(confirm|dismiss|escalate|downgrade|supplement)$")
    reason: Optional[str] = None
    target_level: Optional[str] = Field(None, pattern="^(ORANGE|YELLOW|GREEN)$")
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: extend AlertReviewRequest schema with downgrade/supplement actions and target_level"
```

---

### Task 2: 实现 review_alert 降级分流逻辑

**Files:**
- Modify: `backend/app/routers/alerts.py:186-235`

- [ ] **Step 1: 在 review_alert 中增加 downgrade 和 supplement 处理分支**

将 `review_alert` 函数中的 if-elif 链替换为：

```python
@router.put("/{alert_id}/review", response_model=AlertResponse)
async def review_alert(alert_id: str, review: AlertReviewRequest,
                  db: Session = Depends(get_db)):
    """审核预警"""
    alert = db.query(Alert).filter(Alert.id == UUID(alert_id)).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    original_level = alert.level

    if review.action == "confirm":
        alert.status = "CONFIRMED"
    elif review.action == "dismiss":
        alert.status = "DISMISSED"
    elif review.action == "escalate":
        alert.status = "ESCALATED"
        if alert.level != "RED":
            alert.level = "RED"
    elif review.action == "downgrade":
        if not review.target_level:
            raise HTTPException(400, "降级操作必须指定 target_level")
        if review.target_level == "GREEN":
            alert.status = "DISMISSED"
        else:
            alert.level = review.target_level
            alert.status = "PENDING"
        # 降级理由存入 details
        if review.reason:
            details = alert.details or {}
            details["downgrade_reason"] = review.reason
            details["downgrade_target"] = review.target_level
            alert.details = details
    elif review.action == "supplement":
        # 补充资料：保持状态不变，记录补充内容到 details
        if review.reason:
            details = alert.details or {}
            details["supplement_notes"] = review.reason
            alert.details = details

    alert.reviewed_at = beijing_now()
    db.commit()
    db.refresh(alert)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == alert.pregnant_id).first()

    # escalate 时广播预警
    if review.action == "escalate" and pregnant:
        try:
            prefix = "[已升级]" if alert.level == "RED" and original_level != "RED" else "[紧急通知]"
            alert_data = {
                "id": str(alert.id),
                "pregnant_id": alert.pregnant_id,
                "patient_name": pregnant.display_name,
                "level": alert.level,
                "message": f"{prefix} {alert.message}",
                "trigger_source": alert.trigger_source,
                "status": alert.status,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "gestational_age_days": pregnant.gestational_age_days,
            }
            await ws_manager.broadcast_alert(alert_data)
        except Exception as e:
            logger.warning(f"escalate WebSocket广播失败: {e}")

    # downgrade 到 ORANGE/YELLOW 时广播给护士端
    if review.action == "downgrade" and review.target_level != "GREEN" and pregnant:
        try:
            alert_data = {
                "id": str(alert.id),
                "pregnant_id": alert.pregnant_id,
                "patient_name": pregnant.display_name,
                "level": alert.level,
                "message": f"[医生降级] {alert.message}",
                "trigger_source": alert.trigger_source,
                "status": alert.status,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "gestational_age_days": pregnant.gestational_age_days,
                "downgrade_reason": review.reason,
            }
            await ws_manager.broadcast_alert(alert_data)
        except Exception as e:
            logger.warning(f"downgrade WebSocket广播失败: {e}")

    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/routers/alerts.py
git commit -m "feat: implement alert downgrade triage and supplement logic"
```

---

### Task 3: 增加默认医嘱模板

**Files:**
- Modify: `backend/app/services/order_service.py:52-84`

- [ ] **Step 1: 在 ORDER_TEMPLATES 字典末尾增加通用模板，并修改 get_recommendation 兜底逻辑**

在 `ORDER_TEMPLATES` 字典中（`"emotion_concern"` 之后）增加：

```python
"general": {
    "condition": "常规产检/保健",
    "content": "建议定期产检，注意均衡饮食，适度运动（每日散步30分钟），保证充足睡眠。每日自数胎动，如有腹痛、阴道出血、破水等异常情况请立即就诊。以上为常规孕期保健建议，具体方案需经主治医生评估后确定。",
    "source": "孕期保健指南"
},
```

修改 `get_recommendation` 方法的最后（`return None` 之前），增加兜底返回：

```python
# 无风险或未匹配到特定模板时，返回通用保健建议
return dict(ORDER_TEMPLATES["general"])
```

具体改动位置：在 `order_service.py` 第84行 `return None` 替换为上述兜底返回。

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/order_service.py
git commit -m "feat: add general prenatal care order template as fallback"
```

---

### Task 4: 修复前端降级调用对齐新接口

**Files:**
- Modify: `frontend/src/views/doctor/ReviewWorkbench.vue:847-860`
- Modify: `frontend/src/api/endpoints.ts:80-81`

- [ ] **Step 1: 更新 alertApi.review 签名，支持 target_level 参数**

`endpoints.ts` 第80-81行：

```typescript
review: (alertId: string, action: string, reason?: string, targetLevel?: string) =>
    client.put(`/alerts/${alertId}/review`, { action, reason, target_level: targetLevel }),
```

- [ ] **Step 2: 修改 ReviewWorkbench.vue 中 confirmDowngrade 函数，传递 target_level，并实现分流显示**

`ReviewWorkbench.vue` 第847-860行替换为：

```typescript
/** 确认降级 */
async function confirmDowngrade() {
  if (!selectedAlert.value || !downgradeReason.value.trim()) return
  submitting.value = true
  try {
    await alertApi.review(
      selectedAlert.value.id,
      'downgrade',
      downgradeReason.value,
      downgradeTarget.value
    )
    if (downgradeTarget.value === 'GREEN') {
      // GREEN 降级关闭：从列表移除
      alertList.value = alertList.value.filter((a) => a.id !== selectedAlert.value!.id)
    } else {
      // ORANGE/YELLOW 降级分流：更新列表中等级显示
      selectedAlert.value.level = downgradeTarget.value
      selectedAlert.value.status = 'pending'
    }
    downgradeDialogVisible.value = false
    if (!alertList.value.length) selectedAlert.value = null
  } catch (err) {
    console.error('降级失败:', err)
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 3: 同样修复 doSaveSupplement 调用，传递 supplement action**

`ReviewWorkbench.vue` 第869-879行，将 `'supplement'` action 的调用保持不变（后端现已支持）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/endpoints.ts frontend/src/views/doctor/ReviewWorkbench.vue
git commit -m "feat: align frontend downgrade call with new backend schema"
```

---

### Task 5: OrderManage 增加"新建医嘱"入口

**Files:**
- Modify: `frontend/src/views/doctor/OrderManage.vue`

- [ ] **Step 1: 在模板页面标题区增加"新建医嘱"按钮**

在 `OrderManage.vue` 第5-8行的 `page-header__actions` 区域，`<el-button>` 刷新按钮之前增加：

```html
<el-button type="success" :icon="Plus" @click="showCreateOrderDialog">
  新建医嘱
</el-button>
```

同时需要在 import 中引入 `Plus` 图标：
第205行 `import { Search, Refresh, Document } from '@element-plus/icons-vue'` 改为：
```typescript
import { Search, Refresh, Document, Plus } from '@element-plus/icons-vue'
```

- [ ] **Step 2: 在模板末尾（`</template>` 之前）增加新建医嘱对话框**

在最后一个 `</el-dialog>` 之后、`</template>` 之前增加：

```html
<!-- 新建医嘱对话框 -->
<el-dialog
  v-model="createOrderDialogVisible"
  title="新建医嘱"
  width="520px"
  destroy-on-close
>
  <el-form label-width="80px">
    <el-form-item label="选择孕妇" required>
      <el-select
        v-model="createOrderForm.pregnant_id"
        filterable
        placeholder="请搜索并选择孕妇"
        style="width: 100%"
        @change="onPregnantSelect"
      >
        <el-option
          v-for="p in pregnantList"
          :key="p.pregnant_id"
          :label="`${p.display_name} (${calcGestationalWeekText(p.gestational_age_days)})`"
          :value="p.pregnant_id"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="孕周">
      <el-input-number
        v-model="createOrderForm.gestational_weeks"
        :min="1"
        :max="42"
        :precision="1"
        :step="0.5"
      />
      <span style="margin-left: 8px; color: var(--text-muted); font-size: 12px">周</span>
    </el-form-item>
    <el-form-item label="风险等级">
      <el-select v-model="createOrderForm.risk_level" style="width: 100%">
        <el-option label="RED — 红色高危" value="RED" />
        <el-option label="ORANGE — 橙色预警" value="ORANGE" />
        <el-option label="YELLOW — 黄色关注" value="YELLOW" />
        <el-option label="GREEN — 正常/绿色" value="GREEN" />
        <el-option label="无风险 — 常规保健" value="none" />
      </el-select>
    </el-form-item>
    <el-form-item label="备注">
      <el-input
        v-model="createOrderForm.notes"
        type="textarea"
        :rows="2"
        placeholder="可选备注"
      />
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="createOrderDialogVisible = false">取消</el-button>
    <el-button
      type="primary"
      :loading="creatingOrder"
      :disabled="!createOrderForm.pregnant_id"
      @click="doCreateOrder"
    >
      生成医嘱
    </el-button>
  </template>
</el-dialog>
```

- [ ] **Step 3: 在 script 区增加相关状态和方法**

在 script setup 中增加（放在 `onMounted(loadOrders)` 之前）：

```typescript
// 新建医嘱
const createOrderDialogVisible = ref(false)
const creatingOrder = ref(false)
const pregnantList = ref<Pregnant[]>([])
const createOrderForm = ref({
  pregnant_id: '',
  gestational_weeks: 28,
  risk_level: 'none' as string,
  notes: '',
})

/** 计算孕周文本 */
function calcGestationalWeekText(days?: number): string {
  if (!days) return '未知孕周'
  const w = Math.floor(days / 7)
  const d = days % 7
  return `${w}周+${d}天`
}

/** 显示新建医嘱对话框 */
async function showCreateOrderDialog() {
  createOrderDialogVisible.value = true
  // 加载孕妇列表
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data || []
  } catch (err) {
    console.error('加载孕妇列表失败:', err)
  }
}

/** 选择孕妇后自动填充孕周 */
function onPregnantSelect(pregnantId: string) {
  const p = pregnantList.value.find((item) => item.pregnant_id === pregnantId)
  if (p?.gestational_age_days) {
    createOrderForm.value.gestational_weeks = parseFloat((p.gestational_age_days / 7).toFixed(1))
  }
}

/** 执行新建医嘱 */
async function doCreateOrder() {
  if (!createOrderForm.value.pregnant_id) return
  creatingOrder.value = true
  try {
    const res = await orderApi.generate({
      pregnant_id: createOrderForm.value.pregnant_id,
      risk_level: createOrderForm.value.risk_level === 'none' ? 'GREEN' : createOrderForm.value.risk_level,
      gestational_weeks: createOrderForm.value.gestational_weeks,
    })
    createOrderDialogVisible.value = false
    router.push({ name: 'OrderSign', params: { orderId: res.data.id } })
  } catch (err) {
    console.error('创建医嘱失败:', err)
  } finally {
    creatingOrder.value = false
  }
}
```

同时需要在 import 中增加类型和 API：
第207行增加 `Pregnant` 导入：
```typescript
import type { MedicalOrder, Pregnant } from '@/types'
```
第206行增加 `dashboardApi` 导入：
```typescript
import { orderApi, dashboardApi } from '@/api/endpoints'
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/doctor/OrderManage.vue
git commit -m "feat: add create order entry in OrderManage page"
```

---

### Task 6: DoctorDashboard 增加"快速开医嘱"入口

**Files:**
- Modify: `frontend/src/views/doctor/DoctorDashboard.vue`

- [ ] **Step 1: 在页面标题区增加"快速开医嘱"按钮**

在 `DoctorDashboard.vue` 第15-17行的刷新按钮之前增加：

```html
<el-button type="success" :icon="Plus" @click="showQuickOrderDialog">
  快速开医嘱
</el-button>
```

同时 import 中增加 `Plus` 图标：
第154行 `import { Refresh, Bell, Document } from '@element-plus/icons-vue'` 改为：
```typescript
import { Refresh, Bell, Document, Plus } from '@element-plus/icons-vue'
```

并在 import 中增加 `dashboardApi`：
第155行改为：
```typescript
import { dashboardApi, alertApi, orderApi } from '@/api/endpoints'
```

增加 `Pregnant` 类型导入：
第157行改为：
```typescript
import type { Alert, MedicalOrder, DashboardStats, Pregnant } from '@/types'
```

- [ ] **Step 2: 在模板末尾（`</template>` 之前）增加快速开医嘱对话框**

```html
<!-- 快速开医嘱对话框 -->
<el-dialog
  v-model="quickOrderDialogVisible"
  title="快速开医嘱"
  width="480px"
  destroy-on-close
>
  <el-form label-width="80px">
    <el-form-item label="选择孕妇" required>
      <el-select
        v-model="quickOrderForm.pregnant_id"
        filterable
        placeholder="请搜索并选择孕妇"
        style="width: 100%"
        @change="onQuickOrderPregnantSelect"
      >
        <el-option
          v-for="p in pregnantList"
          :key="p.pregnant_id"
          :label="`${p.display_name} (${calcGestWeekText(p.gestational_age_days)})`"
          :value="p.pregnant_id"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="孕周">
      <el-input-number
        v-model="quickOrderForm.gestational_weeks"
        :min="1"
        :max="42"
        :precision="1"
        :step="0.5"
      />
      <span style="margin-left: 8px; color: var(--text-muted); font-size: 12px">周</span>
    </el-form-item>
    <el-form-item label="风险等级">
      <el-select v-model="quickOrderForm.risk_level" style="width: 100%">
        <el-option label="RED — 红色高危" value="RED" />
        <el-option label="ORANGE — 橙色预警" value="ORANGE" />
        <el-option label="YELLOW — 黄色关注" value="YELLOW" />
        <el-option label="GREEN — 正常/绿色" value="GREEN" />
        <el-option label="无风险 — 常规保健" value="none" />
      </el-select>
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="quickOrderDialogVisible = false">取消</el-button>
    <el-button
      type="primary"
      :loading="quickOrderCreating"
      :disabled="!quickOrderForm.pregnant_id"
      @click="doQuickOrder"
    >
      生成医嘱
    </el-button>
  </template>
</el-dialog>
```

- [ ] **Step 3: 在 script 区增加相关状态和方法**

在 `onMounted` 之前增加：

```typescript
// 快速开医嘱
const quickOrderDialogVisible = ref(false)
const quickOrderCreating = ref(false)
const pregnantList = ref<Pregnant[]>([])
const quickOrderForm = ref({
  pregnant_id: '',
  gestational_weeks: 28,
  risk_level: 'none' as string,
})

function calcGestWeekText(days?: number): string {
  if (!days) return '未知孕周'
  const w = Math.floor(days / 7)
  const d = days % 7
  return `${w}周+${d}天`
}

async function showQuickOrderDialog() {
  quickOrderDialogVisible.value = true
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data || []
  } catch (err) {
    console.error('加载孕妇列表失败:', err)
  }
}

function onQuickOrderPregnantSelect(pregnantId: string) {
  const p = pregnantList.value.find((item) => item.pregnant_id === pregnantId)
  if (p?.gestational_age_days) {
    quickOrderForm.value.gestational_weeks = parseFloat((p.gestational_age_days / 7).toFixed(1))
  }
}

async function doQuickOrder() {
  if (!quickOrderForm.value.pregnant_id) return
  quickOrderCreating.value = true
  try {
    const res = await orderApi.generate({
      pregnant_id: quickOrderForm.value.pregnant_id,
      risk_level: quickOrderForm.value.risk_level === 'none' ? 'GREEN' : quickOrderForm.value.risk_level,
      gestational_weeks: quickOrderForm.value.gestational_weeks,
    })
    quickOrderDialogVisible.value = false
    router.push({ name: 'OrderSign', params: { orderId: res.data.id } })
  } catch (err) {
    console.error('创建医嘱失败:', err)
  } finally {
    quickOrderCreating.value = false
  }
}
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/doctor/DoctorDashboard.vue
git commit -m "feat: add quick order entry in DoctorDashboard"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 启动后端验证降级 API**

```bash
cd backend && python -c "
from app.schemas import AlertReviewRequest
# 验证 downgrade action 通过校验
req = AlertReviewRequest(action='downgrade', reason='测试', target_level='ORANGE')
print('downgrade OK:', req)
# 验证 supplement action 通过校验
req2 = AlertReviewRequest(action='supplement', reason='补充资料测试')
print('supplement OK:', req2)
# 验证旧 action 仍然可用
req3 = AlertReviewRequest(action='confirm')
print('confirm OK:', req3)
"
```

- [ ] **Step 2: 验证订单生成 API 无 alert_id 时正常工作**

```bash
cd backend && python -c "
from app.services.order_service import order_service
# 验证通用模板兜底
rec = order_service.get_recommendation('none', 28, [])
print('fallback template:', rec['condition'])
# 验证无风险标签返回通用模板
rec2 = order_service.get_recommendation('GREEN', 20, ['常规'])
print('general fallback:', rec2['condition'])
"
```

- [ ] **Step 3: 验证前端构建无 TS 错误**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -30
```

预期：无新增类型错误。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: verification tests for downgrade and order generation"
```
