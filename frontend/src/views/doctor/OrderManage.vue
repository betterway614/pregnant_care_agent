<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">医嘱管理</h1>
      <el-button type="success" :icon="Plus" @click="showCreateOrderDialog">
        新建医嘱
      </el-button>
      <el-button type="primary" :icon="Refresh" @click="loadOrders" :loading="loading">
        刷新
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="search-bar">
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 150px" @change="loadOrders">
        <el-option label="全部" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="待签署" value="pending_sign" />
        <el-option label="已签署" value="signed" />
        <el-option label="已执行" value="executed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-input
        v-model="searchQuery"
        placeholder="搜索孕妇姓名..."
        clearable
        :prefix-icon="Search"
        style="width: 240px"
        @keyup.enter="loadOrders"
      />
      <el-button type="primary" :icon="Search" @click="loadOrders">搜索</el-button>
    </div>

    <!-- 医嘱列表 -->
    <div class="content-card">
      <div class="content-card__header">
        <span class="content-card__title">医嘱列表</span>
        <span class="text-light">共 {{ orders.length }} 条</span>
      </div>
      <div class="content-card__body" v-loading="loading">
        <el-table :data="orders" stripe style="width: 100%">
          <el-table-column label="日期" width="90" align="center">
            <template #default="{ row }">
              <span class="text-light">{{ formatDate(row.signed_at || row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="patient_name" label="孕妇" width="100" align="center" />
          <el-table-column label="医嘱内容" min-width="240" align="center">
            <template #default="{ row }">
              <span class="order-content-truncate">{{ truncateContent(row.content, 40) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="getOrderTypeTag(row.order_type)" size="small">
                {{ getOrderTypeText(row.order_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="80" align="center">
            <template #default="{ row }">
              {{ row.source === 'auto_generate' ? 'AI生成' : '手动' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="getStatusTag(row.status)" size="small" effect="plain">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="230" align="center">
            <template #default="{ row }">
              <div class="action-buttons">
                <el-button text type="info" size="small" :icon="View" @click="showDetail(row)">
                  详情
                </el-button>
                <el-button
                  v-if="row.status === 'draft'"
                  text
                  type="warning"
                  size="small"
                  :icon="Edit"
                  @click="handleEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-if="row.status === 'draft' || row.status === 'pending_sign'"
                  text
                  type="success"
                  size="small"
                  :icon="EditPen"
                  @click="confirmSignOrder(row)"
                >
                  签署
                </el-button>
                <el-button
                  v-if="row.status === 'draft' || row.status === 'cancelled'"
                  text
                  type="danger"
                  size="small"
                  :icon="Delete"
                  @click="confirmDeleteOrder(row)"
                >
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空状态 -->
        <div v-if="!orders.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><Document /></el-icon>
          <p>{{ searchQuery ? '未找到匹配的医嘱' : '暂无医嘱记录' }}</p>
        </div>
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="`医嘱详情 - ${detailOrder?.patient_name || ''}`"
      width="600px"
      destroy-on-close
    >
      <template v-if="detailOrder">
        <div class="detail-card">
          <div class="detail-card__section">
            <div class="detail-row">
              <span class="detail-row__label">孕妇姓名</span>
              <span class="detail-row__value">{{ detailOrder.patient_name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-row__label">医嘱类型</span>
              <el-tag size="small">{{ getOrderTypeText(detailOrder.order_type) }}</el-tag>
            </div>
            <div class="detail-row">
              <span class="detail-row__label">来源</span>
              <span>{{ detailOrder.source === 'auto_generate' ? 'AI自动生成' : '医生手动' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-row__label">状态</span>
              <el-tag :type="getStatusTag(detailOrder.status)" size="small" effect="plain">
                {{ getStatusText(detailOrder.status) }}
              </el-tag>
            </div>
            <div class="detail-row">
              <span class="detail-row__label">创建时间</span>
              <span>{{ formatTime(detailOrder.created_at) }}</span>
            </div>
            <div v-if="detailOrder.signed_at" class="detail-row">
              <span class="detail-row__label">签署时间</span>
              <span>{{ formatTime(detailOrder.signed_at) }}</span>
            </div>
          </div>

          <div class="detail-card__divider" />

          <div class="detail-card__section">
            <h4 class="detail-section-title">医嘱内容</h4>
            <div class="detail-content-box order-markdown" v-html="renderMarkdown(detailOrder.content)"></div>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 编辑医嘱对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑医嘱"
      width="560px"
      destroy-on-close
    >
      <div v-if="editingOrder" class="dialog-body">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        >
          孕妇：{{ editingOrder.patient_name }} ｜ 当前状态：草稿
        </el-alert>
        <el-form label-width="80px">
          <el-form-item label="医嘱类型">
            <el-select v-model="editForm.order_type" style="width: 100%">
              <el-option label="用药医嘱" value="用药医嘱" />
              <el-option label="检查医嘱" value="检查医嘱" />
              <el-option label="检验医嘱" value="检验医嘱" />
              <el-option label="治疗医嘱" value="治疗医嘱" />
              <el-option label="护理医嘱" value="护理医嘱" />
              <el-option label="饮食医嘱" value="饮食医嘱" />
              <el-option label="常规医嘱" value="standard" />
              <el-option label="紧急医嘱" value="urgent" />
            </el-select>
          </el-form-item>
          <el-form-item label="医嘱内容" required>
            <el-input
              v-model="editForm.content"
              type="textarea"
              :rows="5"
              placeholder="请输入医嘱内容"
              maxlength="1000"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!editForm.content.trim()" @click="doEditOrder">
          保存修改
        </el-button>
      </template>
    </el-dialog>

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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, Document, Plus, View, Edit, EditPen, Delete } from '@element-plus/icons-vue'
import { orderApi, dashboardApi } from '@/api/endpoints'
import type { MedicalOrder, Pregnant } from '@/types'
import { useAppStore } from '@/stores/app'
import { renderMarkdown } from '@/utils/markdown'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const submitting = ref(false)
const orders = ref<MedicalOrder[]>([])
const filterStatus = ref('')
const searchQuery = ref('')

// 详情弹窗
const detailDialogVisible = ref(false)
const detailOrder = ref<MedicalOrder | null>(null)

// 签署弹窗
const signDialogVisible = ref(false)
const signOrder = ref<MedicalOrder | null>(null)

// 编辑弹窗
const editDialogVisible = ref(false)
const editingOrder = ref<MedicalOrder | null>(null)
const editForm = ref({ content: '', order_type: '' })

/** 格式化日期 */
function formatDate(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** 格式化时间 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 截断内容 */
function truncateContent(content: string, maxLen: number): string {
  if (!content) return ''
  return content.length > maxLen ? content.slice(0, maxLen) + '...' : content
}

/** 医嘱类型汉化 */
function getOrderTypeText(type: string): string {
  const map: Record<string, string> = {
    用药医嘱: '用药',
    检查医嘱: '检查',
    检验医嘱: '检验',
    治疗医嘱: '治疗',
    护理医嘱: '护理',
    饮食医嘱: '饮食',
    standard: '常规',
    urgent: '紧急',
  }
  return map[type] || type
}

/** 医嘱类型标签颜色（按严重/紧急程度映射） */
function getOrderTypeTag(type: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    用药医嘱: 'warning',
    检查医嘱: 'primary',
    检验医嘱: 'info',
    治疗医嘱: 'danger',
    护理医嘱: 'success',
    饮食医嘱: 'success',
    standard: 'info',
    urgent: 'danger',
  }
  return map[type] || 'info'
}

/** 状态标签颜色 */
function getStatusTag(status: string): 'info' | 'warning' | 'success' | 'danger' | 'primary' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
    draft: 'info',
    pending_sign: 'warning',
    signed: 'success',
    executed: 'primary',
    cancelled: 'danger',
  }
  return map[status] || 'info'
}

/** 状态文本 */
function getStatusText(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    pending_sign: '待签署',
    signed: '已签署',
    executed: '已执行',
    cancelled: '已取消',
  }
  return map[status] || status
}

/** 加载医嘱列表 */
async function loadOrders() {
  loading.value = true
  try {
    const params: { status?: string; pregnant_id?: string } = {}
    if (filterStatus.value) {
      // 明确选择了某个状态筛选
      params.status = filterStatus.value
    } else {
      // 默认"全部"排除已取消的医嘱，保持列表清爽，已取消需主动筛选
      params.status = 'draft,pending_sign,signed,executed'
    }
    const res = await orderApi.list(params)
    let list = res.data || []

    // 前端搜索过滤
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      list = list.filter((o) => o.patient_name?.toLowerCase().includes(q))
    }

    orders.value = list
  } catch (err) {
    console.error('加载医嘱列表失败:', err)
  } finally {
    loading.value = false
  }
}

/** 查看详情 */
function showDetail(order: MedicalOrder) {
  detailOrder.value = order
  detailDialogVisible.value = true
}

/** 编辑 */
function handleEdit(order: MedicalOrder) {
  editingOrder.value = order
  editForm.value = { content: order.content, order_type: order.order_type }
  editDialogVisible.value = true
}

/** 保存编辑 */
async function doEditOrder() {
  if (!editingOrder.value || !editForm.value.content.trim()) return
  submitting.value = true
  try {
    await orderApi.update(editingOrder.value.id, {
      content: editForm.value.content,
      order_type: editForm.value.order_type,
    })
    editDialogVisible.value = false
    editingOrder.value = null
    await loadOrders()
  } catch (err) {
    console.error('编辑医嘱失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 签署确认弹窗 — 跳转到医嘱签名页 */
function confirmSignOrder(order: MedicalOrder) {
  router.push({ name: 'OrderSign', params: { orderId: order.id } })
}

/** 删除确认弹窗 */
function confirmDeleteOrder(order: MedicalOrder) {
  ElMessageBox.confirm(
    `确定要删除孕妇「${order.patient_name}」的医嘱吗？删除后状态将变为"已取消"。`,
    '删除确认',
    {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
    },
  )
    .then(async () => {
      try {
        await orderApi.delete(order.id)
        ElMessage.success('医嘱已删除')
        await loadOrders()
      } catch (err: any) {
        ElMessage.error(err?.response?.data?.detail || '删除失败')
      }
    })
    .catch(() => {
      // 用户取消删除
    })
}

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
    pregnantList.value = res.data?.data || []
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

onMounted(loadOrders)
</script>

<style scoped>
/* 医嘱内容截断 */
.order-content-truncate {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* 详情卡片 */
.detail-card {
  padding: 0 4px;
}

.detail-card__section {
  margin-bottom: 18px;
}

.detail-card__divider {
  height: 1px;
  background: var(--border);
  margin: 18px 0;
}

.detail-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px dashed var(--border);
  transition: background var(--transition-fast);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row:hover {
  background: rgba(232, 245, 233, 0.15);
  border-radius: var(--radius-xs);
  margin: 0 -4px;
  padding-left: 4px;
  padding-right: 4px;
}

.detail-row__label {
  width: 90px;
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-weight: 500;
}

.detail-row__value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.detail-section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 14px;
}

.detail-content-box {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
}
.detail-content-box.order-markdown {
  white-space: normal;
}
.detail-content-box.order-markdown :deep(h1),
.detail-content-box.order-markdown :deep(h2),
.detail-content-box.order-markdown :deep(h3),
.detail-content-box.order-markdown :deep(h4) {
  font-size: 15px;
  font-weight: 700;
  margin: 12px 0 6px;
  line-height: 1.5;
  color: var(--text-primary);
}
.detail-content-box.order-markdown :deep(p) {
  margin: 4px 0;
}
.detail-content-box.order-markdown :deep(ul),
.detail-content-box.order-markdown :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}
.detail-content-box.order-markdown :deep(li) {
  margin: 2px 0;
}
.detail-content-box.order-markdown :deep(strong) {
  font-weight: 700;
}
.detail-content-box.order-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}
.detail-content-box.order-markdown :deep(th),
.detail-content-box.order-markdown :deep(td) {
  border: 1px solid var(--border);
  padding: 4px 8px;
  text-align: left;
}
.detail-content-box.order-markdown :deep(th) {
  background: #f0f0f0;
  font-weight: 700;
}
.detail-content-box.order-markdown :deep(blockquote) {
  border-left: 3px solid var(--border);
  margin: 8px 0;
  padding-left: 12px;
  color: var(--text-muted);
}
.detail-content-box.order-markdown :deep(hr) {
  border: none;
  border-top: 1px dashed var(--border);
  margin: 12px 0;
}
.detail-content-box.order-markdown :deep(code) {
  background: rgba(0,0,0,0.04);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
}

/* 签署预览 */
.sign-preview {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 16px;
  border: 1px solid var(--border);
}

.sign-preview__patient {
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--text-primary);
  font-weight: 600;
}

.sign-preview__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}

.empty-state p {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}

.dialog-body {
  padding: 8px 0;
}

/* 操作按钮组 — 居中 + 自适应不截断 */
.action-buttons {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.action-buttons .el-button {
  transition: all var(--transition-fast);
  padding: 0 5px;
  min-width: auto;
}
</style>
