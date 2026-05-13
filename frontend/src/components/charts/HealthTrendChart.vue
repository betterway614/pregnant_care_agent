<template>
  <div class="health-trend-chart" :style="{ height: height + 'px' }">
    <div v-if="!series.length" class="chart-empty">
      <el-empty description="暂无数据" :image-size="80" />
    </div>
    <v-chart
      v-else
      ref="chartRef"
      :option="chartOption"
      :autoresize="true"
      @click="handleClick"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { TrendSeries } from '@/types'

const props = withDefaults(defineProps<{
  series: TrendSeries[]
  axisMode?: 'date' | 'gest_week'
  showNormalRange?: boolean
  interactive?: boolean
  height?: number
}>(), {
  axisMode: 'date',
  showNormalRange: true,
  interactive: true,
  height: 400,
})

const emit = defineEmits<{
  'point-click': [data: { metric: string; date: string; value: number }]
  'range-change': [range: { startDate: string; endDate: string }]
}>()

const chartRef = ref()

// 指标颜色映射
const METRIC_COLORS: Record<string, string> = {
  weight: '#8B5CF6',
  systolic: '#EF4444',
  diastolic: '#F97316',
  blood_sugar_fasting: '#EC4899',
  blood_sugar_postprandial: '#F472B6',
  fetal_movement: '#06B6D4',
  heart_rate: '#10B981',
  sleep_hours: '#6366F1',
  steps: '#F59E0B',
  emotion_score: '#8B5CF6',
}

// 需要双线组合的指标对
const BP_METRICS = ['systolic', 'diastolic']
const SUGAR_METRICS = ['blood_sugar_fasting', 'blood_sugar_postprandial']

function getAxisData(s: TrendSeries): string[] {
  return s.data.map(d => props.axisMode === 'gest_week' ? `孕${d.gest_week}周` : d.date)
}

const chartOption = computed(() => {
  const sList = props.series
  if (!sList.length) return {}

  // 判断是否为血压或血糖组合
  const metricCodes = sList.map(s => s.metric)
  const isBP = BP_METRICS.every(m => metricCodes.includes(m))
  const isSugar = SUGAR_METRICS.every(m => metricCodes.includes(m))
  const isCombo = isBP || isSugar

  if (isCombo) {
    return buildComboOption(sList, isBP)
  }

  // 单指标或多指标独立图表（grid 叠加）
  return buildSingleOption(sList)
})

function buildComboOption(sList: TrendSeries[], isBP: boolean) {
  const primary = sList.find(s => s.metric === (isBP ? 'systolic' : 'blood_sugar_fasting'))!
  const secondary = sList.find(s => s.metric === (isBP ? 'diastolic' : 'blood_sugar_postprandial'))!
  const xAxisData = getAxisData(primary)
  const markAreaData = buildMarkArea(primary, isBP)

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: [primary.name, secondary.name], bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      name: primary.unit,
      min: (val: any) => Math.floor(val.min * 0.9),
      max: (val: any) => Math.ceil(val.max * 1.1),
    },
    series: [
      buildLineSeries(primary, markAreaData),
      buildLineSeries(secondary),
    ],
  }
}

function buildSingleOption(sList: TrendSeries[]) {
  // 单指标
  if (sList.length === 1) {
    const s = sList[0]
    const xAxisData = getAxisData(s)
    const markAreaData = buildMarkArea(s, false)
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
      },
      yAxis: {
        type: 'value',
        name: s.unit,
        min: (val: any) => Math.floor(val.min * 0.9),
        max: (val: any) => Math.ceil(val.max * 1.1),
      },
      series: [buildLineSeries(s, markAreaData)],
    }
  }

  // 多指标：使用多 Y 轴
  const first = sList[0]
  const xAxisData = getAxisData(first)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: sList.map(s => s.name), bottom: 0 },
    grid: { left: 50, right: 50, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
    },
    yAxis: sList.map((s, i) => ({
      type: 'value',
      name: s.unit,
      position: i % 2 === 0 ? 'left' : 'right',
    })),
    series: sList.map((s, i) => ({
      ...buildLineSeries(s),
      yAxisIndex: i,
    })),
  }
}

function buildLineSeries(s: TrendSeries, markArea?: any[]) {
  return {
    name: s.name,
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    data: s.data.map(d => d.value),
    itemStyle: { color: METRIC_COLORS[s.metric] || '#409EFF' },
    lineStyle: { width: 2 },
    areaStyle: { opacity: 0.05 },
    markArea: markArea && markArea.length ? { data: markArea } : undefined,
    markLine: s.normal_range.min != null ? {
      silent: true,
      data: [
        { yAxis: s.normal_range.max, lineStyle: { color: '#E6A23C', type: 'dashed' } },
        ...(s.metric !== 'blood_sugar_postprandial' ? [{ yAxis: s.normal_range.min, lineStyle: { color: '#E6A23C', type: 'dashed' } }] : []),
      ],
    } : undefined,
  }
}

function buildMarkArea(s: TrendSeries, isBP: boolean): any[] {
  if (!props.showNormalRange) return []
  if (!s.normal_range || s.normal_range.min == null) return []

  // 血压特殊：只标异常区域
  if (isBP) {
    if (s.metric === 'systolic') {
      return [[
        { yAxis: 140, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } },
        { yAxis: 200 },
      ]]
    }
    return [[
      { yAxis: 90, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } },
      { yAxis: 150 },
    ]]
  }

  // 通用：正常范围区域
  return [[
    { yAxis: s.normal_range.min, itemStyle: { color: 'rgba(16, 185, 129, 0.06)' } },
    { yAxis: s.normal_range.max },
  ]]
}

function handleClick(params: any) {
  if (!props.interactive || !params.data) return
  const seriesIdx = params.seriesIndex || 0
  const dataIdx = params.dataIndex
  const s = props.series[seriesIdx]
  if (s && s.data[dataIdx]) {
    emit('point-click', {
      metric: s.metric,
      date: s.data[dataIdx].date,
      value: s.data[dataIdx].value,
    })
  }
}

/** 外部调用：跳转到指定日期范围 */
function zoomToRange(startDate: string, endDate: string) {
  emit('range-change', { startDate, endDate })
}

defineExpose({ zoomToRange })
</script>

<style scoped>
.health-trend-chart {
  width: 100%;
  min-height: 200px;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
