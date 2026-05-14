<template>
  <div class="page-container">
    <!-- ==================== 动态光晕背景 ==================== -->
    <div class="halo-bg">
      <div class="halo-orb halo-orb-1"></div>
      <div class="halo-orb halo-orb-2"></div>
      <div class="halo-backdrop"></div>
    </div>

    <div v-if="loading" class="page-loading">
      <el-icon class="is-loading" :size="44" color="#FB7185"><Loading /></el-icon>
      <p>正在为您准备专属孕期数据...</p>
    </div>

    <div v-else class="content-wrapper">
      <!-- 1. 顶部沉浸式问候卡片 (Hero) -->
      <div class="hero-card">
        <div class="hero-header">
          <div>
            <div class="hero-greeting">早上好，{{ pregnantName }}</div>
            <div class="hero-week">孕{{ gestWeek }}周+{{ gestDay }}天 · 距预产期{{ remainDays }}天</div>
          </div>
          <div class="hero-avatar">
            <el-icon :size="28" color="#FB7185"><Avatar /></el-icon>
          </div>
        </div>
        <div class="baby-progress-card">
          <div class="baby-icon-wrap">
            <el-icon :size="32" color="#FB7185"><Moon /></el-icon>
          </div>
          <div class="baby-text">
            <div class="baby-size">宝宝像一颗 <span class="highlight">{{ babySize }}</span> 大小</div>
            <div class="baby-desc">{{ babyDesc }}</div>
          </div>
        </div>
      </div>

      <!-- 2. 动态行动中心 (Action Center - 通知与待办) -->
      <div class="action-center" v-if="hasNotices">
        <!-- 随访通知 -->
        <div 
          v-if="pendingFollowUps.length > 0" 
          class="compact-notice followup-notice interactive-card"
          @click="goToFollowUp(pendingFollowUps[0].id)"
        >
          <div class="c-notice-left">
            <div class="c-notice-icon"><el-icon><Bell /></el-icon><span class="pulse-dot"></span></div>
            <span class="c-notice-title">您有新的随访对话</span>
          </div>
          <div class="c-notice-right">去回复 <el-icon><ArrowRight /></el-icon></div>
        </div>

        <!-- 医嘱通知 -->
        <div
          v-if="pendingOrders.length > 0"
          class="compact-notice order-notice interactive-card"
          @click="goToOrder(pendingOrders[0].id)"
        >
          <div class="c-notice-left">
            <div class="c-notice-icon"><el-icon><DocumentChecked /></el-icon></div>
            <span class="c-notice-title">{{ pendingOrders.length }} 条新医嘱待查看</span>
          </div>
          <div class="c-notice-right">去查看 <el-icon><ArrowRight /></el-icon></div>
        </div>

        <!-- AI 主动问候 -->
        <div 
          v-if="proactiveGreeting" 
          class="compact-notice ai-notice interactive-card"
          :class="{ 'is-expanded': expandedNotice === 'ai' }"
          @click="expandedNotice = expandedNotice === 'ai' ? null : 'ai'"
        >
          <div class="c-notice-header">
            <div class="c-notice-left">
              <div class="c-notice-icon"><el-icon><ChatRound /></el-icon></div>
              <span class="c-notice-title">智能护士留言</span>
            </div>
            <div class="c-notice-right">
              <el-icon class="expand-icon" :class="{ 'is-rotated': expandedNotice === 'ai' }"><ArrowDown /></el-icon>
            </div>
          </div>
          <div class="c-notice-body" v-show="expandedNotice === 'ai'">
            {{ proactiveGreeting.message }}
          </div>
        </div>
      </div>

      <!-- ==================== 模块导航 (Segmented Control) ==================== -->
      <div class="segmented-control">
        <div class="segment-item" :class="{ active: currentTab === 'assistant' }" @click="currentTab = 'assistant'">日常助手</div>
        <div class="segment-item" :class="{ active: currentTab === 'health' }" @click="currentTab = 'health'">健康追踪</div>
        <div class="segment-item" :class="{ active: currentTab === 'discover' }" @click="currentTab = 'discover'">孕期发现</div>
      </div>

      <transition name="fade-slide" mode="out-in">
        <!-- Tab 1: 日常助手 -->
        <div v-if="currentTab === 'assistant'" class="tab-content" key="assistant">
          <!-- 3. 高频工具区 (Quick Tools) -->
          <div class="section-container tools-section">
            <h3 class="section-title">常用工具</h3>
            <div class="bento-grid">
              <div 
                v-for="tool in tools" 
                :key="tool.label" 
                class="bento-item interactive-card glass-card"
                :class="tool.color"
                @click="tool.action()"
              >
                <div class="bento-icon">
                  <el-icon :size="28"><component :is="tool.icon" /></el-icon>
                </div>
                <span class="bento-label">{{ tool.label }}</span>
              </div>
            </div>
          </div>

          <!-- 4. 今日打卡任务 (Daily Tasks) -->
          <div class="section-container tasks-section">
            <h3 class="section-title">今日打卡</h3>
            <div class="task-grid">
              <div
                v-for="(task, idx) in todayTasks"
                :key="idx"
                class="task-item interactive-card glass-card"
                :class="{ 'is-done': task.done }"
                @click="toggleTask(task)"
              >
                <div class="task-icon" :class="task.color">
                  <el-icon :size="20"><component :is="task.icon" /></el-icon>
                </div>
                <div class="task-content">
                  <span class="task-text">{{ task.title }}</span>
                </div>
                <div class="task-checkbox">
                  <el-icon v-if="task.done" color="#fff" :size="16"><Check /></el-icon>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 2: 健康追踪 -->
        <div v-else-if="currentTab === 'health'" class="tab-content" key="health">
          <!-- 5. 健康趋势 (Health Trends) -->
          <div v-if="healthTrends.length > 0" class="section-container trends-section">
            <h3 class="section-title">近期健康趋势</h3>
            <div class="trend-list">
              <div
                v-for="trend in healthTrends"
                :key="trend.metric"
                class="trend-card glass-card"
                :class="{ 'is-warning': trend.is_normal === false }"
              >
                <div class="trend-header">
                  <div class="trend-title-wrap">
                    <div class="trend-icon-wrap" :class="'icon-' + trend.metric">
                      <el-icon><component :is="getTrendIcon(trend.metric)" /></el-icon>
                    </div>
                    <span class="trend-name">{{ trendName(trend.metric) }}</span>
                  </div>
                  <div class="trend-status" :class="trend.is_normal === false ? 'status-warn' : 'status-ok'">
                    {{ trend.is_normal === false ? '异常' : '正常' }}
                  </div>
                </div>
                <div class="trend-body">
                  <span class="trend-value">{{ trend.current_value }}</span>
                  <span class="trend-unit">{{ translateUnit(trend.unit) }}</span>
                </div>
                <div class="trend-summary">{{ trend.summary }}</div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state glass-card">
            <el-icon :size="32" color="#94A3B8"><Document /></el-icon>
            <p>暂无近期健康数据记录</p>
          </div>
        </div>

        <!-- Tab 3: 孕期发现 -->
        <div v-else-if="currentTab === 'discover'" class="tab-content" key="discover">
          <!-- 孕期变化与科普 -->
          <div class="section-container changes-section">
            <h3 class="section-title">本周变化</h3>
            
            <div class="change-cards-scroll">
              <div class="change-card glass-card">
                <div class="change-card-title"><el-icon><Moon /></el-icon> 宝宝变化</div>
                <p>{{ babyInfo.milestone || '宝宝正在健康成长中...' }}</p>
              </div>
              <div class="change-card glass-card">
                <div class="change-card-title"><el-icon><Female /></el-icon> 妈妈变化</div>
                <p>{{ momChanges }}</p>
              </div>
            </div>

            <h3 class="section-title mt-4">专家建议</h3>
            <el-collapse v-if="recommend" class="soft-collapse glass-card" style="padding: 12px 16px; border-radius: 16px;">
              <el-collapse-item title="饮食建议" name="diet">
                <template #title>
                  <div class="collapse-title"><el-icon><Food /></el-icon> 饮食建议</div>
                </template>
                <p class="collapse-text">{{ recommend.diet_advice || '均衡饮食，补充叶酸和铁质。' }}</p>
              </el-collapse-item>
              <el-collapse-item title="运动建议" name="exercise">
                <template #title>
                  <div class="collapse-title"><el-icon><Bicycle /></el-icon> 运动建议</div>
                </template>
                <p class="collapse-text">{{ recommend.exercise_advice || '每天散步30分钟，避免剧烈运动。' }}</p>
              </el-collapse-item>
              <el-collapse-item title="警惕信号" name="warning">
                <template #title>
                  <div class="collapse-title warning"><el-icon><Warning /></el-icon> 警惕信号</div>
                </template>
                <p class="collapse-text text-warning">{{ recommend.warning_signs || '如出现腹痛、出血请立即就医。' }}</p>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </transition>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { 
  Loading, Check, Clock, ScaleToOriginal, ColdDrink, Opportunity, 
  Calendar, Search, Document, Grid, Bell, ArrowRight, DocumentChecked, 
  ChatRound, Avatar, Moon, Female, Food, Bicycle, Warning,
  Odometer, Sunny, ArrowDown
} from '@element-plus/icons-vue'
import { pregnantApi, recommendApi, followUpApi, chatApi, orderApi } from '@/api/endpoints'

const router = useRouter()
const loading = ref(true)
const homeData = ref<any>(null)
const recommend = ref<any>(null)
const currentTab = ref('assistant')
const pendingFollowUps = ref<any[]>([])
const expandedNotice = ref<string | null>(null)
const proactiveGreeting = ref<{ message: string; greeting_type: string; icon: string } | null>(null)
const healthTrends = ref<Array<{ metric: string; current_value: number; unit: string; trend: string; summary: string; is_normal: boolean | null }>>([])
const pendingOrders = ref<any[]>([])

const hasNotices = computed(() => pendingFollowUps.value.length > 0 || pendingOrders.value.length > 0 || proactiveGreeting.value)

const pregnantName = computed(() => homeData.value?.pregnant?.nickname || homeData.value?.pregnant?.display_name || '准妈妈')
const gestWeek = computed(() => Math.floor((homeData.value?.gestational_day || 0) / 7))
const gestDay = computed(() => (homeData.value?.gestational_day || 0) % 7)
const remainDays = computed(() => Math.max(0, 280 - (homeData.value?.gestational_day || 0)))
const babyInfo = computed(() => homeData.value?.baby_info || {})
const babySize = computed(() => babyInfo.value?.size || '未知')
const babyDesc = computed(() => babyInfo.value?.milestone || '正在健康发育中')

const momChanges = computed(() => {
  const w = gestWeek.value
  if (w <= 12) return '可能出现早孕反应，乳房胀痛，尿频。记得补充叶酸。'
  if (w <= 28) return '腹部逐渐隆起，可能感受到胎动。胃口变好，注意均衡营养。'
  return '腹部明显增大，可能感到腰酸背痛。建议左侧卧位休息，准备待产包。'
})

const todayTasks = ref([
  { title: '体重记录', icon: 'ScaleToOriginal', color: 'bg-rose', done: false },
  { title: '血压测量', icon: 'ColdDrink', color: 'bg-sky', done: false },
  { title: '胎动计数', icon: 'Opportunity', color: 'bg-indigo', done: false },
  { title: '补充叶酸', icon: 'Check', color: 'bg-orange', done: false },
])

function toggleTask(task: any) {
  task.done = !task.done
}

const tools = [
  { label: '体重记录', icon: 'ScaleToOriginal', color: 'text-rose', action: () => router.push('/pregnant/tools') },
  { label: '血压记录', icon: 'ColdDrink', color: 'text-sky', action: () => router.push('/pregnant/tools') },
  { label: '胎动计数', icon: 'Opportunity', color: 'text-indigo', action: () => router.push('/pregnant/tools') },
  { label: '检查日程', icon: 'Calendar', color: 'text-emerald', action: () => router.push('/pregnant/schedule') },
  { label: '知识百科', icon: 'Search', color: 'text-amber', action: () => router.push('/pregnant/chat') },
  { label: '数胎动', icon: 'Document', color: 'text-rose', action: () => router.push('/pregnant/tools') },
  { label: '产检提醒', icon: 'Clock', color: 'text-emerald', action: () => router.push('/pregnant/schedule') },
  { label: '全部工具', icon: 'Grid', color: 'text-slate', action: () => router.push('/pregnant/tools') },
]

async function fetchFollowUps() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const [draftRes, inProgressRes] = await Promise.all([
        followUpApi.list({ status: 'draft', pregnant_id: pid }),
        followUpApi.list({ status: 'in_progress', pregnant_id: pid })
      ])
      pendingFollowUps.value = [...((draftRes.data as any[]) || []), ...((inProgressRes.data as any[]) || [])]
        .sort((a: any, b: any) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
    }
  } catch {}
}

function goToFollowUp(recordId: string) {
  router.push(`/pregnant/tools/followup/${recordId}`)
}

function goToOrder(orderId: string) {
  router.push(`/pregnant/orders/${orderId}`)
}

async function fetchProactiveGreeting() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await chatApi.getProactive(pid)
      proactiveGreeting.value = res.data
    }
  } catch {}
}

async function fetchHealthTrends() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await chatApi.getTrends(pid)
      healthTrends.value = res.data?.trends || []
    }
  } catch {}
}

const loadPregnantOrders = async () => {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await orderApi.getPregnantOrders(pid)
      pendingOrders.value = (res.data || []).filter((o: any) => o.status === 'signed')
    }
  } catch {}
}

function trendName(metric: string): string {
  const names: Record<string, string> = {
    weight: '体重', systolic: '收缩压', diastolic: '舒张压',
    fetal_movement: '胎动', blood_sugar: '血糖', heart_rate: '心率'
  }
  return names[metric] || metric
}

function getTrendIcon(metric: string): string {
  const icons: Record<string, string> = {
    weight: 'ScaleToOriginal', systolic: 'Odometer', diastolic: 'Odometer',
    fetal_movement: 'Opportunity', blood_sugar: 'Sunny', heart_rate: 'Odometer'
  }
  return icons[metric] || 'Document'
}

function translateUnit(unit: string): string {
  const units: Record<string, string> = {
    'kg': '公斤',
    'mmHg': '毫米汞柱',
    'bpm': '次/分',
    'mmol/L': '毫摩尔/升',
    'times/h': '次/小时',
    'times/12h': '次/12小时'
  }
  return units[unit] || unit
}

async function fetchData() {
  loading.value = true
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const homeRes = await pregnantApi.getHome(pid).catch(() => null)
      if (homeRes) homeData.value = homeRes.data
      
      loading.value = false
      recommendApi.get(pid).then((res) => { recommend.value = res.data }).catch(() => {})
      return
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 检查是否已登录，未登录时跳转到登录页
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) {
    // 开发环境：使用测试ID；生产环境：应跳转登录
    if (import.meta.env.DEV) {
      localStorage.setItem('currentPregnantId', 'PT_B3D64A13825E')
    } else {
      router.push('/login')
      return
    }
  }
  fetchData()
  fetchFollowUps()
  fetchProactiveGreeting()
  fetchHealthTrends()
  loadPregnantOrders()
})

onActivated(() => {
  fetchFollowUps()
})
</script>

<style scoped>
/* ========== 全局变量 (Soft UI Colors) ========== */
.page-container {
  --c-rose: #FB7185;
  --c-rose-light: #FFF1F2;
  --c-sky: #38BDF8;
  --c-sky-light: #F0F9FF;
  --c-indigo: #818CF8;
  --c-emerald: #34D399;
  --c-amber: #FBBF24;
  --c-orange: #FB923C;
  --c-slate-800: #1E293B;
  --c-slate-600: #475569;
  --c-slate-400: #94A3B8;
  --c-bg: #F8FAFC;
  --card-shadow: 0 4px 16px rgba(148, 163, 184, 0.08);
  --card-shadow-hover: 0 8px 24px rgba(148, 163, 184, 0.12);
  
  background-color: var(--c-bg);
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
  font-family: 'Nunito Sans', 'PingFang SC', sans-serif;
  color: var(--c-slate-800);
}

.content-wrapper {
  position: relative;
  z-index: 1;
  padding: 16px;
}

/* ==================== 动态光晕背景 (Halo) ==================== */
.halo-bg {
  position: absolute;
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

/* ==================== 毛玻璃卡片 ==================== */
.glass-card {
  background: rgba(255, 255, 255, 0.55) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
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

/* ========== 1. 顶部 Hero 卡片 ========== */
.hero-card {
  background: linear-gradient(135deg, rgba(255,228,230,0.85) 0%, rgba(252,231,243,0.7) 100%);
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.9);
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 8px 24px rgba(251, 113, 133, 0.15);
  margin-bottom: 24px;
}
.hero-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.hero-greeting {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}
.hero-week {
  font-size: 13px;
  color: var(--c-slate-600);
}
.hero-avatar {
  background: white;
  padding: 8px;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(251, 113, 133, 0.2);
}
.baby-progress-card {
  background: rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.8);
}
.baby-icon-wrap {
  background: var(--c-rose-light);
  width: 48px; height: 48px;
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
}
.baby-size {
  font-size: 15px; font-weight: 600; margin-bottom: 4px;
}
.highlight {
  color: var(--c-rose); font-weight: 700;
}
.baby-desc {
  font-size: 13px; color: var(--c-slate-600); line-height: 1.4;
}

/* ========== 2. 通知行动中心 (Compact) ========== */
.action-center {
  display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px;
}
.compact-notice {
  border-radius: 16px; padding: 12px 16px;
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 4px 12px rgba(148, 163, 184, 0.05);
  display: flex; flex-direction: column;
}
.followup-notice { background: linear-gradient(135deg, rgba(255,241,242,0.85), rgba(255,255,255,0.7)); }
.order-notice { background: linear-gradient(135deg, rgba(240,249,255,0.85), rgba(255,255,255,0.7)); }
.ai-notice { background: linear-gradient(135deg, rgba(238,242,255,0.85), rgba(255,255,255,0.7)); }

.c-notice-left, .c-notice-right { display: flex; align-items: center; }
.c-notice-header { display: flex; justify-content: space-between; align-items: center; width: 100%; }

/* Default flex-row for simple notices */
.compact-notice:not(.ai-notice) { flex-direction: row; justify-content: space-between; align-items: center; }

.c-notice-left { gap: 10px; }
.c-notice-icon {
  position: relative; width: 32px; height: 32px; border-radius: 10px;
  background: rgba(255,255,255,0.9); display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
}
.followup-notice .c-notice-icon { color: var(--c-rose); }
.order-notice .c-notice-icon { color: var(--c-sky); }
.ai-notice .c-notice-icon { color: var(--c-indigo); }

.c-notice-title { font-size: 14px; font-weight: 600; color: var(--c-slate-800); }
.c-notice-right { font-size: 12px; color: var(--c-slate-500); gap: 4px; }
.followup-notice .c-notice-right { color: var(--c-rose); font-weight: 600; }

.pulse-dot {
  position: absolute; top: -2px; right: -2px; width: 8px; height: 8px;
  background: var(--c-rose); border-radius: 50%;
  animation: pulse 2s infinite;
}

.expand-icon { transition: transform 0.3s; font-size: 14px; }
.expand-icon.is-rotated { transform: rotate(180deg); }

.c-notice-body {
  margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(0,0,0,0.05);
  font-size: 13px; color: var(--c-slate-600); line-height: 1.5;
}

/* ========== 导航 (Segmented Control) ========== */
.segmented-control {
  display: flex;
  background: rgba(255, 255, 255, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: 14px;
  padding: 4px;
  margin-bottom: 20px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 2px 8px rgba(148, 163, 184, 0.05);
}
.segment-item {
  flex: 1;
  text-align: center;
  padding: 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--c-slate-600);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
  -webkit-tap-highlight-color: transparent;
}
.segment-item.active {
  background: #ffffff;
  color: var(--c-rose);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

/* Tab 切换动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* ========== 3. 通用区块标题 ========== */
.section-container { margin-bottom: 28px; }
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--c-slate-800); }

/* ========== 4. 高频工具区 (Bento Grid) ========== */
.bento-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.bento-item {
  border-radius: 16px; padding: 16px 8px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  box-shadow: var(--card-shadow); min-height: 84px; justify-content: center;
}
.bento-label { font-size: 12px; font-weight: 500; text-align: center; }

/* 文本颜色助手 */
.text-rose { color: var(--c-rose); }
.text-sky { color: var(--c-sky); }
.text-indigo { color: var(--c-indigo); }
.text-emerald { color: var(--c-emerald); }
.text-amber { color: var(--c-amber); }
.text-slate { color: var(--c-slate-600); }

/* ========== 5. 今日任务 ========== */
.task-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.task-item {
  border-radius: 16px; padding: 12px;
  display: flex; align-items: center; gap: 8px; min-height: 64px;
  box-shadow: var(--card-shadow);
}
.task-icon {
  width: 36px; height: 36px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center; color: white;
  flex-shrink: 0;
}
.bg-rose { background: var(--c-rose); }
.bg-sky { background: var(--c-sky); }
.bg-indigo { background: var(--c-indigo); }
.bg-orange { background: var(--c-orange); }
.task-content { flex: 1; min-width: 0; }
.task-text { font-size: 14px; font-weight: 600; transition: color 0.3s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.task-checkbox {
  width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--c-slate-400);
  display: flex; align-items: center; justify-content: center; transition: all 0.3s;
  background: rgba(255,255,255,0.5);
  flex-shrink: 0;
}
.task-item.is-done .task-text { color: var(--c-slate-400); text-decoration: line-through; }
.task-item.is-done .task-checkbox { background: var(--c-emerald); border-color: var(--c-emerald); }

/* ========== 6. 健康趋势 ========== */
.trend-list { 
  display: flex; gap: 12px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 12px;
  -webkit-overflow-scrolling: touch;
}
.trend-list::-webkit-scrollbar { display: none; }
.trend-card {
  min-width: 220px; border-radius: 20px; padding: 16px; flex-shrink: 0;
  box-shadow: 0 4px 16px rgba(148, 163, 184, 0.08);
  border: 1px solid rgba(255,255,255,0.8);
  display: flex; flex-direction: column; gap: 12px;
}
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 32px 16px; border-radius: 16px; gap: 12px;
  color: var(--c-slate-400); font-size: 14px;
}
.trend-card.is-warning { background: linear-gradient(135deg, rgba(255,247,237,0.9), rgba(255,255,255,0.7)) !important; border-color: rgba(251,146,60,0.3); }

.trend-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.trend-title-wrap { display: flex; align-items: center; gap: 8px; }
.trend-icon-wrap {
  width: 32px; height: 32px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  background: var(--c-bg); color: var(--c-slate-600);
}
.icon-weight { color: var(--c-rose); background: var(--c-rose-light); }
.icon-systolic, .icon-diastolic { color: var(--c-sky); background: var(--c-sky-light); }
.icon-fetal_movement { color: var(--c-indigo); background: rgba(129,140,248,0.15); }
.icon-blood_sugar { color: var(--c-amber); background: rgba(251,191,36,0.15); }
.icon-heart_rate { color: var(--c-rose); background: var(--c-rose-light); }

.trend-name { font-size: 14px; font-weight: 600; color: var(--c-slate-600); }
.trend-status { font-size: 11px; padding: 4px 10px; border-radius: 20px; font-weight: 600; }
.status-ok { background: rgba(52,211,153,0.15); color: var(--c-emerald); }
.status-warn { background: rgba(251,146,60,0.15); color: var(--c-orange); }

.trend-body { display: flex; align-items: baseline; gap: 4px; }
.trend-value { font-size: 26px; font-weight: 700; color: var(--c-slate-800); font-family: 'Nunito Sans', sans-serif; }
.trend-unit { font-size: 13px; font-weight: 500; color: var(--c-slate-400); }

.trend-summary { font-size: 13px; color: var(--c-slate-500); line-height: 1.4; }

/* ========== 7. 科普与变化 ========== */
.change-cards-scroll {
  display: flex; gap: 12px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 12px;
  -webkit-overflow-scrolling: touch;
}
.change-cards-scroll::-webkit-scrollbar { display: none; }
.change-card {
  min-width: 240px; border-radius: 16px; padding: 16px;
  box-shadow: var(--card-shadow); flex-shrink: 0;
}
.change-card-title {
  display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; margin-bottom: 8px;
  color: var(--c-indigo);
}
.change-card p { font-size: 13px; color: var(--c-slate-600); line-height: 1.5; margin: 0; }

/* 折叠面板美化 */
.soft-collapse { border: none; background: transparent; }
.collapse-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.collapse-title.warning { color: var(--c-rose); }
.collapse-text { font-size: 14px; color: var(--c-slate-600); line-height: 1.6; padding: 0 12px 12px 12px; margin: 0; }
.text-warning { color: var(--c-rose); }

/* 页面加载 */
.page-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 60vh; color: var(--c-slate-600); gap: 16px;
  position: relative; z-index: 1;
}
</style>
