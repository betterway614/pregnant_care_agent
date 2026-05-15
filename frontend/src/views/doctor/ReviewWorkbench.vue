<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">异常审核工作台</h1>
      <div class="page-header__actions">
        <!-- WebSocket 连接状态 -->
        <el-tag
          :type="wsConnected ? 'success' : 'danger'"
          size="small"
          effect="plain"
        >
          {{ wsConnected ? '实时连接' : '连接断开' }}
        </el-tag>

        <el-tag v-if="selectedAlert" type="danger" effect="plain" size="default">
          审核中: {{ selectedAlert.patient_name }}
        </el-tag>
        <el-button text type="primary" :icon="Refresh" @click="loadAlerts" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 新预警通知 -->
    <el-alert
      v-if="pendingNewAlerts.length > 0"
      :title="`收到 ${pendingNewAlerts.length} 条新预警`"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>有新的预警需要处理</span>
          <el-button type="primary" size="small" @click="handleNewAlerts">
            查看新预警
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 三栏布局 -->
    <el-row :gutter="16" style="height: calc(100vh - 180px)">
      <!-- 左侧：高危预警列表 -->
      <el-col :span="7" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">高危预警列表</span>
            <el-tag size="small">{{ alertList.length }}条</el-tag>
          </div>
          <div class="content-card__body" style="flex: 1; overflow-y: auto; padding: 0" v-loading="loading">
            <div
              v-for="alert in alertList"
              :key="alert.id"
              class="alert-list-item"
              :class="{
                'alert-list-item--active': selectedAlert?.id === alert.id,
                'alert-list-item--new': isNewAlert(alert.id)
              }"
              @click="selectAlert(alert)"
            >
              <div class="alert-list-item__header">
                <span class="alert-list-item__name">{{ alert.patient_name }}</span>
                <RiskBadge :level="mapRiskLevel(alert.level)" />
              </div>
              <p class="alert-list-item__msg">{{ alert.message }}</p>
              <div class="alert-list-item__meta">
                <span class="text-light">
                  {{ calcGestationalWeek(alert.gestational_age_days) }}周
                </span>
                <span class="text-light">{{ formatTime(alert.created_at) }}</span>
              </div>
              <!-- 新预警标记 -->
              <div v-if="isNewAlert(alert.id)" class="new-alert-badge">新</div>
            </div>
            <div v-if="!alertList.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><CircleCheck /></el-icon>
              <p>暂无待审核预警</p>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 中间：预警详情 -->
      <el-col :span="10" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">预警详情</span>
            <el-tag v-if="selectedAlert" :type="getAlertStatusTag(selectedAlert.status)" size="small">
              {{ getAlertStatusText(selectedAlert.status) }}
            </el-tag>
          </div>
          <div
            class="content-card__body"
            style="flex: 1; overflow-y: auto"
            v-loading="detailLoading"
          >
            <template v-if="selectedAlert">
              <!-- 风险详情 -->
              <section class="detail-section">
                <h4 class="detail-section__title">风险详情</h4>
                <div class="detail-grid">
                  <div class="detail-item">
                    <span class="detail-item__label">孕妇</span>
                    <span class="detail-item__value">{{ selectedAlert.patient_name }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">风险级别</span>
                    <RiskBadge :level="mapRiskLevel(selectedAlert.level)" />
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">预警来源</span>
                    <span class="detail-item__value">{{ getTriggerSourceText(selectedAlert.trigger_source) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">预警时间</span>
                    <span class="detail-item__value">{{ formatTime(selectedAlert.created_at) }}</span>
                  </div>
                  <div class="detail-item" v-if="selectedAlert.gestational_age_days">
                    <span class="detail-item__label">当前孕周</span>
                    <span class="detail-item__value">{{ calcGestationalWeek(selectedAlert.gestational_age_days) }}周</span>
                  </div>
                </div>
              </section>

              <!-- 触发规则 -->
              <section class="detail-section">
                <h4 class="detail-section__title">触发规则</h4>
                <div class="rule-card">
                  <div class="rule-card__header">
                    <el-icon color="var(--danger)"><WarningFilled /></el-icon>
                    <span>规则 ID: {{ selectedAlert.rule_id || 'N/A' }}</span>
                  </div>
                  <p class="rule-card__desc">{{ selectedAlert.message }}</p>
                </div>
              </section>

              <!-- 相关数据 -->
              <section class="detail-section">
                <h4 class="detail-section__title">相关数据</h4>
                <div class="data-table" v-if="hasDetails">
                  <div
                    v-for="(value, key) in selectedAlert.details"
                    :key="key"
                    class="data-row"
                  >
                    <span class="data-row__key">{{ formatDetailKey(key) }}</span>
                    <span class="data-row__value">{{ formatDetailValue(value) }}</span>
                  </div>
                </div>
                <p v-else class="text-light">暂无详细数据</p>
              </section>
            </template>

            <!-- 未选中提示 -->
            <div v-if="!selectedAlert" class="empty-state">
              <el-icon :size="48" color="var(--text-light)"><Select /></el-icon>
              <p style="margin-top: 12px">请从左侧列表选择一条预警进行审核</p>
            </div>
          </div>

          <!-- 底部审核操作 -->
          <div v-if="selectedAlert" class="review-actions">
            <el-button
              type="danger"
              :icon="WarningFilled"
              :loading="submitting"
              @click="confirmHighRisk"
              :disabled="selectedAlert.status !== 'pending'"
            >
              确认高危
            </el-button>
            <el-button
              type="warning"
              :icon="Edit"
              :loading="submitting"
              @click="showDowngradeDialog"
              :disabled="selectedAlert.status !== 'pending'"
            >
              降级
            </el-button>
            <el-button
              plain
              :icon="FolderAdd"
              @click="handleSupplement"
              :disabled="selectedAlert.status !== 'pending'"
            >
              补充资料
            </el-button>
          </div>
        </div>
      </el-col>

      <!-- 右侧：孕妇辅助信息 -->
      <el-col :span="7" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">孕妇辅助信息</span>
          </div>
          <div
            class="content-card__body"
            style="flex: 1; overflow-y: auto"
            v-loading="pregnantInfoLoading"
          >
            <template v-if="selectedAlert && pregnantFollowUps.length">
              <!-- 最近主诉 -->
              <section class="detail-section">
                <h4 class="detail-section__title">最近主诉</h4>
                <div class="chief-complaint">
                  <p>{{ latestChiefComplaint }}</p>
                  <span class="text-light">{{ latestChiefComplaintDate }}</span>
                </div>
              </section>

              <!-- 随访摘要 -->
              <section class="detail-section">
                <h4 class="detail-section__title">随访摘要</h4>
                <div
                  v-for="record in pregnantFollowUps.slice(0, 5)"
                  :key="record.id"
                  class="followup-item"
                >
                  <div class="followup-item__header">
                    <span class="followup-item__date">{{ formatTime(record.follow_up_date) }}</span>
                    <el-tag
                      :type="record.status === 'confirmed' ? 'success' : 'info'"
                      size="small"
                    >
                      {{ record.status === 'confirmed' ? '已确认' : '待确认' }}
                    </el-tag>
                  </div>
                  <p class="followup-item__summary" v-if="record.summary">
                    {{ record.summary }}
                  </p>
                  <div v-if="record.chief_complaint" class="followup-item__complaint">
                    <el-icon color="var(--text-light)"><ChatDotSquare /></el-icon>
                    {{ record.chief_complaint }}
                  </div>
                </div>
              </section>
            </template>

            <div v-if="!selectedAlert" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><User /></el-icon>
              <p>选择孕妇后查看</p>
            </div>

            <div v-if="selectedAlert && !pregnantFollowUps.length && !pregnantInfoLoading && !aiAnalysisResult" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><ChatDotSquare /></el-icon>
              <p>暂无随访记录</p>
            </div>

            <!-- AI分析按钮 -->
            <div v-if="selectedAlert" style="margin-bottom: 16px">
              <el-button
                type="primary"
                :icon="MagicStick"
                :loading="aiAnalyzing"
                @click="runDoctorAiAnalysis"
                style="width: 100%"
              >
                Dr.智 AI 分析
              </el-button>
            </div>

            <!-- AI分析结果 -->
            <template v-if="aiAnalysisResult">
              <!-- 推理链 -->
              <section v-if="aiAnalysisResult.reasoning_chain?.length" class="detail-section">
                <h4 class="detail-section__title">
                  <el-icon><Guide /></el-icon> 推理链
                </h4>
                <div class="chain-steps">
                  <div
                    v-for="(step, idx) in aiAnalysisResult.reasoning_chain"
                    :key="idx"
                    class="chain-step"
                  >
                    <span class="chain-step__num">{{ idx + 1 }}</span>
                    <span class="chain-step__text">{{ step }}</span>
                  </div>
                </div>
              </section>

              <!-- 鉴别诊断 -->
              <section v-if="aiAnalysisResult.differential_diagnosis?.length" class="detail-section">
                <h4 class="detail-section__title">
                  <el-icon><FirstAidKit /></el-icon> 鉴别诊断
                </h4>
                <div class="diagnosis-list">
                  <div
                    v-for="(dx, idx) in aiAnalysisResult.differential_diagnosis"
                    :key="idx"
                    class="diagnosis-item"
                  >
                    <div class="diagnosis-item__header">
                      <span class="diagnosis-item__condition">{{ dx.condition }}</span>
                      <el-tag
                        :type="confidenceType(dx.confidence)"
                        size="small"
                        effect="plain"
                      >
                        {{ (dx.confidence * 100).toFixed(0) }}%
                      </el-tag>
                    </div>
                    <p v-if="dx.reasoning" class="diagnosis-item__reasoning">{{ dx.reasoning }}</p>
                  </div>
                </div>
              </section>

              <!-- 建议医嘱 -->
              <section v-if="aiAnalysisResult.suggested_orders" class="detail-section">
                <h4 class="detail-section__title">建议医嘱</h4>
                <div class="suggested-orders">
                  {{ aiAnalysisResult.suggested_orders }}
                </div>
              </section>

              <!-- 循证参考 -->
              <section v-if="aiAnalysisResult.evidence_references?.length" class="detail-section">
                <h4 class="detail-section__title">循证参考</h4>
                <ul class="evidence-list">
                  <li v-for="(ref, idx) in aiAnalysisResult.evidence_references" :key="idx">
                    {{ ref }}
                  </li>
                </ul>
              </section>
            </template>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 降级弹窗 -->
    <el-dialog
      v-model="downgradeDialogVisible"
      title="降级确认"
      width="420px"
      destroy-on-close
    >
      <div class="dialog-body">
        <p style="margin-bottom: 12px">请选择降级目标等级并填写理由：</p>
        <el-radio-group v-model="downgradeTarget" style="margin-bottom: 16px">
          <el-radio value="ORANGE">橙色预警</el-radio>
          <el-radio value="YELLOW">黄色关注</el-radio>
          <el-radio value="GREEN">正常</el-radio>
        </el-radio-group>
        <el-input
          v-model="downgradeReason"
          type="textarea"
          :rows="3"
          placeholder="请填写降级理由（必填）"
        />
      </div>
      <template #footer>
        <el-button @click="downgradeDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!downgradeReason.trim()"
          @click="confirmDowngrade"
        >
          确认降级
        </el-button>
      </template>
    </el-dialog>

    <!-- 医嘱建议对话框 -->
    <el-dialog
      v-model="orderDialogVisible"
      title="医嘱建议"
      width="560px"
      destroy-on-close
    >
      <div v-loading="orderGenerating" class="dialog-body">
        <template v-if="generatedOrder">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
          >
            <p>以下是根据当前风险评估结果生成的医嘱建议，请审核后确认或手写修改。</p>
          </el-alert>

          <div class="order-preview">
            <div class="order-preview__header">
              <span class="order-preview__label">建议医嘱内容</span>
              <el-tag size="small">{{ generatedOrder.order_type }}</el-tag>
            </div>
            <div class="order-preview__content">
              {{ generatedOrder.content }}
            </div>
            <div class="order-preview__meta">
              <span class="text-light">来源: {{ generatedOrder.source }}</span>
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="orderDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="acceptOrder">
          采纳
        </el-button>
        <el-button plain :loading="submitting" @click="writeManually">
          手写医嘱
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Refresh, WarningFilled, Edit, FolderAdd,
  Select, ChatDotSquare, User, CircleCheck,
  MagicStick, Guide, FirstAidKit,
} from '@element-plus/icons-vue'
import { alertApi, orderApi, followUpApi, doctorAiApi } from '@/api/endpoints'
import { getWebSocketClient } from '@/utils/websocket'
import type { Alert, MedicalOrder, FollowUpRecord } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { ElNotification } from 'element-plus'

const route = useRoute()
const router = useRouter()

// 数据状态
const loading = ref(false)
const detailLoading = ref(false)
const pregnantInfoLoading = ref(false)
const submitting = ref(false)
const alertList = ref<Alert[]>([])
const selectedAlert = ref<Alert | null>(null)
const pregnantFollowUps = ref<FollowUpRecord[]>([])

// WebSocket 相关状态
const wsConnected = ref(false)
const pendingNewAlerts = ref<Alert[]>([])
const newAlertIds = ref<Set<string>>(new Set())
const wsClient = ref<ReturnType<typeof getWebSocketClient> | null>(null)

// 降级状态
const downgradeDialogVisible = ref(false)
const downgradeTarget = ref('ORANGE')
const downgradeReason = ref('')

// 医嘱状态
const orderDialogVisible = ref(false)
const orderGenerating = ref(false)
const generatedOrder = ref<MedicalOrder | null>(null)

// AI分析状态
const aiAnalyzing = ref(false)
const aiAnalysisResult = ref<any>(null)

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
    critical: 'RED',
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

/** 预警来源文本 */
function getTriggerSourceText(source: string): string {
  const map: Record<string, string> = {
    fgr_assessment: 'FGR评估',
    vital_signs: '生命体征',
    lab_result: '检验结果',
    symptom_check: '症状筛查',
    followup: '随访',
  }
  return map[source] || source
}

/** 预警状态标签 */
function getAlertStatusTag(status: string): 'danger' | 'warning' | 'success' | 'info' {
  const map: Record<string, 'danger' | 'warning' | 'success' | 'info'> = {
    pending: 'danger',
    confirmed: 'warning',
    downgraded: 'warning',
    resolved: 'success',
    dismissed: 'info',
  }
  return map[status] || 'info'
}

/** 预警状态文本 */
function getAlertStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '待审核',
    confirmed: '已确认',
    downgraded: '已降级',
    resolved: '已解决',
    dismissed: '已忽略',
  }
  return map[status] || status
}

/** 是否有详情数据 */
const hasDetails = computed(() => {
  return selectedAlert.value?.details && Object.keys(selectedAlert.value.details).length > 0
})

/** 格式化详情键 */
function formatDetailKey(key: string): string {
  const map: Record<string, string> = {
    value: '测量值',
    threshold: '阈值',
    metric_code: '指标代码',
    unit: '单位',
    trend: '趋势',
    deviation: '偏差',
    confidence_interval: '置信区间',
    gestational_weeks: '孕周',
    risk_score: '风险评分',
  }
  return map[key] || key
}

/** 格式化详情值 */
function formatDetailValue(value: any): string {
  if (typeof value === 'object') {
    if (value.lowerBound !== undefined && value.upperBound !== undefined) {
      return `${(value.lowerBound * 100).toFixed(1)}% ~ ${(value.upperBound * 100).toFixed(1)}%`
    }
    return JSON.stringify(value)
  }
  return String(value)
}

/** 最近主诉 */
const latestChiefComplaint = computed(() => {
  const records = pregnantFollowUps.value
  if (!records.length) return '暂无'
  return records[0].chief_complaint || '无主诉'
})

const latestChiefComplaintDate = computed(() => {
  const records = pregnantFollowUps.value
  if (!records.length) return ''
  return formatTime(records[0].follow_up_date)
})

/** 选择预警 */
async function selectAlert(alert: Alert) {
  selectedAlert.value = alert
  detailLoading.value = false
  pregnantInfoLoading.value = true
  pregnantFollowUps.value = []
  aiAnalysisResult.value = null

  // 更新URL
  router.replace(`/doctor/review/${alert.id}`)

  // 加载孕妇随访信息
  try {
    const res = await followUpApi.list({ pregnant_id: alert.pregnant_id })
    pregnantFollowUps.value = (res.data || []).sort(
      (a, b) => new Date(b.follow_up_date || 0).getTime() - new Date(a.follow_up_date || 0).getTime()
    )
  } catch (err) {
    console.error('加载孕妇随访信息失败:', err)
  } finally {
    pregnantInfoLoading.value = false
  }
}

/** 加载预警列表 */
async function loadAlerts() {
  loading.value = true
  try {
    const res = await alertApi.list({ status: 'pending' })
    alertList.value = res.data || []
  } catch (err) {
    console.error('加载预警列表失败:', err)
  } finally {
    loading.value = false
  }
}

/** 确认高危 */
async function confirmHighRisk() {
  if (!selectedAlert.value) return
  submitting.value = true
  try {
    await alertApi.review(selectedAlert.value.id, 'confirm')
    // 触发医嘱建议对话框
    await generateOrderSuggestion()
    // 从列表中移除
    alertList.value = alertList.value.filter((a) => a.id !== selectedAlert.value!.id)
  } catch (err) {
    console.error('确认高危失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 显示降级弹窗 */
function showDowngradeDialog() {
  downgradeTarget.value = 'ORANGE'
  downgradeReason.value = ''
  downgradeDialogVisible.value = true
}

/** 确认降级 */
async function confirmDowngrade() {
  if (!selectedAlert.value || !downgradeReason.value.trim()) return
  submitting.value = true
  try {
    await alertApi.review(selectedAlert.value.id, 'downgrade', downgradeReason.value)
    selectedAlert.value.status = 'downgraded'
    alertList.value = alertList.value.filter((a) => a.id !== selectedAlert.value!.id)
    downgradeDialogVisible.value = false
  } catch (err) {
    console.error('降级失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 补充资料 */
function handleSupplement() {
  // 预留补充资料功能
}

/** 生成医嘱建议 */
async function generateOrderSuggestion() {
  if (!selectedAlert.value) return
  orderGenerating.value = true
  orderDialogVisible.value = true
  generatedOrder.value = null
  try {
    const res = await orderApi.generate({
      pregnant_id: selectedAlert.value.pregnant_id,
      alert_id: selectedAlert.value.id,
      risk_level: selectedAlert.value.level,
      gestational_weeks: calcGestationalWeek(selectedAlert.value.gestational_age_days),
    })
    generatedOrder.value = res.data
  } catch (err) {
    console.error('生成医嘱建议失败:', err)
  } finally {
    orderGenerating.value = false
  }
}

/** 采纳医嘱 */
async function acceptOrder() {
  if (!generatedOrder.value) return
  submitting.value = true
  try {
    await orderApi.update(generatedOrder.value.id, { status: 'draft' })
    orderDialogVisible.value = false
    selectedAlert.value = null
  } catch (err) {
    console.error('采纳医嘱失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 手写医嘱 */
function writeManually() {
  orderDialogVisible.value = false
  // 跳转到医嘱管理页面
  router.push('/doctor/orders')
}

/** 触发AI分析 */
async function runDoctorAiAnalysis() {
  if (!selectedAlert.value) return
  aiAnalyzing.value = true
  aiAnalysisResult.value = null
  try {
    const res = await doctorAiApi.analyze(selectedAlert.value.pregnant_id)
    aiAnalysisResult.value = res.data
  } catch (err) {
    console.error('AI分析失败:', err)
  } finally {
    aiAnalyzing.value = false
  }
}

/** 鉴别诊断置信度颜色 */
function confidenceType(confidence: number): 'danger' | 'warning' | 'info' {
  if (confidence >= 0.7) return 'danger'
  if (confidence >= 0.4) return 'warning'
  return 'info'
}

/**
 * 初始化 WebSocket
 */
function initWebSocket() {
  const doctorId = 'current-doctor'
  wsClient.value = getWebSocketClient(doctorId)

  // 注册预警回调
  wsClient.value.onAlert((alert: Alert) => {
    console.log('审核工作台收到新预警:', alert)

    // 添加到待处理列表
    pendingNewAlerts.value.push(alert)
    newAlertIds.value.add(alert.id)

    // 添加到预警列表顶部
    alertList.value.unshift(alert)

    // 显示通知
    ElNotification({
      title: '新预警通知',
      message: `${alert.patient_name}: ${alert.message}`,
      type: getAlertType(alert.level),
      duration: 5000,
    })
  })

  // 注册连接状态回调
  wsClient.value.onStateChange((state: string) => {
    wsConnected.value = state === 'OPEN'
  })

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
 * 处理新预警
 */
function handleNewAlerts() {
  // 选中第一个新预警
  if (pendingNewAlerts.value.length > 0) {
    const firstNewAlert = pendingNewAlerts.value[0]
    selectAlert(firstNewAlert)

    // 清空待处理列表
    pendingNewAlerts.value = []
  }
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

// 根据路由参数选中预警
onMounted(async () => {
  await loadAlerts()
  initWebSocket()

  // 根据路由参数选中预警
  const alertId = route.params.alertId as string
  if (alertId) {
    const found = alertList.value.find((a) => a.id === alertId)
    if (found) {
      await selectAlert(found)
    }
  }
})

onUnmounted(() => {
  // 清理 WebSocket 连接
  if (wsClient.value) {
    wsClient.value.disconnect()
  }
})
</script>

<style scoped>
.page-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 预警列表项 */
.alert-list-item {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
  position: relative;
}

.alert-list-item:hover {
  background: var(--primary-bg);
}

.alert-list-item--active {
  background: var(--primary-bg);
  border-left: 3px solid var(--primary);
}

/* 新预警样式 */
.alert-list-item--new {
  border-left: 3px solid var(--warning);
  background: var(--warning-light);
}

.new-alert-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--warning);
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
}

.alert-list-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.alert-list-item__name {
  font-weight: 600;
  font-size: 14px;
}

.alert-list-item__msg {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 6px;
}

.alert-list-item__meta {
  display: flex;
  justify-content: space-between;
}

/* 详情区块 */
.detail-section {
  margin-bottom: 24px;
}

.detail-section__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item__label {
  font-size: 12px;
  color: var(--text-light);
}

.detail-item__value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 规则卡片 */
.rule-card {
  background: var(--danger-light);
  border-radius: var(--radius-sm);
  padding: 14px;
}

.rule-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.rule-card__desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

/* 数据表格 */
.data-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.data-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  background: var(--bg-page);
  border-radius: 6px;
}

.data-row__key {
  font-size: 13px;
  color: var(--text-light);
}

.data-row__value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 底部审核操作栏 */
.review-actions {
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
  background: var(--bg-card);
}

/* 主诉 */
.chief-complaint {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 14px;
}

.chief-complaint p {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  margin-bottom: 8px;
}

/* 随访项 */
.followup-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.followup-item:last-child {
  border-bottom: none;
}

.followup-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.followup-item__date {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.followup-item__summary {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 6px;
}

.followup-item__complaint {
  font-size: 12px;
  color: var(--text-light);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 医嘱预览 */
.order-preview {
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 16px;
}

.order-preview__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.order-preview__label {
  font-weight: 600;
  font-size: 14px;
}

.order-preview__content {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  padding: 12px;
  background: var(--bg-card);
  border-radius: 6px;
  margin-bottom: 10px;
  border: 1px solid var(--border);
}

.order-preview__meta {
  font-size: 12px;
}

.text-light {
  font-size: 12px;
  color: var(--text-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  gap: 8px;
}

.empty-state p {
  color: var(--text-light);
  font-size: 14px;
}

.dialog-body {
  padding: 8px 0;
}

/* 推理链 */
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
.diagnosis-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.diagnosis-item {
  background: var(--bg-page);
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

/* 建议医嘱 */
.suggested-orders {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  background: var(--bg-page);
  border-radius: 6px;
  padding: 12px;
  white-space: pre-wrap;
}

/* 循证参考 */
.evidence-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-light);
  line-height: 1.8;
}
</style>
