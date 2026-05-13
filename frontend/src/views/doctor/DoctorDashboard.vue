<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">医生工作台</h1>
      <el-button type="primary" :icon="Refresh" @click="loadAllData" :loading="loading">
        刷新数据
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-grid-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in statCards" :key="card.label">
        <StatCard
          :icon="card.icon"
          :value="card.value"
          :label="card.label"
          :color="card.color"
          :bg-color="card.bgColor"
          :sub-label="card.subLabel"
        />
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
                  <RiskBadge :level="mapRiskLevel(row.level)" />
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

    <!-- Dr.智 AI 会诊面板 -->
    <div class="content-card" style="margin-top: 16px">
      <div class="content-card__header">
        <span class="content-card__title" style="display: flex; align-items: center; gap: 8px">
          <AgentAvatar agent="zhiyi" :size="24" />
          Dr.智 AI 智能会诊
        </span>
        <el-button text type="primary" size="small" @click="showAiPanel = !showAiPanel">
          {{ showAiPanel ? '收起' : '展开' }}
        </el-button>
      </div>
      <div class="content-card__body" v-if="showAiPanel">
        <div class="ai-panel">
          <div class="ai-panel__input">
            <el-select
              v-model="aiPatientId"
              filterable
              placeholder="选择孕妇进行AI分析"
              style="flex: 1"
              clearable
            >
              <el-option
                v-for="p in pregnantList"
                :key="p.pregnant_id"
                :label="`${p.display_name} (孕${(p.gestational_age_days||0)/7|0}周)${p.risk_tags?.length ? ' ['+p.risk_tags.join(',')+']' : ''}`"
                :value="p.pregnant_id"
              />
            </el-select>
            <el-input
              v-model="aiQuery"
              placeholder="补充查询内容（可选）"
              style="width: 200px"
              clearable
            />
            <el-button
              type="primary"
              :loading="aiLoading"
              :disabled="!aiPatientId"
              @click="runAiAnalysis"
            >
              <el-icon><MagicStick /></el-icon> AI 分析
            </el-button>
          </div>

          <div v-if="aiResult" class="ai-result" v-loading="aiLoading">
            <el-alert
              v-if="aiResult.risk_summary"
              title="风险总结"
              :description="aiResult.risk_summary"
              type="error"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-alert
              v-if="aiResult.analysis"
              title="综合分析"
              :description="aiResult.analysis"
              type="info"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />

            <!-- 鉴别诊断推理链 -->
            <div v-if="aiResult.reasoning_chain?.length" class="reasoning-chain">
              <h4 class="section-title">
                <el-icon><Guide /></el-icon> 推理链
              </h4>
              <div class="chain-steps">
                <div
                  v-for="(step, idx) in aiResult.reasoning_chain"
                  :key="idx"
                  class="chain-step"
                >
                  <span class="chain-step__num">{{ idx + 1 }}</span>
                  <span class="chain-step__text">{{ step }}</span>
                </div>
              </div>
            </div>

            <!-- 鉴别诊断 -->
            <div v-if="aiResult.differential_diagnosis?.length" class="differential-diagnosis">
              <h4 class="section-title">
                <el-icon><FirstAidKit /></el-icon> 鉴别诊断
              </h4>
              <div class="diagnosis-list">
                <div
                  v-for="(dx, idx) in aiResult.differential_diagnosis"
                  :key="idx"
                  class="diagnosis-item"
                >
                  <div class="diagnosis-item__header">
                    <span class="diagnosis-item__condition">{{ dx.condition }}</span>
                    <el-tag
                      :type="dx.confidence >= 0.7 ? 'danger' : dx.confidence >= 0.4 ? 'warning' : 'info'"
                      size="small"
                      effect="plain"
                    >
                      {{ (dx.confidence * 100).toFixed(0) }}%
                    </el-tag>
                  </div>
                  <p v-if="dx.reasoning" class="diagnosis-item__reasoning">{{ dx.reasoning }}</p>
                </div>
              </div>
            </div>

            <el-alert
              v-if="aiResult.suggested_orders"
              title="建议医嘱"
              :description="aiResult.suggested_orders"
              type="warning"
              show-icon
              :closable="false"
              style="margin-bottom: 12px; margin-top: 12px"
            />
            <div v-if="aiResult.evidence_references?.length" class="evidence-refs">
              <p class="refs-title">循证参考：</p>
              <ul>
                <li v-for="(ref, idx) in aiResult.evidence_references" :key="idx">{{ ref }}</li>
              </ul>
            </div>
          </div>

          <div v-if="!aiResult && !aiLoading" class="ai-empty">
            <el-icon :size="40" color="var(--text-muted)"><MagicStick /></el-icon>
            <p>选择孕妇后点击"AI分析"，Dr.智将提供智能综合分析建议</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Bell, Document, MagicStick, Guide, FirstAidKit } from '@element-plus/icons-vue'
import { dashboardApi, alertApi, orderApi, doctorAiApi } from '@/api/endpoints'
import type { Pregnant } from '@/types'
import type { Alert, MedicalOrder, DashboardStats } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import AgentAvatar from '@/components/common/AgentAvatar.vue'

const router = useRouter()
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

/** 统计卡片配置 */
const statCards = computed(() => [
  {
    icon: 'WarningFilled',
    value: stats.value.high_risk_count,
    label: '高危孕妇数',
    color: '#D32F2F',
    bgColor: '#FFEBEE',
    subLabel: '红色高危',
  },
  {
    icon: 'Bell',
    value: stats.value.pending_alerts,
    label: '待审核预警',
    color: '#E65100',
    bgColor: '#FFF3E0',
    subLabel: '待处理',
  },
  {
    icon: 'Edit',
    value: stats.value.pending_reviews,
    label: '待签署医嘱',
    color: '#1976D2',
    bgColor: '#E3F2FD',
    subLabel: '等待签署',
  },
  {
    icon: 'DataAnalysis',
    value: fgrHighRiskCount.value,
    label: 'FGR高风险数',
    color: '#7B1FA2',
    bgColor: '#F3E5F5',
    subLabel: '胎儿生长受限',
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
      alertApi.list({ status: 'pending' }),
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

/** 签署医嘱 */
async function handleSignOrder(order: MedicalOrder) {
  try {
    await orderApi.sign(order.id, 'current-doctor')
    await loadAllData()
  } catch (err) {
    console.error('签署失败:', err)
  }
}

// ==================== AI 智能会诊 ====================
const showAiPanel = ref(false)
const aiPatientId = ref('')
const aiQuery = ref('')
const aiLoading = ref(false)
const aiResult = ref<any>(null)
const pregnantList = ref<Pregnant[]>([])

async function loadPatientList() {
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data || []
  } catch { /* ignore */ }
}

async function runAiAnalysis() {
  if (!aiPatientId.value) return
  aiLoading.value = true
  aiResult.value = null
  try {
    const res = await doctorAiApi.analyze(aiPatientId.value, aiQuery.value)
    aiResult.value = res.data
  } catch (err: any) {
    aiResult.value = {
      risk_summary: '',
      analysis: 'AI会诊暂时不可用，请查看孕妇详情进行手动评估',
      suggested_orders: '',
      evidence_references: [],
    }
  } finally {
    aiLoading.value = false
  }
}

onMounted(() => {
  loadAllData()
  loadPatientList()
})
</script>

<style scoped>
.stat-grid-row {
  margin-bottom: 24px;
}

/* 医嘱列表项 */
.order-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}

.order-item:last-child {
  border-bottom: none;
}

.order-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.order-item__patient {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.order-item__content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 6px;
}

.order-item__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.text-light {
  font-size: 12px;
  color: var(--text-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  gap: 12px;
}

.empty-state p {
  color: var(--text-light);
  font-size: 14px;
}

/* AI 面板 */
.ai-panel__input {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.ai-result {
  min-height: 100px;
}

.ai-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-muted);
  font-size: 13px;
}

.evidence-refs {
  background: var(--info-light);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
}

.refs-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.evidence-refs ul {
  margin-left: 16px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.8;
}

/* 推理链 */
.reasoning-chain {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-bottom: 12px;
  border-left: 3px solid var(--primary);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.chain-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chain-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.chain-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  min-width: 22px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

/* 鉴别诊断 */
.differential-diagnosis {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-bottom: 12px;
}

.diagnosis-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.diagnosis-item {
  background: var(--bg-card);
  border-radius: 6px;
  padding: 12px;
  border: 1px solid var(--border);
}

.diagnosis-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.diagnosis-item__condition {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.diagnosis-item__reasoning {
  font-size: 12px;
  color: var(--text-light);
  line-height: 1.6;
  margin: 0;
}
</style>
