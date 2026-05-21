<template>
  <div
    class="capsule-chip-group"
    :class="[
      `capsule-chip-group--${role}`,
      { 'capsule-chip-group--readonly': readonly, 'capsule-chip-group--scroll': scrollable },
    ]"
    role="group"
  >
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="capsule-chip"
      :class="{
        'capsule-chip--active': !readonly && modelValue === opt.value,
        'capsule-chip--readonly': readonly && modelValue === opt.value,
      }"
      :style="getChipStyle(opt)"
      :disabled="readonly && modelValue !== opt.value"
      @click="!readonly && $emit('update:modelValue', opt.value)"
    >
      <el-icon v-if="opt.icon && iconMap[opt.icon]" :size="14">
        <component :is="iconMap[opt.icon]" />
      </el-icon>
      <span>{{ opt.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import {
  Warning, TrendCharts, ChatDotRound, More, Calendar,
  DataAnalysis, Guide, FirstAidKit, Document, Reading,
} from '@element-plus/icons-vue'
import type { AgentRole, ChipOption } from '@/config/agentFabTools'

const props = defineProps<{
  options: ChipOption[]
  modelValue?: string
  role: AgentRole
  readonly?: boolean
  scrollable?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const iconMap: Record<string, any> = {
  Warning, TrendCharts, ChatDotRound, More, Calendar,
  DataAnalysis, Guide, FirstAidKit, Document, Reading,
}

function getChipStyle(opt: ChipOption) {
  if (!opt.color || props.readonly) return {}
  if (props.modelValue === opt.value) {
    return { '--chip-accent': opt.color }
  }
  return {}
}
</script>

<style scoped>
.capsule-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.capsule-chip-group--scroll {
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 2px;
}

.capsule-chip-group--scroll::-webkit-scrollbar {
  display: none;
}

.capsule-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: var(--capsule-min-height);
  padding: 6px var(--capsule-padding-x);
  border-radius: var(--capsule-radius);
  border: 1px solid var(--border);
  background: var(--capsule-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
  white-space: nowrap;
  flex-shrink: 0;
}

.capsule-chip:hover:not(:disabled) {
  background: var(--glass-bg-strong);
  color: var(--text-primary);
}

.capsule-chip:focus-visible {
  outline: 2px solid var(--doctor-accent);
  outline-offset: 2px;
}

.capsule-chip-group--nurse .capsule-chip:focus-visible {
  outline-color: var(--nurse-accent);
}

.capsule-chip-group--doctor .capsule-chip--active {
  border-color: var(--chip-accent, var(--doctor-accent));
  color: var(--chip-accent, var(--doctor-accent));
  background: color-mix(in srgb, var(--chip-accent, var(--doctor-accent)) 10%, transparent);
}

.capsule-chip-group--nurse .capsule-chip--active {
  border-color: var(--chip-accent, var(--nurse-accent));
  color: var(--chip-accent, var(--nurse-accent));
  background: color-mix(in srgb, var(--chip-accent, var(--nurse-accent)) 10%, transparent);
}

.capsule-chip--readonly {
  cursor: default;
  opacity: 0.85;
}

.capsule-chip-group--doctor .capsule-chip--readonly {
  background: var(--doctor-accent-bg);
  border-color: rgba(16, 185, 129, 0.2);
  color: var(--doctor-accent);
}

.capsule-chip-group--nurse .capsule-chip--readonly {
  background: var(--nurse-accent-bg);
  border-color: rgba(99, 102, 241, 0.2);
  color: var(--nurse-accent);
}

@media (prefers-reduced-motion: reduce) {
  .capsule-chip {
    transition: none;
  }
}
</style>
