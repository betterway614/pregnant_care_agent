<template>
  <div
    class="analysis-result-card"
    :class="[
      `analysis-result-card--${role}`,
      `analysis-result-card--${severity}`,
      { 'analysis-result-card--collapsed': collapsible && !expanded },
    ]"
    :id="sectionId"
  >
    <button
      type="button"
      class="analysis-result-card__header"
      :aria-expanded="expanded"
      @click="collapsible && toggle()"
    >
      <div class="analysis-result-card__accent" />
      <el-icon v-if="iconComponent" :size="16" class="analysis-result-card__icon">
        <component :is="iconComponent" />
      </el-icon>
      <span class="analysis-result-card__title">{{ title }}</span>
      <el-icon v-if="collapsible" :size="14" class="analysis-result-card__chevron">
        <ArrowDown v-if="expanded" />
        <ArrowRight v-else />
      </el-icon>
    </button>
    <div v-show="!collapsible || expanded" class="analysis-result-card__body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Warning, DataAnalysis, Guide, FirstAidKit, Document, Reading, Calendar,
  ArrowDown, ArrowRight,
} from '@element-plus/icons-vue'
import type { AgentRole, Severity } from '@/config/agentFabTools'

const props = withDefaults(defineProps<{
  title: string
  severity?: Severity
  icon?: string
  role: AgentRole
  collapsible?: boolean
  defaultExpanded?: boolean
  sectionId?: string
}>(), {
  severity: 'info',
  collapsible: true,
  defaultExpanded: false,
})

const expanded = ref(props.defaultExpanded)

watch(() => props.defaultExpanded, (val) => {
  expanded.value = val
})

const iconMap: Record<string, any> = {
  Warning, DataAnalysis, Guide, FirstAidKit, Document, Reading, Calendar,
}

const iconComponent = computed(() => props.icon ? iconMap[props.icon] : null)

function toggle() {
  expanded.value = !expanded.value
}

defineExpose({ expanded })
</script>

<style scoped>
.analysis-result-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-radius: var(--radius);
  border: 1px solid var(--glass-border);
  margin-bottom: 10px;
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}

.analysis-result-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px 14px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  position: relative;
  min-height: var(--capsule-min-height);
}

.analysis-result-card__accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
}

.analysis-result-card--danger .analysis-result-card__accent { background: var(--danger); }
.analysis-result-card--warning .analysis-result-card__accent { background: var(--warning); }
.analysis-result-card--info .analysis-result-card__accent { background: var(--info); }
.analysis-result-card--success .analysis-result-card__accent { background: var(--success); }

.analysis-result-card__icon {
  margin-left: 6px;
  flex-shrink: 0;
}

.analysis-result-card--danger .analysis-result-card__icon { color: var(--danger); }
.analysis-result-card--warning .analysis-result-card__icon { color: var(--warning); }
.analysis-result-card--info .analysis-result-card__icon { color: var(--info); }
.analysis-result-card--success .analysis-result-card__icon { color: var(--success); }

.analysis-result-card__title {
  flex: 1;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.analysis-result-card__chevron {
  color: var(--text-muted);
  flex-shrink: 0;
}

.analysis-result-card__body {
  padding: 0 14px 14px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.analysis-result-card__header:focus-visible {
  outline: 2px solid var(--doctor-accent);
  outline-offset: -2px;
}

.analysis-result-card--nurse .analysis-result-card__header:focus-visible {
  outline-color: var(--nurse-accent);
}
</style>
