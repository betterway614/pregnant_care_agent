<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">FGR专项看板</h1>
      <el-button type="primary" :icon="Refresh" @click="loadData" :loading="loading">
        刷新数据
      </el-button>
    </div>

    <!-- 分布统计卡片 -->
    <el-row :gutter="16" class="stat-grid-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in distributionCards" :key="card.label">
        <StatCard
          :icon="card.icon"
          :value="card.value"
          :label="card.label"
          :color="card.color"
          :bg-color="card.bgColor"
          :sub-label="card.subLabel"
        />
      </el-col>
    </el-row>

    <!-- 搜索/筛选栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索孕妇姓名..."
        clearable
        :prefix-icon="Search"
        style="width: 240px"
        @input="handleSearch"
      />
      <el-select v-model="filterRisk" placeholder="风险等级筛选" clearable style="width: 150px" @change="handleFilter">
        <el-option label="全部" value="" />
        <el-option label="高风险" value="high" />
        <el-option label="中风险" value="medium" />
        <el-option label="低风险" value="low" />
      </el-select>
      <el-select v-model="filterGestWeek" placeholder="孕周范围" clearable style="width: 150px" @change="handleFilter">
        <el-option label="全部" value="" />
        <el-option label="早孕期 (~14周)" value="early" />
        <el-option label="中孕期 (15-28周)" value="mid" />
        <el-option label="晚孕期 (29周~)" value="late" />
      </el-select>
    </div>

    <!-- FGR孕妇列表 -->
    <div class="content-card" style="margin-bottom: 16px">
      <div class="content-card__header">
        <span class="content-card__title">FGR孕妇列表</span>
        <span class="text-light">共 {{ filteredPregnant.length }} 人</span>
      </div>
      <div class="content-card__body" v-loading="loading">
        <el-table :data="filteredPregnant" stripe style="width: 100%" @row-click="handleRowClick">
          <el-table-column prop="display_name" label="孕妇姓名" min-width="100" />
          <el-table-column label="孕周" width="80" align="center">
            <template #default="{ row }">
              <span class="gest-week">{{ calcGestationalWeek(row.gestational_age_days) }}周</span>
            </template>
          </el-table-column>
          <el-table-column label="最近FGR等级" width="130">
            <template #default="{ row }">
              <RiskBadge :level="getLatestFgrLevel(row)" />
            </template>
          </el-table-column>
          <el-table-column label="置信区间" width="160" align="center">
            <template #default="{ row }">
              <span class="confidence-range">{{ formatConfidence(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click.stop="openTrendDrawer(row)">
                查看趋势
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!filteredPregnant.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><Search /></el-icon>
          <p>{{ searchQuery ? '未找到匹配孕妇' : '暂无FGR孕妇数据' }}</p>
        </div>
      </div>
    </div>

    <!-- 置信区间范围说明 -->
    <div class="content-card">
      <div class="content-card__header">
        <span class="content-card__title">风险等级置信区间范围</span>
        <el-tooltip content="置信区间反映模型预测的可靠性范围" placement="top">
          <el-icon color="var(--text-light)"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="content-card__body">
        <el-row :gutter="16">
          <el-col :span="8" v-for="range in confidenceRanges" :key="range.label">
            <div class="confidence-card" :style="{ borderLeftColor: range.color }">
              <div class="confidence-card__header">
                <RiskBadge :level="range.level" />
                <span class="confidence-card__range">{{ range.lower }} ~ {{ range.upper }}</span>
              </div>
              <p class="confidence-card__desc">{{ range.desc }}</p>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>

    <!-- 趋势图抽屉 -->
    <el-drawer
      v-model="trendDrawerVisible"
      :title="`${trendPregnant?.display_name || ''} - FGR风险趋势`"
      size="500px"
      destroy-on-close
    >
      <div v-loading="trendLoading" style="min-height: 300px">
        <template v-if="trendData.length">
          <!-- 趋势统计头部 -->
          <div class="trend-summary">
            <div class="trend-summary__item">
              <span class="trend-summary__label">当前风险</span>
              <RiskBadge :level="trendCurrentLevel" />
            </div>
            <div class="trend-summary__item">
              <span class="trend-summary__label">数据点数</span>
              <strong>{{ trendData.length }}</strong>
            </div>
            <div class="trend-summary__item">
              <span class="trend-summary__label">趋势方向</span>
              <el-tag :type="trendDirection === 'up' ? 'danger' : trendDirection === 'down' ? 'success' : 'info'" size="small">
                {{ trendDirection === 'up' ? '上升' : trendDirection === 'down' ? '下降' : '平稳' }}
              </el-tag>
            </div>
          </div>

          <!-- CSS 柱状趋势图 -->
          <div class="bar-chart">
            <div class="bar-chart__y-axis">
              <span>1.0</span>
              <span>0.8</span>
              <span>0.6</span>
              <span>0.4</span>
              <span>0.2</span>
              <span>0.0</span>
            </div>
            <div class="bar-chart__canvas">
              <div class="bar-chart__grid">
                <div v-for="i in 5" :key="i" class="bar-chart__grid-line" :style="{ bottom: `${i * 20}%` }" />
              </div>
              <div
                v-for="(point, idx) in trendData"
                :key="idx"
                class="bar-chart__bar-group"
                :style="{ left: `${(idx / (trendData.length - 1 || 1)) * 100}%` }"
              >
                <div
                  class="bar-chart__bar"
                  :style="{ height: `${point.risk_score * 100}%`, background: getBarColor(point.risk_score) }"
                >
                  <el-tooltip
                    :content="`${point.gestational_weeks}周: ${(point.risk_score * 100).toFixed(0)}分`"
                    placement="top"
                  >
                    <div class="bar-chart__dot" :style="{ background: getBarColor(point.risk_score) }" />
                  </el-tooltip>
                </div>
                <span class="bar-chart__label" v-if="trendData.length <= 15 || idx % Math.ceil(trendData.length / 10) === 0">
                  {{ point.gestational_weeks }}w
                </span>
              </div>
            </div>
          </div>

          <!-- 趋势数据表格 -->
          <el-divider />
          <h4 style="margin-bottom: 12px; font-size: 14px">历史评估记录</h4>
          <el-table :data="trendData" stripe size="small" max-height="240">
            <el-table-column label="孕周" width="70" align="center">
              <template #default="{ row }">{{ row.gestational_weeks }}周</template>
            </el-table-column>
            <el-table-column label="风险评分" width="90" align="center">
              <template #default="{ row }">{{ (row.risk_score * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="置信区间" width="120" align="center">
              <template #default="{ row }">
                {{ (row.confidence_lower * 100).toFixed(1) }}% ~ {{ (row.confidence_upper * 100).toFixed(1) }}%
              </template>
            </el-table-column>
            <el-table-column label="评估时间" width="90" align="center">
              <template #default="{ row }">
                {{ formatTime(row.assessed_at) }}
              </template>
            </el-table-column>
          </el-table>
        </template>
        <div v-if="!trendData.length && !trendLoading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><TrendCharts /></el-icon>
          <p>暂无趋势数据</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search, Refresh, InfoFilled, TrendCharts } from '@element-plus/icons-vue'
import { dashboardApi, fgrApi, alertApi } from '@/api/endpoints'
import type { Pregnant, FgrAssessment, FgrTrendPoint, Alert } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const loading = ref(false)
const searchQuery = ref('')
const filterRisk = ref('')
const filterGestWeek = ref('')
const pregnant = ref<Pregnant[]>([])
const alertList = ref<Alert[]>([])
const trendDrawerVisible = ref(false)
const trendPregnant = ref<Pregnant | null>(null)
const trendData = ref<FgrTrendPoint[]>([])
const trendLoading = ref(false)

/** 风险等级对应颜色 */
const riskColors: Record<string, string> = {
  high: '#D32F2F',
  medium: '#E65100',
  low: '#2E7D32',
}

/** 分布统计卡片 */
const distributionCards = computed(() => {
  const total = pregnant.value.length
  const highCount = pregnant.value.filter((p) => getLatestFgrLevel(p) === 'high').length
  const mediumCount = pregnant.value.filter((p) => getLatestFgrLevel(p) === 'medium').length
  const lowCount = pregnant.value.filter((p) => getLatestFgrLevel(p) === 'low').length

  return [
    {
      icon: 'User',
      value: total,
      label: '总FGR孕妇',
      color: 'var(--primary)',
      bgColor: 'var(--primary-bg)',
      subLabel: '监测中',
    },
    {
      icon: 'WarningFilled',
      value: highCount,
      label: '高风险',
      color: '#D32F2F',
      bgColor: '#FFEBEE',
      subLabel: `占比 ${total ? ((highCount / total) * 100).toFixed(0) : 0}%`,
    },
    {
      icon: 'WarningFilled',
      value: mediumCount,
      label: '中风险',
      color: '#E65100',
      bgColor: '#FFF3E0',
      subLabel: `占比 ${total ? ((mediumCount / total) * 100).toFixed(0) : 0}%`,
    },
    {
      icon: 'CircleCheck',
      value: lowCount,
      label: '低风险',
      color: '#2E7D32',
      bgColor: '#E8F5E9',
      subLabel: `占比 ${total ? ((lowCount / total) * 100).toFixed(0) : 0}%`,
    },
  ]
})

/** 获取孕妇最新FGR风险等级 */
function getLatestFgrLevel(pregnant: Pregnant): string {
  const fgrAlerts = alertList.value
    .filter((a) => a.pregnant_id === pregnant.pregnant_id && a.trigger_source?.toLowerCase().includes('fgr'))
  if (!fgrAlerts.length) return 'low'
  const latest = fgrAlerts.sort(
    (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
  )[0]
  return mapLevelToFgr(latest.level)
}

/** 映射预警级别到FGR风险等级 */
function mapLevelToFgr(level: string): string {
  const map: Record<string, string> = {
    RED: 'high',
    ORANGE: 'medium',
    YELLOW: 'low',
    GREEN: 'low',
    high: 'high',
    medium: 'medium',
    low: 'low',
  }
  return map[level] || 'low'
}

/** 格式化置信区间显示 */
function formatConfidence(pregnant: Pregnant): string {
  const fgrAlerts = alertList.value
    .filter((a) => a.pregnant_id === pregnant.pregnant_id && a.trigger_source?.toLowerCase().includes('fgr'))
  if (!fgrAlerts.length) return '--'
  const latest = fgrAlerts.sort(
    (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
  )[0]
  const details = latest.details
  if (details?.confidence_interval) {
    const ci = details.confidence_interval
    return `${(ci.lowerBound * 100).toFixed(1)}% ~ ${(ci.upperBound * 100).toFixed(1)}%`
  }
  return '--'
}

/** 计算孕周 */
function calcGestationalWeek(days?: number): number {
  if (!days) return 0
  return Math.floor(days / 7)
}

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** 根据孕周天数判断阶段 */
function getGestStage(days?: number): string {
  if (!days) return ''
  const weeks = Math.floor(days / 7)
  if (weeks <= 14) return 'early'
  if (weeks <= 28) return 'mid'
  return 'late'
}

/** 过滤后的孕妇列表 */
const filteredPregnant = computed(() => {
  let list = pregnant.value

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter((p) => p.display_name?.toLowerCase().includes(q))
  }

  if (filterRisk.value) {
    list = list.filter((p) => getLatestFgrLevel(p) === filterRisk.value)
  }

  if (filterGestWeek.value) {
    list = list.filter((p) => getGestStage(p.gestational_age_days) === filterGestWeek.value)
  }

  return list
})

/** 搜索 */
function handleSearch() {
  // computed 会自动响应
}

/** 筛选 */
function handleFilter() {
  // computed 会自动响应
}

/** 打开趋势抽屉 */
async function openTrendDrawer(pregnant: Pregnant) {
  trendPregnant.value = pregnant
  trendDrawerVisible.value = true
  trendLoading.value = true
  trendData.value = []
  try {
    const res = await fgrApi.trend(pregnant.pregnant_id)
    trendData.value = (res.data || []).sort(
      (a, b) => a.gestational_weeks - b.gestational_weeks
    )
  } catch (err) {
    console.error('加载FGR趋势失败:', err)
  } finally {
    trendLoading.value = false
  }
}

/** 当前风险等级 */
const trendCurrentLevel = computed(() => {
  if (!trendData.value.length) return 'low'
  const latest = trendData.value[trendData.value.length - 1]
  if (latest.risk_score >= 0.7) return 'high'
  if (latest.risk_score >= 0.4) return 'medium'
  return 'low'
})

/** 趋势方向 */
const trendDirection = computed(() => {
  if (trendData.value.length < 2) return 'stable'
  const first = trendData.value[0].risk_score
  const last = trendData.value[trendData.value.length - 1].risk_score
  const diff = last - first
  if (diff > 0.1) return 'up'
  if (diff < -0.1) return 'down'
  return 'stable'
})

/** 获取柱状图颜色 */
function getBarColor(score: number): string {
  if (score >= 0.7) return '#D32F2F'
  if (score >= 0.4) return '#E65100'
  return '#4CAF50'
}

/** 置信区间范围说明 */
const confidenceRanges = [
  {
    level: 'high',
    label: '高风险',
    color: '#D32F2F',
    lower: '70%',
    upper: '100%',
    desc: 'FGR可能性较高，建议加强监测频率，考虑进一步影像学检查。',
  },
  {
    level: 'medium',
    label: '中风险',
    color: '#E65100',
    lower: '40%',
    upper: '70%',
    desc: '需要关注，建议2周内复查超声，综合评估胎儿生长指标。',
  },
  {
    level: 'low',
    label: '低风险',
    color: '#2E7D32',
    lower: '0%',
    upper: '40%',
    desc: '目前风险较低，按常规产检流程进行管理即可。',
  },
]

/** 点击行查看详情 */
function handleRowClick(row: Pregnant) {
  // 当前跳转到趋势查看，也可以扩展为跳转孕妇详情
}

/** 加载数据 */
async function loadData() {
  loading.value = true
  try {
    const [pregnantRes, alertsRes] = await Promise.all([
      dashboardApi.pregnant(),
      alertApi.list({ status: 'pending,confirmed' }),
    ])
    pregnant.value = pregnantRes.data || []
    alertList.value = alertsRes.data || []
  } catch (err) {
    console.error('加载FGR看板数据失败:', err)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.stat-grid-row {
  margin-bottom: 24px;
}

.search-bar {
  margin-bottom: 20px;
}

/* 孕周标签 */
.gest-week {
  font-weight: 600;
  color: var(--text-primary);
}

.confidence-range {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* 置信区间卡片 */
.confidence-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: var(--radius-sm);
  padding: 16px;
  transition: var(--transition);
}

.confidence-card:hover {
  box-shadow: var(--shadow-hover);
}

.confidence-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.confidence-card__range {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.confidence-card__desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* 趋势摘要 */
.trend-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  background: var(--bg-page);
  border-radius: var(--radius-sm);
  padding: 16px;
}

.trend-summary__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.trend-summary__label {
  font-size: 12px;
  color: var(--text-light);
}

/* CSS 柱状图 */
.bar-chart {
  display: flex;
  height: 240px;
  margin-bottom: 16px;
  padding: 16px 0;
  position: relative;
}

.bar-chart__y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding-right: 8px;
  font-size: 11px;
  color: var(--text-light);
  width: 32px;
  flex-shrink: 0;
}

.bar-chart__canvas {
  flex: 1;
  position: relative;
  border-left: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.bar-chart__grid {
  position: absolute;
  inset: 0;
}

.bar-chart__grid-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border);
  opacity: 0.5;
}

.bar-chart__bar-group {
  position: absolute;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translateX(-50%);
}

.bar-chart__bar {
  width: 8px;
  border-radius: 4px 4px 0 0;
  min-height: 4px;
  transition: height 0.5s ease;
  cursor: pointer;
  position: relative;
}

.bar-chart__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  position: absolute;
  top: -5px;
  left: -1px;
  cursor: pointer;
  transition: transform 0.2s;
}

.bar-chart__dot:hover {
  transform: scale(1.5);
}

.bar-chart__label {
  font-size: 10px;
  color: var(--text-light);
  margin-top: 6px;
  white-space: nowrap;
}

.text-light {
  font-size: 12px;
  color: var(--text-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  gap: 12px;
}

.empty-state p {
  color: var(--text-light);
  font-size: 14px;
}
</style>
