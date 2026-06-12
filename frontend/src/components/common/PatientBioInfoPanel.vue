<template>
  <div class="bio-panel" v-loading="loading">
    <!-- 基础信息卡片 -->
    <section class="bio-panel__section">
      <h4 class="bio-panel__title">
        <el-icon><User /></el-icon> 基础信息
      </h4>
      <div class="info-grid">
        <div class="info-item">
          <span class="info-item__label">孕妇</span>
          <span class="info-item__value">{{ basicInfo.name }}</span>
        </div>
        <div class="info-item">
          <span class="info-item__label">孕周</span>
          <span class="info-item__value">{{ basicInfo.gest_week }}周</span>
        </div>
        <div class="info-item">
          <span class="info-item__label">预产期</span>
          <span class="info-item__value">{{ basicInfo.edd || '未知' }}</span>
        </div>
        <div class="info-item">
          <span class="info-item__label">风险标签</span>
          <span class="info-item__value">
            <el-tag
              v-for="tag in basicInfo.risk_tags"
              :key="tag"
              size="small"
              :type="tagType(tag)"
              style="margin-right: 4px"
            >
              {{ tag }}
            </el-tag>
            <span v-if="!basicInfo.risk_tags?.length" class="text-muted">无特殊风险</span>
          </span>
        </div>
      </div>
    </section>

    <!-- 健康趋势图表 -->
    <section class="bio-panel__section" v-if="showTrends">
      <h4 class="bio-panel__title">
        <el-icon><TrendCharts /></el-icon> 健康趋势
      </h4>
      <MetricCategorySelector
        v-model="selectedMetrics"
        :categories="['vital_signs', 'blood_sugar', 'daily_tracking', 'fetal']"
        :role="role"
        @update:model-value="loadHealthTrends"
      />
      <HealthTrendChart
        v-if="trendsData?.series?.length"
        :series="trendsData.series"
        :height="260"
        :show-normal-range="true"
      />
      <div v-else-if="!trendsLoading" class="empty-hint">暂无健康数据</div>
    </section>

    <!-- 生化指标面板 -->
    <section class="bio-panel__section" v-if="showLab">
      <h4 class="bio-panel__title">
        <el-icon><DataAnalysis /></el-icon> 生化指标
      </h4>
      <div v-if="labItems.length" class="lab-table">
        <div
          v-for="item in labItems"
          :key="item.lab_key"
          class="lab-row"
          :class="{ 'lab-row--abnormal': item.is_normal === false }"
        >
          <span class="lab-row__name">{{ item.name }}</span>
          <span
            class="lab-row__value"
            :class="{ 'lab-row__value--high': item.is_normal === false }"
          >
            {{ item.latest_value }}{{ item.unit ? ' ' + item.unit : '' }}
          </span>
          <span class="lab-row__range" v-if="item.normal_low != null && item.normal_high != null">
            正常: {{ item.normal_low }}-{{ item.normal_high }}
          </span>
          <span v-else class="lab-row__range">定性</span>
          <!-- 趋势小图（定量指标且有>=2个数据点） -->
          <div v-if="!item.is_qualitative && item.data_points.length >= 2" class="lab-row__spark">
            <MiniSpark :points="item.data_points" :low="item.normal_low" :high="item.normal_high" />
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">{{ labLoaded ? '暂无生化指标数据' : '加载中...' }}</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { User, TrendCharts, DataAnalysis } from '@element-plus/icons-vue'
import { pregnantApi } from '@/api/endpoints'
import type { HealthTrendResponse, LabTrendItem, LabTrendResponse } from '@/types'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import MetricCategorySelector from '@/components/charts/MetricCategorySelector.vue'
import MiniSpark from '@/components/charts/MiniSpark.vue'

const props = withDefaults(defineProps<{
  pregnantId: string
  showTrends?: boolean
  showLab?: boolean
  role?: 'pregnant' | 'nurse' | 'doctor'
}>(), {
  showTrends: true,
  showLab: true,
  role: 'pregnant',
})

const loading = ref(false)
const basicInfo = ref({
  name: '',
  gest_week: 0,
  edd: '',
  risk_tags: [] as string[],
})

// 健康趋势
const trendsLoading = ref(false)
const trendsData = ref<HealthTrendResponse | null>(null)
const selectedMetrics = ref(props.role === 'pregnant'
  ? ['weight', 'systolic', 'diastolic']
  : ['systolic', 'diastolic', 'weight', 'blood_sugar_fasting'])

// 生化指标
const labLoaded = ref(false)
const labItems = ref<LabTrendItem[]>([])

function tagType(tag: string): 'danger' | 'warning' | 'info' | 'success' {
  if (tag.includes('FGR') || tag.includes('高危')) return 'danger'
  if (tag.includes('GDM') || tag.includes('高血压')) return 'warning'
  if (tag.includes('焦虑') || tag.includes('情绪')) return 'info'
  return 'success'
}

async function loadBasicInfo() {
  if (!props.pregnantId) return
  try {
    const res = await pregnantApi.get(props.pregnantId)
    const p = res.data
    const gest_days = p.gestational_age_days || 0
    basicInfo.value = {
      name: p.display_name || p.nickname || '',
      gest_week: Math.floor(gest_days / 7),
      edd: p.edd || '',
      risk_tags: p.risk_tags || [],
    }
  } catch {
    // silent
  }
}

async function loadHealthTrends() {
  if (!props.pregnantId || !selectedMetrics.value.length) return
  trendsLoading.value = true
  try {
    const res = await pregnantApi.getHealthTrends(props.pregnantId, {
      metrics: selectedMetrics.value.join(','),
      granularity: 'weekly',
    })
    trendsData.value = res.data
  } catch {
    trendsData.value = null
  } finally {
    trendsLoading.value = false
  }
}

async function loadLabTrends() {
  if (!props.pregnantId) return
  try {
    const res = await pregnantApi.getLabTrends(props.pregnantId, 20)
    const data: LabTrendResponse = res.data
    labItems.value = data.items || []
  } catch {
    labItems.value = []
  } finally {
    labLoaded.value = true
  }
}

async function loadAll() {
  loading.value = true
  await Promise.all([loadBasicInfo(), loadHealthTrends(), loadLabTrends()])
  loading.value = false
}

watch(() => props.pregnantId, (id) => {
  if (id) loadAll()
}, { immediate: true })

defineExpose({ refresh: loadAll })
</script>

<style scoped>
.bio-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 200px;
}

.bio-panel__section {
  background: var(--glass-bg, rgba(255,255,255,0.6));
  border: 1px solid var(--glass-border, rgba(255,255,255,0.4));
  border-radius: 8px;
  padding: 14px;
}

.bio-panel__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #303133);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border, #e4e7ed);
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.info-item__label {
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.info-item__value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.metric-controls {
  margin-bottom: 10px;
  overflow-x: auto;
}

/* 生化指标表格 */
.lab-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lab-row {
  display: grid;
  grid-template-columns: 110px 100px 90px 80px;
  align-items: center;
  padding: 8px 10px;
  background: rgba(241, 245, 249, 0.5);
  border-radius: 4px;
  transition: background 0.2s;
  gap: 8px;
}

.lab-row:hover {
  background: rgba(232, 245, 233, 0.3);
}

.lab-row--abnormal {
  background: rgba(255, 235, 238, 0.6);
}

.lab-row__name {
  font-size: 13px;
  color: var(--text-secondary, #606266);
  font-weight: 500;
}

.lab-row__value {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #303133);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.lab-row__value--high {
  color: var(--danger, #f56c6c);
}

.lab-row__range {
  font-size: 11px;
  color: var(--text-muted, #909399);
}

.lab-row__spark {
  display: flex;
  justify-content: flex-end;
}

.empty-hint {
  text-align: center;
  padding: 24px 0;
  font-size: 13px;
  color: var(--text-muted, #909399);
}

.text-muted {
  color: var(--text-muted, #909399);
  font-size: 13px;
}
</style>
