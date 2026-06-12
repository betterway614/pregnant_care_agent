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
        <el-option label="已升级" value="ESCALATED" />
        <el-option label="已自动关闭" value="AUTO_DISMISSED" />
      </el-select>
      <el-select v-model="filterPregnantId" placeholder="按孕妇筛选" clearable filterable style="width: 180px" @change="handleFilterChange">
        <el-option v-for="p in pregnantList" :key="p.pregnant_id" :label="p.display_name" :value="p.pregnant_id" />
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
                  <el-button size="small" type="primary" @click.stop="handleReview(row, 'nurse_confirm')">
                    确认
                  </el-button>
                  <el-button
                    v-if="row.level === 'YELLOW' || row.level === 'ORANGE'"
                    size="small" type="warning"
                    @click.stop="handleReview(row, 'nurse_escalate')"
                  >
                    {{ row.level === 'YELLOW' ? '升级' : '升级为红色' }}
                  </el-button>
                  <el-button
                    v-if="hasBeenDowngraded(row)"
                    size="small" type="danger"
                    @click.stop="handleReview(row, 'nurse_appeal')"
                  >
                    复议
                  </el-button>
                  <el-button size="small" @click.stop="handleReview(row, 'nurse_dismiss')">
                    解除
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

        <!-- LLM 分析结果 -->
        <template v-if="selectedAlert.details?.llm_analysis">
          <el-divider />
          <div class="detail-section">
            <h4 class="detail-section__title">
              <el-icon><MagicStick /></el-icon>
              AI 分析
            </h4>
            <div class="llm-analysis">
              <div class="llm-block">
                <span class="llm-block__label">风险解读</span>
                <p class="llm-block__content">{{ selectedAlert.details.llm_analysis.risk_interpretation }}</p>
              </div>
              <div class="llm-block">
                <span class="llm-block__label">建议措施</span>
                <ul class="llm-block__list">
                  <li v-for="(action, i) in selectedAlert.details.llm_analysis.recommended_actions" :key="i">
                    {{ action }}
                  </li>
                </ul>
              </div>
              <div class="llm-block">
                <span class="llm-block__label">严重程度评估</span>
                <p class="llm-block__content">{{ selectedAlert.details.llm_analysis.severity_assessment }}</p>
              </div>
            </div>
          </div>
        </template>

        <div class="detail-section" v-if="hasRawDetails(selectedAlert.details)">
          <h4 class="detail-section__title">原始数据</h4>
          <pre class="detail-section__pre">{{ formatRawDetails(selectedAlert.details) }}</pre>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Refresh, Bell, MagicStick } from '@element-plus/icons-vue'
import { alertApi, dashboardApi } from '@/api/endpoints'
import { getNurseWebSocketClient } from '@/utils/websocket'
import { useAppStore } from '@/stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import type { Alert } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

const router = useRouter()
const appStore = useAppStore()
const nurseId = ref(appStore.currentUserId || 'nurse')
let wsClient: any = null

const loading = ref(false)
const error = ref('')
const submitting = ref(false)
const alerts = ref<Alert[]>([])
const filterLevel = ref('')
const filterStatus = ref('')
const filterPregnantId = ref('')
const pregnantList = ref<any[]>([])

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
    ESCALATED: '已升级',
    AUTO_DISMISSED: '已自动关闭',
  }
  return map[normalizeAlertStatus(status)] || status
}

/** 状态标签类型 */
function statusTagType(status: string): string {
  const map: Record<string, string> = {
    PENDING: 'warning',
    CONFIRMED: 'success',
    DISMISSED: 'info',
    ESCALATED: 'danger',
    AUTO_DISMISSED: 'info',
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

/** 判断是否有原始数据（排除 llm_analysis） */
function hasRawDetails(details: Record<string, any> | undefined): boolean {
  if (!details) return false
  const raw = { ...details }
  delete raw.llm_analysis
  return Object.keys(raw).length > 0
}

/** 格式化原始数据（排除 llm_analysis） */
function formatRawDetails(details: Record<string, any>): string {
  const raw = { ...details }
  delete raw.llm_analysis
  return JSON.stringify(raw, null, 2)
}

/** 加载预警列表 */
async function fetchAlerts() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (filterLevel.value) params.level = filterLevel.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPregnantId.value) params.pregnant_id = filterPregnantId.value
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

/** 检查预警是否曾被医生降级过 */
function hasBeenDowngraded(row: any): boolean {
  return row.details?.history?.some((h: any) => h.action === 'downgrade') ?? false
}

/** 处理预警（确认/解除/升级/复议），action 与后端 AlertReviewRequest 一致 */
async function handleReview(row: any, action: string) {
  const actionsNeedReason = ['nurse_dismiss', 'nurse_escalate', 'nurse_appeal', 'dismiss']
  let reason = ''
  let targetLevel: string | undefined

  if (actionsNeedReason.includes(action)) {
    try {
      const { value } = await ElMessageBox.prompt(
        action === 'nurse_escalate' ? '请填写升级理由' :
        action === 'nurse_appeal' ? '请填写复议理由' : '请填写理由',
        '操作确认'
      )
      reason = value
    } catch {
      return
    }
  }

  if (action === 'nurse_escalate') {
    const newLevel = row.level === 'YELLOW' ? 'ORANGE' : 'RED'
    try {
      await ElMessageBox.confirm(
        `确认将预警从 ${row.level} 升级为 ${newLevel}？`,
        '升级确认',
        { confirmButtonText: '确认升级', type: 'warning' }
      )
    } catch {
      return
    }
  }

  submitting.value = true
  try {
    await alertApi.review(row.id, action, reason)
    ElMessage.success('操作成功')
    await fetchAlerts()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchAlerts()
  // 加载孕妇列表用于筛选
  dashboardApi.pregnant({ page_size: 100 }).then(res => {
    pregnantList.value = res.data?.data || []
  }).catch(() => {})
  wsClient = getNurseWebSocketClient(nurseId.value)
  wsClient.onAlert(() => {
    fetchAlerts()
  })
  wsClient.connect()
})

onUnmounted(() => {
  if (wsClient) {
    wsClient.disconnect()
  }
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.filter-summary {
  margin-left: 8px;
}

.text-nowrap {
  white-space: nowrap;
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}

/* 详情抽屉 */
.detail-section {
  margin-bottom: 20px;
}

.detail-section__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.detail-section__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
}

.detail-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
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

.detail-label {
  width: 80px;
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-weight: 500;
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.detail-section__pre {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  padding: 14px;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  margin: 0;
  border: 1px solid var(--border);
}

/* 操作列：表头与单元格居中，与全局 table-row-actions 左对齐区分 */
.table-row-actions.table-row-actions--alert {
  justify-content: center;
}

/* LLM 分析区块 */
.llm-analysis {
  background: linear-gradient(135deg, rgba(46, 125, 50, 0.04), rgba(102, 187, 106, 0.04));
  border: 1px solid rgba(46, 125, 50, 0.12);
  border-radius: var(--radius-sm);
  padding: 16px;
}

.llm-block {
  margin-bottom: 14px;
}

.llm-block:last-child {
  margin-bottom: 0;
}

.llm-block__label {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  background: var(--primary-bg);
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.llm-block__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
}

.llm-block__list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.llm-block__list li {
  margin-bottom: 4px;
}
</style>
