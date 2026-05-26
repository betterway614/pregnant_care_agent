<template>
  <div class="doctor-ai-fab-container">
    <el-button
      class="doctor-ai-fab brand-gradient-btn"
      type="primary"
      circle
      size="large"
      @click="togglePanel"
    >
      <AgentAvatar agent="zhiyi" :size="24" />
    </el-button>

    <transition name="el-zoom-in-bottom">
      <div v-if="panelVisible" class="agent-fab-panel agent-fab-panel--doctor">
        <div class="agent-fab-panel__header">
          <div class="agent-fab-panel__title">
            <AgentAvatar agent="zhiyi" :size="20" />
            <span>Dr.智 AI 临床助手</span>
          </div>
          <el-button text circle :icon="Close" @click="panelVisible = false" />
        </div>

        <CapsuleTabBar v-model="activeTab" :tabs="DOCTOR_FAB_TABS" role="doctor" />

        <div class="agent-fab-panel__body">
          <div v-show="activeTab === 'chat'" class="agent-fab-panel__pane">
            <DoctorAIChat />
          </div>

          <div v-show="activeTab === 'analysis'" class="agent-fab-panel__pane agent-fab-panel__pane--scroll">
            <ToolActionBar
              v-model:patient-id="aiPatientId"
              v-model:active-section="activeAnalysisSection"
              :patients="pregnantList"
              role="doctor"
              :loading="aiLoading"
              action-label="开始分析"
              patient-placeholder="选择孕妇进行分析"
              show-risk-tags
              :section-options="analysisSectionChips"
              @action="runAiAnalysis"
            >
              <template #extra>
                <div class="analysis-query-capsule">
                  <input
                    v-model="aiQuery"
                    class="analysis-query-capsule__input"
                    placeholder="补充查询（可选）"
                  />
                </div>
              </template>
            </ToolActionBar>

            <AnalysisSkeleton v-if="aiLoading" role="doctor" />

            <div v-else-if="aiResult" ref="analysisResultRef" class="analysis-results">
              <AnalysisResultCard
                v-if="aiResult.risk_summary"
                id="section-risk_summary"
                title="风险总结"
                icon="Warning"
                severity="danger"
                role="doctor"
                :default-expanded="firstSectionKey === 'risk_summary'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.risk_summary)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.analysis"
                id="section-analysis"
                title="综合分析"
                icon="DataAnalysis"
                severity="info"
                role="doctor"
                :default-expanded="firstSectionKey === 'analysis'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.analysis)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.reasoning_chain?.length"
                id="section-reasoning_chain"
                title="推理链"
                icon="Guide"
                severity="info"
                role="doctor"
                :default-expanded="firstSectionKey === 'reasoning_chain'"
              >
                <div class="reasoning-timeline">
                  <div
                    v-for="(step, idx) in aiResult.reasoning_chain"
                    :key="idx"
                    class="reasoning-timeline__step"
                  >
                    <span class="reasoning-timeline__num">{{ idx + 1 }}</span>
                    <span class="reasoning-timeline__text">{{ step }}</span>
                  </div>
                </div>
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.suggested_orders"
                id="section-suggested_orders"
                title="建议医嘱"
                icon="Document"
                severity="warning"
                role="doctor"
                :default-expanded="firstSectionKey === 'suggested_orders'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.suggested_orders)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.evidence_references?.length"
                id="section-evidence_references"
                title="循证参考"
                icon="Reading"
                severity="info"
                role="doctor"
                :default-expanded="firstSectionKey === 'evidence_references'"
              >
                <div class="evidence-chips">
                  <span
                    v-for="(ref, idx) in aiResult.evidence_references"
                    :key="idx"
                    class="evidence-chip"
                  >{{ ref }}</span>
                </div>
              </AnalysisResultCard>
            </div>

            <EmptyToolState
              v-else
              :icon="MagicStick"
              role="doctor"
              message="选择孕妇后点击「开始分析」，Dr.智将提供风险评估、治疗建议等临床分析"
            />
          </div>

          <div v-show="activeTab === 'report'" class="agent-fab-panel__pane">
            <DoctorReport :patients="pregnantList" />
          </div>

          <div v-show="activeTab === 'issues'" class="agent-fab-panel__pane agent-fab-panel__pane--scroll">
            <CapsuleChipGroup
              v-model="issueFilter"
              :options="ISSUE_FILTER_OPTIONS"
              role="doctor"
              class="issues-filter"
            />
            <IssueCard
              v-for="issue in filteredIssues"
              :key="issue.id"
              :title="issue.title"
              :description="issue.description"
              :patient-name="issue.patient_name"
              :priority="issue.priority"
              :status="issue.status"
              :time="formatTime(issue.created_at)"
              role="doctor"
              @resolve="resolveIssue(issue)"
            />
            <EmptyToolState
              v-if="!filteredIssues.length"
              :icon="Bell"
              role="doctor"
              message="暂无相关问题"
            />
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Close, MagicStick, Bell } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import DoctorAIChat from '../DoctorAIChat.vue'
import DoctorReport from '../DoctorReport.vue'
import {
  CapsuleTabBar,
  ToolActionBar,
  AnalysisResultCard,
  EmptyToolState,
  IssueCard,
  AnalysisSkeleton,
  CapsuleChipGroup,
} from '@/components/agent-fab'
import {
  DOCTOR_FAB_TABS,
  DOCTOR_ANALYSIS_SECTIONS,
  ISSUE_FILTER_OPTIONS,
} from '@/config/agentFabTools'
import { dashboardApi, doctorAiApi, collaborationApi } from '@/api/endpoints'
import { renderMarkdown } from '@/utils/markdown'
import type { Pregnant } from '@/types'

const panelVisible = ref(false)
const activeTab = ref('chat')
const aiPatientId = ref('')
const aiQuery = ref('')
const aiLoading = ref(false)
const aiResult = ref<any>(null)
const pregnantList = ref<Pregnant[]>([])
const activeAnalysisSection = ref('')
const analysisResultRef = ref<HTMLElement | null>(null)
const issueFilter = ref('pending')
const allIssues = ref<any[]>([])

const analysisSectionChips = computed(() =>
  DOCTOR_ANALYSIS_SECTIONS.map(s => ({ value: s.key, label: s.label, icon: s.icon })),
)

const firstSectionKey = computed(() => {
  if (!aiResult.value) return ''
  for (const s of DOCTOR_ANALYSIS_SECTIONS) {
    const val = aiResult.value[s.key]
    if (Array.isArray(val) ? val.length : val) return s.key
  }
  return ''
})

const filteredIssues = computed(() => allIssues.value)

watch(activeAnalysisSection, (key) => {
  if (!key) return
  const section = DOCTOR_ANALYSIS_SECTIONS.find(s => s.key === key)
  if (section?.scrollTarget) {
    document.getElementById(section.scrollTarget)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
})

function togglePanel() {
  panelVisible.value = !panelVisible.value
  if (panelVisible.value && !pregnantList.value.length) loadPatientList()
}

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
  } catch {
    aiResult.value = {
      analysis: 'AI分析暂时不可用，请查看孕妇详情进行手动评估',
    }
  } finally {
    aiLoading.value = false
  }
}

watch(issueFilter, () => loadIssues())

async function loadIssues() {
  try {
    if (issueFilter.value === 'all') {
      const [pending, resolved] = await Promise.all([
        collaborationApi.listDoctorIssues('pending'),
        collaborationApi.listDoctorIssues('resolved'),
      ])
      allIssues.value = [...(pending.data || []), ...(resolved.data || [])]
    } else {
      const status = issueFilter.value === 'resolved' ? 'resolved' : 'pending'
      const res = await collaborationApi.listDoctorIssues(status)
      allIssues.value = res.data || []
    }
  } catch { /* ignore */ }
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

onMounted(() => {
  loadPatientList()
  loadIssues()
})
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
  box-shadow: var(--shadow-md);
  transition: transform var(--transition);
}

.doctor-ai-fab:hover {
  transform: scale(1.05);
}

.agent-fab-panel {
  position: absolute;
  bottom: 72px;
  right: 0;
  width: var(--fab-panel-width);
  height: var(--fab-panel-height);
  background: var(--bg-page);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
}

.agent-fab-panel__header {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0;
}

.agent-fab-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 15px;
}

.agent-fab-panel__body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.agent-fab-panel__pane {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.agent-fab-panel__pane--scroll {
  overflow-y: auto;
  padding: 12px 16px 16px;
  -webkit-overflow-scrolling: touch;
}

.analysis-query-capsule {
  flex: 1;
  min-width: 0;
}

.analysis-query-capsule__input {
  width: 100%;
  min-height: var(--capsule-min-height);
  padding: 8px 14px;
  border: 1px solid var(--capsule-border);
  border-radius: var(--capsule-radius);
  background: var(--capsule-bg);
  font-size: 13px;
  font-family: inherit;
  color: var(--text-primary);
  outline: none;
}

.analysis-query-capsule__input:focus-visible {
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

.analysis-results {
  flex: 1;
}

.reasoning-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reasoning-timeline__step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.reasoning-timeline__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  border-radius: var(--capsule-radius);
  background: var(--doctor-accent-gradient);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.reasoning-timeline__text {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  padding-top: 2px;
}

.evidence-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.evidence-chip {
  padding: 6px 12px;
  border-radius: var(--capsule-radius);
  background: var(--info-light);
  border: 1px solid rgba(21, 101, 192, 0.15);
  font-size: 11px;
  color: var(--info);
  line-height: 1.4;
}

.issues-filter {
  margin-bottom: 12px;
}

:deep(.doctor-chat) {
  height: 100%;
  border: none;
  border-radius: 0;
}

@media (prefers-reduced-motion: reduce) {
  .doctor-ai-fab {
    transition: none;
  }
}
</style>
