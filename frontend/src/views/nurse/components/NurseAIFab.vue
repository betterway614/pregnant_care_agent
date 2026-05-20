<template>
  <div class="nurse-ai-fab-container">
    <!-- 悬浮球 -->
    <el-button
      class="nurse-ai-fab brand-gradient-btn"
      type="primary"
      circle
      size="large"
      @click="togglePanel"
    >
      <AgentAvatar agent="xiaohu" :size="24" />
    </el-button>

    <!-- 展开的面板 -->
    <transition name="el-zoom-in-bottom">
      <div v-if="panelVisible" class="nurse-ai-panel">
        <div class="nurse-ai-panel__header">
          <div class="nurse-ai-panel__title">
            <AgentAvatar agent="xiaohu" :size="20" />
            <span>小护 AI 智能助手</span>
          </div>
          <el-button text circle :icon="Close" @click="panelVisible = false" />
        </div>

        <el-tabs v-model="activeTab" class="nurse-ai-panel__tabs">
          <!-- 对话 Tab -->
          <el-tab-pane label="对话" name="chat">
            <NurseAIChat />
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
                    :label="`${p.display_name} (孕${Math.floor((p.gestational_age_days||0)/7)}周)`"
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
              <div v-if="aiResult" class="analysis-result" v-loading="aiLoading">
                <el-alert
                  v-if="aiResult.summary"
                  title="综合分析"
                  :description="aiResult.summary"
                  type="info"
                  show-icon
                  :closable="false"
                  class="mb-3"
                />
                <el-alert
                  v-if="aiResult.risk_assessment"
                  title="风险评估"
                  :description="aiResult.risk_assessment"
                  :type="aiResult.risk_assessment.includes('高危') ? 'error' : 'warning'"
                  show-icon
                  :closable="false"
                  class="mb-3"
                />
                <el-alert
                  v-if="aiResult.nursing_suggestions"
                  title="护理建议"
                  :description="aiResult.nursing_suggestions"
                  type="success"
                  show-icon
                  :closable="false"
                  class="mb-3"
                />
                <div v-if="aiResult.followup_focus?.length" class="followup-focus">
                  <p class="focus-title">随访重点关注：</p>
                  <el-tag
                    v-for="(item, idx) in aiResult.followup_focus"
                    :key="idx"
                    size="small"
                    class="focus-tag"
                  >{{ item }}</el-tag>
                </div>
              </div>

              <!-- 空状态 -->
              <div v-if="!aiResult && !aiLoading" class="analysis-empty">
                <el-icon :size="40" color="var(--text-muted)"><MagicStick /></el-icon>
                <p>选择孕妇后点击"AI分析"，小护将为您提供智能护理分析建议</p>
              </div>
            </div>
          </el-tab-pane>

          <!-- 上报 Tab -->
          <el-tab-pane label="上报" name="report">
            <div class="report-tab">
              <el-form :model="reportForm" label-position="top" size="small">
                <el-form-item label="问题类型">
                  <el-select v-model="reportForm.issue_type" placeholder="选择问题类型" style="width: 100%">
                    <el-option label="风险预警" value="risk_alert" />
                    <el-option label="异常数据" value="abnormal_data" />
                    <el-option label="患者投诉" value="patient_complaint" />
                  </el-select>
                </el-form-item>
                <el-form-item label="优先级">
                  <el-radio-group v-model="reportForm.priority">
                    <el-radio-button label="low">低</el-radio-button>
                    <el-radio-button label="medium">中</el-radio-button>
                    <el-radio-button label="high">高</el-radio-button>
                    <el-radio-button label="urgent">紧急</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="问题标题">
                  <el-input v-model="reportForm.title" placeholder="简要描述问题" />
                </el-form-item>
                <el-form-item label="详细描述">
                  <el-input v-model="reportForm.description" type="textarea" :rows="3" placeholder="详细描述问题情况" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="submitReport" :loading="reportLoading" style="width: 100%">
                    上报给医生
                  </el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Close, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import NurseAIChat from '../NurseAIChat.vue'
import { dashboardApi, nurseAiApi, aiAnalysisApi, collaborationApi } from '@/api/endpoints'
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

    // 保存到后端
    await aiAnalysisApi.save({
      pregnant_id: aiPatientId.value,
      result_data: res.data,
      analysis_type: 'general',
    })
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
  // 预加载孕妇列表
  loadPatientList()
})

// ==================== 问题上报 ====================
const reportForm = ref({
  issue_type: 'risk_alert',
  priority: 'medium',
  title: '',
  description: '',
})
const reportLoading = ref(false)

async function submitReport() {
  if (!reportForm.value.title || !reportForm.value.description) {
    ElMessage.warning('请填写问题标题和描述')
    return
  }

  reportLoading.value = true
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    await collaborationApi.reportIssue({
      pregnant_id: pregnantId,
      ...reportForm.value,
    })
    ElMessage.success('问题已上报给医生')
    reportForm.value = {
      issue_type: 'risk_alert',
      priority: 'medium',
      title: '',
      description: '',
    }
  } catch (error) {
    ElMessage.error('上报失败，请重试')
  } finally {
    reportLoading.value = false
  }
}
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
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s;
}

.nurse-ai-fab:hover {
  transform: scale(1.05);
}

.nurse-ai-panel {
  position: absolute;
  bottom: 72px;
  right: 0;
  width: 380px;
  height: 560px;
  background: var(--bg-page);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
}

.nurse-ai-panel__header {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}

.nurse-ai-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 15px;
}

.nurse-ai-panel__tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.nurse-ai-panel__tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  background: var(--bg-card);
}

.nurse-ai-panel__tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.nurse-ai-panel__tabs :deep(.el-tab-pane) {
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
}

.analysis-result {
  flex: 1;
}

.mb-3 {
  margin-bottom: 12px;
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

.focus-tag {
  margin: 0 8px 8px 0;
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

/* 覆盖 NurseAIChat 的默认高度 */
:deep(.nurse-chat) {
  height: 100%;
  border: none;
  border-radius: 0;
}

/* 上报 Tab 样式 */
.report-tab {
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}
</style>
