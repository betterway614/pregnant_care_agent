<template>
  <div class="doctor-ai-fab-container">
    <!-- 悬浮球 -->
    <el-button
      class="doctor-ai-fab brand-gradient-btn"
      type="primary"
      circle
      size="large"
      @click="togglePanel"
    >
      <AgentAvatar agent="zhiyi" :size="24" />
    </el-button>

    <!-- 展开的面板 -->
    <transition name="el-zoom-in-bottom">
      <div v-if="panelVisible" class="doctor-ai-panel">
        <div class="doctor-ai-panel__header">
          <div class="doctor-ai-panel__title">
            <AgentAvatar agent="zhiyi" :size="20" />
            <span>Dr.智 AI 临床助手</span>
          </div>
          <el-button text circle :icon="Close" @click="panelVisible = false" />
        </div>

        <el-tabs v-model="activeTab" class="doctor-ai-panel__tabs">
          <!-- 对话 Tab -->
          <el-tab-pane label="对话" name="chat">
            <DoctorAIChat />
          </el-tab-pane>

          <!-- 分析 Tab -->
          <el-tab-pane label="分析" name="analysis">
            <div class="analysis-tab">
              <div class="analysis-input">
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
                    :label="`${p.display_name} (孕${Math.floor((p.gestational_age_days||0)/7)}周)${p.risk_tags?.length ? ' ['+p.risk_tags.join(',')+']' : ''}`"
                    :value="p.pregnant_id"
                  />
                </el-select>
                <el-input
                  v-model="aiQuery"
                  placeholder="补充查询（可选）"
                  style="width: 150px"
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

              <!-- AI分析结果 -->
              <div v-if="aiResult" class="analysis-result" v-loading="aiLoading">
                <el-alert
                  v-if="aiResult.risk_summary"
                  title="风险总结"
                  :description="aiResult.risk_summary"
                  type="error"
                  show-icon
                  :closable="false"
                  class="mb-3"
                />
                <el-alert
                  v-if="aiResult.analysis"
                  title="综合分析"
                  :description="aiResult.analysis"
                  type="info"
                  show-icon
                  :closable="false"
                  class="mb-3"
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
                  class="mb-3"
                />
                <div v-if="aiResult.evidence_references?.length" class="evidence-refs">
                  <p class="refs-title">循证参考：</p>
                  <ul>
                    <li v-for="(ref, idx) in aiResult.evidence_references" :key="idx">{{ ref }}</li>
                  </ul>
                </div>
              </div>

              <!-- 空状态 -->
              <div v-if="!aiResult && !aiLoading" class="analysis-empty">
                <el-icon :size="40" color="var(--text-muted)"><MagicStick /></el-icon>
                <p>选择孕妇后点击"AI分析"，Dr.智将提供鉴别诊断、治疗建议等临床分析</p>
              </div>
            </div>
          </el-tab-pane>

          <!-- 报告 Tab -->
          <el-tab-pane label="报告" name="report">
            <DoctorReport />
          </el-tab-pane>

          <!-- 问题 Tab -->
          <el-tab-pane label="问题" name="issues">
            <div class="issues-tab">
              <div class="issues-list">
                <div v-for="issue in issues" :key="issue.id" class="issue-item">
                  <div class="issue-header">
                    <el-tag :type="getPriorityType(issue.priority)" size="small">
                      {{ getPriorityLabel(issue.priority) }}
                    </el-tag>
                    <span class="issue-time">{{ formatTime(issue.created_at) }}</span>
                  </div>
                  <div class="issue-title">{{ issue.title }}</div>
                  <div class="issue-desc">{{ issue.description }}</div>
                  <div class="issue-footer">
                    <span class="issue-patient">{{ issue.patient_name }}</span>
                    <el-button
                      v-if="issue.status === 'pending'"
                      type="primary"
                      size="small"
                      @click="resolveIssue(issue)"
                    >
                      处理
                    </el-button>
                    <el-tag v-else type="success" size="small">已处理</el-tag>
                  </div>
                </div>
                <div v-if="!issues.length" class="issues-empty">
                  <el-icon :size="40" color="var(--text-muted)"><Bell /></el-icon>
                  <p>暂无待处理问题</p>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Close, MagicStick, Guide, FirstAidKit, Bell } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import DoctorAIChat from '../DoctorAIChat.vue'
import DoctorReport from '../DoctorReport.vue'
import { dashboardApi, doctorAiApi, collaborationApi } from '@/api/endpoints'
import type { Pregnant } from '@/types'

const panelVisible = ref(false)
const activeTab = ref('chat')

function togglePanel() {
  panelVisible.value = !panelVisible.value
  if (panelVisible.value && !pregnantList.value.length) {
    loadPatientList()
  }
}

// ==================== AI 智能分析 ====================
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
      analysis: 'AI分析暂时不可用，请查看孕妇详情进行手动评估',
      suggested_orders: '',
      evidence_references: [],
    }
  } finally {
    aiLoading.value = false
  }
}

onMounted(() => {
  // 预加载孕妇列表
  loadPatientList()
  // 加载待处理问题
  loadIssues()
})

// ==================== 问题处理 ====================
const issues = ref<any[]>([])

async function loadIssues() {
  try {
    const res = await collaborationApi.listDoctorIssues('pending')
    issues.value = res.data || []
  } catch { /* ignore */ }
}

function getPriorityType(priority: string) {
  const map: Record<string, string> = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    urgent: 'danger',
  }
  return map[priority] || 'info'
}

function getPriorityLabel(priority: string) {
  const map: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    urgent: '紧急',
  }
  return map[priority] || '中'
}

function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function resolveIssue(issue: any) {
  try {
    await ElMessageBox.confirm('确认已处理该问题？', '处理确认')
    await collaborationApi.resolveIssue(issue.id, '已处理')
    ElMessage.success('问题已处理')
    loadIssues()
  } catch { /* ignore */ }
}
</script>

<style scoped>
.doctor-ai-fab-container {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.doctor-ai-fab {
  width: 56px;
  height: 56px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s;
}

.doctor-ai-fab:hover {
  transform: scale(1.05);
}

.doctor-ai-panel {
  position: absolute;
  bottom: 72px;
  right: 0;
  width: 420px;
  height: 600px;
  background: var(--bg-page);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
}

.doctor-ai-panel__header {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}

.doctor-ai-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 15px;
}

.doctor-ai-panel__tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doctor-ai-panel__tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  background: var(--bg-card);
}

.doctor-ai-panel__tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.doctor-ai-panel__tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 分析 Tab 样式 */
.analysis-tab {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.analysis-input {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.analysis-result {
  flex: 1;
}

.mb-3 {
  margin-bottom: 12px;
}

/* 推理链 */
.reasoning-chain {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 14px;
  margin-bottom: 12px;
  border-left: 3px solid var(--primary);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
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
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.chain-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  min-width: 20px;
  border-radius: 50%;
  background: var(--primary-gradient);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

/* 鉴别诊断 */
.differential-diagnosis {
  background: rgba(241, 245, 249, 0.5);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 14px;
  margin-bottom: 12px;
}

.diagnosis-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diagnosis-item {
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  padding: 10px;
  border: 1px solid var(--glass-border);
}

.diagnosis-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.diagnosis-item__condition {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.diagnosis-item__reasoning {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0;
}

.evidence-refs {
  background: rgba(21, 101, 192, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  padding: 12px;
  border: 1px solid rgba(21, 101, 192, 0.1);
}

.refs-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.evidence-refs ul {
  margin-left: 16px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.analysis-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
  text-align: center;
  padding: 0 24px;
}

/* 覆盖 DoctorAIChat 的默认高度 */
:deep(.doctor-chat) {
  height: 100%;
  border: none;
  border-radius: 0;
}

/* 问题 Tab 样式 */
.issues-tab {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}

.issue-item {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
}

.issue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.issue-time {
  font-size: 12px;
  color: var(--text-muted);
}

.issue-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.issue-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.issue-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.issue-patient {
  font-size: 13px;
  color: var(--text-muted);
}

.issues-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 12px;
  color: var(--text-muted);
}
</style>
