<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">预警管理</h1>
      <el-button type="primary" class="brand-gradient-btn" :icon="Refresh" @click="fetchAlerts" :loading="loading">
        刷新
      </el-button>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      closable
      class="mb-4"
      @close="error = ''"
    />

    <!-- 筛选栏 -->
    <div class="search-bar">
      <el-select v-model="filterLevel" placeholder="预警级别筛选" clearable style="width: 160px" @change="handleFilterChange">
        <el-option label="全部级别" value="" />
        <el-option label="红色高危" value="RED" />
        <el-option label="橙色预警" value="ORANGE" />
        <el-option label="黄色关注" value="YELLOW" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="处理状态筛选" clearable style="width: 160px" @change="handleFilterChange">
        <el-option label="全部状态" value="" />
        <el-option label="待处理" value="PENDING" />
        <el-option label="已确认" value="CONFIRMED" />
        <el-option label="已驳回" value="DISMISSED" />
      </el-select>
      <span class="text-light filter-summary" v-if="alerts.length">
        共 {{ alerts.length }} 条预警
      </span>
    </div>

    <!-- 预警列表 -->
    <div class="content-card">
      <div class="content-card__body" v-loading="loading">
        <el-table
          :data="alerts"
          stripe
          style="width: 100%"
          size="small"
          @row-click="viewDetail"
        >
          <el-table-column label="时间" width="150">
            <template #default="{ row }">
              <span class="text-nowrap">{{ formatTime(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="patient_name" label="孕妇" min-width="90" />
          <el-table-column label="预警级别" width="110">
            <template #default="{ row }">
              <RiskBadge :level="row.level" />
            </template>
          </el-table-column>
          <el-table-column prop="trigger_source" label="触发规则" min-width="100" show-overflow-tooltip />
          <el-table-column prop="message" label="预警消息" min-width="200" show-overflow-tooltip />
          <el-table-column label="处理状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <div class="table-row-actions table-row-actions--alert">
                <el-button type="primary" class="brand-gradient-btn" size="small" @click.stop="goPregnantDetail(row)">
                  孕妇详情
                </el-button>
                <template v-if="isAlertPending(row.status)">
                  <el-button type="primary" class="brand-gradient-btn" size="small" @click.stop="handleReview(row, 'confirm')">
                    确认
                  </el-button>
                  <el-button type="primary" class="brand-gradient-btn" size="small" @click.stop="handleReview(row, 'dismiss')">
                    驳回
                  </el-button>
                </template>
                <el-tag v-else size="small" effect="plain" :type="statusTagType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空状态 -->
        <div v-if="!alerts.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><Bell /></el-icon>
          <p>{{ hasActiveFilter ? '暂无匹配的预警记录' : '暂无预警，一切正常' }}</p>
        </div>
      </div>
    </div>

    <!-- 预警详情抽屉 -->
    <el-drawer
      v-model="detailVisible"
      :title="`预警详情 - ${selectedAlert?.patient_name || ''}`"
      size="500px"
      destroy-on-close
    >
      <template v-if="selectedAlert">
        <div class="detail-section">
          <div class="detail-row">
            <span class="detail-label">孕妇</span>
            <span class="detail-value">{{ selectedAlert.patient_name || '--' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">预警级别</span>
            <RiskBadge :level="selectedAlert.level" />
          </div>
          <div class="detail-row">
            <span class="detail-label">处理状态</span>
            <el-tag :type="statusTagType(selectedAlert.status)" size="small" effect="plain">
              {{ statusLabel(selectedAlert.status) }}
            </el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">触发来源</span>
            <span class="detail-value">{{ selectedAlert.trigger_source || '--' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">规则ID</span>
            <span class="detail-value">{{ selectedAlert.rule_id || '--' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">孕周</span>
            <span class="detail-value">
              {{ selectedAlert.gestational_age_days ? Math.floor(selectedAlert.gestational_age_days / 7) + '周' : '--' }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">预警时间</span>
            <span class="detail-value">{{ formatTime(selectedAlert.created_at) }}</span>
          </div>
        </div>

        <el-divider />

        <div class="detail-section">
          <h4 class="detail-section__title">预警消息</h4>
          <p class="detail-section__content">{{ selectedAlert.message || '--' }}</p>
        </div>

        <div class="detail-section" v-if="Object.keys(selectedAlert.details || {}).length">
          <h4 class="detail-section__title">原始数据</h4>
          <pre class="detail-section__pre">{{ JSON.stringify(selectedAlert.details, null, 2) }}</pre>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Refresh, Bell } from '@element-plus/icons-vue'
import { alertApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import type { Alert } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const alerts = ref<Alert[]>([])
const filterLevel = ref('')
const filterStatus = ref('')

/** 详情抽屉 */
const detailVisible = ref(false)
const selectedAlert = ref<Alert | null>(null)

/** 查看详情 */
function viewDetail(row: Alert) {
  selectedAlert.value = row
  detailVisible.value = true
}

/** 跳转到孕妇详情页 */
function goPregnantDetail(row: Alert) {
  if (row.pregnant_id) {
    router.push({ name: 'NursePregnantDetail', params: { pregnantId: row.pregnant_id } })
  }
}

/** 是否有活跃筛选条件 */
const hasActiveFilter = computed(() => !!(filterLevel.value || filterStatus.value))

/** 与后端一致的状态码（大小写不敏感） */
function normalizeAlertStatus(status: string): string {
  return (status || '').toUpperCase()
}

function isAlertPending(status: string): boolean {
  return normalizeAlertStatus(status) === 'PENDING'
}

/** 状态标签映射（展示中文，兼容后端大写枚举） */
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    PENDING: '待处理',
    CONFIRMED: '已确认',
    DISMISSED: '已驳回',
  }
  return map[normalizeAlertStatus(status)] || status
}

/** 状态标签类型 */
function statusTagType(status: string): string {
  const map: Record<string, string> = {
    PENDING: 'warning',
    CONFIRMED: 'success',
    DISMISSED: 'info',
  }
  return map[normalizeAlertStatus(status)] || 'info'
}

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return '--'
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 筛选变化时重新加载 */
function handleFilterChange() {
  fetchAlerts()
}

/** 加载预警列表 */
async function fetchAlerts() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (filterLevel.value) params.level = filterLevel.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await alertApi.list(params)
    alerts.value = res.data || []
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '加载预警失败'
    error.value = msg
    console.error('加载预警列表失败:', err)
  } finally {
    loading.value = false
  }
}

/** 处理预警（确认/驳回），action 与后端 AlertReviewRequest 一致 */
async function handleReview(alert: Alert, action: 'confirm' | 'dismiss') {
  const actionText = action === 'confirm' ? '确认' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确定${actionText}该预警？`,
      `${actionText}预警`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: action === 'confirm' ? 'primary' : 'warning' }
    )
  } catch {
    return
  }

  try {
    await alertApi.review(alert.id, action)
    ElMessage.success(`${actionText}成功`)
    await fetchAlerts()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || `${actionText}失败`
    ElMessage.error(msg)
    console.error(`${actionText}预警失败:`, err)
  }
}

onMounted(fetchAlerts)
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.search-bar {
  margin-bottom: 20px;
  align-items: center;
}

.filter-summary {
  margin-left: 8px;
}

.text-nowrap {
  white-space: nowrap;
}

.text-light {
  font-size: 12px;
  color: var(--text-light);
}

/* 详情抽屉 */
.detail-section {
  margin-bottom: 16px;
}

.detail-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.detail-section__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

.detail-row {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  width: 80px;
  font-size: 13px;
  color: var(--text-light);
  flex-shrink: 0;
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.detail-section__pre {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  margin: 0;
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

/* 操作列：表头与单元格居中，与全局 table-row-actions 左对齐区分 */
.table-row-actions.table-row-actions--alert {
  justify-content: center;
}
</style>
