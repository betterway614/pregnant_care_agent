<template>
  <div class="sign-page">
    <!-- 工具栏 -->
    <div class="toolbar no-print">
      <el-button @click="$router.back()" size="small">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="toolbar-title">医嘱签署</span>
      <div class="toolbar-actions">
        <el-button @click="showSignature = !showSignature" size="small">
          {{ showSignature ? '收起签名' : '手写签名' }}
        </el-button>
        <el-button type="primary" size="small" @click="doPrint">预览打印</el-button>
        <el-button type="success" size="small" :loading="exporting" @click="doExportPdf">导出 PDF</el-button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="28"><Loading /></el-icon>
      <span>加载医嘱...</span>
    </div>

    <template v-else-if="order">
      <!-- 红色警告横幅 -->
      <el-alert
        class="warning-banner"
        type="error"
        :closable="false"
        show-icon
      >
        <template #title>
          <span class="warning-text">
            ⚠️ 此医嘱为AI辅助生成，必须经医生修改确认并手写签名后方可生效，严禁直接发送给孕妇
          </span>
        </template>
      </el-alert>

      <!-- 医嘱信息卡片 -->
      <div class="info-card">
        <div class="info-card__row">
          <span class="info-card__label">孕妇：</span>
          <span class="info-card__value">{{ order.patient_name || '未知' }}</span>
          <span class="info-card__label" style="margin-left: 24px">类型：</span>
          <el-tag size="small">{{ typeLabel }}</el-tag>
          <span class="info-card__label" style="margin-left: 24px">来源：</span>
          <el-tag :type="order.source === 'AI_RECOMMENDED' ? 'warning' : 'info'" size="small">
            {{ sourceLabel }}
          </el-tag>
        </div>
      </div>

      <!-- 医嘱内容编辑区 -->
      <div class="content-card">
        <div class="content-card__header">
          <span class="content-card__title">医嘱内容（可编辑修改）</span>
          <el-tag v-if="contentModified" type="success" size="small">已修改</el-tag>
          <el-tag v-else type="danger" size="small">待修改</el-tag>
        </div>
        <el-input
          v-model="editContent"
          type="textarea"
          :rows="8"
          placeholder="请审核并修改医嘱内容..."
          maxlength="2000"
          show-word-limit
          @input="onContentChange"
        />
        <div class="content-card__hint">
          医生必须审核并修改AI生成的医嘱内容，确认无误后方可签署。修改后上方标签将变为"已修改"。
        </div>
      </div>

      <!-- 医生备注 -->
      <div class="notes-card">
        <div class="notes-card__header">
          <span class="notes-card__title">医生备注（可选）</span>
        </div>
        <el-input
          v-model="doctorNotes"
          type="textarea"
          :rows="3"
          placeholder="可添加额外的临床备注说明..."
          maxlength="500"
          show-word-limit
        />
      </div>

      <!-- 手写签名区 -->
      <div v-if="showSignature" class="sign-area no-print">
        <SignaturePad ref="signaturePadRef" label="医生手写签名" :width="400" :height="120">
          <template #actions="{ dataUrl, hasDrawn }">
            <el-button type="primary" size="small" :disabled="!hasDrawn" @click="saveSignature(dataUrl)">
              保存签名
            </el-button>
          </template>
        </SignaturePad>
      </div>

      <!-- 签名状态 -->
      <div v-if="savedSignature || order.signature_data?.image" class="sign-status no-print">
        <el-icon color="var(--success)"><CircleCheck /></el-icon>
        <span>签名已就绪</span>
        <img v-if="savedSignature || order.signature_data?.image"
             :src="savedSignature || order.signature_data?.image"
             class="sign-status__preview" />
      </div>

      <!-- 确认签署按钮 -->
      <div class="submit-area no-print">
        <el-button
          type="danger"
          size="large"
          :loading="submitting"
          :disabled="!canSign"
          @click="doSignOrder"
        >
          确认签署并发布医嘱
        </el-button>
        <div v-if="!canSign" class="submit-hint">
          <span v-if="!contentModified">请先修改医嘱内容</span>
          <span v-else-if="!savedSignature && !order.signature_data?.image">请先手写签名</span>
        </div>
      </div>

      <!-- 打印预览区（签署后显示） -->
      <div v-if="order.status === 'signed' || previewMode" class="print-section">
        <OrderDocumentPrint
          :patient-name="order.patient_name || '未知'"
          :gest-week="gestWeek"
          :content="editContent"
          :order-type="order.order_type"
          :source="order.source"
          :signature-image="savedSignature || order.signature_data?.image"
        />
      </div>
    </template>

    <!-- 错误状态 -->
    <div v-else class="empty-state">
      <el-icon :size="48" color="var(--text-light)"><WarningFilled /></el-icon>
      <p>医嘱不存在或加载失败</p>
      <el-button @click="$router.back()">返回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Loading, CircleCheck, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orderApi } from '@/api/endpoints'
import type { MedicalOrder } from '@/types'
import SignaturePad from '@/components/followup/SignaturePad.vue'
import OrderDocumentPrint from '@/components/orders/OrderDocumentPrint.vue'

const route = useRoute()
const router = useRouter()
const orderId = route.params.orderId as string

const loading = ref(true)
const submitting = ref(false)
const exporting = ref(false)
const showSignature = ref(false)
const previewMode = ref(false)
const order = ref<MedicalOrder | null>(null)
const editContent = ref('')
const originalContent = ref('')
const doctorNotes = ref('')
const savedSignature = ref<string | null>(null)
const signaturePadRef = ref<InstanceType<typeof SignaturePad> | null>(null)

const contentModified = computed(() => editContent.value !== originalContent.value)

const canSign = computed(() => {
  // AI生成的医嘱必须修改后才能签署
  if (order.value?.source === 'AI_RECOMMENDED' && !contentModified.value) return false
  // 必须有签名
  if (!savedSignature.value && !order.value?.signature_data?.image) return false
  return true
})

const typeLabel = computed(() => {
  const map: Record<string, string> = { standard: '标准医嘱', custom: '自定义医嘱' }
  return map[order.value?.order_type || ''] || order.value?.order_type || '标准医嘱'
})

const sourceLabel = computed(() => {
  const map: Record<string, string> = { AI_RECOMMENDED: 'AI辅助生成', DOCTOR_WRITTEN: '医生手写' }
  return map[order.value?.source || ''] || order.value?.source || 'AI辅助生成'
})

const gestWeek = computed(() => {
  // 尝试从order中获取孕周信息，暂无则显示未知
  return '未知'
})

function onContentChange() {
  // contentModified computed property will auto-update
}

function saveSignature(dataUrl: string) {
  savedSignature.value = dataUrl
  showSignature.value = false
  ElMessage.success('签名已保存')
}

async function doSignOrder() {
  if (!order.value) return

  try {
    await ElMessageBox.confirm(
      '确认签署后将发布医嘱给孕妇端，且不可撤回。请确认医嘱内容已审核修改完毕。',
      '确认签署',
      { confirmButtonText: '确认签署', cancelButtonText: '再检查一下', type: 'warning' }
    )
  } catch {
    return
  }

  submitting.value = true
  try {
    // 先更新医嘱内容
    if (contentModified.value) {
      await orderApi.update(orderId, {
        content: editContent.value,
        doctor_notes: doctorNotes.value
      })
    }

    // 签署
    await orderApi.sign(orderId, {
      doctor_id: 'doctor_001',
      signature_image: savedSignature.value || undefined,
      signer_name: '主治医生',
    })

    ElMessage.success('医嘱已签署并发布')
    // 重新加载展示打印预览
    const res = await orderApi.list({})
    const updated = (res.data || []).find((o: MedicalOrder) => o.id === orderId)
    if (updated) order.value = updated
    previewMode.value = true
  } catch (err: any) {
    const msg = err.response?.data?.detail || '签署失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

function doPrint() {
  window.print()
}

async function doExportPdf() {
  exporting.value = true
  try {
    const html2pdf = (await import('html2pdf.js')).default
    const el = document.querySelector('.order-doc') as HTMLElement
    if (!el) return
    await html2pdf().set({
      margin: 8,
      filename: `医嘱单_${orderId.slice(0, 8)}.pdf`,
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

onMounted(async () => {
  try {
    const res = await orderApi.list({})
    const found = (res.data || []).find((o: MedicalOrder) => o.id === orderId)
    if (found) {
      order.value = found
      editContent.value = found.content || ''
      originalContent.value = found.content || ''
      doctorNotes.value = found.doctor_notes || ''
    }
  } catch (err) {
    console.error('加载医嘱失败:', err)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.sign-page {
  max-width: 680px;
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
  font-size: 16px;
  font-weight: 700;
}

.toolbar-actions {
  display: flex;
  gap: 6px;
}

.warning-banner {
  margin-bottom: 12px;
}

.warning-text {
  font-size: 14px;
  font-weight: 700;
  color: #d32f2f;
}

.info-card {
  background: #fff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 12px;
}

.info-card__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.info-card__label {
  font-size: 13px;
  color: var(--text-muted);
}

.info-card__value {
  font-size: 14px;
  font-weight: 600;
}

.content-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 12px;
}

.content-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.content-card__title {
  font-size: 14px;
  font-weight: 700;
}

.content-card__hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.notes-card {
  background: #fff;
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 12px;
}

.notes-card__header {
  margin-bottom: 12px;
}

.notes-card__title {
  font-size: 14px;
  font-weight: 700;
}

.sign-area {
  background: #fff;
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 12px;
}

.sign-status {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--success);
}

.sign-status__preview {
  max-width: 120px;
  max-height: 40px;
  margin-left: auto;
}

.submit-area {
  text-align: center;
  padding: 16px 0;
  margin-bottom: 24px;
}

.submit-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--danger);
}

.print-section {
  margin-top: 16px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--text-muted);
}

@media print {
  .no-print { display: none !important; }
  .sign-page {
    padding: 0;
    background: #fff;
    max-width: none;
  }
  @page {
    size: A5 portrait;
    margin: 8mm;
  }
}
</style>
