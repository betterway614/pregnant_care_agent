<template>
  <div class="doctor-report">
    <div class="report-header">
      <el-select
        v-model="selectedPatient"
        filterable
        placeholder="选择孕妇生成报告"
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
        :loading="loading"
        :disabled="!selectedPatient"
        @click="generateReport"
      >
        <el-icon><Document /></el-icon> 生成报告
      </el-button>
    </div>

    <div v-if="report" class="report-content">
      <div class="report-meta">
        <span>{{ report.patient_name }}</span>
        <span class="text-muted">{{ report.generated_at }}</span>
      </div>
      <div class="report-body" v-html="renderMarkdown(report.report)" />
    </div>

    <div v-if="!report && !loading" class="report-empty">
      <el-icon :size="40" color="var(--text-muted)"><Document /></el-icon>
      <p>选择孕妇后点击"生成报告"，AI将生成孕期健康报告</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { dashboardApi, doctorAiApi } from '@/api/endpoints'
import { marked } from 'marked'
import type { Pregnant } from '@/types'

const selectedPatient = ref('')
const loading = ref(false)
const report = ref<any>(null)
const pregnantList = ref<Pregnant[]>([])

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string
}

async function loadPatientList() {
  try {
    const res = await dashboardApi.pregnant()
    pregnantList.value = res.data || []
  } catch { /* ignore */ }
}

async function generateReport() {
  if (!selectedPatient.value) return
  loading.value = true
  report.value = null
  try {
    const res = await doctorAiApi.generateReport(selectedPatient.value)
    report.value = res.data
  } catch (error) {
    console.error('生成报告失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPatientList()
})
</script>

<style scoped>
.doctor-report {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.report-header {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.report-content {
  flex: 1;
  overflow-y: auto;
}

.report-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 13px;
}

.text-muted {
  color: var(--text-muted);
}

.report-body {
  font-size: 13px;
  line-height: 1.6;
}

.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3) {
  margin: 12px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.report-body :deep(p) {
  margin: 8px 0;
}

.report-body :deep(ul),
.report-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.report-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
