<template>
  <span class="risk-badge" :class="[`risk-badge--${level}`, { 'risk-badge--dot': dot }]">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  level: string
  dot?: boolean
}>()

const labelMap: Record<string, string> = {
  RED: '红色高危',
  ORANGE: '橙色预警',
  YELLOW: '黄色关注',
  GREEN: '正常',
  high: '高风险',
  medium: '中风险',
  low: '低风险',
  critical: '极高风险',
}

const label = computed(() => labelMap[props.level] || props.level)
</script>
