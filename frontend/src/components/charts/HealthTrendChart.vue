<template>
  <div class="health-trend-chart" :style="{ height: height + 'px' }">
    <div v-if="!series.length" class="chart-empty">
      <el-empty description="暂无数据" :image-size="80" />
    </div>
    <v-chart
      v-else
      ref="chartRef"
      :option="INIT_OPTION"
      :autoresize="true"
      manual-update
      @click="handleClick"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
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

// 初始空 option，仅用于首次渲染
const INIT_OPTION = {}

// 稳定的函数引用
function axisMin(val: any) { return Math.floor(val.min * 0.9) }
function axisMax(val: any) { return Math.ceil(val.max * 1.1) }

const METRIC_COLORS: Record<string, string> = {
  // 健康趋势指标
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
  // 化验指标
  hemoglobin_g_L: '#DC2626',
  alt: '#EA580C',
  ast: '#F59E0B',
  creatinine: '#10B981',
  albumin: '#8B5CF6',
  uric_acid: '#06B6D4',
  wbc: '#EC4899',
  platelet: '#6366F1',
  hct: '#F472B6',
  bilirubin_total: '#84CC16',
}

const BP_METRICS = ['systolic', 'diastolic']
const SUGAR_METRICS = ['blood_sugar_fasting', 'blood_sugar_postprandial']

function getAxisData(s: TrendSeries): string[] {
  return s.data.map(d => props.axisMode === 'gest_week' ? `孕${d.gest_week}周` : d.date)
}

// 简化日期显示格式 - 只显示月/日
function formatDateLabel(dateStr: string): string {
  if (!dateStr) return ''
  const parts = dateStr.split('-')
  if (parts.length >= 3) {
    return `${parts[1]}/${parts[2]}`
  }
  return dateStr
}

// 计算标签显示间隔 - 根据数据点数量动态调整
function calculateInterval(dataLength: number): number {
  if (dataLength <= 7) return 0  // 7个以内显示全部
  if (dataLength <= 14) return 1  // 14个以内隔一个显示
  if (dataLength <= 30) return 2  // 30个以内隔两个显示
  return Math.floor(dataLength / 10)  // 更多数据时动态计算
}

function buildOption() {
  const sList = props.series
  if (!sList.length) return {}

  const metricCodes = sList.map(s => s.metric)

  // ── 检测配对组 ──
  // 血压对：当收缩压和舒张压同时存在时，配对为 combo
  const hasBP = BP_METRICS.every(m => metricCodes.includes(m))
  // 血糖对：当空腹血糖和餐后血糖同时存在时，配对为 combo
  const hasSugar = SUGAR_METRICS.every(m => metricCodes.includes(m))

  // 只有配对指标时，使用 combo chart
  const nonBPMetrics = sList.filter(s => !BP_METRICS.includes(s.metric) && !SUGAR_METRICS.includes(s.metric))
  const onlyComboMetrics = nonBPMetrics.length === 0

  if (onlyComboMetrics) {
    if (hasBP) return buildComboOption(sList, true)
    if (hasSugar) return buildComboOption(sList, false)
  }

  // 有混合指标时，使用智能分组多轴模式
  return buildMixedOption(sList, hasBP, hasSugar)
}

function buildComboOption(sList: TrendSeries[], isBP: boolean) {
  const primary = sList.find(s => s.metric === (isBP ? 'systolic' : 'blood_sugar_fasting'))!
  const secondary = sList.find(s => s.metric === (isBP ? 'diastolic' : 'blood_sugar_postprandial'))!
  const xAxisData = getAxisData(primary)
  const markAreaData = buildMarkArea(primary, isBP)
  const interval = calculateInterval(xAxisData.length)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: { backgroundColor: '#6a7985' },
        lineStyle: { color: '#E4E7ED', type: 'dashed' },
      },
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#E4E7ED',
      textStyle: { color: '#303133', fontSize: 12 },
    },
    legend: {
      data: [primary.name, secondary.name],
      top: 0,
      left: 'center',
      itemWidth: 16,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#606266' },
    },
    grid: { left: 60, right: 30, top: 40, bottom: 50, containLabel: false },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: {
        interval,
        fontSize: 11,
        color: '#909399',
        formatter: formatDateLabel,
      },
      axisLine: { lineStyle: { color: '#E4E7ED' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: primary.unit,
      min: axisMin,
      max: axisMax,
      nameTextStyle: { fontSize: 11, color: '#909399' },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#F2F6FC', type: 'dashed' } },
    },
    series: [buildLineSeries(primary, markAreaData), buildLineSeries(secondary)],
  }
}

function buildMixedOption(sList: TrendSeries[], hasBP: boolean, hasSugar: boolean) {
  if (sList.length === 1) {
    const s = sList[0]
    const xAxisData = getAxisData(s)
    const markAreaData = buildMarkArea(s, false)
    const interval = calculateInterval(xAxisData.length)
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          label: { backgroundColor: '#6a7985' },
          lineStyle: { color: '#E4E7ED', type: 'dashed' },
        },
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#E4E7ED',
        textStyle: { color: '#303133', fontSize: 12 },
      },
      grid: { left: 60, right: 30, top: 30, bottom: 50, containLabel: false },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLabel: {
          interval,
          fontSize: 11,
          color: '#909399',
          formatter: formatDateLabel,
        },
        axisLine: { lineStyle: { color: '#E4E7ED' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        name: s.unit,
        min: axisMin,
        max: axisMax,
        nameTextStyle: { fontSize: 11, color: '#909399' },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#F2F6FC', type: 'dashed' } },
      },
      series: [buildLineSeries(s, markAreaData)],
    }
  }

  const first = sList[0]
  const xAxisData = getAxisData(first)
  const interval = calculateInterval(xAxisData.length)

  // ── 按单位分组：相同单位的指标共享一个 Y 轴，最多 left/right 两个轴 ──
  // 超过 2 种单位时，只取出现频率最高的 2 组，其余指标归入"其他"轴
  const unitGroups = new Map<string, TrendSeries[]>()
  for (const s of sList) {
    const key = s.unit || '_no_unit'
    if (!unitGroups.has(key)) unitGroups.set(key, [])
    unitGroups.get(key)!.push(s)
  }
  // 按组内指标数降序排列，最多保留 2 组
  const sortedUnits = [...unitGroups.entries()].sort((a, b) => b[1].length - a[1].length)
  const primaryUnits = sortedUnits.slice(0, 2)
  const overflowUnits = sortedUnits.slice(2)
  // 超出的指标合并到最近的主轴（按单位相似度或默认左轴）
  if (overflowUnits.length > 0) {
    const fallbackGroup = primaryUnits[0] // 归入第一组（左轴）
    for (const [, overflowSeries] of overflowUnits) {
      fallbackGroup[1].push(...overflowSeries)
    }
  }

  const yAxisDefs: any[] = []
  const unitToAxisIdx = new Map<string, number>()
  let axisIdx = 0
  for (const [unit, group] of primaryUnits) {
    // 计算该组的全局 min/max，让同单位指标共享刻度
    const allVals = group.flatMap(s => s.data.map(d => d.value))
    const groupMin = allVals.length ? Math.floor(Math.min(...allVals) * 0.9) : 0
    const groupMax = allVals.length ? Math.ceil(Math.max(...allVals) * 1.1) : 100
    yAxisDefs.push({
      type: 'value',
      name: unit === '_no_unit' ? '' : unit,
      position: axisIdx % 2 === 0 ? 'left' : 'right',
      min: groupMin,
      max: groupMax,
      nameTextStyle: { fontSize: 11, color: '#909399', padding: axisIdx % 2 === 0 ? [0, 40, 0, 0] : [0, 0, 0, 40] },
      axisLine: { show: false },
      // 只在第一个轴显示分割线，避免多轴时线条重叠
      splitLine: axisIdx === 0 ? { lineStyle: { color: '#F2F6FC', type: 'dashed' } } : { show: false },
    })
    unitToAxisIdx.set(unit, axisIdx)
    axisIdx++
  }
  // 超出的指标映射到第一轴，并记录溢出指标名称供提示
  for (const [unit] of overflowUnits) {
    unitToAxisIdx.set(unit, 0)
  }
  const overflowNames = overflowUnits.flatMap(([, series]) => series.map(s => s.name))
  if (overflowNames.length > 0) {
    console.warn(`[HealthTrendChart] 指标单位过多，以下指标已合并到左轴显示：${overflowNames.join('、')}`)
  }

  // 只有 1 个 Y 轴时去掉 name 避免重复显示单位（tooltip 已有）
  if (yAxisDefs.length === 1) {
    yAxisDefs[0].name = ''
  }

  const series = sList.map(s => {
    const unitKey = s.unit || '_no_unit'
    return { ...buildLineSeries(s), yAxisIndex: unitToAxisIdx.get(unitKey)! }
  })

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: { backgroundColor: '#6a7985' },
        lineStyle: { color: '#E4E7ED', type: 'dashed' },
      },
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#E4E7ED',
      textStyle: { color: '#303133', fontSize: 12 },
    },
    legend: {
      data: sList.map(s => s.name),
      top: 0,
      left: 'center',
      itemWidth: 16,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#606266' },
    },
    grid: { left: 60, right: 60, top: 40, bottom: 50, containLabel: false },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: {
        interval,
        fontSize: 11,
        color: '#909399',
        formatter: formatDateLabel,
      },
      axisLine: { lineStyle: { color: '#E4E7ED' } },
      axisTick: { show: false },
    },
    yAxis: yAxisDefs,
    series,
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
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: `${METRIC_COLORS[s.metric] || '#409EFF'}20` },
          { offset: 1, color: `${METRIC_COLORS[s.metric] || '#409EFF'}05` },
        ],
      },
    },
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

  if (isBP) {
    if (s.metric === 'systolic') return [[{ yAxis: 140, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } }, { yAxis: 200 }]]
    return [[{ yAxis: 90, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } }, { yAxis: 150 }]]
  }

  return [[{ yAxis: s.normal_range.min, itemStyle: { color: 'rgba(16, 185, 129, 0.06)' } }, { yAxis: s.normal_range.max }]]
}

// 手动更新图表 — 仅在 series 或 axisMode 实际变化时调用
function updateChart() {
  if (!chartRef.value) return
  const option = buildOption()
  if (Object.keys(option).length > 0) {
    chartRef.value.setOption(option, { notMerge: false, replaceMerge: ['series'] })
  }
}

// watch series 和 axisMode，手动触发更新
watch(() => [props.series, props.axisMode], () => {
  nextTick(() => updateChart())
}, { deep: true })

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

function zoomToRange(startDate: string, endDate: string) {
  emit('range-change', { startDate, endDate })
}

defineExpose({ zoomToRange })
</script>

<style scoped>
.health-trend-chart {
  width: 100%;
  min-height: 250px;
  position: relative;
}

.health-trend-chart > :deep(div) {
  width: 100% !important;
  height: 100% !important;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
