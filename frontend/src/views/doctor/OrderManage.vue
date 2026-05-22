<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">医嘱管理</h1>
      <el-button type="primary" :icon="Refresh" @click="loadOrders" :loading="loading">
        刷新
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="search-bar">
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 150px" @change="loadOrders">
        <el-option label="全部" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="已签署" value="signed" />
        <el-option label="已执行" value="executed" />
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
              <span class="text-light">{{ formatDate(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="patient_name" label="孕妇" width="100" />
          <el-table-column label="医嘱内容" min-width="240">
            <template #default="{ row }">
              <span class="order-content-truncate">{{ truncateContent(row.content, 40) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="getOrderTypeTag(row.order_type)" size="small">
                {{ row.order_type }}
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
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="showDetail(row)">
                详情
              </el-button>
              <el-button
                v-if="row.status === 'draft'"
                text
                type="warning"
                size="small"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="row.status === 'draft' || row.status === 'pending_sign'"
                text
                type="success"
                size="small"
                @click="confirmSignOrder(row)"
              >
                签署
              </el-button>
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
              <el-tag size="small">{{ detailOrder.order_type }}</el-tag>
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
          </div>

          <div class="detail-card__divider" />

          <div class="detail-card__section">
            <h4 class="detail-section-title">医嘱内容</h4>
            <div class="detail-content-box">
              {{ detailOrder.content }}
            </div>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, Document } from '@element-plus/icons-vue'
import { orderApi } from '@/api/endpoints'
import type { MedicalOrder } from '@/types'
import { useAppStore } from '@/stores/app'

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

/** 医嘱类型标签颜色 */
function getOrderTypeTag(type: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    用药医嘱: 'warning',
    检查医嘱: 'primary',
    检验医嘱: 'info',
    治疗医嘱: 'danger',
    护理医嘱: 'success',
    饮食医嘱: 'success',
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
      params.status = filterStatus.value
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
  white-space: pre-wrap;
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
</style>
