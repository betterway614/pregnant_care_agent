<template>
  <div class="tool-action-bar" :class="`tool-action-bar--${role}`">
    <div class="tool-action-bar__row">
      <PatientSelectorCapsule
        :model-value="patientId"
        :patients="patients"
        :role="role"
        :placeholder="patientPlaceholder"
        :show-risk-tags="showRiskTags"
        @update:model-value="$emit('update:patientId', $event)"
      />
    </div>
    <div v-if="$slots.extra" class="tool-action-bar__row tool-action-bar__row--extra">
      <slot name="extra" />
    </div>
    <div v-if="sectionOptions?.length" class="tool-action-bar__row">
      <CapsuleChipGroup
        :model-value="activeSection"
        :options="sectionOptions"
        :role="role"
        scrollable
        @update:model-value="$emit('update:activeSection', $event)"
      />
    </div>
    <button
      type="button"
      class="tool-action-bar__action"
      :class="{ 'tool-action-bar__action--loading': loading }"
      :disabled="!patientId || loading"
      @click="$emit('action')"
    >
      <el-icon v-if="loading" class="is-loading" :size="16"><Loading /></el-icon>
      <el-icon v-else :size="16"><component :is="actionIcon" /></el-icon>
      <span>{{ actionLabel }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { MagicStick, Document, Loading } from '@element-plus/icons-vue'
import PatientSelectorCapsule from './PatientSelectorCapsule.vue'
import CapsuleChipGroup from './CapsuleChipGroup.vue'
import type { AgentRole, ChipOption } from '@/config/agentFabTools'
import type { Pregnant } from '@/types'

const props = withDefaults(defineProps<{
  patientId: string
  patients: Pregnant[]
  role: AgentRole
  loading?: boolean
  actionLabel?: string
  actionIconName?: 'magic' | 'document'
  patientPlaceholder?: string
  showRiskTags?: boolean
  sectionOptions?: ChipOption[]
  activeSection?: string
}>(), {
  loading: false,
  actionLabel: '开始分析',
  actionIconName: 'magic',
  patientPlaceholder: '选择孕妇',
  showRiskTags: false,
  activeSection: '',
})

defineEmits<{
  'update:patientId': [value: string]
  'update:activeSection': [value: string]
  action: []
}>()

const actionIcon = computed(() => props.actionIconName === 'document' ? Document : MagicStick)
</script>

<style scoped>
.tool-action-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.tool-action-bar__row--extra {
  display: flex;
  gap: 8px;
}

.tool-action-bar__action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  padding: 10px 20px;
  border: none;
  border-radius: var(--capsule-radius);
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.tool-action-bar--doctor .tool-action-bar__action {
  background: var(--doctor-accent-gradient);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
}

.tool-action-bar--nurse .tool-action-bar__action {
  background: var(--nurse-accent-gradient);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.tool-action-bar__action:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
}

.tool-action-bar__action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.tool-action-bar__action:focus-visible {
  outline: 2px solid var(--text-primary);
  outline-offset: 2px;
}

.tool-action-bar__action--loading {
  position: relative;
  overflow: hidden;
}

.tool-action-bar__action--loading::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .tool-action-bar__action {
    transition: none;
  }
  .tool-action-bar__action--loading::after {
    animation: none;
  }
}
</style>
