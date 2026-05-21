<template>
  <div class="patient-selector-capsule" :class="`patient-selector-capsule--${role}`">
    <el-select
      :model-value="modelValue"
      filterable
      :placeholder="placeholder"
      class="patient-selector-capsule__select"
      clearable
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option
        v-for="p in patients"
        :key="p.pregnant_id"
        :label="formatPatientLabel(p.display_name, p.gestational_age_days, showRiskTags ? p.risk_tags : undefined)"
        :value="p.pregnant_id"
      />
    </el-select>
  </div>
</template>

<script setup lang="ts">
import type { AgentRole } from '@/config/agentFabTools'
import { formatPatientLabel } from '@/config/agentFabTools'
import type { Pregnant } from '@/types'

withDefaults(defineProps<{
  modelValue: string
  patients: Pregnant[]
  role: AgentRole
  placeholder?: string
  showRiskTags?: boolean
}>(), {
  placeholder: '选择孕妇',
  showRiskTags: false,
})

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<style scoped>
.patient-selector-capsule__select {
  width: 100%;
}

.patient-selector-capsule :deep(.el-select__wrapper) {
  min-height: var(--capsule-min-height);
  border-radius: var(--capsule-radius);
  background: var(--capsule-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: var(--capsule-shadow);
  border: 1px solid var(--capsule-border);
  padding: 4px 12px;
}

.patient-selector-capsule--doctor :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

.patient-selector-capsule--nurse :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}
</style>
