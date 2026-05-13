<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button text @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <h1 class="page-title">{{ pregnantInfo?.display_name || '孕妇详情' }}</h1>
      <span v-if="pregnantInfo?.gestational_age_days" class="header-subtitle">
        孕{{ Math.floor(pregnantInfo.gestational_age_days / 7) }}周
      </span>
      <div v-if="pregnantInfo?.risk_tags?.length" class="risk-tags">
        <el-tag v-for="tag in pregnantInfo.risk_tags" :key="tag" type="danger" size="small">
          {{ tag }}
        </el-tag>
      </div>
    </div>

    <!-- 主内容区 -->
    <el-row :gutter="16" class="detail-body">
      <!-- 左侧：随访时间线 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">随访记录</span>
            <el-tag size="small">{{ followUpRecords.length }} 条</el-tag>
          </div>
          <div class="content-card__body">
            <FollowUpTimeline
              :records="followUpRecords"
              :selected-id="selectedFollowUpId"
              @select="handleFollowUpSelect"
            />
          </div>
        </div>
      </el-col>

      <!-- 右侧：健康数据曲线 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">健康趋势</span>
            <div class="chart-controls">
              <el-checkbox-group v-model="selectedMetrics" @change="loadTrendData" size="small">
                <el-checkbox value="weight">体重</el-checkbox>
                <el-checkbox value="systolic">收缩压</el-checkbox>
                <el-checkbox value="diastolic">舒张压</el-checkbox>
                <el-checkbox value="blood_sugar_fasting">空腹血糖</el-checkbox>
                <el-checkbox value="blood_sugar_postprandial">餐后血糖</el-checkbox>
                <el-checkbox value="fetal_movement">胎动</el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-model="axisMode" size="small" @change="loadTrendData" style="margin-left: 12px">
                <el-radio-button value="date">日期</el-radio-button>
                <el-radio-button value="gestational_week">孕周</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="content-card__body">
            <HealthTrendChart
              ref="chartRef"
              :series="trendSeries"
              :axis-mode="axisMode === 'gestational_week' ? 'gest_week' : 'date'"
              :show-normal-range="true"
              :interactive="true"
              :height="450"
              @point-click="handlePointClick"
            />
          </div>
        </div>

        <!-- 异常数据摘要卡片 -->
        <div v-if="abnormalMetrics.length" class="content-card" style="margin-top: 16px">
          <div class="content-card__header">
            <span class="content-card__title" style="color: #f56c6c">异常数据提示</span>
          </div>
          <div class="content-card__body">
            <div v-for="item in abnormalMetrics" :key="item.metric" class="abnormal-item">
              <el-icon color="#f56c6c"><WarningFilled /></el-icon>
              <span>{{ item.name }}: {{ item.latest_value }}{{ item.unit }}</span>
              <el-tag type="danger" size="small">超出正常范围</el-tag>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, WarningFilled } from '@element-plus/icons-vue'
import { pregnantApi } from '@/api/endpoints'
import FollowUpTimeline from '@/components/followup/FollowUpTimeline.vue'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import type { TrendSeries, FollowUpHistoryRecord, Pregnant } from '@/types'

const route = useRoute()
const router = useRouter()
const pregnantId = computed(() => route.params.pregnantId as string)

const pregnantInfo = ref<Pregnant | null>(null)
const followUpRecords = ref<FollowUpHistoryRecord[]>([])
const selectedFollowUpId = ref<string | null>(null)
const selectedMetrics = ref(['systolic', 'diastolic', 'weight', 'blood_sugar_fasting'])
const axisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const chartRef = ref()

// 异常数据检测
const abnormalMetrics = computed(() => {
  return trendSeries.value.filter(s => s.is_normal === false)
})

async function loadPregnantInfo() {
  try {
    const res = await pregnantApi.get(pregnantId.value)
    pregnantInfo.value = res.data
  } catch { /* ignore */ }
}

async function loadFollowUpHistory() {
  try {
    const res = await pregnantApi.getFollowUpHistory(pregnantId.value, { limit: 50 })
    followUpRecords.value = res.data.records || []
  } catch { /* ignore */ }
}

async function loadTrendData() {
  if (!pregnantId.value || !selectedMetrics.value.length) {
    trendSeries.value = []
    return
  }
  try {
    const res = await pregnantApi.getHealthTrends(pregnantId.value, {
      metrics: selectedMetrics.value.join(','),
      axis_mode: axisMode.value,
    })
    trendSeries.value = res.data.series || []
  } catch {
    trendSeries.value = []
  }
}

function handleFollowUpSelect(record: FollowUpHistoryRecord) {
  selectedFollowUpId.value = record.id
  if (record.follow_up_date && chartRef.value) {
    const followDate = new Date(record.follow_up_date)
    const start = new Date(followDate)
    start.setDate(start.getDate() - 7)
    const end = new Date(followDate)
    end.setDate(end.getDate() + 7)
    chartRef.value.zoomToRange(
      start.toISOString().slice(0, 10),
      end.toISOString().slice(0, 10),
    )
  }
}

function handlePointClick(data: { metric: string; date: string; value: number }) {
  console.log('Point clicked:', data)
}

onMounted(() => {
  loadPregnantInfo()
  loadFollowUpHistory()
  loadTrendData()
})
</script>

<style scoped>
.detail-body {
  margin-top: 16px;
}

.header-subtitle {
  font-size: 14px;
  color: #909399;
  margin-left: 8px;
}

.risk-tags {
  display: inline-flex;
  gap: 4px;
  margin-left: 12px;
}

.chart-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.abnormal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 14px;
}

.abnormal-item:not(:last-child) {
  border-bottom: 1px solid #ebeef5;
}
</style>
