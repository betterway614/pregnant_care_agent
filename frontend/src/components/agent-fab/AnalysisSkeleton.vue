<template>
  <div class="analysis-skeleton" :class="`analysis-skeleton--${role}`">
    <div v-for="i in count" :key="i" class="analysis-skeleton__card">
      <div class="analysis-skeleton__header">
        <div class="analysis-skeleton__bar analysis-skeleton__bar--short" />
        <div class="analysis-skeleton__bar analysis-skeleton__bar--title" />
      </div>
      <div class="analysis-skeleton__body">
        <div class="analysis-skeleton__bar" />
        <div class="analysis-skeleton__bar analysis-skeleton__bar--medium" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentRole } from '@/config/agentFabTools'

withDefaults(defineProps<{
  role: AgentRole
  count?: number
}>(), {
  count: 3,
})
</script>

<style scoped>
.analysis-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.analysis-skeleton__card {
  background: var(--glass-bg);
  border-radius: var(--radius);
  border: 1px solid var(--glass-border);
  padding: 14px;
}

.analysis-skeleton__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.analysis-skeleton__bar {
  height: 12px;
  border-radius: var(--capsule-radius);
  background: linear-gradient(90deg, var(--bg-surface) 25%, rgba(255,255,255,0.8) 50%, var(--bg-surface) 75%);
  background-size: 200% 100%;
  animation: skeletonPulse 1.5s ease-in-out infinite;
}

.analysis-skeleton__bar--short {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
}

.analysis-skeleton__bar--title {
  width: 40%;
  height: 14px;
}

.analysis-skeleton__bar--medium {
  width: 70%;
}

.analysis-skeleton__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.analysis-skeleton--doctor .analysis-skeleton__bar {
  background: linear-gradient(90deg, var(--doctor-accent-bg) 25%, rgba(255,255,255,0.6) 50%, var(--doctor-accent-bg) 75%);
  background-size: 200% 100%;
}

.analysis-skeleton--nurse .analysis-skeleton__bar {
  background: linear-gradient(90deg, var(--nurse-accent-bg) 25%, rgba(255,255,255,0.6) 50%, var(--nurse-accent-bg) 75%);
  background-size: 200% 100%;
}

@keyframes skeletonPulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .analysis-skeleton__bar {
    animation: none;
    background: var(--bg-surface);
  }
}
</style>
