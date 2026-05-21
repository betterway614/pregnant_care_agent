<template>
  <div
    class="issue-card"
    :class="`issue-card--${role}`"
    :style="{ '--priority-color': priorityColor }"
  >
    <div class="issue-card__accent" />
    <div class="issue-card__content">
      <div class="issue-card__header">
        <span class="issue-card__priority-capsule">{{ priorityLabel }}</span>
        <span class="issue-card__time">{{ time }}</span>
      </div>
      <div class="issue-card__title">{{ title }}</div>
      <div class="issue-card__desc">{{ description }}</div>
      <div class="issue-card__footer">
        <span class="issue-card__patient">{{ patientName }}</span>
        <button
          v-if="status === 'pending'"
          type="button"
          class="issue-card__action"
          @click="$emit('resolve')"
        >
          处理
        </button>
        <span v-else class="issue-card__resolved">已处理</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentRole } from '@/config/agentFabTools'
import { PRIORITY_LABELS, PRIORITY_COLORS } from '@/config/agentFabTools'

const props = defineProps<{
  title: string
  description: string
  patientName?: string
  priority: string
  status: string
  time?: string
  role?: AgentRole
}>()

defineEmits<{ resolve: [] }>()

const priorityLabel = computed(() => PRIORITY_LABELS[props.priority] || '中')
const priorityColor = computed(() => PRIORITY_COLORS[props.priority] || PRIORITY_COLORS.medium)
</script>

<style scoped>
.issue-card {
  display: flex;
  margin-bottom: 10px;
  border-radius: var(--radius);
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--glass-border);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}

.issue-card__accent {
  width: 4px;
  flex-shrink: 0;
  background: var(--priority-color);
}

.issue-card__content {
  flex: 1;
  padding: 12px 14px;
  min-width: 0;
}

.issue-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.issue-card__priority-capsule {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 10px;
  border-radius: var(--capsule-radius);
  font-size: 11px;
  font-weight: 700;
  color: var(--priority-color);
  background: color-mix(in srgb, var(--priority-color) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--priority-color) 25%, transparent);
}

.issue-card__time {
  font-size: 11px;
  color: var(--text-muted);
}

.issue-card__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.issue-card__desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 10px;
}

.issue-card__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.issue-card__patient {
  font-size: 12px;
  color: var(--text-muted);
}

.issue-card__action {
  min-height: 32px;
  padding: 4px 16px;
  border-radius: var(--capsule-radius);
  border: 1.5px solid var(--doctor-accent);
  background: transparent;
  color: var(--doctor-accent);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.issue-card__action:hover {
  background: var(--doctor-accent-bg);
}

.issue-card__action:focus-visible {
  outline: 2px solid var(--doctor-accent);
  outline-offset: 2px;
}

.issue-card__resolved {
  font-size: 12px;
  font-weight: 600;
  color: var(--success);
  padding: 4px 10px;
  border-radius: var(--capsule-radius);
  background: var(--success-light);
}
</style>
