<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">预警管理</h1>
      <el-button type="primary" :icon="Refresh" @click="fetchAlerts" :loading="loading">
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
        <el-option label="待处理" value="pending" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已驳回" value="dismissed" />
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
          :default-expand-all="false"
          row-key="id"
        >
          <!-- 展开行 -->
          <el-table-column type="expand" width="40">
            <template #default="{ row }">
              <div class="expand-detail">
                <div class="expand-detail__section">
                  <h4 class="expand-detail__title">预警详情</h4>
                  <div class="expand-detail__grid">
                    <div class="expand-detail__item">
                      <span class="expand-detail__label">触发来源</span>
                      <span class="expand-detail__value">{{ row.trigger_source || '--' }}</span>
                    </div>
                    <div class="expand-detail__item">
                      <span class="expand-detail__label">规则ID</span>
                      <span class="expand-detail__value">{{ row.rule_id || '--' }}</span>
                    </div>
                    <div class="expand-detail__item">
                      <span class="expand-detail__label">孕周</span>
                      <span class="expand-detail__value">
                        {{ row.gestational_age_days ? Math.floor(row.gestational_age_days / 7) + '周' : '--' }}
                      </span>
                    </div>
                    <div class="expand-detail__item">
                      <span class="expand-detail__label">预警时间</span>
                      <span class="expand-detail__value">{{ formatTime(row.created_at) }}</span>
                    </div>
                  </div>
                </div>

                <div class="expand-detail__section" v-if="Object.keys(row.details || {}).length">
                  <h4 class="expand-detail__title">原始数据</h4>
                  <pre class="expand-detail__pre">{{ JSON.stringify(row.details, null, 2) }}</pre>
                </div>
              </div>
            </template>
          </el-table-column>

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
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button size="small" type="primary" @click.stop="handleReview(row, 'confirmed')">
                  确认
                </el-button>
                <el-button size="small" @click.stop="handleReview(row, 'dismissed')">
                  驳回
                </el-button>
              </template>
              <span v-else class="text-light handled-text">
                {{ row.status === 'confirmed' ? '已处理' : '已驳回' }}
              </span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Refresh, Bell } from '@element-plus/icons-vue'
import { alertApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Alert } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

const loading = ref(false)
const error = ref('')
const alerts = ref<Alert[]>([])
const filterLevel = ref('')
const filterStatus = ref('')

/** 是否有活跃筛选条件 */
const hasActiveFilter = computed(() => !!(filterLevel.value || filterStatus.value))

/** 状态标签映射 */
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理',
    confirmed: '已确认',
    dismissed: '已驳回',
  }
  return map[status] || status
}

/** 状态标签类型 */
function statusTagType(status: string): string {
  const map: Record<string, string> = {
    pending: 'warning',
    confirmed: 'success',
    dismissed: 'info',
  }
  return map[status] || 'info'
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

/** 处理预警（确认/驳回） */
async function handleReview(alert: Alert, action: string) {
  const actionText = action === 'confirmed' ? '确认' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确定${actionText}该预警？`,
      `${actionText}预警`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: action === 'confirmed' ? 'primary' : 'warning' }
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

.handled-text {
  font-size: 13px;
  padding: 0 8px;
}

/* 展开详情 */
.expand-detail {
  padding: 12px 24px 12px 40px;
  background: var(--bg-page);
  border-radius: var(--radius-sm);
}

.expand-detail__section {
  margin-bottom: 16px;
}

.expand-detail__section:last-child {
  margin-bottom: 0;
}

.expand-detail__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.expand-detail__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.expand-detail__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.expand-detail__label {
  font-size: 11px;
  color: var(--text-light);
}

.expand-detail__value {
  font-size: 13px;
  color: var(--text-primary);
}

.expand-detail__pre {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
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
</style>
