<template>
  <div
    class="capsule-tab-bar"
    :class="`capsule-tab-bar--${role}`"
    role="tablist"
  >
    <button
      v-for="tab in tabs"
      :key="tab.name"
      type="button"
      role="tab"
      class="capsule-tab-bar__item"
      :class="{ 'capsule-tab-bar__item--active': modelValue === tab.name }"
      :aria-selected="modelValue === tab.name"
      @click="$emit('update:modelValue', tab.name)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import type { AgentRole, FabTab } from '@/config/agentFabTools'

defineProps<{
  tabs: FabTab[]
  modelValue: string
  role: AgentRole
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<style scoped>
.capsule-tab-bar {
  display: flex;
  gap: 4px;
  padding: 4px;
  margin: 8px 12px;
  background: var(--capsule-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--capsule-border);
  border-radius: var(--capsule-radius);
  box-shadow: var(--capsule-shadow);
}

.capsule-tab-bar__item {
  flex: 1;
  min-height: var(--capsule-min-height);
  padding: var(--capsule-padding-y) var(--capsule-padding-x);
  border: none;
  border-radius: var(--capsule-radius);
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), box-shadow var(--transition-fast);
  white-space: nowrap;
}

.capsule-tab-bar__item:hover:not(.capsule-tab-bar__item--active) {
  background: rgba(255, 255, 255, 0.5);
  color: var(--text-primary);
}

.capsule-tab-bar__item:focus-visible {
  outline: 2px solid var(--doctor-accent);
  outline-offset: 2px;
}

.capsule-tab-bar--nurse .capsule-tab-bar__item:focus-visible {
  outline-color: var(--nurse-accent);
}

.capsule-tab-bar--doctor .capsule-tab-bar__item--active {
  background: var(--doctor-accent-gradient);
  color: #fff;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
}

.capsule-tab-bar--nurse .capsule-tab-bar__item--active {
  background: var(--nurse-accent-gradient);
  color: #fff;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

@media (prefers-reduced-motion: reduce) {
  .capsule-tab-bar__item {
    transition: none;
  }
}
</style>
