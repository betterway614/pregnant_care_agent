<template>
  <div class="metric-category-selector">
    <!-- 分类标签栏 -->
    <div class="category-tabs">
      <button
        v-for="cat in visibleCategories"
        :key="cat.key"
        :class="['cat-tab', { active: activeCategory === cat.key }]"
        @click="activeCategory = cat.key"
      >
        <span class="cat-icon">{{ cat.icon }}</span>
        <span class="cat-name">{{ cat.name }}</span>
        <span class="cat-count">{{ selectedInCategory(cat).length }}/{{ cat.metrics.length }}</span>
      </button>
    </div>

    <!-- 当前分类的指标列表 -->
    <div class="category-metrics" v-if="currentCategory">
      <div class="cat-header">
        <span class="cat-desc">{{ currentCategory.description }}</span>
        <el-button
          size="small"
          text
          type="primary"
          @click="toggleAll(currentCategory)"
        >
          {{ isAllSelected(currentCategory) ? '取消全选' : '全选' }}
        </el-button>
      </div>
      <div class="metric-checkboxes">
        <el-checkbox
          v-for="metric in currentCategory.metrics"
          :key="metric"
          :model-value="isSelected(metric)"
          :label="getLabel(metric)"
          :disabled="props.disabledMetrics.includes(metric)"
          size="small"
          @change="(val: boolean) => toggleMetric(metric, val)"
        />
      </div>

      <!-- 配对组提示 -->
      <div
        v-if="currentCategory.comboGroups?.length"
        class="combo-hint"
      >
        💡 {{ currentCategory.comboGroups.map(g => g.name).join('、') }}已配对显示
      </div>
    </div>

    <!-- 已选指标摘要 -->
    <div class="selected-summary" v-if="selectedMetrics.length">
      <span class="summary-label">已选 {{ selectedMetrics.length }} 项：</span>
      <el-tag
        v-for="m in selectedMetrics"
        :key="m"
        size="small"
        :color="getMetricColor(m)"
        closable
        @close="toggleMetric(m, false)"
      >
        {{ getLabel(m) }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  CATEGORIES, LAB_CATEGORY, getAllCategories,
  type IndicatorCategory,
} from '@/utils/labelMaps'
import { trendName, labLabel } from '@/utils/labelMaps'

const props = withDefaults(defineProps<{
  modelValue: string[]             // 已选的 metric codes
  categories?: ('vital_signs' | 'blood_sugar' | 'daily_tracking' | 'fetal' | 'lab_tests')[]  // 允许的分类
  disabledMetrics?: string[]       // 禁用的指标（如已配对管理的）
  role?: 'pregnant' | 'nurse' | 'doctor'
}>(), {
  modelValue: () => [],
  categories: () => ['vital_signs', 'blood_sugar', 'daily_tracking', 'fetal'],
  disabledMetrics: () => [],
  role: 'pregnant',
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const activeCategory = ref(props.categories[0])

// 可见的分类（按 props.categories 过滤）
const visibleCategories = computed(() => {
  const all = getAllCategories()
  return all.filter(c => props.categories.includes(c.key as any))
})

// 当前激活的分类
const currentCategory = computed(() =>
  visibleCategories.value.find(c => c.key === activeCategory.value)
)

// 选中的指标
const selectedMetrics = computed(() => props.modelValue)

function isSelected(metric: string): boolean {
  return props.modelValue.includes(metric)
}

function selectedInCategory(cat: IndicatorCategory): number[] {
  // bug compatibility: return number[]
  return cat.metrics.filter(m => props.modelValue.includes(m)) as any
}

function isAllSelected(cat: IndicatorCategory): boolean {
  return cat.metrics.every(m => props.modelValue.includes(m))
}

function toggleMetric(metric: string, checked: boolean) {
  const next = checked
    ? [...new Set([...props.modelValue, metric])]
    : props.modelValue.filter(m => m !== metric)
  emit('update:modelValue', next)
}

function toggleAll(cat: IndicatorCategory) {
  if (isAllSelected(cat)) {
    // 取消全选
    emit('update:modelValue', props.modelValue.filter(m => !cat.metrics.includes(m)))
  } else {
    // 全选
    emit('update:modelValue', [...new Set([...props.modelValue, ...cat.metrics])])
  }
}

function getLabel(metric: string): string {
  // 尝试从健康指标和化验指标中查找
  return trendName(metric) || labLabel(metric) || metric
}

const METRIC_COLORS_MAP: Record<string, string> = {
  weight: '#8B5CF6', systolic: '#EF4444', diastolic: '#F97316',
  blood_sugar_fasting: '#EC4899', blood_sugar_postprandial: '#F472B6',
  fetal_movement: '#06B6D4', heart_rate: '#10B981',
  sleep_hours: '#6366F1', steps: '#F59E0B', emotion_score: '#8B5CF6',
  hemoglobin_g_L: '#EF4444', alt: '#F97316', ast: '#F59E0B',
  creatinine: '#10B981', uric_acid: '#06B6D4', albumin: '#8B5CF6',
  wbc: '#EC4899', platelet: '#6366F1', hct: '#F472B6', bilirubin_total: '#84CC16',
}

function getMetricColor(metric: string): string {
  return METRIC_COLORS_MAP[metric] || '#909399'
}
</script>

<style scoped>
.metric-category-selector {
  --cat-active: #409EFF;
  --cat-hover: #ECF5FF;
  --cat-bg: #F5F7FA;
  border-radius: 8px;
  overflow: hidden;
}

.category-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px 0;
  background: var(--cat-bg);
  border-bottom: 1px solid #E4E7ED;
  overflow-x: auto;
  scrollbar-width: none;
}
.category-tabs::-webkit-scrollbar { display: none; }

.cat-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-radius: 8px 8px 0 0;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  transition: all .2s;
  border-bottom: 2px solid transparent;
}
.cat-tab:hover { background: var(--cat-hover); color: var(--cat-active); }
.cat-tab.active {
  background: #fff;
  color: var(--cat-active);
  border-bottom-color: var(--cat-active);
  font-weight: 600;
}
.cat-icon { font-size: 16px; }
.cat-count {
  font-size: 11px;
  color: #909399;
  background: #F2F6FC;
  padding: 1px 6px;
  border-radius: 10px;
}
.cat-tab.active .cat-count {
  background: #ECF5FF;
  color: var(--cat-active);
}

.category-metrics {
  padding: 12px 16px;
  background: #fff;
}
.cat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.cat-desc {
  font-size: 12px;
  color: #909399;
}

.metric-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.combo-hint {
  margin-top: 8px;
  font-size: 11px;
  color: #E6A23C;
}

.selected-summary {
  padding: 8px 16px 12px;
  background: #fff;
  border-top: 1px solid #EBEEF5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.summary-label {
  font-size: 11px;
  color: #909399;
  margin-right: 4px;
}
</style>
