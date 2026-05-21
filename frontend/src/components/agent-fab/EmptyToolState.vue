<template>
  <div
    class="empty-tool-state"
    :class="`empty-tool-state--${role}`"
  >
    <div class="empty-tool-state__icon">
      <el-icon :size="40" color="var(--text-muted)">
        <component :is="icon" />
      </el-icon>
    </div>
    <p class="empty-tool-state__text">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import type { AgentRole } from '@/config/agentFabTools'

defineProps<{
  icon: Component
  message: string
  role: AgentRole
}>()
</script>

<style scoped>
.empty-tool-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  padding: 24px;
  text-align: center;
}

.empty-tool-state__icon {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--capsule-bg);
  border: 1px solid var(--capsule-border);
  box-shadow: var(--capsule-shadow);
}

.empty-tool-state--doctor .empty-tool-state__icon {
  background: var(--doctor-accent-bg);
}

.empty-tool-state--nurse .empty-tool-state__icon {
  background: var(--nurse-accent-bg);
}

.empty-tool-state__text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted);
  max-width: 280px;
}
</style>
