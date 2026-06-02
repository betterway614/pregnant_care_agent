<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">医生工作台</h1>
      <div class="page-header__actions">
        <!-- WebSocket 连接状态指示器 -->
        <el-tag
          :type="wsConnected ? 'success' : 'danger'"
          size="small"
          effect="plain"
        >
          {{ wsConnected ? '实时连接' : '连接断开' }}
        </el-tag>
        <el-button type="success" :icon="Plus" @click="showQuickOrderDialog">
          快速开医嘱
        </el-button>
        <el-button type="primary" :icon="Refresh" @click="loadAllData" :loading="loading">
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 新预警通知横幅 -->
    <el-alert
      v-if="newAlert"
      :title="`新预警: ${newAlert.patient_name}`"
      :description="newAlert.message"
      :type="getAlertType(newAlert.level)"
      show-icon
      :closable="true"
      @close="newAlert = null"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>{{ newAlert.message }}</span>
          <el-button type="primary" size="small" @click="goToReview(newAlert)">
            立即处理
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-grid-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in statCards" :key="card.label">
        <div class="stat-card-wrapper" @click="card.route && $router.push(card.route)">
          <StatCard
            :icon="card.icon"
            :value="card.value"
            :label="card.label"
            :color="card.color"
            :bg-color="card.bgColor"
            :sub-label="card.subLabel"
          />
        </div>
      </el-col>
    </el-row>

    <!-- 主要内容区域 -->
    <el-row :gutter="16">
      <!-- 高危预警概览 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">高危预警概览</span>
            <el-tag v-if="alertStats.highCount" type="danger" size="small">
              待处理 {{ alertStats.highCount }} 条
            </el-tag>
          </div>
          <div class="content-card__body" v-loading="loading">
            <el-table :data="recentAlerts" stripe style="width: 100%" size="small" @row-click="handleAlertClick">
              <el-table-column prop="patient_name" label="孕妇" min-width="90" />
              <el-table-column label="风险级别" width="100">
                <template #default="{ row }">
                  <div :class="{ 'new-alert-highlight': isNewAlert(row.id) }">
                    <RiskBadge :level="mapRiskLevel(row.level)" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="孕周" width="70" align="center">
                <template #default="{ row }">
                  {{ calcGestationalWeek(row.gestational_age_days) }}周
                </template>
              </el-table-column>
              <el-table-column prop="message" label="预警原因" min-width="160" show-overflow-tooltip />
              <el-table-column label="时间" width="80" align="center">
                <template #default="{ row }">
                  <span class="text-light">{{ formatTime(row.created_at) }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!recentAlerts.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><Bell /></el-icon>
              <p>暂无待处理预警</p>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 待处理医嘱 -->
      <el-col :span="10">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">待处理医嘱</span>
            <el-button text type="primary" size="small" @click="$router.push('/doctor/orders')">
              查看全部
            </el-button>
          </div>
          <div class="content-card__body" v-loading="loading">
            <div v-for="order in pendingOrders" :key="order.id" class="order-item">
              <div class="order-item__header">
                <span class="order-item__patient">{{ order.patient_name }}</span>
                <el-tag
                  :type="order.status === 'draft' ? 'info' : 'warning'"
                  size="small"
                >
                  {{ order.status === 'draft' ? '草稿' : '待签署' }}
                </el-tag>
              </div>
              <p class="order-item__content">{{ order.content }}</p>
              <div class="order-item__footer">
                <span class="text-light">{{ formatTime(order.created_at) }}</span>
                <el-button
                  v-if="order.status === 'draft'"
                  text
                  type="primary"
                  size="small"
                  @click="$router.push('/doctor/orders')"
                >
                  编辑
                </el-button>
                <el-button
                  v-else
                  text
                  type="primary"
                  size="small"
                  @click="handleSignOrder(order)"
                >
                  签署
                </el-button>
              </div>
            </div>
            <div v-if="!pendingOrders.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><Document /></el-icon>
              <p>暂无待处理医嘱</p>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Bell, Document, Plus } from '@element-plus/icons-vue'
import { dashboardApi, alertApi, orderApi } from '@/api/endpoints'
import { getWebSocketClient } from '@/utils/websocket'
import { useAppStore } from '@/stores/app'
import type { Alert, MedicalOrder, DashboardStats, Pregnant } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { ElNotification } from 'element-plus'

const router = useRouter()
const appStore = useAppStore()
const loading = ref(false)
const stats = ref<DashboardStats>({
  total_pregnant: 0,
  pending_alerts: 0,
  today_followups: 0,
  pending_reviews: 0,
  high_risk_count: 0,
  weekly_new_pregnant: 0,
})
const recentAlerts = ref<Alert[]>([])
const pendingOrders = ref<MedicalOrder[]>([])

// WebSocket 相关状态
const wsConnected = ref(false)
const newAlert = ref<Alert | null>(null)
const newAlertIds = ref<Set<string>>(new Set())
const wsClient = ref<ReturnType<typeof getWebSocketClient> | null>(null)

/** 统计卡片配置 */
const statCards = computed(() => [
  {
    icon: 'WarningFilled',
    value: stats.value.high_risk_count,
    label: '高危孕妇数',
    color: '#D32F2F',
    bgColor: '#FFEBEE',
    subLabel: '红色高危',
    route: '/doctor/review',
  },
  {
    icon: 'Bell',
    value: stats.value.pending_alerts,
    label: '待审核预警',
    color: '#E65100',
    bgColor: '#FFF3E0',
    subLabel: '待处理',
    route: '/doctor/review',
  },
  {
    icon: 'Edit',
    value: stats.value.pending_reviews,
    label: '待签署医嘱',
    color: '#1976D2',
    bgColor: '#E3F2FD',
    subLabel: '等待签署',
    route: '/doctor/orders',
  },
  {
    icon: 'DataAnalysis',
    value: fgrHighRiskCount.value,
    label: 'FGR高风险数',
    color: '#7B1FA2',
    bgColor: '#F3E5F5',
    subLabel: '胎儿生长受限',
    route: '/doctor/fgr-board',
  },
])

/** FGR高风险计数（从预警中统计） */
const fgrHighRiskCount = computed(() =>
  recentAlerts.value.filter(
    (a) => a.level === 'RED' && a.trigger_source?.toLowerCase().includes('fgr')
  ).length
)

/** 预警概览统计 */
const alertStats = computed(() => ({
  total: recentAlerts.value.length,
  highCount: recentAlerts.value.filter((a) => a.level === 'RED' || a.level === 'ORANGE').length,
}))

/** 风险级别映射 */
function mapRiskLevel(level: string): string {
  const map: Record<string, string> = {
    RED: 'RED',
    ORANGE: 'ORANGE',
    YELLOW: 'YELLOW',
    GREEN: 'GREEN',
    high: 'RED',
    medium: 'ORANGE',
    low: 'YELLOW',
  }
  return map[level] || 'YELLOW'
}

/** 计算孕周 */
function calcGestationalWeek(days?: number): number {
  if (!days) return 0
  return Math.floor(days / 7)
}

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 加载所有数据 */
async function loadAllData() {
  loading.value = true
  try {
    const [statsRes, alertsRes, ordersRes] = await Promise.all([
      dashboardApi.stats(),
      alertApi.list({ status: 'pending,escalated' }),
      orderApi.list({ status: 'draft,pending_sign' }),
    ])
    stats.value = statsRes.data
    recentAlerts.value = (alertsRes.data || []).slice(0, 10)
    pendingOrders.value = (ordersRes.data || []).slice(0, 8)
  } catch (err) {
    console.error('加载工作台数据失败:', err)
  } finally {
    loading.value = false
  }
}

/** 点击预警行跳转到孕妇详情页 */
function handleAlertClick(alert: Alert) {
  if (alert.pregnant_id) {
    router.push({ name: 'DoctorPregnantDetail', params: { pregnantId: alert.pregnant_id } })
  }
}

/** 签署医嘱 — 跳转到医嘱签名页 */
function handleSignOrder(order: MedicalOrder) {
  router.push({ name: 'OrderSign', params: { orderId: order.id } })
}

/**
 * 处理连接状态变化回调（命名函数以便注销）
 */
function handleStateChange(state: string) {
  wsConnected.value = state === 'OPEN'
}

/**
 * 处理新预警回调（命名函数以便注销）
 */
function handleNewAlert(alert: Alert) {
  console.log('收到新预警:', alert)

  // 更新状态
  newAlert.value = alert
  newAlertIds.value.add(alert.id)

  // 添加到列表顶部
  recentAlerts.value.unshift(alert)

  // 更新统计
  stats.value.pending_alerts++
  if (alert.level === 'RED' || alert.level === 'ORANGE') {
    stats.value.high_risk_count++
  }

  // 显示通知
  ElNotification({
    title: '新预警通知',
    message: `${alert.patient_name}: ${alert.message}`,
    type: getAlertType(alert.level),
    duration: 5000,
  })
}

/**
 * 初始化 WebSocket
 */
function initWebSocket() {
  const doctorId = appStore.currentUserId || 'doctor' // 从登录状态获取医生ID
  wsClient.value = getWebSocketClient(doctorId)

  // 注册预警回调
  wsClient.value.onAlert(handleNewAlert)

  // 注册连接状态回调
  wsClient.value.onStateChange(handleStateChange)

  // 连接 WebSocket
  wsClient.value.connect()
}

/**
 * 判断是否是新预警
 */
function isNewAlert(alertId: string): boolean {
  return newAlertIds.value.has(alertId)
}

/**
 * 获取预警类型
 */
function getAlertType(level: string): 'success' | 'warning' | 'info' | 'error' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'error'> = {
    RED: 'error',
    ORANGE: 'warning',
    YELLOW: 'info',
  }
  return map[level] || 'info'
}

/**
 * 跳转到审核页面
 */
function goToReview(alert: Alert) {
  router.push(`/doctor/review/${alert.id}`)
}

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

onMounted(() => {
  loadAllData()
  initWebSocket()
})

onUnmounted(() => {
  // 清理 WebSocket 连接和回调
  if (wsClient.value) {
    wsClient.value.offAlert(handleNewAlert)
    wsClient.value.offStateChange(handleStateChange)
    wsClient.value.disconnect()
  }
})
</script>

<style scoped>
/* 新预警高亮样式 */
.new-alert-highlight {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-grid-row {
  margin-bottom: 28px;
}

.stat-card-wrapper {
  cursor: pointer;
}

/* 医嘱列表项 */
.order-item {
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  transition: background var(--transition-fast);
}

.order-item:last-child {
  border-bottom: none;
}

.order-item:hover {
  background: rgba(232, 245, 233, 0.2);
  border-radius: var(--radius-sm);
  margin: 0 -8px;
  padding-left: 8px;
  padding-right: 8px;
}

.order-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.order-item__patient {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-primary);
}

.order-item__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}

.order-item__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
</style>
