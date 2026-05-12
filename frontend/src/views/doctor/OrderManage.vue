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

    <!-- 签署确认对话框 -->
    <el-dialog
      v-model="signDialogVisible"
      title="签署确认"
      width="400px"
      destroy-on-close
    >
      <div class="dialog-body">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        >
          请确认已审核医嘱内容，签署后将生效执行。
        </el-alert>
        <div v-if="signOrder" class="sign-preview">
          <p class="sign-preview__patient">
            <strong>孕妇：</strong>{{ signOrder.patient_name }}
          </p>
          <p class="sign-preview__content">{{ truncateContent(signOrder.content, 80) }}</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="signDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSignOrder">
          确认签署
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Search, Refresh, Document } from '@element-plus/icons-vue'
import { orderApi } from '@/api/endpoints'
import type { MedicalOrder } from '@/types'
import { useAppStore } from '@/stores/app'

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
  // 预留编辑功能，可跳转或打开编辑弹窗
}

/** 签署确认弹窗 */
function confirmSignOrder(order: MedicalOrder) {
  signOrder.value = order
  signDialogVisible.value = true
}

/** 执行签署 */
async function doSignOrder() {
  if (!signOrder.value) return
  submitting.value = true
  try {
    const doctorId = appStore.currentRole === 'doctor' ? 'doctor_001' : 'current-doctor'
    await orderApi.sign(signOrder.value.id, doctorId)
    signDialogVisible.value = false
    signOrder.value = null
    await loadOrders()
  } catch (err) {
    console.error('签署医嘱失败:', err)
  } finally {
    submitting.value = false
  }
}

onMounted(loadOrders)
</script>

<style scoped>
/* 医嘱内容截断 */
.order-content-truncate {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* 详情卡片 */
.detail-card {
  padding: 0 4px;
}

.detail-card__section {
  margin-bottom: 16px;
}

.detail-card__divider {
  height: 1px;
  background: var(--border);
  margin: 16px 0;
}

.detail-row {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed var(--border);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row__label {
  width: 90px;
  font-size: 13px;
  color: var(--text-light);
  flex-shrink: 0;
}

.detail-row__value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.detail-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.detail-content-box {
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
}

/* 签署预览 */
.sign-preview {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 14px;
}

.sign-preview__patient {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.sign-preview__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.text-light {
  font-size: 12px;
  color: var(--text-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 0;
  gap: 12px;
}

.empty-state p {
  color: var(--text-light);
  font-size: 14px;
}

.dialog-body {
  padding: 8px 0;
}
</style>
