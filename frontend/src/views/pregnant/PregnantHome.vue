<template>
  <div class="page-container">
    <div v-if="loading" class="page-loading">
      <el-icon class="loading-icon" :size="36"><Loading /></el-icon>
      <p>正在加载...</p>
    </div>

    <template v-else>
      <!-- 顶部渐变问候卡片 -->
      <div class="patient-header-card">
        <div class="patient-header-card__greeting">早上好呀</div>
        <div class="patient-header-card__name">{{ pregnantName }}</div>
        <div class="patient-header-card__week">孕{{ gestWeek }}+{{ gestDay }}周 · 还剩{{ remainDays }}天</div>
        <div class="patient-header-card__baby">
          <div class="patient-header-card__baby-icon">{{ babyEmoji }}</div>
          <div class="patient-header-card__baby-text">
            宝宝现在像一颗<span style="font-weight:700">{{ babySize }}</span>大小<br/>
            {{ babyDesc }}
          </div>
        </div>
      </div>

      <!-- 待处理随访通知 -->
      <div
        v-if="pendingFollowUps.length > 0"
        class="followup-notice-card"
        @click="goToFollowUp(pendingFollowUps[0].id)"
      >
        <div class="followup-notice__inner">
          <div class="followup-notice__icon-wrap">
            <span class="followup-notice__bell">🔔</span>
            <span class="followup-notice__pulse-dot"></span>
          </div>
          <div class="followup-notice__body">
            <div class="followup-notice__title">小护发来随访对话</div>
            <div class="followup-notice__action">点击查看并回复 →</div>
          </div>
        </div>
      </div>

      <!-- 待查看医嘱通知 -->
      <el-card v-if="pendingOrders.length > 0" shadow="hover" class="notification-card" style="border-left: 4px solid #e6a23c;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span style="font-size: 24px;">📋</span>
          <div>
            <div style="font-weight: 600; color: #303133;">待查看医嘱</div>
            <div style="font-size: 13px; color: #909399;">您有 {{ pendingOrders.length }} 条医嘱待查看</div>
          </div>
        </div>
      </el-card>

      <!-- AI 主动问候 -->
      <div
        v-if="proactiveGreeting"
        class="proactive-greeting-card"
      >
        <div class="proactive-greeting__inner">
          <span class="proactive-greeting__icon">{{ proactiveGreeting.icon }}</span>
          <div class="proactive-greeting__text">{{ proactiveGreeting.message }}</div>
        </div>
      </div>

      <!-- 健康趋势 -->
      <div v-if="healthTrends.length > 0" class="health-trends-card">
        <div class="health-trends__title">
          <span class="dot" style="background: #42A5F5"></span>近期健康趋势
        </div>
        <div class="health-trends__list">
          <div
            v-for="trend in healthTrends"
            :key="trend.metric"
            class="trend-item"
            :class="{ 'trend-item--warning': trend.is_normal === false }"
          >
            <div class="trend-item__header">
              <span class="trend-item__icon">{{ trendIcon(trend.metric) }}</span>
              <span class="trend-item__name">{{ trendName(trend.metric) }}</span>
              <span class="trend-item__value">{{ trend.current_value }}{{ trend.unit }}</span>
            </div>
            <div class="trend-item__summary">{{ trend.summary }}</div>
          </div>
        </div>
      </div>

      <!-- 胎宝宝变化 -->
      <div class="patient-info-card">
        <div class="patient-info-card__title">
          <span class="dot"></span>胎宝宝变化
        </div>
        <p class="info-card__text">{{ babyInfo.milestone || '宝宝正在健康成长中...' }}</p>
      </div>

      <!-- 妈妈变化 -->
      <div class="patient-info-card">
        <div class="patient-info-card__title">
          <span class="dot" style="background: #CE93D8"></span>妈妈变化
        </div>
        <p class="info-card__text">{{ momChanges }}</p>
      </div>

      <!-- 今日提醒 -->
      <div class="patient-info-card">
        <div class="patient-info-card__title">
          <span class="dot" style="background: #42A5F5"></span>今日提醒
        </div>
        <div
          v-for="(task, idx) in todayTasks"
          :key="idx"
          class="reminder-item"
          @click="toggleTask(task)"
        >
          <div class="reminder-item__icon" :class="task.color || 'pink'">
            <el-icon :size="18"><component :is="task.icon" /></el-icon>
          </div>
          <span class="reminder-item__text">{{ task.title }}</span>
          <div class="reminder-item__check" :class="{ done: task.done }">
            <span v-if="task.done">✓</span>
          </div>
        </div>
      </div>

      <!-- 孕期助手工具 -->
      <div class="patient-info-card">
        <div class="patient-info-card__title">
          <span class="dot" style="background: #FF9800"></span>孕期助手
        </div>
        <div class="tool-grid">
          <div v-for="tool in tools" :key="tool.label" class="tool-item" @click="tool.action()">
            <div class="tool-item__icon" :class="tool.color">
              <el-icon :size="tool.iconSize || 22"><component :is="tool.icon" /></el-icon>
            </div>
            <span class="tool-item__label">{{ tool.label }}</span>
          </div>
        </div>
      </div>

      <!-- 孕期知识速览 -->
      <div class="patient-info-card" v-if="recommend">
        <div class="patient-info-card__title">
          <span class="dot" style="background: #66BB6A"></span>本周注意事项
        </div>
        <el-collapse>
          <el-collapse-item title="饮食建议" name="diet">
            <p class="info-card__text">{{ recommend.diet_advice || '均衡饮食，补充叶酸和铁质。' }}</p>
          </el-collapse-item>
          <el-collapse-item title="运动建议" name="exercise">
            <p class="info-card__text">{{ recommend.exercise_advice || '每天散步30分钟，避免剧烈运动。' }}</p>
          </el-collapse-item>
          <el-collapse-item title="警惕信号" name="warning">
            <p class="info-card__text" style="color: #EC407A">{{ recommend.warning_signs || '如出现腹痛、出血请立即就医。' }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loading, Check, Clock, ScaleToOriginal, ColdDrink, Opportunity, ChatDotSquare, Calendar, Search, Document, HomeFilled } from '@element-plus/icons-vue'
import { pregnantApi, recommendApi, followUpApi, chatApi, orderApi } from '@/api/endpoints'

const router = useRouter()
const loading = ref(true)
const homeData = ref<any>(null)
const recommend = ref<any>(null)
const pendingFollowUps = ref<any[]>([])
const proactiveGreeting = ref<{ message: string; greeting_type: string; icon: string } | null>(null)
const healthTrends = ref<Array<{ metric: string; current_value: number; unit: string; trend: string; summary: string; is_normal: boolean | null }>>([])
const pendingOrders = ref<any[]>([])

const pregnantName = computed(() => homeData.value?.pregnant?.nickname || homeData.value?.pregnant?.display_name || '准妈妈')
const gestWeek = computed(() => {
  const d = homeData.value?.gestational_day || 0
  return Math.floor(d / 7)
})
const gestDay = computed(() => {
  const d = homeData.value?.gestational_day || 0
  return d % 7
})
const remainDays = computed(() => Math.max(0, 280 - (homeData.value?.gestational_day || 0)))
const babyInfo = computed(() => homeData.value?.baby_info || {})
const babySize = computed(() => babyInfo.value?.size || '?')
const babyDesc = computed(() => babyInfo.value?.milestone || '正在健康发育中')
const babyEmoji = computed(() => {
  const w = gestWeek.value
  if (w <= 8) return '🍇'
  if (w <= 12) return '🍒'
  if (w <= 16) return '🥑'
  if (w <= 20) return '🍌'
  if (w <= 24) return '🌽'
  if (w <= 28) return '🍆'
  if (w <= 32) return '🎃'
  if (w <= 36) return '🥬'
  return '🍉'
})

const momChanges = computed(() => {
  const w = gestWeek.value
  if (w <= 12) return '可能出现早孕反应（恶心、疲劳），乳房胀痛。子宫增大压迫膀胱导致尿频。记得补充叶酸哦。'
  if (w <= 28) return '腹部逐渐隆起，可能开始感受到胎动。皮肤可能出现色素沉着（妊娠线）。胃口变好，注意均衡营养。'
  return '腹部明显增大，可能感到腰酸背痛，睡眠质量下降。胎动更加明显。建议左侧卧位休息，准备好待产包。'
})

const defaultTasks = [
  { title: '今日体重记录', icon: 'ScaleToOriginal', color: 'pink', done: false },
  { title: '今日血压测量', icon: 'ColdDrink', color: 'purple', done: false },
  { title: '今日胎动计数', icon: 'Opportunity', color: 'blue', done: false },
  { title: '补充叶酸和钙片', icon: 'Check', color: 'orange', done: false },
]
const todayTasks = ref<{ title: string; icon: string; color: string; done: boolean; key?: string }[]>([...defaultTasks])

function toggleTask(task: any) {
  task.done = !task.done
}

const tools = [
  { label: '体重记录', icon: 'ScaleToOriginal', color: 'pink', iconSize: 22, action: () => router.push('/pregnant/tools') },
  { label: '血压记录', icon: 'ColdDrink', color: 'purple', iconSize: 22, action: () => router.push('/pregnant/tools') },
  { label: '胎动计数', icon: 'Opportunity', color: 'blue', iconSize: 22, action: () => router.push('/pregnant/tools') },
  { label: '检查日程', icon: 'Calendar', color: 'teal', iconSize: 22, action: () => router.push('/pregnant/schedule') },
  { label: '知识百科', icon: 'Search', color: 'orange', iconSize: 22, action: () => router.push('/pregnant/chat') },
  { label: '产检提醒', icon: 'Clock', color: 'green', iconSize: 22, action: () => router.push('/pregnant/schedule') },
  { label: '数胎动', icon: 'Document', color: 'pink', iconSize: 22, action: () => router.push('/pregnant/tools') },
  { label: '更多', icon: 'HomeFilled', color: 'purple', iconSize: 22, action: () => router.push('/pregnant/tools') },
]

async function fetchFollowUps() {
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    if (pregnantId) {
      // 获取活跃随访：draft（待开始）和 in_progress（进行中）
      const [draftRes, inProgressRes] = await Promise.all([
        followUpApi.list({ status: 'draft', pregnant_id: pregnantId }),
        followUpApi.list({ status: 'in_progress', pregnant_id: pregnantId }),
      ])
      pendingFollowUps.value = [
        ...((draftRes.data as any[]) || []),
        ...((inProgressRes.data as any[]) || []),
      ].sort((a: any, b: any) => {
        // 按创建时间倒序，最新的在前
        const da = new Date(a.created_at || 0).getTime()
        const db = new Date(b.created_at || 0).getTime()
        return db - da
      })
    }
  } catch {
    /* ignore */
  }
}

function goToFollowUp(recordId: string) {
  router.push(`/pregnant/chat?followup=${recordId}`)
}

async function fetchProactiveGreeting() {
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    if (pregnantId) {
      const res = await chatApi.getProactive(pregnantId)
      proactiveGreeting.value = res.data
    }
  } catch {
    /* ignore */
  }
}

async function fetchHealthTrends() {
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    if (pregnantId) {
      const res = await chatApi.getTrends(pregnantId)
      healthTrends.value = res.data?.trends || []
    }
  } catch {
    /* ignore */
  }
}

const loadPregnantOrders = async () => {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await orderApi.getPregnantOrders(pid)
      pendingOrders.value = (res.data || []).filter((o: any) => o.status === 'signed')
    }
  } catch (e) {
    // 静默处理
  }
}

function trendIcon(metric: string): string {
  const icons: Record<string, string> = {
    weight: '⚖️',
    systolic: '🫀',
    diastolic: '🫀',
    fetal_movement: '👶',
    blood_sugar: '🩸',
    heart_rate: '💓',
  }
  return icons[metric] || '📊'
}

function trendName(metric: string): string {
  const names: Record<string, string> = {
    weight: '体重',
    systolic: '收缩压',
    diastolic: '舒张压',
    fetal_movement: '胎动',
    blood_sugar: '血糖',
    heart_rate: '心率',
    emotion_score: '情绪评分',
    sleep_hours: '睡眠时长',
    steps: '运动步数',
  }
  return names[metric] || metric
}

async function fetchData() {
  loading.value = true
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    if (pregnantId) {
      // 主数据必须拿到，推荐数据可以异步加载
      try {
        const homeRes = await pregnantApi.getHome(pregnantId)
        homeData.value = homeRes.data

        if (homeData.value?.today_tasks?.length) {
          todayTasks.value = homeData.value.today_tasks.map((t: any) => ({
            ...t, done: t.status === 'done', color: 'pink',
          }))
        }
      } catch {
        // 主数据失败也放行，使用默认数据
      }

      // 页面先渲染，推荐数据后台加载
      loading.value = false
      recommendApi.get(pregnantId).then((res) => {
        recommend.value = res.data
      }).catch(() => {})
      return
    }
  } catch {
    // 离线模式用默认数据
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 首次进入设置默认孕妇ID
  if (!localStorage.getItem('currentPregnantId')) {
    localStorage.setItem('currentPregnantId', 'PT_B3D64A13825E')
  }
  fetchData()
  fetchFollowUps()
  fetchProactiveGreeting()
  fetchHealthTrends()
  loadPregnantOrders()
})
</script>

<style scoped>
/* 随访通知卡片 */
.followup-notice-card {
  background: linear-gradient(135deg, #F3E5F5 0%, #E1BEE7 100%);
  border-radius: var(--pt-radius);
  padding: 16px 20px;
  margin-bottom: 14px;
  cursor: pointer;
  border: 1px solid rgba(206, 147, 216, 0.3);
  box-shadow: 0 2px 14px rgba(206, 147, 216, 0.15);
  transition: all 0.2s;
}

.followup-notice-card:hover {
  box-shadow: 0 4px 20px rgba(206, 147, 216, 0.25);
  transform: translateY(-1px);
}

.followup-notice-card:active {
  transform: scale(0.98);
}

/* AI 主动问候卡片 */
.proactive-greeting-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border-radius: var(--pt-radius);
  padding: 14px 18px;
  margin-bottom: 14px;
  border: 1px solid rgba(66, 165, 245, 0.2);
  box-shadow: 0 2px 12px rgba(66, 165, 245, 0.1);
}
.proactive-greeting__inner {
  display: flex;
  align-items: center;
  gap: 12px;
}
.proactive-greeting__icon {
  font-size: 24px;
  flex-shrink: 0;
}
.proactive-greeting__text {
  font-size: 14px;
  color: #1565c0;
  line-height: 1.5;
}

/* 健康趋势卡片 */
.health-trends-card {
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border-radius: var(--pt-radius);
  padding: 16px 18px;
  margin-bottom: 14px;
  border: 1px solid rgba(76, 175, 80, 0.2);
}
.health-trends__title {
  font-size: 15px;
  font-weight: 600;
  color: #2e7d32;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.health-trends__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trend-item {
  background: rgba(255, 255, 255, 0.7);
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(76, 175, 80, 0.1);
}
.trend-item--warning {
  background: rgba(255, 243, 224, 0.8);
  border-color: rgba(255, 152, 0, 0.3);
}
.trend-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.trend-item__icon {
  font-size: 16px;
}
.trend-item__name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}
.trend-item__value {
  margin-left: auto;
  font-size: 14px;
  font-weight: 700;
  color: #2e7d32;
}
.trend-item--warning .trend-item__value {
  color: #e65100;
}
.trend-item__summary {
  font-size: 12px;
  color: #666;
  line-height: 1.4;
  padding-left: 24px;
}

.followup-notice__inner {
  display: flex;
  align-items: center;
  gap: 14px;
}

.followup-notice__icon-wrap {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.followup-notice__bell {
  font-size: 24px;
}

.followup-notice__pulse-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #EC407A;
  animation: pulse-dot 1.8s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(1.6);
  }
}

.followup-notice__body {
  flex: 1;
}

.followup-notice__title {
  font-size: 15px;
  font-weight: 700;
  color: #4A148C;
  margin-bottom: 4px;
}

.followup-notice__action {
  font-size: 13px;
  color: #7B1FA2;
  font-weight: 500;
}

/* 页面加载 */
.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--pt-text-muted);
  gap: 12px;
}

.loading-icon {
  animation: spin 1s linear infinite;
  color: var(--pt-primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.info-card__text {
  font-size: 14px;
  color: var(--pt-text-secondary);
  line-height: 1.7;
}

:deep(.el-collapse) {
  border: none;
}

:deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: var(--pt-text);
  border: none;
  background: transparent;
  padding: 8px 0;
}

:deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}

:deep(.el-collapse-item__content) {
  padding: 0 0 8px 0;
}

/* ==================== 移动端响应式 ==================== */
@media (max-width: 430px) {
  /* 头部卡片 - 紧凑 */
  .patient-header-card { padding: 14px 14px; min-height: auto; margin-bottom: 10px; }
  .patient-header-card__name { font-size: 18px; }
  .patient-header-card__week { font-size: 13px; }
  .patient-header-card__baby { margin-top: 6px; }
  .patient-header-card__baby-icon { width: 36px; height: 36px; font-size: 20px; }
  .patient-header-card__baby-text { font-size: 12px; }

  /* 随访通知 */
  .followup-notice-card { padding: 10px 12px; margin-bottom: 8px; }
  .followup-notice__icon-wrap { width: 40px; height: 40px; }
  .followup-notice__bell { font-size: 20px; }
  .followup-notice__title { font-size: 13px; }
  .followup-notice__action { font-size: 12px; }

  /* AI 问候 */
  .proactive-greeting-card { padding: 10px 12px; margin-bottom: 8px; }
  .proactive-greeting__icon { font-size: 20px; }
  .proactive-greeting__text { font-size: 13px; line-height: 1.4; }

  /* 健康趋势 */
  .health-trends-card { padding: 10px 12px; margin-bottom: 8px; }
  .health-trends__title { font-size: 14px; margin-bottom: 8px; }
  .health-trends__list { gap: 6px; }
  .trend-item { padding: 8px 10px; }
  .trend-item__header { gap: 6px; margin-bottom: 2px; }
  .trend-item__value { font-size: 13px; }
  .trend-item__summary { font-size: 11px; padding-left: 22px; }

  /* 信息卡片 */
  .patient-info-card { padding: 12px 14px; margin-bottom: 8px; }
  .patient-info-card__title { font-size: 14px; margin-bottom: 8px; }

  /* 提醒项 */
  .reminder-item { padding: 9px 0; gap: 10px; }
  .reminder-item__icon { width: 32px; height: 32px; }
  .reminder-item__text { font-size: 13px; }

  /* 工具网格 */
  .tool-grid { gap: 4px; }
  .tool-item { padding: 8px 4px; }
  .tool-item__icon { width: 38px; height: 38px; font-size: 18px; }
  .tool-item__label { font-size: 10px; }

  /* 本周注意事项 */
  .info-card__text { font-size: 13px; line-height: 1.5; }
  :deep(.el-collapse-item__header) { padding: 6px 0; font-size: 13px; }
}
</style>
