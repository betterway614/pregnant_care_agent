<template>
  <div class="page-container">
    <div class="sub-page-header">
      <el-page-header @back="$router.back()">
        <template #content>健康趋势</template>
      </el-page-header>
    </div>

    <div class="patient-info-card">
      <!-- 指标选择器 -->
      <div class="trend-metric-selector">
        <el-checkbox-group v-model="selectedMetrics" @change="loadTrendData">
          <el-checkbox v-for="m in metricOptions" :key="m.value" :label="m.value" :value="m.value">
            {{ m.label }}
          </el-checkbox>
        </el-checkbox-group>
      </div>

      <!-- 横轴模式切换 -->
      <div class="trend-axis-toggle">
        <el-radio-group v-model="trendAxisMode" size="small" @change="loadTrendData">
          <el-radio-button value="date">按日期</el-radio-button>
          <el-radio-button value="gestational_week">按孕周</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 图表 -->
      <HealthTrendChart
        :series="trendSeries"
        :axis-mode="trendAxisMode === 'gestational_week' ? 'gest_week' : 'date'"
        :show-normal-range="true"
        :interactive="true"
        :height="350"
        @point-click="handlePointClick"
        @range-change="handleRangeChange"
      />

      <!-- 数据点详情 -->
      <div v-if="pointDetail" class="point-detail-card">
        <div class="point-detail__header">
          <span class="point-detail__name">{{ pointDetail.name }}</span>
          <el-tag v-if="pointDetail.isNormal === true" type="success" size="small">正常</el-tag>
          <el-tag v-else-if="pointDetail.isNormal === false" type="danger" size="small">异常</el-tag>
          <button class="point-detail__close" @click="pointDetail = null">✕</button>
        </div>
        <div class="point-detail__body">
          <span class="point-detail__value">{{ pointDetail.value }}</span>
          <span class="point-detail__unit">{{ pointDetail.unit }}</span>
          <span class="point-detail__date">{{ pointDetail.date }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { pregnantApi } from '@/api/endpoints'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import type { TrendSeries } from '@/types'

const selectedMetrics = ref<string[]>(['weight', 'systolic', 'diastolic'])
const trendAxisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const trendLoading = ref(false)
const pointDetail = ref<{ metric: string; name: string; date: string; value: number; unit: string; isNormal: boolean | null } | null>(null)

const metricOptions = [
  { value: 'weight', label: '体重' },
  { value: 'systolic', label: '收缩压' },
  { value: 'diastolic', label: '舒张压' },
  { value: 'blood_sugar_fasting', label: '空腹血糖' },
  { value: 'blood_sugar_postprandial', label: '餐后血糖' },
  { value: 'fetal_movement', label: '胎动' },
  { value: 'heart_rate', label: '心率' },
  { value: 'sleep_hours', label: '睡眠' },
  { value: 'steps', label: '步数' },
]

function loadTrendData() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid || !selectedMetrics.value.length) { trendSeries.value = []; return }
  trendLoading.value = true
  pregnantApi.getHealthTrends(pid, {
    metrics: selectedMetrics.value.join(','),
    axis_mode: trendAxisMode.value,
  }).then(res => { trendSeries.value = res.data.series || [] })
    .catch(() => { trendSeries.value = [] })
    .finally(() => { trendLoading.value = false })
}

function handlePointClick(data: { metric: string; date: string; value: number }) {
  const s = trendSeries.value.find(s => s.metric === data.metric)
  if (s) pointDetail.value = { metric: data.metric, name: s.name, date: data.date, value: data.value, unit: s.unit, isNormal: s.is_normal }
}

function handleRangeChange(range: { startDate: string; endDate: string }) {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid || !selectedMetrics.value.length) return
  trendLoading.value = true
  pregnantApi.getHealthTrends(pid, { metrics: selectedMetrics.value.join(','), axis_mode: trendAxisMode.value, start_date: range.startDate, end_date: range.endDate })
    .then(res => { trendSeries.value = res.data.series || [] })
    .catch(() => {}).finally(() => { trendLoading.value = false })
}

onMounted(() => { loadTrendData() })
</script>

<style scoped>
.page-container { overflow-y: auto; -webkit-overflow-scrolling: touch; height: 100%; box-sizing: border-box; padding-bottom: 24px; }
.sub-page-header { padding: 12px 16px; border-bottom: 1px solid #eee; background: #fff; position: sticky; top: 0; z-index: 10; }
.trend-metric-selector { margin-bottom: 12px; }
.trend-metric-selector .el-checkbox { margin-right: 12px; margin-bottom: 4px; }
.trend-axis-toggle { display: flex; justify-content: center; margin-bottom: 12px; }
.point-detail-card { margin-top: 12px; padding: 12px 16px; background: linear-gradient(135deg, #e3f2fd, #f3e5f5); border-radius: 12px; border: 1px solid rgba(66, 165, 245, 0.2); }
.point-detail__header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.point-detail__name { font-size: 14px; font-weight: 600; color: #303133; }
.point-detail__close { margin-left: auto; width: 20px; height: 20px; border: none; border-radius: 50%; background: rgba(0, 0, 0, 0.06); color: #909399; font-size: 10px; cursor: pointer; }
.point-detail__body { display: flex; align-items: baseline; gap: 6px; }
.point-detail__value { font-size: 28px; font-weight: 800; font-family: 'Figtree', sans-serif; color: #1976d2; }
.point-detail__unit { font-size: 14px; color: #666; }
.point-detail__date { font-size: 12px; color: #999; margin-left: auto; }
</style>
