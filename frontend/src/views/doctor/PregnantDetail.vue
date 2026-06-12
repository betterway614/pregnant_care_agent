<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button text @click="$router.push('/doctor/patients')">
        <el-icon><ArrowLeft /></el-icon> 返回孕妇列表
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

    <!-- 快捷操作栏 -->
    <div class="action-bar" v-if="pregnantInfo">
      <el-button type="primary" @click="triggerFollowUp">
        <el-icon><Document /></el-icon> 触发随访
      </el-button>
      <el-button type="warning" @click="viewAlerts">
        <el-icon><WarningFilled /></el-icon> 查看预警
      </el-button>
      <el-button type="success" @click="generateOrder">
        <el-icon><EditPen /></el-icon> 生成医嘱
      </el-button>
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
              <MetricCategorySelector
                v-model="selectedMetrics"
                :categories="['vital_signs', 'blood_sugar', 'daily_tracking', 'fetal', 'lab_tests']"
                role="doctor"
                @update:model-value="loadTrendData"
              />
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
import { ArrowLeft, WarningFilled, Document, EditPen } from '@element-plus/icons-vue'
import { pregnantApi, followUpApi } from '@/api/endpoints'
import { ElMessage } from 'element-plus'
import FollowUpTimeline from '@/components/followup/FollowUpTimeline.vue'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import MetricCategorySelector from '@/components/charts/MetricCategorySelector.vue'
import type { TrendSeries, FollowUpHistoryRecord, Pregnant, LabTrendItem } from '@/types'
import { LAB_METRIC_OPTIONS, LAB_METRIC_META } from '@/utils/labelMaps'

const route = useRoute()
const router = useRouter()
const pregnantId = computed(() => route.params.pregnantId as string)

/** 快捷操作 */
async function triggerFollowUp() {
  try {
    await followUpApi.trigger(pregnantId.value)
    ElMessage.success('随访已触发')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '触发失败')
  }
}
function viewAlerts() {
  router.push({ path: '/doctor/review', query: { pregnant_id: pregnantId.value } })
}
function generateOrder() {
  router.push({ path: '/doctor/orders', query: { pregnant_id: pregnantId.value, action: 'generate' } })
}

const pregnantInfo = ref<Pregnant | null>(null)
const followUpRecords = ref<FollowUpHistoryRecord[]>([])
const selectedFollowUpId = ref<string | null>(null)
const selectedMetrics = ref(['systolic', 'diastolic', 'weight', 'blood_sugar_fasting'])
const axisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const chartRef = ref()

// 化验指标 key 集合，用于分离 health/lab 两类数据源
const LAB_METRIC_KEYS = new Set(LAB_METRIC_OPTIONS.map(m => m.value))

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
  const allSeries: TrendSeries[] = []

  // 分离健康指标和化验指标（两个不同的数据源）
  const healthMetrics = selectedMetrics.value.filter(m => !LAB_METRIC_KEYS.has(m))
  const labMetrics = selectedMetrics.value.filter(m => LAB_METRIC_KEYS.has(m))

  // 加载基础健康趋势
  if (healthMetrics.length) {
    try {
      const res = await pregnantApi.getHealthTrends(pregnantId.value, {
        metrics: healthMetrics.join(','),
        axis_mode: axisMode.value,
      })
      allSeries.push(...(res.data.series || []))
    } catch { /* ignore */ }
  }

  // 加载生化指标趋势
  if (labMetrics.length) {
    try {
      const labRes = await pregnantApi.getLabTrends(pregnantId.value, 50)
      const labItems: LabTrendItem[] = labRes.data.items || []
      for (const item of labItems) {
        if (!labMetrics.includes(item.lab_key)) continue
        if (item.is_qualitative) continue
        const meta = LAB_METRIC_META[item.lab_key]
        if (!meta) continue

        const data = item.data_points
          .filter(dp => dp.value != null)
          .map(dp => ({
            date: dp.date,
            gest_week: dp.gest_week,
            value: dp.value!,
          }))
        if (!data.length) continue

        let trend: TrendSeries['trend'] = 'insufficient_data'
        if (data.length >= 2) {
          const first = data[0].value
          const last = data[data.length - 1].value
          const diff = last - first
          if (Math.abs(diff) < (meta.normal_high || 100) * 0.05) trend = 'stable'
          else trend = diff > 0 ? 'rising' : 'falling'
        }

        allSeries.push({
          metric: item.lab_key,
          name: meta.name,
          unit: meta.unit,
          normal_range: {
            min: meta.normal_low ?? 0,
            max: meta.normal_high ?? 999,
          },
          data,
          trend,
          latest_value: data.length ? data[data.length - 1].value : null,
          is_normal: item.is_normal,
        })
      }
    } catch { /* ignore */ }
  }

  trendSeries.value = allSeries
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

const pointDetail = ref<{ metric: string; name: string; date: string; value: number; unit: string; isNormal: boolean | null } | null>(null)

function handlePointClick(data: { metric: string; date: string; value: number }) {
  const s = trendSeries.value.find(s => s.metric === data.metric)
  if (s) {
    pointDetail.value = {
      metric: data.metric,
      name: s.name,
      date: data.date,
      value: data.value,
      unit: s.unit,
      isNormal: s.is_normal,
    }
  }
}

onMounted(() => {
  loadPregnantInfo()
  loadFollowUpHistory()
  loadTrendData()
})
</script>

<style scoped>
.detail-body {
  margin-top: 20px;
}

.header-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin-left: 8px;
  font-weight: 500;
}

.risk-tags {
  display: inline-flex;
  gap: 6px;
  margin-left: 12px;
}

.chart-controls {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chart-controls__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.chart-controls__label {
  font-size: 11px;
  color: var(--text-muted);
  margin-right: 4px;
  white-space: nowrap;
  min-width: 56px;
}

.abnormal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  font-size: 14px;
  transition: background var(--transition-fast);
}

.abnormal-item:hover {
  background: rgba(211, 47, 47, 0.04);
  border-radius: var(--radius-xs);
  margin: 0 -4px;
  padding-left: 4px;
  padding-right: 4px;
}

.abnormal-item:not(:last-child) {
  border-bottom: 1px solid var(--border);
}

.point-detail-card {
  margin-top: 14px;
  padding: 16px 18px;
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.point-detail__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.point-detail__name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.point-detail__close {
  margin-left: auto;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
}

.point-detail__close:hover {
  background: rgba(0, 0, 0, 0.1);
  transform: scale(1.1);
}

.point-detail__body {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.point-detail__value {
  font-size: 28px;
  font-weight: 800;
  font-family: 'Figtree', sans-serif;
  background: var(--primary-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.5px;
}

.point-detail__unit {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.point-detail__date {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
  font-weight: 500;
}

.action-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
</style>
