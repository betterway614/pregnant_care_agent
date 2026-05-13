<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">护士工作台</h1>
      <el-button type="primary" :icon="Refresh" @click="fetchData" :loading="loading">
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

    <!-- 主要内容 -->
    <el-row :gutter="16">
      <!-- 最近预警 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">最近预警</span>
            <el-button text type="primary" size="small" @click="$router.push('/nurse/alerts')">
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
            <el-button text type="primary" size="small" @click="$router.push('/nurse/followups')">
              查看全部
            </el-button>
          </div>
          <div class="content-card__body" v-loading="loading">
            <div v-for="fu in recentFollowUps" :key="fu.id" class="followup-item">
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

    <!-- AI 智能助手面板 -->
    <div class="content-card" style="margin-top: 16px">
      <div class="content-card__header">
        <span class="content-card__title" style="display: flex; align-items: center; gap: 8px">
          <AgentAvatar agent="xiaohu" :size="24" />
          小护 AI 智能助手
        </span>
        <div style="display: flex; gap: 8px">
          <el-button text type="primary" size="small" @click="showAiChat = !showAiChat">
            {{ showAiChat ? '分析' : '对话' }}
          </el-button>
          <el-button text type="primary" size="small" @click="showAiPanel = !showAiPanel">
            {{ showAiPanel ? '收起' : '展开' }}
          </el-button>
        </div>
      </div>
      <div class="content-card__body" v-if="showAiPanel">
        <!-- 对话模式 -->
        <NurseAIChat v-if="showAiChat" />
        <!-- 分析模式 -->
        <div v-else class="ai-panel">
          <div class="ai-panel__input">
            <el-select
              v-model="aiPatientId"
              filterable
              placeholder="选择孕妇进行分析"
              style="flex: 1"
              clearable
            >
              <el-option
                v-for="p in pregnantList"
                :key="p.pregnant_id"
                :label="`${p.display_name} (孕${(p.gestational_age_days||0)/7|0}周)`"
                :value="p.pregnant_id"
              />
            </el-select>
            <el-button
              type="primary"
              :loading="aiLoading"
              :disabled="!aiPatientId"
              @click="runAiAnalysis"
            >
              <el-icon><MagicStick /></el-icon> AI 分析
            </el-button>
          </div>

          <!-- AI分析结果 -->
          <div v-if="aiResult" class="ai-result" v-loading="aiLoading">
            <el-alert
              v-if="aiResult.summary"
              title="综合分析"
              :description="aiResult.summary"
              type="info"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-alert
              v-if="aiResult.risk_assessment"
              title="风险评估"
              :description="aiResult.risk_assessment"
              :type="aiResult.risk_assessment.includes('高危') ? 'error' : 'warning'"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-alert
              v-if="aiResult.nursing_suggestions"
              title="护理建议"
              :description="aiResult.nursing_suggestions"
              type="success"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <div v-if="aiResult.followup_focus?.length" class="followup-focus">
              <p class="focus-title">随访重点关注：</p>
              <el-tag
                v-for="(item, idx) in aiResult.followup_focus"
                :key="idx"
                size="large"
                style="margin: 4px"
              >{{ item }}</el-tag>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="!aiResult && !aiLoading" class="ai-empty">
            <el-icon :size="40" color="var(--text-muted)"><MagicStick /></el-icon>
            <p>选择孕妇后点击"AI分析"，小护将为您提供智能护理分析建议</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Bell, Document, MagicStick } from '@element-plus/icons-vue'
import { dashboardApi, alertApi, followUpApi, nurseAiApi } from '@/api/endpoints'
import type { DashboardStats, Alert, FollowUpRecord, Pregnant } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import NurseAIChat from './NurseAIChat.vue'

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

/** 统计卡片配置 */
const statCards = computed(() => [
  {
    icon: 'UserFilled',
    value: stats.value.total_pregnant,
    label: '总孕妇数',
    color: 'var(--primary)',
    bgColor: 'var(--primary-bg)',
    subLabel: '当前管理',
  },
  {
    icon: 'WarningFilled',
    value: stats.value.pending_alerts,
    label: '待处理预警',
    color: 'var(--warning)',
    bgColor: '#FFF3E0',
    subLabel: '需及时处理',
  },
  {
    icon: 'Calendar',
    value: stats.value.today_followups,
    label: '今日随访',
    color: 'var(--info)',
    bgColor: '#E3F2FD',
    subLabel: '计划中',
  },
  {
    icon: 'DocumentChecked',
    value: stats.value.pending_reviews,
    label: '待审核记录',
    color: 'var(--accent)',
    bgColor: '#E0F2F1',
    subLabel: '待确认归档',
  },
])

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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
}

/** 点击预警行跳转 */
function handleAlertClick(alert: Alert) {
  router.push(`/nurse/alerts?highlight=${alert.id}`)
}

// ==================== AI 智能分析 ====================
const showAiPanel = ref(false)
const showAiChat = ref(false)
const aiPatientId = ref('')
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
    const res = await nurseAiApi.analyze(aiPatientId.value)
    aiResult.value = res.data
  } catch (err: any) {
    aiResult.value = {
      summary: 'AI分析暂时不可用，请联系管理员',
      nursing_suggestions: '',
      risk_assessment: '',
      followup_focus: [],
    }
  } finally {
    aiLoading.value = false
  }
}

onMounted(() => {
  fetchData()
  loadPatientList()
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.stat-grid-row {
  margin-bottom: 24px;
}

/* 随访列表项 */
.followup-item {
  padding: 14px 0;
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
  margin-bottom: 6px;
}

.followup-item__footer {
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

.followup-focus {
  background: var(--primary-bg);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
}

.focus-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
</style>
