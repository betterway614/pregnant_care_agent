<template>
  <div class="print-page">
    <div class="toolbar no-print">
      <el-button @click="$router.back()" size="small">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="toolbar-title">{{ pageTitle }}</span>
      <div class="toolbar-actions">
        <el-button
          size="small"
          :disabled="isArchived || !summaryModified"
          @click="showSignature = !showSignature"
        >
          {{ showSignature ? '收起签名' : nurseSignature ? '签名已保存' : '手写签名' }}
        </el-button>
        <el-button
          type="primary"
          size="small"
          :disabled="isArchived || !summaryModified || !nurseSignature"
          :loading="archiveLoading"
          @click="doArchive"
        >
          确认归档
        </el-button>
        <el-button size="small" :disabled="!canPrint" @click="doPrint">打印</el-button>
        <el-button type="success" size="small" :disabled="!canPrint" :loading="exporting" @click="doExportPdf">导出 PDF</el-button>
      </div>
    </div>

    <div v-if="!loading && !isArchived" class="archive-steps no-print">
      <div class="step-item" :class="{ 'step-item--done': !!archiveDraft }">1 AI 原稿</div>
      <div class="step-item" :class="{ 'step-item--done': summaryModified }">2 护士修改</div>
      <div class="step-item" :class="{ 'step-item--done': !!nurseSignature }">3 签名</div>
      <div class="step-item" :class="{ 'step-item--done': isArchived }">4 归档</div>
    </div>

    <div v-if="showSignature" class="sign-area no-print">
      <SignaturePad ref="signaturePad" label="护士签名" :width="360" :height="100">
        <template #actions="{ dataUrl, hasDrawn }">
          <el-button type="primary" size="small" :disabled="!hasDrawn" @click="saveSignature(dataUrl)">
            保存签名
          </el-button>
          <el-button size="small" :disabled="!hasDrawn" @click="signaturePad?.clear()">
            清除重签
          </el-button>
        </template>
      </SignaturePad>
      <div v-if="nurseSignature" class="sign-saved-tip">签名已保存</div>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="28"><Loading /></el-icon>
      <span>{{ loadingText }}</span>
    </div>

    <template v-else>
      <div ref="printEl" class="record-preview">
        <FollowUpRecordPrint
          :snapshot="snapshot"
          :record-id="recordId"
          :nurse-signature="nurseSignature"
        />
      </div>

      <div v-if="!isArchived" class="summary-editor no-print">
        <div class="summary-editor__header">
          <span class="summary-editor__title">归档总结</span>
          <el-tag v-if="archiveDraft" size="small" type="info">AI 原稿已生成</el-tag>
          <el-tag v-if="summaryModified" size="small" type="success">护士已修改</el-tag>
        </div>

        <div class="summary-grid">
          <div class="summary-panel">
            <div class="summary-panel__label">AI 原稿</div>
            <div class="summary-panel__body">{{ archiveDraft || '正在生成 AI 归档总结...' }}</div>
          </div>
          <div class="summary-panel summary-panel--editable">
            <div class="summary-panel__label">护士定稿</div>
            <el-input
              v-model="archiveSummary"
              type="textarea"
              :rows="8"
              resize="vertical"
              placeholder="请在 AI 原稿基础上修改后保存"
            />
          </div>
        </div>

        <div class="summary-actions">
          <span class="summary-hint" :class="{ 'summary-hint--ok': summaryModified }">
            {{ summaryHint }}
          </span>
          <el-button type="primary" size="small" :loading="savingSummary" @click="saveSummary">
            保存护士定稿
          </el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { followUpApi } from '@/api/endpoints'
import SignaturePad from '@/components/followup/SignaturePad.vue'
import FollowUpRecordPrint from '@/components/followup/FollowUpRecordPrint.vue'

const route = useRoute()
const recordId = route.params.id as string

const loading = ref(true)
const loadingText = ref('加载中...')
const exporting = ref(false)
const archiveLoading = ref(false)
const savingSummary = ref(false)
const showSignature = ref(false)
const nurseSignature = ref<string | null>(null)
const printEl = ref<HTMLElement | null>(null)
const signaturePad = ref<InstanceType<typeof SignaturePad> | null>(null)

const recordStatus = ref('')
const snapshot = ref<Record<string, any>>({})
const archiveDraft = ref('')
const archiveSummary = ref('')
const summaryModified = ref(false)

const isArchived = computed(() => recordStatus.value === 'archived')
const canPrint = computed(() => isArchived.value)
const pageTitle = computed(() => isArchived.value ? '随访记录 — 打印发布' : '随访记录 — 归档确认')
const summaryHint = computed(() => {
  if (summaryModified.value) return '已保存不同于 AI 原稿的护士定稿，可以签名。'
  if (!archiveDraft.value) return 'AI 原稿生成后，护士定稿必须修改后保存。'
  if (normalizeText(archiveSummary.value) === normalizeText(archiveDraft.value)) return '护士定稿仍与 AI 原稿相同，后端不会允许签名。'
  return '当前内容已有修改，请保存护士定稿。'
})

onMounted(() => {
  loadPage()
})

async function loadPage() {
  loading.value = true
  loadingText.value = '加载随访记录...'
  try {
    const res = await followUpApi.getDocument(recordId)
    applyDocument(res.data)
    if (recordStatus.value === 'confirmed') {
      loadingText.value = '生成 AI 归档总结原稿...'
      const summaryRes = await followUpApi.generateArchiveSummary(recordId)
      applyArchiveSummary(summaryRes.data)
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function applyDocument(data: any) {
  recordStatus.value = data.status || ''
  snapshot.value = data.snapshot || {}
  if (data.signature?.image) {
    nurseSignature.value = data.signature.image
  } else {
    nurseSignature.value = null
  }
  if (data.archive_summary) {
    applyArchiveSummary(data.archive_summary)
  }
}

function applyArchiveSummary(data: any) {
  archiveDraft.value = data.ai_draft_text || ''
  archiveSummary.value = data.nurse_final_text || data.ai_draft_text || ''
  summaryModified.value = !!data.modified
  snapshot.value = {
    ...snapshot.value,
    archive_summary_draft_text: archiveDraft.value,
    archive_summary_final_text: data.nurse_final_text || snapshot.value.archive_summary_final_text || '',
    archive_summary_modified: !!data.modified,
  }
}

function normalizeText(text: string) {
  return String(text || '').replace(/\s+/g, '')
}

async function saveSummary() {
  if (!archiveDraft.value) {
    ElMessage.warning('AI 原稿尚未生成')
    return
  }
  if (normalizeText(archiveSummary.value) === normalizeText(archiveDraft.value)) {
    ElMessage.warning('护士定稿必须和 AI 原稿不同')
    return
  }
  savingSummary.value = true
  try {
    const res = await followUpApi.updateArchiveSummary(recordId, archiveSummary.value)
    applyArchiveSummary(res.data)
    ElMessage.success('护士定稿已保存')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingSummary.value = false
  }
}

async function saveSignature(dataUrl: string) {
  if (!summaryModified.value) {
    ElMessage.warning('请先保存不同于 AI 原稿的护士定稿')
    return
  }
  try {
    await followUpApi.sign(recordId, dataUrl, '护士')
    nurseSignature.value = dataUrl
    showSignature.value = false
    ElMessage.success('签名已保存')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '签名保存失败')
  }
}

async function doArchive() {
  if (!summaryModified.value) {
    ElMessage.warning('请先保存不同于 AI 原稿的护士定稿')
    return
  }
  if (!nurseSignature.value) {
    ElMessage.warning('请先完成护士签名')
    return
  }
  archiveLoading.value = true
  try {
    await followUpApi.archive(recordId)
    ElMessage.success('已归档，可打印或导出 PDF')
    await loadPage()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '归档失败')
  } finally {
    archiveLoading.value = false
  }
}

function doPrint() {
  if (!canPrint.value) {
    ElMessage.warning('归档后方可打印')
    return
  }
  window.print()
}

async function doExportPdf() {
  if (!canPrint.value) {
    ElMessage.warning('归档后方可导出 PDF')
    return
  }
  exporting.value = true
  try {
    const el = printEl.value
    if (!el) { ElMessage.warning('页面未加载完成'); return }
    const html2pdf = (await import('html2pdf.js')).default
    await html2pdf().set({
      margin: 8,
      filename: `随访记录_${recordId.slice(0, 8)}.pdf`,
      image: { type: 'jpeg', quality: 0.95 },
      html2canvas: { scale: 2 },
      jsPDF: { unit: 'mm', format: 'a5', orientation: 'portrait' },
    } as any).from(el).save()
    ElMessage.success('PDF 已导出')
  } catch {
    ElMessage.error('PDF 导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.print-page {
  max-width: 760px;
  margin: 0 auto;
  padding: 16px;
  background: var(--bg-page, #f5f7fb);
  min-height: 100vh;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 12px;
  gap: 8px;
  flex-wrap: wrap;
}
.toolbar-title {
  font-size: 15px;
  font-weight: 700;
  flex: 1;
  white-space: nowrap;
}
.toolbar-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.archive-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.step-item {
  padding: 8px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  color: #606266;
  font-size: 13px;
  text-align: center;
}
.step-item--done {
  border-color: #95d475;
  background: #f0f9eb;
  color: #3d7d18;
  font-weight: 700;
}
.sign-area {
  margin-bottom: 12px;
  padding: 14px;
  background: #fff;
  border-radius: 8px;
}
.sign-saved-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #67c23a;
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 60px 0;
  color: var(--text-muted, #909399);
}
.record-preview {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  margin-bottom: 12px;
  overflow: hidden;
}
.summary-editor {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}
.summary-editor__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.summary-editor__title {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.summary-panel {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  overflow: hidden;
  background: #fafafa;
}
.summary-panel__label {
  padding: 8px 10px;
  border-bottom: 1px solid #e4e7ed;
  font-size: 13px;
  font-weight: 700;
  color: #606266;
  background: #f5f7fa;
}
.summary-panel__body {
  min-height: 168px;
  padding: 10px;
  white-space: pre-wrap;
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
}
.summary-panel--editable {
  background: #fff;
}
.summary-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}
.summary-hint {
  font-size: 12px;
  color: #e6a23c;
}
.summary-hint--ok {
  color: #67c23a;
}
@media (max-width: 720px) {
  .summary-grid { grid-template-columns: 1fr; }
  .archive-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media print {
  .no-print { display: none !important; }
  .print-page { padding: 0; background: #fff; max-width: none; }
  .record-preview { box-shadow: none; border-radius: 0; }
  .summary-editor { display: none; }
  @page { size: A5 portrait; margin: 8mm; }
}
</style>
