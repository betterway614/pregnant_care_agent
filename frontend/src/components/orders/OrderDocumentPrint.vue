<template>
  <div class="order-print">
    <!-- 记录单（A5 排版） -->
    <div class="order-doc" ref="printEl">
      <div class="doc-header">
        <div class="doc-header__brand">AI-Care 孕期智能管理平台</div>
        <div class="doc-header__title">医 嘱 单</div>
      </div>

      <div class="doc-info">
        <div class="doc-info__row">
          <span>孕妇：{{ patientName }}</span>
          <span>孕周：{{ gestWeek }}</span>
          <span>日期：{{ signDate }}</span>
        </div>
        <div class="doc-info__row">
          <span>类型：{{ typeLabel }}</span>
          <span>来源：{{ sourceLabel }}</span>
        </div>
      </div>

      <div class="doc-section">
        <div class="doc-section__title">医嘱内容</div>
        <div class="doc-section__content">{{ content }}</div>
      </div>

      <div class="doc-warning">
        >>> 本医嘱经医生审核修改并手写签名确认 <<<
        >>> 如有疑问请咨询您的产检医生 <<<
      </div>

      <div class="doc-signature">
        <div class="doc-signature__box">
          <span class="doc-signature__label">医生签名：</span>
          <img v-if="signatureImage" :src="signatureImage" class="doc-signature__img" />
          <span v-else class="doc-signature__blank">__________________</span>
        </div>
        <div class="doc-signature__box">
          <span class="doc-signature__label">日期：</span>
          <span>{{ signDate }}</span>
        </div>
      </div>

      <div class="doc-footer">
        本记录由 AI-Care 孕期智能管理平台生成 | 打印日期：{{ printDate }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  patientName: string
  gestWeek: string
  content: string
  orderType?: string
  source?: string
  signatureImage?: string | null
}>()

const signDate = computed(() => new Date().toLocaleDateString('zh-CN'))
const printDate = computed(() => new Date().toLocaleDateString('zh-CN'))

const typeLabel = computed(() => {
  const map: Record<string, string> = { standard: '标准医嘱', custom: '自定义医嘱' }
  return map[props.orderType || ''] || props.orderType || '标准医嘱'
})

const sourceLabel = computed(() => {
  const map: Record<string, string> = { AI_RECOMMENDED: 'AI辅助生成', DOCTOR_WRITTEN: '医生手写' }
  return map[props.source || ''] || props.source || 'AI辅助生成'
})
</script>

<style scoped>
.order-print {
  max-width: 600px;
  margin: 0 auto;
}

.order-doc {
  background: #fff;
  padding: 12mm 10mm;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  font-family: 'SimSun', 'Noto Serif SC', serif;
  font-size: 14px;
  line-height: 2;
  color: #333;
}

.doc-header {
  text-align: center;
  margin-bottom: 16px;
}

.doc-header__brand {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}

.doc-header__title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 8px;
}

.doc-info {
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f8f9fa;
  border-radius: 4px;
}

.doc-info__row {
  display: flex;
  gap: 24px;
  font-size: 13px;
}

.doc-section {
  margin-bottom: 16px;
}

.doc-section__title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 2px solid #333;
}

.doc-section__content {
  font-size: 14px;
  line-height: 2;
  white-space: pre-wrap;
  padding: 8px 0;
}

.doc-warning {
  text-align: center;
  color: #d32f2f;
  font-weight: 700;
  font-size: 12px;
  line-height: 2.2;
  margin: 16px 0;
  padding: 8px 0;
  border-top: 1px dashed #d32f2f;
  border-bottom: 1px dashed #d32f2f;
}

.doc-signature {
  margin-top: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.doc-signature__box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-signature__label {
  font-size: 14px;
  font-weight: 600;
}

.doc-signature__img {
  max-width: 140px;
  max-height: 45px;
}

.doc-signature__blank {
  color: #999;
}

.doc-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 11px;
  color: #999;
  padding-top: 12px;
  border-top: 1px solid #eee;
}

/* 打印样式 */
@media print {
  .order-doc {
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
