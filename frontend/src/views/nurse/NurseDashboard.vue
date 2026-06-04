<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">护士工作台</h1>
      <el-button type="primary" class="brand-gradient-btn" :icon="Refresh" @click="fetchData" :loading="loading">
        刷新数据
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

    <!-- 智能晨会简报 -->
    <div class="briefing-section" v-if="briefing">
      <div class="content-card briefing-card">
        <div class="content-card__header" @click="briefingExpanded = !briefingExpanded">
          <div class="briefing-header-left">
            <el-icon class="briefing-icon"><Sunny /></el-icon>
            <span class="content-card__title">今日晨会简报</span>
            <el-tag size="small" type="info">{{ briefing.date }}</el-tag>
          </div>
          <div class="briefing-header-right">
            <el-icon class="expand-icon" :class="{ 'is-rotated': briefingExpanded }"><ArrowDown /></el-icon>
          </div>
        </div>
        <!-- 摘要行（始终显示） -->
        <div class="briefing-summary" v-if="briefing.summary">
          {{ briefing.summary }}
        </div>
        <!-- 展开详情 -->
        <transition name="briefing-slide">
          <div v-show="briefingExpanded" class="briefing-body">
            <!-- 风险分层 -->
            <div class="briefing-risk-row">
              <div class="briefing-risk-chip risk-red" v-if="briefing.red_patients.length">
                <span class="risk-count">{{ briefing.red_patients.length }}</span>
                <span class="risk-label">红色预警</span>
              </div>
              <div class="briefing-risk-chip risk-orange" v-if="briefing.orange_patients.length">
                <span class="risk-count">{{ briefing.orange_patients.length }}</span>
                <span class="risk-label">橙色关注</span>
              </div>
              <div class="briefing-risk-chip risk-yellow" v-if="briefing.yellow_patients.length">
                <span class="risk-count">{{ briefing.yellow_patients.length }}</span>
                <span class="risk-label">黄色提醒</span>
              </div>
              <div class="briefing-risk-chip risk-none" v-if="!briefing.red_patients.length && !briefing.orange_patients.length && !briefing.yellow_patients.length">
                <el-icon><CircleCheck /></el-icon>
                <span class="risk-label">暂无预警</span>
              </div>
            </div>

            <!-- 红色患者列表 -->
            <div v-if="briefing.red_patients.length" class="briefing-patient-list">
              <div class="briefing-patient-title">🔴 红色预警患者</div>
              <div
                v-for="p in briefing.red_patients"
                :key="p.pregnant_id"
                class="briefing-patient-item"
                @click="$router.push(`/nurse/pregnant/${p.pregnant_id}`)"
              >
                <span class="bp-name">{{ p.display_name }}</span>
                <span class="bp-gest">孕{{ p.gest_week }}周</span>
                <span class="bp-alert">{{ p.latest_alert_message }}</span>
                <el-tag size="small" type="danger">{{ p.alert_count }}条预警</el-tag>
              </div>
            </div>

            <!-- AI 建议 -->
            <div v-if="briefing.ai_recommendations.length" class="briefing-recommendations">
              <div class="briefing-patient-title">💡 AI 建议</div>
              <div
                v-for="(rec, idx) in briefing.ai_recommendations"
                :key="idx"
                class="briefing-rec-item"
              >
                {{ rec }}
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <!-- 主要内容 -->
    <el-row :gutter="16">
      <!-- 最近预警 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">最近预警</span>
            <el-button type="primary" class="brand-gradient-btn" size="small" @click="$router.push('/nurse/alerts')">
              查看全部
            </el-button>
          </div>
          <div class="content-card__body" v-loading="loading">
            <el-table :data="recentAlerts" stripe style="width: 100%" size="small" @row-click="handleAlertClick">
              <el-table-column label="孕妇" min-width="80">
                <template #default="{ row }">
                  {{ row.patient_name || row.pregnant_id }}
                </template>
              </el-table-column>
              <el-table-column label="风险级别" width="100">
                <template #default="{ row }">
                  <RiskBadge :level="row.level" />
                </template>
              </el-table-column>
              <el-table-column prop="message" label="预警消息" min-width="180" show-overflow-tooltip />
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

      <!-- 最近随访 -->
      <el-col :span="10">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">最近随访</span>
            <el-button type="primary" class="brand-gradient-btn" size="small" @click="$router.push('/nurse/followup')">
              查看全部
            </el-button>
          </div>
          <div class="content-card__body" v-loading="loading">
            <div v-for="fu in recentFollowUps" :key="fu.id" class="followup-item clickable" @click="$router.push('/nurse/followup')">
              <div class="followup-item__header">
                <span class="followup-item__name">{{ fu.patient_name || fu.pregnant_id }}</span>
                <el-tag
                  :type="fu.status === 'confirmed' ? 'success' : 'info'"
                  size="small"
                >
                  {{ fu.status === 'confirmed' ? '已确认' : '草稿' }}
                </el-tag>
              </div>
              <p class="followup-item__complaint">
                {{ fu.chief_complaint || '无主诉' }}
              </p>
              <div class="followup-item__footer">
                <span class="text-light">{{ formatTime(fu.follow_up_date) }}</span>
                <span class="text-light" v-if="fu.gestational_week">孕{{ fu.gestational_week }}</span>
              </div>
            </div>
            <div v-if="!recentFollowUps.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><Document /></el-icon>
              <p>暂无随访记录</p>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Bell, Document, Sunny, ArrowDown, CircleCheck } from '@element-plus/icons-vue'
import { dashboardApi, alertApi, followUpApi, nurseBriefingApi } from '@/api/endpoints'
import { getNurseWebSocketClient } from '@/utils/websocket'
import { ElNotification } from 'element-plus'
import type { DashboardStats, Alert, FollowUpRecord, Pregnant } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const stats = ref<DashboardStats>({
  total_pregnant: 0,
  pending_alerts: 0,
  today_followups: 0,
  pending_reviews: 0,
  high_risk_count: 0,
  weekly_new_pregnant: 0,
})
const recentAlerts = ref<Alert[]>([])
const recentFollowUps = ref<FollowUpRecord[]>([])

/** 晨会简报 */
interface BriefingPatient {
  pregnant_id: string
  display_name: string
  gest_week: number
  risk_level: string
  alert_count: number
  latest_alert_message?: string
}
interface MorningBriefing {
  date: string
  total_patients: number
  red_patients: BriefingPatient[]
  orange_patients: BriefingPatient[]
  yellow_patients: BriefingPatient[]
  today_followups: number
  pending_reviews: number
  ai_recommendations: string[]
  summary: string
}
const briefing = ref<MorningBriefing | null>(null)
const briefingExpanded = ref(true)

/** 定时刷新间隔（非预警数据） */
const REFRESH_INTERVAL = 120000 // 2分钟
let refreshTimer: ReturnType<typeof setInterval> | null = null

/** WebSocket 客户端 */
const nurseId = localStorage.getItem('nurse_id') || 'default_nurse'
const wsClient = getNurseWebSocketClient(nurseId)

/** 处理实时预警推送 */
function handleNewAlert(alert: Alert) {
  // 更新待处理预警计数
  stats.value = {
    ...stats.value,
    pending_alerts: stats.value.pending_alerts + 1,
  }

  // 将新预警插入列表头部（保持最多5条）
  recentAlerts.value = [alert, ...recentAlerts.value].slice(0, 5)

  // 弹出通知
  const levelText: Record<string, string> = { RED: '高危', ORANGE: '预警', YELLOW: '关注' }
  ElNotification({
    title: `新${levelText[alert.level] || ''}预警`,
    message: `${alert.patient_name}: ${alert.message}`,
    type: alert.level === 'RED' ? 'error' : alert.level === 'ORANGE' ? 'warning' : 'info',
    duration: 8000,
  })
}

/** 统计卡片配置 */
const statCards = computed(() => [
  {
    icon: 'UserFilled',
    value: stats.value.total_pregnant,
    label: '总孕妇数',
    color: 'var(--primary)',
    bgColor: 'var(--primary-bg)',
    subLabel: '当前管理',
    route: null,
  },
  {
    icon: 'WarningFilled',
    value: stats.value.pending_alerts,
    label: '待处理预警',
    color: 'var(--warning)',
    bgColor: '#FFF3E0',
    subLabel: '需及时处理',
    route: '/nurse/alerts',
  },
  {
    icon: 'Calendar',
    value: stats.value.today_followups,
    label: '今日随访',
    color: 'var(--info)',
    bgColor: '#E3F2FD',
    subLabel: '计划中',
    route: '/nurse/followup',
  },
  {
    icon: 'DocumentChecked',
    value: stats.value.pending_reviews,
    label: '待审核记录',
    color: 'var(--accent)',
    bgColor: '#E0F2F1',
    subLabel: '待确认归档',
    route: '/nurse/followup',
  },
])

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 加载晨会简报 */
async function fetchBriefing() {
  try {
    const res = await nurseBriefingApi.getMorningBriefing()
    briefing.value = res.data
  } catch (e) {
    console.warn('[Dashboard] 加载晨会简报失败:', e)
  }
}

/** 加载所有数据 */
async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const [statsRes, alertsRes, followupsRes] = await Promise.all([
      dashboardApi.stats(),
      alertApi.list({ status: 'pending' }),
      followUpApi.list(),
    ])
    stats.value = statsRes.data
    recentAlerts.value = (alertsRes.data || []).slice(0, 5)
    recentFollowUps.value = (followupsRes.data || []).slice(0, 5)
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '加载数据失败'
    error.value = msg
    console.error('加载工作台数据失败:', err)
  } finally {
    loading.value = false
  }
  // 晨会简报独立加载（不影响主数据）
  fetchBriefing()
}

/** 点击预警行跳转 */
function handleAlertClick(alert: Alert) {
  router.push(`/nurse/alerts?highlight=${alert.id}`)
}

onMounted(() => {
  fetchData()
  // WebSocket 实时接收预警
  wsClient.connect()
  wsClient.onAlert(handleNewAlert)
  // 非预警数据定时刷新
  refreshTimer = setInterval(fetchData, REFRESH_INTERVAL)
})

onUnmounted(() => {
  wsClient.offAlert(handleNewAlert)
  wsClient.disconnect()
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.stat-card-wrapper {
  cursor: pointer;
}

.stat-grid-row {
  margin-bottom: 28px;
}

/* 随访列表项 */
.followup-item {
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  transition: background var(--transition-fast);
}

.followup-item:last-child {
  border-bottom: none;
}

.followup-item.clickable {
  cursor: pointer;
}

.followup-item:hover {
  background: rgba(232, 245, 233, 0.2);
  border-radius: var(--radius-sm);
  margin: 0 -8px;
  padding-left: 8px;
  padding-right: 8px;
}

.followup-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.followup-item__name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.followup-item__complaint {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}

.followup-item__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 0;
  gap: 14px;
}

.empty-state p {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}

/* ========== 晨会简报 ========== */
.briefing-section {
  margin-bottom: 20px;
}
.briefing-card {
  border-left: 3px solid var(--primary);
}
.briefing-card .content-card__header {
  cursor: pointer;
  user-select: none;
}
.briefing-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.briefing-icon {
  color: #F59E0B;
  font-size: 20px;
}
.briefing-header-right {
  display: flex;
  align-items: center;
}
.expand-icon {
  transition: transform 0.3s;
  font-size: 16px;
  color: var(--text-muted);
}
.expand-icon.is-rotated {
  transform: rotate(180deg);
}
.briefing-summary {
  padding: 0 20px 12px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.briefing-body {
  padding: 0 20px 16px;
}
.briefing-risk-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.briefing-risk-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}
.risk-red {
  background: #FEE2E2;
  color: #DC2626;
}
.risk-orange {
  background: #FFEDD5;
  color: #EA580C;
}
.risk-yellow {
  background: #FEF9C3;
  color: #CA8A04;
}
.risk-none {
  background: #F0FDF4;
  color: #16A34A;
}
.risk-count {
  font-size: 18px;
  font-weight: 700;
}
.briefing-patient-list {
  margin-bottom: 16px;
}
.briefing-patient-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}
.briefing-patient-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.briefing-patient-item:hover {
  background: var(--primary-bg);
}
.bp-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  min-width: 60px;
}
.bp-gest {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 50px;
}
.bp-alert {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.briefing-recommendations {
  margin-top: 4px;
}
.briefing-rec-item {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border-light);
}
.briefing-rec-item:last-child {
  border-bottom: none;
}
.briefing-slide-enter-active,
.briefing-slide-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}
.briefing-slide-enter-from,
.briefing-slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.briefing-slide-enter-to,
.briefing-slide-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
