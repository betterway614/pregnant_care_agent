<template>
  <div class="patient-schedule">
    <!-- ==================== 动态光晕背景 ==================== -->
    <div class="halo-bg">
      <div class="halo-orb halo-orb-1"></div>
      <div class="halo-orb halo-orb-2"></div>
      <div class="halo-backdrop"></div>
    </div>

    <div class="page-container schedule-container content-wrapper">
      <!-- 页面标题 -->
      <div class="schedule-header">
        <h1 class="page-title">检查日程</h1>
        <p class="page-subtitle">查看和管理您的孕期检查计划</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="page-loading">
        <el-icon class="is-loading" :size="36" color="#FB7185"><Loading /></el-icon>
        <p>正在为您加载日程...</p>
      </div>

      <template v-else>
        <!-- 日历视图 -->
        <div class="soft-card calendar-card">
          <el-calendar v-model="selectedDate" class="schedule-calendar">
            <template #date-cell="{ data }">
              <div class="calendar-cell" :class="{ 'has-check': hasCheckOnDate(data.day) }">
                <span class="calendar-day">{{ data.day.split('-').pop()?.replace(/^0/, '') }}</span>
                <span v-if="hasCheckOnDate(data.day)" class="calendar-dot" />
              </div>
            </template>
          </el-calendar>
        </div>

        <!-- 选中日期的日程列表 -->
        <div class="soft-card schedule-list-card">
          <div class="card-header">
            <div class="card-title-row">
              <el-icon color="#FB7185" :size="20"><Calendar /></el-icon>
              <span>{{ selectedDateText }} 检查安排</span>
            </div>
            <div v-if="selectedDateSchedules.length" class="soft-badge">
              {{ selectedDateSchedules.length }} 项
            </div>
          </div>

          <div v-if="selectedDateSchedules.length" class="schedule-list">
            <div
              v-for="item in selectedDateSchedules"
              :key="item.id"
              class="schedule-item interactive-card"
              :class="{ 'is-completed': item.status === 'completed' }"
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
                    <div
                      class="check-type-tag"
                      :class="getCheckTypeTagType(item.node_type)"
                    >
                      {{ getCheckTypeLabel(item.node_type) }}
                    </div>
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

          <div v-else class="empty-state">
            <el-icon :size="48" color="#94A3B8"><Calendar /></el-icon>
            <p>当前日期暂无检查安排</p>
            <span class="empty-hint">选择日历中有<span class="dot-legend">粉色小点</span>标记的日期查看详情</span>
          </div>
        </div>

        <!-- 近期所有检查概览 -->
        <div class="soft-card upcoming-card">
          <div class="card-header">
            <div class="card-title-row">
              <el-icon color="#38BDF8" :size="20"><List /></el-icon>
              <span>所有检查计划</span>
            </div>
            <div v-if="allSchedules.length" class="soft-badge">
              {{ completedCount }} / {{ allSchedules.length }} 项
            </div>
          </div>

          <div v-if="allSchedules.length" class="all-schedule-list">
            <div
              v-for="item in sortedAllSchedules"
              :key="item.id"
              class="all-schedule-item interactive-card"
              :class="{ 'is-completed': item.status === 'completed' }"
            >
              <div class="all-item-date">
                <span class="all-date-text">{{ formatDateShort(item.scheduled_date) }}</span>
              </div>
              <div class="all-item-info">
                <span class="all-item-name">{{ item.item }}</span>
                <div
                  class="check-type-tag"
                  :class="getCheckTypeTagType(item.node_type)"
                >
                  {{ getCheckTypeLabel(item.node_type) }}
                </div>
              </div>
              <div class="all-item-status">
                <el-icon
                  v-if="item.status === 'completed'"
                  color="#34D399"
                  :size="20"
                >
                  <CircleCheck />
                </el-icon>
                <el-icon
                  v-else-if="item.status === 'pending'"
                  color="#94A3B8"
                  :size="20"
                >
                  <Clock />
                </el-icon>
                <el-icon
                  v-else
                  color="#FBBF24"
                  :size="20"
                >
                  <Warning />
                </el-icon>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <el-icon :size="48" color="#94A3B8"><List /></el-icon>
            <p>暂无检查计划</p>
          </div>
        </div>
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
import { useAppStore } from '@/stores/app'

/* ============ 常量 ============ */
const appStore = useAppStore()
const PREGNANT_ID = computed(() => appStore.currentPregnantId || '')

/* ============ 响应式状态 ============ */
const loading = ref(true)
const selectedDate = ref(new Date())
const allSchedules = ref<ScheduleNode[]>([])

/* ============ 计算属性 ============ */
const selectedDateStr = computed(() => {
  const d = selectedDate.value
  const y = d.getFullYear()
  const m = (d.getMonth() + 1).toString().padStart(2, '0')
  const day = d.getDate().toString().padStart(2, '0')
  return `${y}-${m}-${day}`
})

const selectedDateText = computed(() => {
  const d = selectedDate.value
  const m = d.getMonth() + 1
  const day = d.getDate()
  const weekNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${m}月${day}日 ${weekNames[d.getDay()]}`
})

const checkDateSet = computed<Set<string>>(() => {
  const set = new Set<string>()
  for (const s of allSchedules.value) {
    if (s.scheduled_date) {
      set.add(s.scheduled_date.split('T')[0])
    }
  }
  return set
})

const selectedDateSchedules = computed(() => {
  return allSchedules.value.filter((s) => {
    const dateStr = s.scheduled_date?.split('T')[0] || ''
    return dateStr === selectedDateStr.value
  })
})

const completedCount = computed(() => {
  return allSchedules.value.filter((s) => s.status === 'completed').length
})

const sortedAllSchedules = computed(() => {
  return [...allSchedules.value].sort((a, b) => {
    if (a.status !== b.status) {
      return a.status === 'completed' ? 1 : -1
    }
    return (a.scheduled_date || '').localeCompare(b.scheduled_date || '')
  })
})

/* ============ 工具函数 ============ */
function hasCheckOnDate(dayStr: string): boolean {
  return checkDateSet.value.has(dayStr)
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '--'
  return dateStr.split('T')[0] || dateStr
}

function formatDateShort(dateStr?: string): string {
  if (!dateStr) return '--'
  const raw = dateStr.split('T')[0] || dateStr
  const parts = raw.split('-')
  return `${parts[1] || '--'}-${parts[2] || '--'}`
}

function getCheckTypeTagType(type?: string): string {
  if (!type) return 'tag-info'
  const t = type.toLowerCase()
  if (['fgr_high_risk', 'urgent'].includes(t)) return 'tag-danger'
  if (['routine', '常规'].includes(t)) return 'tag-success'
  if (['important'].includes(t)) return 'tag-warning'
  return 'tag-info'
}

function getCheckTypeLabel(type?: string): string {
  if (!type) return '常规'
  const labelMap: Record<string, string> = {
    routine: '常规',
    fgr_high_risk: '高风险',
    urgent: '紧急',
    important: '重要',
    examination: '检查',
    follow_up: '随访',
  }
  return labelMap[type] || type
}

function getStatusClass(status: string): string {
  if (status === 'completed') return 'status-completed'
  if (status === 'pending') return 'status-pending'
  return 'status-other'
}

function getStatusColor(status: string): string {
  if (status === 'completed') return '#34D399'
  if (status === 'pending') return '#94A3B8'
  return '#FBBF24'
}

/* ============ 数据加载 ============ */
async function loadSchedules() {
  loading.value = true
  try {
    const res = await scheduleApi.get(PREGNANT_ID.value)
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
/* ========== 全局变量 (Soft UI Colors) ========== */
.patient-schedule {
  --c-rose: #FB7185;
  --c-rose-light: #FFF1F2;
  --c-sky: #38BDF8;
  --c-sky-light: #F0F9FF;
  --c-emerald: #34D399;
  --c-emerald-light: #ECFDF5;
  --c-amber: #FBBF24;
  --c-amber-light: #FFFBEB;
  --c-slate-800: #1E293B;
  --c-slate-600: #475569;
  --c-slate-400: #94A3B8;
  --c-bg: #F8FAFC;
  --card-shadow: 0 4px 16px rgba(148, 163, 184, 0.1);
  --card-shadow-hover: 0 8px 24px rgba(148, 163, 184, 0.15);

  background: var(--c-bg);
  min-height: 100vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  font-family: 'Nunito Sans', 'PingFang SC', sans-serif;
  position: relative;
}

.content-wrapper {
  position: relative;
  z-index: 1;
}

/* ==================== 动态光晕背景 (Halo) ==================== */
.halo-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}
.halo-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.85;
  animation: halo-float 20s infinite ease-in-out alternate;
}
.halo-orb-1 {
  top: -10%; left: -20%;
  width: 140vw; height: 140vw;
  background: radial-gradient(circle, #FECDD3 0%, transparent 70%);
}
.halo-orb-2 {
  top: 40%; right: -20%;
  width: 120vw; height: 120vw;
  background: radial-gradient(circle, #FCE7F3 0%, transparent 70%);
  animation-delay: -5s;
}
.halo-backdrop {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
}
@keyframes halo-float {
  0% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(15vw, 15vh) scale(1.1); }
  100% { transform: translate(-10vw, 10vh) scale(0.9); }
}

.schedule-container {
  max-width: 480px;
  margin: 0 auto;
  padding: 24px 16px 40px;
}

/* ========== 交互动画基础 ========== */
.interactive-card {
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  -webkit-tap-highlight-color: transparent;
}
.interactive-card:active {
  transform: scale(0.96);
}

/* ========== 页面头部 ========== */
.schedule-header {
  margin-bottom: 24px;
}

.schedule-header .page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--c-slate-800);
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--c-slate-600);
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
  color: var(--c-slate-600);
}

/* ========== 通用软卡片 ========== */
.soft-card {
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 20px;
  box-shadow: var(--card-shadow);
  margin-bottom: 20px;
  overflow: hidden;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--c-bg);
}
.card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--c-slate-800);
}
.soft-badge {
  background: var(--c-bg);
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--c-slate-600);
}

/* ========== 日历覆盖样式 ========== */
.calendar-card {
  padding: 12px;
}
.schedule-calendar {
  --el-calendar-border: transparent;
  --el-calendar-header-border-bottom: transparent;
}
.schedule-calendar :deep(.el-calendar__header) {
  padding: 8px 12px 8px;
}
.schedule-calendar :deep(.el-calendar__title) {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-slate-800);
}
.schedule-calendar :deep(.el-calendar-table td) {
  border: none !important;
  padding: 2px !important;
}
.schedule-calendar :deep(.el-calendar-table th) {
  font-size: 13px;
  color: var(--c-slate-400);
  border: none !important;
}
.schedule-calendar :deep(.el-calendar-table td.is-selected) {
  background-color: transparent;
}
.schedule-calendar :deep(.el-calendar-table td.is-today) {
  background-color: transparent;
}
.schedule-calendar :deep(.el-calendar-table td.is-selected .calendar-day) {
  background-color: var(--c-rose);
  color: white;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(251, 113, 133, 0.4);
}
.schedule-calendar :deep(.el-calendar-table td.is-today .calendar-day:not(.is-selected .calendar-day)) {
  color: var(--c-rose);
  font-weight: 700;
}

.schedule-calendar :deep(.el-calendar-day) {
  height: 44px !important;
  padding: 0 !important;
  display: flex;
  align-items: center;
  justify-content: center;
}

.calendar-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  position: relative;
}
.calendar-day {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-slate-800);
  transition: all 0.2s ease;
}
.schedule-calendar :deep(.el-calendar-table .prev-month .calendar-day),
.schedule-calendar :deep(.el-calendar-table .next-month .calendar-day) {
  color: var(--c-slate-400);
  font-weight: 400;
}
.calendar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--c-rose);
  position: absolute;
  bottom: 2px;
}

/* ========== 日程列表项 ========== */
.schedule-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.schedule-item {
  background: var(--c-bg);
  border-radius: 16px;
  padding: 16px;
}
.schedule-item.is-completed {
  opacity: 0.6;
}
.schedule-item-left {
  display: flex;
  gap: 16px;
}
.schedule-time-indicator {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.schedule-time-indicator.status-completed { background: var(--c-emerald-light); }
.schedule-time-indicator.status-pending { background: white; border: 1px solid var(--c-slate-400); }
.schedule-time-indicator.status-other { background: var(--c-amber-light); }

.schedule-item-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.schedule-item-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.schedule-item-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--c-slate-800);
  line-height: 1.4;
}
.schedule-item-bottom {
  display: flex;
  align-items: center;
  gap: 16px;
}
.schedule-item-time {
  font-size: 13px;
  color: var(--c-slate-600);
  display: flex;
  align-items: center;
  gap: 6px;
}
.schedule-item-status {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-slate-600);
}

/* ========== 自定义标签 ========== */
.check-type-tag {
  padding: 4px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.tag-danger { background: var(--c-rose-light); color: var(--c-rose); }
.tag-warning { background: var(--c-amber-light); color: var(--c-amber); }
.tag-success { background: var(--c-emerald-light); color: var(--c-emerald); }
.tag-info { background: white; color: var(--c-slate-600); border: 1px solid var(--c-bg); }

/* ========== 全部日程概览 ========== */
.all-schedule-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.all-schedule-item {
  background: var(--c-bg);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.all-schedule-item.is-completed {
  opacity: 0.6;
}
.all-item-date {
  background: white;
  padding: 8px;
  border-radius: 12px;
  min-width: 54px;
  text-align: center;
}
.all-date-text {
  font-size: 14px;
  font-weight: 700;
  color: var(--c-slate-800);
}
.all-item-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.all-item-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--c-slate-800);
}

/* ========== 空状态 ========== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--c-slate-400);
  text-align: center;
}
.empty-state p {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--c-slate-600);
}
.empty-hint {
  font-size: 13px;
}
.dot-legend {
  color: var(--c-rose);
  font-weight: 700;
  margin: 0 4px;
}

</style>
