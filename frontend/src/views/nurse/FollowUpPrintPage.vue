<template>
  <div class="print-page">
    <!-- 工具栏（打印时隐藏） -->
    <div class="toolbar no-print">
      <el-button @click="$router.back()" size="small">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="toolbar-title">随访记录打印</span>
      <div class="toolbar-actions">
        <el-button @click="showSignature = !showSignature" size="small">
          {{ showSignature ? '收起签名' : '手写签名' }}
        </el-button>
        <el-button type="primary" size="small" @click="doPrint">打印</el-button>
        <el-button type="success" size="small" :loading="exporting" @click="doExportPdf">导出 PDF</el-button>
      </div>
    </div>

    <!-- 签名板 -->
    <div v-if="showSignature" class="sign-area no-print">
      <SignaturePad ref="signaturePad" label="护士签名" :width="360" :height="100">
        <template #actions="{ dataUrl, hasDrawn }">
          <el-button type="primary" size="small" :disabled="!hasDrawn" @click="saveSignature(dataUrl)">
            保存签名
          </el-button>
        </template>
      </SignaturePad>
    </div>

    <!-- 记录单（A5 纯文本） -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="28"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    <div v-else class="record-doc" ref="printEl">
      <pre class="record-text">{{ recordText }}</pre>
      <div v-if="nurseSignature" class="sign-area-print">
        <img :src="nurseSignature" class="sign-img" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { followUpApi } from '@/api/endpoints'
import SignaturePad from '@/components/followup/SignaturePad.vue'

const route = useRoute()
const recordId = route.params.id as string

const loading = ref(true)
const exporting = ref(false)
const showSignature = ref(false)
const recordText = ref('')
const nurseSignature = ref<string | null>(null)
const printEl = ref<HTMLElement | null>(null)

onMounted(async () => {
  try {
    const res = await followUpApi.getDocument(recordId)
    const data = res.data
    recordText.value = data.text || '暂无归档文档，请先确认归档该随访记录。'
    if (data.signature?.image) {
      nurseSignature.value = data.signature.image
    }
  } catch (err: any) {
    if (err.response?.status === 404) {
      recordText.value = '该记录尚未生成归档文档，请先在随访管理页面确认归档。'
    } else {
      ElMessage.error('加载失败')
    }
  } finally {
    loading.value = false
  }
})

async function saveSignature(dataUrl: string) {
  try {
    await followUpApi.sign(recordId, dataUrl, '护士')
    nurseSignature.value = dataUrl
    showSignature.value = false
    ElMessage.success('签名已保存')
  } catch {
    ElMessage.error('签名保存失败')
  }
}

function doPrint() {
  window.print()
}

async function doExportPdf() {
  exporting.value = true
  try {
    const el = printEl.value
    if (!el) return
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
  max-width: 600px;
  margin: 0 auto;
  padding: 16px;
  background: var(--bg-page);
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
}
.toolbar-title {
  font-size: 15px;
  font-weight: 700;
}
.toolbar-actions { display: flex; gap: 6px; }
.sign-area {
  margin-bottom: 12px;
  padding: 14px;
  background: #fff;
  border-radius: 8px;
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 60px 0;
  color: var(--text-muted);
}

/* A5 记录单 */
.record-doc {
  background: #fff;
  padding: 12mm 10mm;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.record-text {
  font-family: 'SimSun', 'Noto Serif SC', serif;
  font-size: 14px;
  line-height: 2;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #333;
}
.sign-area-print {
  margin-top: -20px;
  display: flex;
  justify-content: flex-start;
  padding-left: 96px;
  font-family: 'SimSun', 'Noto Serif SC', serif;
}
.sign-img {
  max-width: 160px;
  max-height: 50px;
}

/* 打印样式 — A5 */
@media print {
  .no-print { display: none !important; }
  .print-page {
    padding: 0;
    background: #fff;
    max-width: none;
  }
  .record-doc {
    box-shadow: none;
    border-radius: 0;
    padding: 8mm 10mm;
  }
  @page {
    size: A5 portrait;
    margin: 8mm;
  }
}
</style>
