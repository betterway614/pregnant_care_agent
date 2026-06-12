<template>
  <div class="metric-category-selector">
    <!-- 分类标签栏 -->
    <div class="category-tabs">
      <button
        v-for="cat in visibleCategories"
        :key="cat.key"
        :class="['cat-tab', { active: activeCategory === cat.key }]"
        @click="switchToCategory(cat.key)"
      >
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
          :class="['toggle-all-btn', { 'is-deselect': isAllSelected(currentCategory) }]"
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
        {{ currentCategory.comboGroups.map(g => g.name).join('、') }}已配对显示
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  getAllCategories,
  type IndicatorCategory,
} from '@/utils/labelMaps'
import { trendName, labLabel } from '@/utils/labelMaps'

const props = withDefaults(defineProps<{
  modelValue: string[]
  categories?: ('vital_signs' | 'blood_sugar' | 'daily_tracking' | 'fetal' | 'lab_tests')[]
  disabledMetrics?: string[]
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

const visibleCategories = computed(() => {
  const all = getAllCategories()
  return all.filter(c => props.categories.includes(c.key as any))
})

const currentCategory = computed(() =>
  visibleCategories.value.find(c => c.key === activeCategory.value)
)

const selectedMetrics = computed(() => props.modelValue)

function isSelected(metric: string): boolean {
  return props.modelValue.includes(metric)
}

function selectedInCategory(cat: IndicatorCategory): string[] {
  return cat.metrics.filter(m => props.modelValue.includes(m))
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
    emit('update:modelValue', props.modelValue.filter(m => !cat.metrics.includes(m)))
  } else {
    emit('update:modelValue', [...new Set([...props.modelValue, ...cat.metrics])])
  }
}

/** 切换分类时自动全选该分类下的所有指标 */
function switchToCategory(catKey: string) {
  activeCategory.value = catKey
  const cat = visibleCategories.value.find(c => c.key === catKey)
  if (cat) {
    emit('update:modelValue', [...cat.metrics])
  }
}

function getLabel(metric: string): string {
  return trendName(metric) || labLabel(metric) || metric
}
</script>

<style scoped>
.metric-category-selector {
  --cat-active: #FB7185;
  --cat-hover: #FFF1F2;
  --cat-bg: #FDF2F4;
  --cat-active-bg: #FFF5F5;
  border-radius: 8px;
  overflow: hidden;
}

.category-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px 0;
  background: var(--cat-bg);
  border-bottom: 1px solid #FEE2E2;
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
.cat-count {
  font-size: 11px;
  color: #909399;
  background: #FEE2E2;
  padding: 1px 6px;
  border-radius: 10px;
}
.cat-tab.active .cat-count {
  background: #FECACA;
  color: var(--cat-active);
}

.category-metrics {
  padding: 12px 16px;
  background: var(--cat-active-bg);
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

/* 全选/取消按钮 — 粉色主题 */
.toggle-all-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 14px;
  border: 1px solid var(--cat-active);
  color: var(--cat-active);
  background: transparent;
  transition: all .2s;
}
.toggle-all-btn:hover {
  background: var(--cat-hover);
}
.toggle-all-btn.is-deselect {
  background: var(--cat-active);
  color: #fff;
}
.toggle-all-btn.is-deselect:hover {
  background: #F43F5E;
}
</style>
