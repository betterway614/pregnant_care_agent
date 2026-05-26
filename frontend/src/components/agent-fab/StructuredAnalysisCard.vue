<template>
  <div class="structured-card" :class="`structured-card--${role}`">
    <!-- 风险摘要 -->
    <div v-if="data.risk_summary" class="structured-card__section structured-card__risk">
      <div class="structured-card__risk-bar" />
      <div class="structured-card__risk-body">
        <div class="structured-card__section-label">
          <el-icon :size="14"><WarningFilled /></el-icon>
          风险摘要
        </div>
        <p class="structured-card__risk-text">{{ data.risk_summary }}</p>
      </div>
    </div>

    <!-- 综合分析 -->
    <div v-if="data.analysis" class="structured-card__section">
      <div class="structured-card__section-label">
        <el-icon :size="14"><DataAnalysis /></el-icon>
        综合分析
      </div>
      <div class="structured-card__md" v-html="renderMarkdown(data.analysis)" />
    </div>

    <!-- 推理链 -->
    <div v-if="data.reasoning_chain?.length" class="structured-card__section">
      <div class="structured-card__section-label">
        <el-icon :size="14"><Guide /></el-icon>
        推理链
      </div>
      <div class="reasoning-steps">
        <div
          v-for="(step, idx) in data.reasoning_chain"
          :key="idx"
          class="reasoning-step"
        >
          <span class="reasoning-step__num">{{ idx + 1 }}</span>
          <span class="reasoning-step__text">{{ step }}</span>
        </div>
      </div>
    </div>

    <!-- 建议医嘱 -->
    <div v-if="data.suggested_orders" class="structured-card__section">
      <div class="structured-card__section-label">
        <el-icon :size="14"><Document /></el-icon>
        建议医嘱
      </div>
      <div class="structured-card__md" v-html="renderMarkdown(data.suggested_orders)" />
    </div>

    <!-- 证据引用 -->
    <div v-if="data.evidence_references?.length" class="structured-card__section">
      <div class="structured-card__section-label">
        <el-icon :size="14"><Reading /></el-icon>
        循证参考
      </div>
      <div class="evidence-tags">
        <span
          v-for="(ref, idx) in data.evidence_references"
          :key="idx"
          class="evidence-tag"
        >{{ ref }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled, FirstAidKit, DataAnalysis, Guide, Document, Reading } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'
import type { StructuredAnalysis } from '@/utils/markdown'

defineProps<{
  data: StructuredAnalysis
  role: 'doctor' | 'nurse' | 'pregnant'
}>()
</script>

<style scoped>
.structured-card {
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 14px;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.6;
}

.structured-card__section {
  padding: 10px 14px;
}

.structured-card__section + .structured-card__section {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.structured-card__section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 12px;
  color: #475569;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ---- 风险摘要 ---- */
.structured-card__risk {
  display: flex;
  gap: 0;
  padding: 0;
}

.structured-card__risk-bar {
  width: 4px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #ef4444, #f97316);
  border-radius: 4px 0 0 4px;
}

.structured-card__risk-body {
  padding: 10px 14px;
  flex: 1;
}

.structured-card__risk-body .structured-card__section-label {
  color: #dc2626;
}

.structured-card__risk-text {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #991b1b;
  line-height: 1.5;
}

/* ---- 推理链 ---- */
.reasoning-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reasoning-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.reasoning-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  border-radius: 8px;
  background: #e2e8f0;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.structured-card--doctor .reasoning-step__num {
  background: linear-gradient(135deg, #34d399, #10b981);
  color: #fff;
}

.structured-card--nurse .reasoning-step__num {
  background: linear-gradient(135deg, #818cf8, #6366f1);
  color: #fff;
}

.structured-card--pregnant .reasoning-step__num {
  background: linear-gradient(135deg, #fb7185, #e11d48);
  color: #fff;
}

.reasoning-step__text {
  font-size: 12px;
  color: #475569;
  padding-top: 2px;
  line-height: 1.5;
}

/* ---- 证据标签 ---- */
.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.evidence-tag {
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  font-size: 11px;
  color: #2563eb;
  line-height: 1.4;
}

/* ---- Markdown 内容区 ---- */
.structured-card__md :deep(p) {
  margin: 0 0 6px;
}

.structured-card__md :deep(p:last-child) {
  margin-bottom: 0;
}

.structured-card__md :deep(strong) {
  font-weight: 600;
}

.structured-card__md :deep(ul),
.structured-card__md :deep(ol) {
  padding-left: 18px;
  margin: 4px 0;
}

.structured-card__md :deep(li) {
  margin: 2px 0;
}
</style>
