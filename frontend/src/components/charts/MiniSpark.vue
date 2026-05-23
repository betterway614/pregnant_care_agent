<template>
  <svg :width="width" :height="height" class="mini-spark">
    <!-- 正常范围背景 -->
    <rect
      v-if="low != null && high != null && yRange"
      :x="0"
      :y="yScale(high)"
      :width="width"
      :height="yScale(low) - yScale(high)"
      fill="rgba(76, 175, 80, 0.08)"
    />
    <!-- 趋势线 -->
    <polyline
      v-if="points.length >= 2"
      :points="linePath"
      fill="none"
      :stroke="lineColor"
      stroke-width="1.5"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
    <!-- 数据点 -->
    <circle
      v-for="(pt, i) in numericPoints"
      :key="i"
      :cx="xScale(i)"
      :cy="yScale(pt)"
      :r="2"
      :fill="lineColor"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LabTrendDataPoint } from '@/types'

const props = withDefaults(defineProps<{
  points: LabTrendDataPoint[]
  low?: number | null
  high?: number | null
  width?: number
  height?: number
}>(), {
  width: 70,
  height: 24,
  low: null,
  high: null,
})

const numericPoints = computed(() =>
  props.points.filter(p => p.value != null).map(p => p.value as number)
)

const yRange = computed(() => {
  const vals = numericPoints.value
  if (!vals.length) return null
  let min = Math.min(...vals)
  let max = Math.max(...vals)
  if (props.low != null) min = Math.min(min, props.low)
  if (props.high != null) max = Math.max(max, props.high)
  if (max === min) { min -= 1; max += 1 }
  return { min, max }
})

function xScale(i: number): number {
  const n = numericPoints.value.length
  if (n <= 1) return props.width / 2
  return (i / (n - 1)) * (props.width - 4) + 2
}

function yScale(val: number): number {
  if (!yRange.value) return props.height / 2
  const { min, max } = yRange.value
  return props.height - 2 - ((val - min) / (max - min)) * (props.height - 4)
}

const linePath = computed(() =>
  numericPoints.value.map((v, i) => `${xScale(i)},${yScale(v)}`).join(' ')
)

const lineColor = computed(() => {
  if (numericPoints.value.length === 0) return '#909399'
  const last = numericPoints.value[numericPoints.value.length - 1]
  if (props.low != null && last < props.low) return '#e6a23c'
  if (props.high != null && last > props.high) return '#f56c6c'
  return '#409eff'
})
</script>

<style scoped>
.mini-spark {
  display: block;
}
</style>
