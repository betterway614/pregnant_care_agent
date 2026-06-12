<template>
  <div class="nurse-ai-fab-container">
    <el-button
      class="nurse-ai-fab brand-gradient-btn"
      type="primary"
      circle
      size="large"
      @click="togglePanel"
    >
      <AgentAvatar agent="xiaohu" :size="24" />
    </el-button>

    <transition name="el-zoom-in-bottom">
      <div v-if="panelVisible" class="agent-fab-panel agent-fab-panel--nurse">
        <div class="agent-fab-panel__header">
          <div class="agent-fab-panel__title">
            <AgentAvatar agent="xiaohu" :size="20" />
            <span>小护 AI 智能助手</span>
          </div>
          <el-button text circle :icon="Close" @click="panelVisible = false" />
        </div>

        <CapsuleTabBar v-model="activeTab" :tabs="NURSE_FAB_TABS" role="nurse" />

        <div class="agent-fab-panel__body">
          <div v-show="activeTab === 'chat'" class="agent-fab-panel__pane">
            <NurseAIChat />
          </div>

          <div v-show="activeTab === 'analysis'" class="agent-fab-panel__pane agent-fab-panel__pane--scroll">
            <ToolActionBar
              v-model:patient-id="aiPatientId"
              :patients="pregnantList"
              role="nurse"
              :loading="aiLoading"
              action-label="开始分析"
              patient-placeholder="选择孕妇进行分析"
              @action="runAiAnalysis"
            />

            <AnalysisSkeleton v-if="aiLoading" role="nurse" />

            <div v-else-if="aiResult" class="analysis-results">
              <AnalysisResultCard
                v-if="aiResult.summary"
                id="section-summary"
                title="综合分析"
                icon="DataAnalysis"
                severity="info"
                role="nurse"
                :default-expanded="firstSectionKey === 'summary'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.summary)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.risk_assessment"
                id="section-risk_assessment"
                title="风险评估"
                icon="Warning"
                :severity="aiResult.risk_assessment.includes('高危') ? 'danger' : 'warning'"
                role="nurse"
                :default-expanded="firstSectionKey === 'risk_assessment'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.risk_assessment)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.nursing_suggestions"
                id="section-nursing_suggestions"
                title="护理建议"
                icon="FirstAidKit"
                severity="success"
                role="nurse"
                :default-expanded="firstSectionKey === 'nursing_suggestions'"
              >
                <div class="analysis-markdown" v-html="renderMarkdown(aiResult.nursing_suggestions)" />
              </AnalysisResultCard>

              <AnalysisResultCard
                v-if="aiResult.followup_focus?.length"
                id="section-followup_focus"
                title="随访重点关注"
                icon="Calendar"
                severity="info"
                role="nurse"
                :default-expanded="firstSectionKey === 'followup_focus'"
              >
                <div class="followup-chips">
                  <span
                    v-for="(item, idx) in aiResult.followup_focus"
                    :key="idx"
                    class="followup-chip"
                  >{{ item }}</span>
                </div>
              </AnalysisResultCard>
            </div>

            <EmptyToolState
              v-else
              :icon="MagicStick"
              role="nurse"
              message="选择孕妇后点击「开始分析」，小护将为您提供智能护理分析建议"
            />
          </div>

          <div v-show="activeTab === 'report'" class="agent-fab-panel__pane agent-fab-panel__pane--scroll">
            <ReportFormCapsule
              v-model="reportForm"
              role="nurse"
              :loading="reportLoading"
              :show-success="reportSuccess"
              @submit="submitReport"
            />
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Close, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import NurseAIChat from '../NurseAIChat.vue'
import {
  CapsuleTabBar,
  ToolActionBar,
  AnalysisResultCard,
  EmptyToolState,
  AnalysisSkeleton,
  ReportFormCapsule,
} from '@/components/agent-fab'
import type { ReportFormData } from '@/components/agent-fab'
import { NURSE_FAB_TABS, NURSE_ANALYSIS_SECTIONS } from '@/config/agentFabTools'
import { dashboardApi, nurseAiApi, aiAnalysisApi, collaborationApi } from '@/api/endpoints'
import { renderMarkdown } from '@/utils/markdown'
import type { Pregnant } from '@/types'

const panelVisible = ref(false)
const activeTab = ref('chat')
const aiPatientId = ref('')
const aiLoading = ref(false)
const aiResult = ref<any>(null)
const pregnantList = ref<Pregnant[]>([])
const reportLoading = ref(false)
const reportSuccess = ref(false)
const reportForm = ref<ReportFormData>({
  issue_type: 'risk_alert',
  priority: 'medium',
  title: '',
  description: '',
})

const firstSectionKey = computed(() => {
  if (!aiResult.value) return ''
  for (const s of NURSE_ANALYSIS_SECTIONS) {
    const val = aiResult.value[s.key]
    if (Array.isArray(val) ? val.length : val) return s.key
  }
  return ''
})

function togglePanel() {
  panelVisible.value = !panelVisible.value
  if (panelVisible.value && !pregnantList.value.length) loadPatientList()
}

async function loadPatientList() {
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data?.data || []
  } catch { /* ignore */ }
}

async function runAiAnalysis() {
  if (!aiPatientId.value) return
  aiLoading.value = true
  aiResult.value = null
  try {
    const res = await nurseAiApi.analyze(aiPatientId.value)
    aiResult.value = res.data
    await aiAnalysisApi.save({
      pregnant_id: aiPatientId.value,
      result_data: res.data,
      analysis_type: 'general',
    })
  } catch {
    aiResult.value = {
      summary: 'AI分析暂时不可用，请联系管理员',
    }
  } finally {
    aiLoading.value = false
  }
}

async function submitReport() {
  if (!reportForm.value.title || !reportForm.value.description) {
    ElMessage.warning('请填写问题标题和描述')
    return
  }
  reportLoading.value = true
  reportSuccess.value = false
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    await collaborationApi.reportIssue({
      pregnant_id: pregnantId,
      ...reportForm.value,
    })
    reportSuccess.value = true
    reportForm.value = {
      issue_type: 'risk_alert',
      priority: 'medium',
      title: '',
      description: '',
    }
    setTimeout(() => { reportSuccess.value = false }, 3000)
  } catch {
    ElMessage.error('上报失败，请重试')
  } finally {
    reportLoading.value = false
  }
}

onMounted(loadPatientList)
</script>

<style scoped>
.nurse-ai-fab-container {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.nurse-ai-fab {
  width: 56px;
  height: 56px;
  box-shadow: var(--shadow-md);
  transition: transform var(--transition);
}

.nurse-ai-fab:hover {
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

.analysis-results {
  flex: 1;
}

.followup-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.followup-chip {
  padding: 6px 14px;
  border-radius: var(--capsule-radius);
  background: var(--nurse-accent-bg);
  border: 1px solid rgba(46, 125, 50, 0.2);
  font-size: 12px;
  font-weight: 600;
  color: var(--nurse-accent);
}

:deep(.nurse-chat) {
  height: 100%;
  border: none;
  border-radius: 0;
}

@media (prefers-reduced-motion: reduce) {
  .nurse-ai-fab {
    transition: none;
  }
}
</style>
