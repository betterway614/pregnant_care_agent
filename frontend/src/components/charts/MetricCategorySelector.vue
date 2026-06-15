<template>
  <div class="metric-category-selector" :style="cssVars">
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
      <div v-if="currentCategory.comboGroups?.length" class="combo-hint">
        {{ currentCategory.comboGroups.map(g => g.name).join('、') }}已配对显示
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getAllCategories, type IndicatorCategory, TREND_NAME_MAP, LAB_LABEL_MAP } from '@/utils/labelMaps'

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

// ── 角色色板 ──
const ROLE_PALETTE: Record<string, { active: string; hover: string; bg: string; activeBg: string; border: string; dark: string }> = {
  pregnant:  { active: '#FB7185', hover: '#FFF1F2', bg: '#FDF2F4', activeBg: '#FFF5F5', border: '#FEE2E2', dark: '#F43F5E' },
  nurse:     { active: '#6366F1', hover: '#EEF2FF', bg: '#EEF2FF', activeBg: '#F5F3FF', border: '#E0E7FF', dark: '#4F46E5' },
  doctor:    { active: '#10B981', hover: '#ECFDF5', bg: '#ECFDF5', activeBg: '#F0FDF4', border: '#D1FAE5', dark: '#059669' },
}

const palette = computed(() => ROLE_PALETTE[props.role] || ROLE_PALETTE.pregnant)

const cssVars = computed(() => ({
  '--cat-active': palette.value.active,
  '--cat-hover': palette.value.hover,
  '--cat-bg': palette.value.bg,
  '--cat-active-bg': palette.value.activeBg,
  '--cat-border': palette.value.border,
  '--cat-dark': palette.value.dark,
}))

const activeCategory = ref(props.categories[0])

const visibleCategories = computed(() => {
  const all = getAllCategories()
  return all.filter(c => props.categories.includes(c.key as any))
})

const currentCategory = computed(() =>
  visibleCategories.value.find(c => c.key === activeCategory.value)
)

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

function switchToCategory(catKey: string) {
  activeCategory.value = catKey as typeof props.categories[number]
  const cat = visibleCategories.value.find(c => c.key === catKey)
  if (cat) emit('update:modelValue', [...cat.metrics])
}

function getLabel(metric: string): string {
  // trendName 对化验指标会返回英文 key，需显式判断后再走 labLabel
  const t = TREND_NAME_MAP[metric]
  if (t) return t
  const l = LAB_LABEL_MAP[metric]
  if (l) return l
  return metric
}
</script>

<style scoped>
.metric-category-selector {
  border-radius: 8px;
  overflow: hidden;
}

.category-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px 0;
  background: var(--cat-bg);
  border-bottom: 1px solid var(--cat-border);
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
  background: var(--cat-border);
  padding: 1px 6px;
  border-radius: 10px;
}
.cat-tab.active .cat-count {
  color: var(--cat-active);
  opacity: .85;
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

/* Element Plus 复选框 — 角色色系 */
.metric-checkboxes :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: var(--cat-active) !important;
  border-color: var(--cat-active) !important;
}
.metric-checkboxes :deep(.el-checkbox__input.is-checked:hover .el-checkbox__inner) {
  border-color: var(--cat-active) !important;
}
.metric-checkboxes :deep(.el-checkbox__input.is-focus .el-checkbox__inner) {
  border-color: var(--cat-active) !important;
}
.metric-checkboxes :deep(.el-checkbox__label) {
  font-size: 13px;
  color: #4a4a4a;
}
.metric-checkboxes :deep(.el-checkbox.is-checked .el-checkbox__label) {
  color: var(--cat-active);
  font-weight: 500;
}

/* 全选/取消按钮 */
.toggle-all-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 14px;
  border: 1px solid var(--cat-active);
  color: var(--cat-active);
  background: transparent;
  transition: all .2s;
}
.toggle-all-btn:hover { background: var(--cat-hover); }
.toggle-all-btn.is-deselect {
  background: var(--cat-active);
  color: #fff;
}
.toggle-all-btn.is-deselect:hover {
  background: var(--cat-dark);
}
</style>
