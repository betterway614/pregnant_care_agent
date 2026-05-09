<template>
  <div class="patient-schedule">
    <div class="page-container schedule-container">
      <!-- 页面标题 -->
      <div class="schedule-header">
        <h1 class="page-title">检查日程</h1>
        <p class="page-subtitle">查看和管理您的孕期检查计划</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="page-loading">
        <el-icon class="loading-icon" :size="36"><Loading /></el-icon>
        <p>正在加载日程...</p>
      </div>

      <template v-else>
        <!-- 日历视图 -->
        <el-card shadow="hover" class="calendar-card">
          <el-calendar v-model="selectedDate" class="schedule-calendar">
            <template #date-cell="{ data }">
              <div class="calendar-cell" :class="{ 'has-check': hasCheckOnDate(data.day) }">
                <span class="calendar-day">{{ data.day.split('-').pop()?.replace(/^0/, '') }}</span>
                <span v-if="hasCheckOnDate(data.day)" class="calendar-dot" />
              </div>
            </template>
          </el-calendar>
        </el-card>

        <!-- 选中日期的日程列表 -->
        <el-card shadow="hover" class="schedule-list-card">
          <template #header>
            <div class="card-header">
              <div class="card-title-row">
                <el-icon color="var(--pt-primary)" :size="20"><Calendar /></el-icon>
                <span>{{ selectedDateText }} 检查安排</span>
              </div>
              <el-tag v-if="selectedDateSchedules.length" size="small" round effect="plain">
                {{ selectedDateSchedules.length }} 项
              </el-tag>
            </div>
          </template>

          <div v-if="selectedDateSchedules.length" class="schedule-list">
            <div
              v-for="item in selectedDateSchedules"
              :key="item.id"
              class="schedule-item"
              :class="{ 'schedule-item--completed': item.status === 'completed' }"
            >
              <div class="schedule-item-left">
                <div class="schedule-time-indicator" :class="getStatusClass(item.status)">
                  <el-icon
                    :size="16"
                    :color="getStatusColor(item.status)"
                  >
                    <CircleCheck v-if="item.status === 'completed'" />
                    <Clock v-else-if="item.status === 'pending'" />
                    <Close v-else />
                  </el-icon>
                </div>
                <div class="schedule-item-content">
                  <div class="schedule-item-top">
                    <span class="schedule-item-name">{{ item.item }}</span>
                    <el-tag
                      :type="getCheckTypeTagType(item.node_type)"
                      size="small"
                      effect="plain"
                      round
                      class="check-type-tag"
                    >
                      {{ getCheckTypeLabel(item.node_type) }}
                    </el-tag>
                  </div>
                  <div class="schedule-item-bottom">
                    <span class="schedule-item-time">
                      <el-icon :size="13"><Clock /></el-icon>
                      {{ formatDate(item.scheduled_date) }}
                    </span>
                    <span class="schedule-item-status">
                      {{ item.status === 'completed' ? '已完成' : item.status === 'pending' ? '待完成' : item.status }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <el-empty v-else description="当前日期暂无检查安排" :image-size="60">
            <template #description>
              <p class="empty-hint">选择日历中有<span class="dot-legend">绿色圆点</span>标记的日期查看详情</p>
            </template>
          </el-empty>
        </el-card>

        <!-- 近期所有检查概览 -->
        <el-card shadow="hover" class="upcoming-card">
          <template #header>
            <div class="card-header">
              <div class="card-title-row">
                <el-icon color="var(--pt-accent)" :size="20"><List /></el-icon>
                <span>所有检查计划</span>
              </div>
              <el-tag v-if="allSchedules.length" size="small" round effect="plain">
                {{ completedCount }} / {{ allSchedules.length }} 项
              </el-tag>
            </div>
          </template>

          <div v-if="allSchedules.length" class="all-schedule-list">
            <div
              v-for="item in sortedAllSchedules"
              :key="item.id"
              class="all-schedule-item"
              :class="{ 'all-schedule-item--completed': item.status === 'completed' }"
            >
              <div class="all-item-date">
                <span class="all-date-text">{{ formatDateShort(item.scheduled_date) }}</span>
              </div>
              <div class="all-item-info">
                <span class="all-item-name">{{ item.item }}</span>
                <el-tag
                  :type="getCheckTypeTagType(item.node_type)"
                  size="small"
                  effect="plain"
                  round
                >
                  {{ getCheckTypeLabel(item.node_type) }}
                </el-tag>
              </div>
              <div class="all-item-status">
                <el-icon
                  v-if="item.status === 'completed'"
                  color="var(--pt-primary)"
                  :size="18"
                >
                  <CircleCheck />
                </el-icon>
                <el-icon
                  v-else-if="item.status === 'pending'"
                  color="var(--pt-text-muted)"
                  :size="18"
                >
                  <Clock />
                </el-icon>
                <el-icon
                  v-else
                  color="#F57C00"
                  :size="18"
                >
                  <Warning />
                </el-icon>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无检查计划" :image-size="60" />
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Loading,
  Calendar,
  List,
  Clock,
  CircleCheck,
  Close,
  Warning,
} from '@element-plus/icons-vue'
import { scheduleApi } from '@/api/endpoints'
import type { ScheduleNode } from '@/types'
import { ElMessage } from 'element-plus'

/* ============ 常量 ============ */
const PREGNANT_ID = 'current-pregnant-id'

/* ============ 响应式状态 ============ */
const loading = ref(true)
const selectedDate = ref(new Date())
const allSchedules = ref<ScheduleNode[]>([])

/* ============ 计算属性 ============ */
/** 选中日期字符串 YYYY-MM-DD */
const selectedDateStr = computed(() => {
  const d = selectedDate.value
  const y = d.getFullYear()
  const m = (d.getMonth() + 1).toString().padStart(2, '0')
  const day = d.getDate().toString().padStart(2, '0')
  return `${y}-${m}-${day}`
})

/** 选中日期的可读文本 */
const selectedDateText = computed(() => {
  const d = selectedDate.value
  const m = d.getMonth() + 1
  const day = d.getDate()
  const weekNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${m}月${day}日 ${weekNames[d.getDay()]}`
})

/** 有检查安排的日期集合 */
const checkDateSet = computed<Set<string>>(() => {
  const set = new Set<string>()
  for (const s of allSchedules.value) {
    if (s.scheduled_date) {
      set.add(s.scheduled_date.split('T')[0])
    }
  }
  return set
})

/** 选中日期的日程列表 */
const selectedDateSchedules = computed(() => {
  return allSchedules.value.filter((s) => {
    const dateStr = s.scheduled_date?.split('T')[0] || ''
    return dateStr === selectedDateStr.value
  })
})

/** 已完成数量 */
const completedCount = computed(() => {
  return allSchedules.value.filter((s) => s.status === 'completed').length
})

/** 排序后的所有日程 */
const sortedAllSchedules = computed(() => {
  return [...allSchedules.value].sort((a, b) => {
    // 待完成在前，已完成在后
    if (a.status !== b.status) {
      return a.status === 'completed' ? 1 : -1
    }
    // 同一状态下按日期排序
    return (a.scheduled_date || '').localeCompare(b.scheduled_date || '')
  })
})

/* ============ 工具函数 ============ */
/** 判断某天是否有检查 */
function hasCheckOnDate(dayStr: string): boolean {
  return checkDateSet.value.has(dayStr)
}

/** 格式化日期 */
function formatDate(dateStr?: string): string {
  if (!dateStr) return '--'
  return dateStr.split('T')[0] || dateStr
}

/** 简短日期格式 MM-DD */
function formatDateShort(dateStr?: string): string {
  if (!dateStr) return '--'
  const raw = dateStr.split('T')[0] || dateStr
  const parts = raw.split('-')
  return `${parts[1] || '--'}-${parts[2] || '--'}`
}

/** 获取检查类型标签颜色 */
function getCheckTypeTagType(type?: string): 'danger' | 'warning' | 'success' | 'info' {
  if (!type) return 'info'
  const t = type.toLowerCase()
  if (['fgr_high_risk', 'urgent'].includes(t)) return 'danger'
  if (['routine', '常规'].includes(t)) return 'success'
  if (['important'].includes(t)) return 'warning'
  return 'info'
}

/** 获取检查类型标签文字 */
function getCheckTypeLabel(type?: string): string {
  if (!type) return '常规'
  const labelMap: Record<string, string> = {
    routine: '常规',
    fgr_high_risk: 'FGR 高风险',
    urgent: '紧急',
    important: '重要',
    examination: '检查',
    follow_up: '随访',
  }
  return labelMap[type] || type
}

/** 获取状态 CSS 类名 */
function getStatusClass(status: string): string {
  if (status === 'completed') return 'status-completed'
  if (status === 'pending') return 'status-pending'
  return 'status-other'
}

/** 获取状态图标颜色 */
function getStatusColor(status: string): string {
  if (status === 'completed') return 'var(--pt-primary)'
  if (status === 'pending') return 'var(--pt-text-muted)'
  return '#F57C00'
}

/* ============ 数据加载 ============ */
async function loadSchedules() {
  loading.value = true
  try {
    const res = await scheduleApi.get(PREGNANT_ID)
    allSchedules.value = res.data || []
  } catch (err) {
    console.error('加载日程失败:', err)
    ElMessage.error('加载日程失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

/* ============ 生命周期 ============ */
onMounted(() => {
  loadSchedules()
})
</script>

<style scoped>
.patient-schedule {
  height: 100%;
  background: #FFF5F7;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 24px;
  box-sizing: border-box;
}

.schedule-container {
  max-width: 480px;
  margin: 0 auto;
  padding: 28px 20px 24px;
}

/* ========== 页面头部 ========== */
.schedule-header {
  margin-bottom: 24px;
}

.schedule-header .page-title {
  font-family: 'Figtree', sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--pt-text);
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--pt-text-muted);
  margin: 0;
}

/* ========== 加载状态 ========== */
.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 16px;
  color: var(--pt-text-muted);
}

.loading-icon {
  animation: spin 1.2s linear infinite;
  color: var(--pt-primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ========== 日历卡片 ========== */
.calendar-card {
  margin-bottom: 16px;
  border-radius: var(--pt-radius) !important;
  box-shadow: var(--pt-shadow);
  border: 1px solid var(--pt-border) !important;
  transition: 0.2s ease;
}

.calendar-card:hover {
  box-shadow: var(--pt-shadow-hover);
}

.calendar-card :deep(.el-card__body) {
  padding: 12px;
}

.schedule-calendar {
  --el-calendar-border: var(--pt-border);
  --el-calendar-header-border-bottom: var(--pt-border);
  --el-calendar-cell-width: auto;
}

.schedule-calendar :deep(.el-calendar-table) {
  table-layout: fixed;
}

.schedule-calendar :deep(.el-calendar-table td) {
  height: auto !important;
  min-height: 0;
}

.schedule-calendar :deep(.el-calendar-table th) {
  font-size: 12px;
  font-weight: 600;
  color: var(--pt-text-muted);
  padding: 6px 0;
}

.schedule-calendar :deep(.el-calendar-table tbody tr td) {
  height: auto !important;
}

.schedule-calendar :deep(.el-calendar__header) {
  padding: 10px 12px;
}

.schedule-calendar :deep(.el-calendar__title) {
  font-family: 'Figtree', sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--pt-text);
}

.schedule-calendar :deep(.el-calendar__button-group .el-button) {
  color: var(--pt-text-secondary);
}

.schedule-calendar :deep(.el-calendar__button-group .el-button:hover) {
  color: var(--pt-primary);
}

/* ========== 日历单元格 ========== */
.calendar-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding-top: 4px;
  position: relative;
  min-height: 32px;
}

.calendar-day {
  font-size: 13px;
  font-weight: 500;
  color: var(--pt-text);
}

.schedule-calendar :deep(.el-calendar-table .current .calendar-day) {
  color: #fff;
}

.calendar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: linear-gradient(135deg, #F48FB1, #EC407A);
  margin-top: 3px;
  box-shadow: 0 0 4px rgba(244, 143, 177, 0.35);
  animation: dotFadeIn 0.3s ease;
}

@keyframes dotFadeIn {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

/* 今日样式覆盖 */
.schedule-calendar :deep(.el-calendar-table td.is-today) {
  background: var(--pt-primary-light);
}

/* ========== 日程列表卡片 ========== */
.schedule-list-card {
  margin-bottom: 16px;
  border-radius: var(--pt-radius) !important;
  box-shadow: var(--pt-shadow);
  border: 1px solid var(--pt-border) !important;
  transition: 0.2s ease;
}

.schedule-list-card:hover {
  box-shadow: var(--pt-shadow-hover);
}

.schedule-list-card :deep(.el-card__header) {
  padding: 16px 20px;
  background: var(--pt-card-bg-solid);
  border-bottom: 1px solid var(--pt-border);
}

.schedule-list-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Figtree', sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--pt-text);
}

/* ========== 日程项 ========== */
.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.schedule-item {
  padding: 14px 16px;
  border-radius: var(--pt-radius-sm);
  background: var(--pt-card-bg-solid);
  transition: 0.2s ease;
}

.schedule-item:hover {
  background: var(--pt-primary-light);
}

.schedule-item--completed {
  opacity: 0.65;
}

.schedule-item-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.schedule-time-indicator {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.schedule-time-indicator.status-completed {
  background: #FCE4EC;
}

.schedule-time-indicator.status-pending {
  background: var(--pt-card-bg-solid);
  border: 1.5px solid var(--pt-border);
}

.schedule-time-indicator.status-other {
  background: #FFF3E0;
}

.schedule-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.schedule-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.schedule-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--pt-text);
}

.check-type-tag {
  flex-shrink: 0;
}

.schedule-item-bottom {
  display: flex;
  align-items: center;
  gap: 16px;
}

.schedule-item-time {
  font-size: 12px;
  color: var(--pt-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

.schedule-item-status {
  font-size: 12px;
  font-weight: 500;
  color: var(--pt-text-secondary);
}

/* ========== 空白提示 ========== */
.empty-hint {
  font-size: 12px;
  color: var(--pt-text-muted);
  margin: 0;
}

.dot-legend {
  color: var(--pt-primary);
  font-weight: 500;
}

/* ========== 所有检查概览卡片 ========== */
.upcoming-card {
  margin-bottom: 16px;
  border-radius: var(--pt-radius) !important;
  box-shadow: var(--pt-shadow);
  border: 1px solid var(--pt-border) !important;
  transition: 0.2s ease;
}

.upcoming-card:hover {
  box-shadow: var(--pt-shadow-hover);
}

.upcoming-card :deep(.el-card__header) {
  padding: 16px 20px;
  background: var(--pt-card-bg-solid);
  border-bottom: 1px solid var(--pt-border);
}

.upcoming-card :deep(.el-card__body) {
  padding: 16px 20px;
}

/* ========== 所有日程列表 ========== */
.all-schedule-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.all-schedule-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--pt-radius-sm);
  background: var(--pt-card-bg-solid);
  transition: 0.2s ease;
}

.all-schedule-item:hover {
  background: var(--pt-primary-light);
}

.all-schedule-item--completed {
  opacity: 0.6;
}

.all-item-date {
  min-width: 48px;
  text-align: center;
  flex-shrink: 0;
}

.all-date-text {
  font-family: 'Figtree', sans-serif;
  font-size: 13px;
  font-weight: 600;
  color: var(--pt-text);
}

.all-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.all-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--pt-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.all-item-status {
  flex-shrink: 0;
}

/* ========== 触摸反馈 ========== */
.schedule-item {
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.15s ease, background 0.2s ease;
}

.schedule-item:active {
  transform: scale(0.97);
}

.tab-item {
  -webkit-tap-highlight-color: transparent;
}

/* ========== 响应式 ========== */
@media (min-width: 769px) {
  .schedule-container {
    max-width: 560px;
    padding: 32px 24px 48px;
  }
}

@media (max-width: 430px) {
  .schedule-container {
    padding: 16px 14px 20px;
    max-width: 480px;
    gap: 10px;
  }

  .schedule-header {
    margin-bottom: 16px;
  }

  .schedule-header .page-title {
    font-size: 20px;
  }

  .page-subtitle {
    font-size: 12px;
  }

  .schedule-calendar :deep(.el-calendar__title) {
    font-size: 14px;
  }

  .schedule-calendar :deep(.el-calendar__header) {
    padding: 6px 4px;
  }

  .schedule-calendar :deep(.el-calendar__button-group .el-button) {
    padding: 4px 8px;
    font-size: 12px;
  }

  .schedule-calendar :deep(.el-calendar-table) {
    table-layout: fixed;
  }

  .schedule-calendar :deep(.el-calendar-table th) {
    font-size: 11px;
    padding: 4px 0;
  }

  .schedule-calendar :deep(.el-calendar-table td) {
    height: auto !important;
    padding: 2px !important;
    border-bottom: none !important;
  }

  .schedule-calendar :deep(.el-calendar-table tbody tr) {
    height: auto !important;
  }

  .schedule-calendar :deep(.el-calendar-table tbody tr td) {
    height: 36px !important;
    padding: 2px !important;
  }

  .calendar-cell {
    min-height: 0;
    padding-top: 2px;
  }

  .calendar-day {
    font-size: 12px;
    line-height: 1.3;
  }

  .calendar-card :deep(.el-card__body) {
    padding: 6px 8px;
  }

  .schedule-list-card :deep(.el-card__header),
  .upcoming-card :deep(.el-card__header) {
    padding: 12px 14px;
  }

  .schedule-list-card :deep(.el-card__body),
  .upcoming-card :deep(.el-card__body) {
    padding: 12px 14px;
  }

  .card-title-row {
    font-size: 14px;
  }

  .schedule-item {
    padding: 12px 14px;
  }

  .schedule-item-name {
    font-size: 13px;
  }

  .schedule-item-time,
  .schedule-item-status {
    font-size: 11px;
  }

  .all-schedule-item {
    padding: 10px 12px;
    gap: 10px;
  }

  .all-item-date {
    min-width: 42px;
  }

  .all-date-text {
    font-size: 12px;
  }

  .all-item-name {
    font-size: 13px;
  }

  .all-item-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}

@media (max-width: 374px) {
  .schedule-container {
    padding: 12px 10px 16px;
  }

  .schedule-header .page-title {
    font-size: 18px;
  }

  .schedule-calendar :deep(.el-calendar-table tbody tr td) {
    height: 32px !important;
    padding: 1px !important;
  }

  .schedule-calendar :deep(.el-calendar__header) {
    padding: 4px 2px;
  }

  .schedule-calendar :deep(.el-calendar-table th) {
    font-size: 10px;
    padding: 3px 0;
  }

  .calendar-day {
    font-size: 11px;
  }

  .schedule-item {
    padding: 10px 12px;
  }

  .schedule-item-name {
    font-size: 12px;
  }

  .all-schedule-item {
    padding: 8px 10px;
  }
}
</style>
