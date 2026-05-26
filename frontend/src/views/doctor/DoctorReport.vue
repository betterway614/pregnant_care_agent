<template>
  <div class="doctor-report">
    <ToolActionBar
      v-model:patient-id="selectedPatient"
      :patients="patientList"
      role="doctor"
      :loading="loading"
      action-label="生成报告"
      action-icon-name="document"
      patient-placeholder="选择孕妇生成报告"
      @action="generateReport"
    />

    <AnalysisSkeleton v-if="loading" role="doctor" :count="2" />

    <div v-else-if="report" class="report-content">
      <div class="report-meta">
        <span class="report-meta__name">{{ report.patient_name }}</span>
        <span class="report-meta__time">{{ report.generated_at }}</span>
      </div>

      <AnalysisResultCard
        v-for="(section, idx) in reportSections"
        :key="idx"
        :title="section.title"
        icon="Document"
        severity="info"
        role="doctor"
        :default-expanded="idx === 0"
        :collapsible="reportSections.length > 1"
      >
        <div class="report-section-body" v-html="section.html" />
      </AnalysisResultCard>
    </div>

    <EmptyToolState
      v-else
      :icon="Document"
      role="doctor"
      message="选择孕妇后点击「生成报告」，AI 将生成孕期健康报告"
    />

    <div v-if="report && !loading" class="report-actions">
      <button type="button" class="report-actions__btn" @click="copyReport">
        <el-icon :size="14"><CopyDocument /></el-icon>
        复制
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Document, CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'
import {
  ToolActionBar,
  AnalysisResultCard,
  EmptyToolState,
  AnalysisSkeleton,
} from '@/components/agent-fab'
import { dashboardApi, doctorAiApi } from '@/api/endpoints'
import type { Pregnant } from '@/types'

const props = defineProps<{
  patients?: Pregnant[]
}>()

const selectedPatient = ref('')
const loading = ref(false)
const report = ref<any>(null)
const localPatients = ref<Pregnant[]>([])

const patientList = computed(() => props.patients?.length ? props.patients : localPatients.value)

interface ReportSection {
  title: string
  html: string
}

const reportSections = computed((): ReportSection[] => {
  if (!report.value?.report) return []
  const text = report.value.report as string
  const parts = text.split(/(?=^#{1,3}\s)/m).filter(Boolean)
  if (parts.length <= 1) {
    return [{ title: '报告正文', html: renderMarkdown(text) }]
  }
  return parts.map(part => {
    const match = part.match(/^#{1,3}\s+(.+?)[\n\r]/)
    const title = match ? match[1].trim() : '报告内容'
    const body = match ? part.slice(match[0].length) : part
    return { title, html: renderMarkdown(body.trim()) }
  })
})

async function loadPatientList() {
  if (props.patients?.length) return
  try {
    const res = await dashboardApi.pregnant()
    localPatients.value = res.data || []
  } catch { /* ignore */ }
}

async function generateReport() {
  if (!selectedPatient.value) return
  loading.value = true
  report.value = null
  try {
    const res = await doctorAiApi.generateReport(selectedPatient.value)
    report.value = res.data
  } catch {
    ElMessage.error('生成报告失败，请重试')
  } finally {
    loading.value = false
  }
}

async function copyReport() {
  if (!report.value?.report) return
  try {
    await navigator.clipboard.writeText(report.value.report)
    ElMessage.success('报告已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

onMounted(loadPatientList)
</script>

<style scoped>
.doctor-report {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
  overflow: hidden;
}

.report-content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.report-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: var(--capsule-radius);
  background: var(--doctor-accent-bg);
  font-size: 13px;
}

.report-meta__name {
  font-weight: 600;
  color: var(--text-primary);
}

.report-meta__time {
  color: var(--text-muted);
  font-size: 12px;
}

.report-section-body {
  font-size: 13px;
  line-height: 1.6;
}

.report-section-body :deep(p) {
  margin: 6px 0;
}

.report-section-body :deep(ul),
.report-section-body :deep(ol) {
  margin: 6px 0;
  padding-left: 18px;
}

.report-actions {
  display: flex;
  gap: 8px;
  padding-top: 10px;
  flex-shrink: 0;
}

.report-actions__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 6px 16px;
  border-radius: var(--capsule-radius);
  border: 1px solid var(--doctor-accent);
  background: transparent;
  color: var(--doctor-accent);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.report-actions__btn:hover {
  background: var(--doctor-accent-bg);
}

.report-actions__btn:focus-visible {
  outline: 2px solid var(--doctor-accent);
  outline-offset: 2px;
}
</style>
