<template>
  <div class="report-form-capsule" :class="`report-form-capsule--${role}`">
    <div v-if="showSuccess" class="report-form-capsule__banner">
      问题已成功上报给医生
    </div>

    <div class="report-form-capsule__section">
      <label class="report-form-capsule__label">问题类型</label>
      <CapsuleChipGroup
        :model-value="modelValue.issue_type"
        :options="issueTypeOptions"
        :role="role"
        @update:model-value="updateField('issue_type', $event)"
      />
    </div>

    <div class="report-form-capsule__section">
      <label class="report-form-capsule__label">优先级</label>
      <CapsuleChipGroup
        :model-value="modelValue.priority"
        :options="priorityOptions"
        :role="role"
        @update:model-value="updateField('priority', $event)"
      />
    </div>

    <div class="report-form-capsule__section">
      <label class="report-form-capsule__label" for="report-title">问题标题</label>
      <div class="report-form-capsule__input-wrap">
        <input
          id="report-title"
          :value="modelValue.title"
          class="report-form-capsule__input"
          placeholder="简要描述问题"
          @input="updateField('title', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>

    <div class="report-form-capsule__section">
      <label class="report-form-capsule__label" for="report-desc">详细描述</label>
      <div class="report-form-capsule__input-wrap">
        <textarea
          id="report-desc"
          :value="modelValue.description"
          class="report-form-capsule__textarea"
          rows="3"
          placeholder="详细描述问题情况"
          @input="updateField('description', ($event.target as HTMLTextAreaElement).value)"
        />
      </div>
    </div>

    <button
      type="button"
      class="report-form-capsule__submit"
      :disabled="loading"
      @click="$emit('submit')"
    >
      <el-icon v-if="loading" class="is-loading" :size="16"><Loading /></el-icon>
      <span>{{ loading ? '上报中...' : '上报给医生' }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'
import CapsuleChipGroup from './CapsuleChipGroup.vue'
import { NURSE_REPORT_ISSUE_TYPES, PRIORITY_OPTIONS } from '@/config/agentFabTools'
import type { AgentRole } from '@/config/agentFabTools'

export interface ReportFormData {
  issue_type: string
  priority: string
  title: string
  description: string
}

const props = defineProps<{
  modelValue: ReportFormData
  role: AgentRole
  loading?: boolean
  showSuccess?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ReportFormData]
  submit: []
}>()

const issueTypeOptions = NURSE_REPORT_ISSUE_TYPES
const priorityOptions = PRIORITY_OPTIONS

function updateField<K extends keyof ReportFormData>(key: K, value: ReportFormData[K]) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped>
.report-form-capsule {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.report-form-capsule__banner {
  padding: 10px 14px;
  border-radius: var(--capsule-radius);
  background: var(--success-light);
  color: var(--success);
  font-size: 13px;
  font-weight: 600;
  text-align: center;
}

.report-form-capsule__label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.report-form-capsule__input-wrap {
  background: var(--capsule-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--capsule-border);
  border-radius: var(--radius);
  padding: 2px;
  box-shadow: var(--capsule-shadow);
}

.report-form-capsule__input,
.report-form-capsule__textarea {
  width: 100%;
  border: none;
  background: transparent;
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-primary);
  outline: none;
  resize: vertical;
}

.report-form-capsule__input::placeholder,
.report-form-capsule__textarea::placeholder {
  color: var(--text-muted);
}

.report-form-capsule__submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  margin-top: 4px;
  border: none;
  border-radius: var(--capsule-radius);
  background: var(--nurse-accent-gradient);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
  transition: opacity var(--transition-fast);
}

.report-form-capsule__submit:hover:not(:disabled) {
  opacity: 0.92;
}

.report-form-capsule__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.report-form-capsule__submit:focus-visible {
  outline: 2px solid var(--nurse-accent);
  outline-offset: 2px;
}
</style>
