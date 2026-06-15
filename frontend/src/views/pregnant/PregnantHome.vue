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
            <div class="hero-greeting">{{ greetingText }}，{{ pregnantName }}</div>
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
        >
          <div class="c-notice-left" @click="goToFollowUp(pendingFollowUps[0].id)">
            <div class="c-notice-icon"><el-icon><Bell /></el-icon><span class="pulse-dot"></span></div>
            <span class="c-notice-title">您有新的随访对话</span>
          </div>
          <div class="c-notice-right">
            <span class="dismiss-btn" @click.stop="dismissActionCenter('followup')">忽略</span>
            <span class="go-link" @click="goToFollowUp(pendingFollowUps[0].id)">去回复 <el-icon><ArrowRight /></el-icon></span>
          </div>
        </div>

        <!-- 医嘱通知 -->
        <div
          v-if="pendingOrders.length > 0"
          class="compact-notice order-notice interactive-card"
          :class="{ 'is-expanded': expandedNotice === 'order' }"
        >
          <div
            class="c-notice-header"
            @click="expandedNotice = expandedNotice === 'order' ? null : 'order'"
          >
            <div class="c-notice-left">
              <div class="c-notice-icon"><el-icon><DocumentChecked /></el-icon></div>
              <span class="c-notice-title">{{ pendingOrders.length }} 条新医嘱待查看</span>
            </div>
            <div class="c-notice-right">
              <span class="dismiss-btn" @click.stop="dismissActionCenter('order')">忽略</span>
              <el-icon class="expand-icon" :class="{ 'is-rotated': expandedNotice === 'order' }"><ArrowDown /></el-icon>
            </div>
          </div>
          <div class="c-notice-body" v-show="expandedNotice === 'order'">
            <div
              v-for="o in pendingOrders"
              :key="o.id"
              class="order-list-item"
              @click="goToOrder(o.id)"
            >
              <span class="order-item-type">{{ o.order_type === 'custom' ? '自定义医嘱' : '标准医嘱' }}</span>
              <span class="order-item-date">{{ formatOrderDate(o.signed_at || o.created_at) }}</span>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
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
              <span class="dismiss-btn" @click.stop="dismissActionCenter('greeting')">忽略</span>
              <el-icon class="expand-icon" :class="{ 'is-rotated': expandedNotice === 'ai' }"><ArrowDown /></el-icon>
            </div>
          </div>
          <div class="c-notice-body" v-show="expandedNotice === 'ai'">
            {{ proactiveGreeting.message }}
          </div>
        </div>
      </div>

      <!-- ==================== 通知消息列表 ==================== -->
      <div class="notifications-section" v-if="alertNotifications.length > 0 || proactiveNotifications.length > 0">
        <!-- 温馨提示卡片（来自预警服务，已过滤高危项，仅显示体重/血压等基本指标） -->
        <div
          v-for="item in alertNotifications.slice(0, 3)"
          :key="'alert-' + item.id"
          class="notice-card notice-gentle interactive-card"
          @click="onAlertNoticeClick(item)"
        >
          <div class="notice-icon-wrap notice-icon-gentle">
            <el-icon><Sunny /></el-icon>
          </div>
          <div class="notice-content">
            <div class="notice-title">{{ item.title }}</div>
            <div class="notice-body">{{ item.body }}</div>
          </div>
          <el-icon class="notice-arrow"><ArrowRight /></el-icon>
        </div>
        <!-- 主动提醒卡片（产检排期、血压异常提醒等） -->
        <div
          v-for="item in proactiveNotifications.slice(0, 3)"
          :key="'proactive-' + item.id"
          class="notice-card interactive-card"
          @click="onProactiveNoticeClick(item)"
        >
          <div class="notice-icon-wrap">
            <el-icon><ChatRound /></el-icon>
          </div>
          <div class="notice-content">
            <div class="notice-title">{{ item.title }}</div>
            <div class="notice-body">{{ item.body }}</div>
          </div>
          <el-icon class="notice-arrow"><ArrowRight /></el-icon>
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
          <!-- 3. 快捷操作区 (Quick Actions) — 每个入口直达具体功能页 -->
          <div class="section-container tools-section">
            <h3 class="section-title">快捷操作</h3>
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
                <span class="bento-desc">{{ tool.desc }}</span>
              </div>
            </div>
          </div>

          <!-- 4. 今日待办 (Daily Checklist) — 与快捷操作互补，打卡+快捷录入 -->
          <div class="section-container tasks-section">
            <div class="section-header">
              <h3 class="section-title">今日待办</h3>
              <span class="section-action" @click="router.push('/pregnant/tools/health-record')">
                快捷录入 <el-icon><ArrowRight /></el-icon>
              </span>
            </div>
            <div class="task-grid">
              <div
                v-for="(task, idx) in todayTasks"
                :key="idx"
                class="task-item interactive-card glass-card"
                :class="{ 'is-done': task.done }"
                @click="handleTaskClick(task)"
              >
                <div class="task-icon" :class="task.color">
                  <el-icon :size="20"><component :is="task.icon" /></el-icon>
                </div>
                <div class="task-content">
                  <span class="task-text">{{ task.title }}</span>
                  <span class="task-hint">{{ task.hint }}</span>
                </div>
                <!-- 纯打卡项显示 checkbox，快捷入口显示箭头 -->
                <template v-if="task.route">
                  <el-icon class="task-arrow"><ArrowRight /></el-icon>
                </template>
                <template v-else>
                  <div class="task-checkbox" @click.stop="toggleTask(task)">
                    <el-icon v-if="task.done" color="#fff" :size="16"><Check /></el-icon>
                  </div>
                </template>
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
                class="trend-card glass-card interactive-card"
                :class="{ 'is-warning': trend.is_normal === false }"
                @click="router.push('/pregnant/tools/health-trend')"
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
            <button class="empty-cta" @click="router.push('/pregnant/tools/health-record')">去记录第一条数据</button>
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

            <!-- 孕期日记入口 -->
            <div class="diary-entry-card glass-card interactive-card" @click="router.push('/pregnant/diary')">
              <el-icon class="diary-entry-icon" :size="32" color="#FB7185"><Notebook /></el-icon>
              <div class="diary-entry-content">
                <div class="diary-entry-title">查看孕期日记</div>
                <div class="diary-entry-desc">AI 为你记录的每周孕期故事</div>
              </div>
              <el-icon class="diary-entry-arrow"><ArrowRight /></el-icon>
            </div>

            <h3 class="section-title mt-4">专家建议</h3>
            <div v-if="recommendError" class="recommend-error glass-card" style="padding: 16px; border-radius: 16px; text-align: center;">
              <p style="color: #E74C3C; margin-bottom: 8px; font-size: 13px;">加载失败，请稍后重试</p>
              <el-button size="small" @click="retryRecommend">重新加载</el-button>
            </div>
            <div v-else-if="!recommend" class="recommend-skeleton glass-card">
              <div class="skeleton-line" v-for="i in 3" :key="i"></div>
            </div>
            <el-collapse v-else class="soft-collapse glass-card" style="padding: 12px 16px; border-radius: 16px;">
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
  Loading, Check, ScaleToOriginal, Opportunity,
  Calendar, Document, Bell, ArrowRight, DocumentChecked,
  ChatRound, Avatar, Moon, Female, Food, Bicycle, Warning,
  Odometer, Sunny, ArrowDown, TrendCharts, ChatDotSquare, Edit
} from '@element-plus/icons-vue'
import { pregnantApi, recommendApi, followUpApi, chatApi, orderApi, proactiveApi, alertNotificationApi } from '@/api/endpoints'
import { trendName } from '@/utils/labelMaps'

const router = useRouter()
const loading = ref(true)
const homeData = ref<any>(null)
const recommend = ref<any>(null)
const recommendError = ref(false)
const currentTab = ref('assistant')
const pendingFollowUps = ref<any[]>([])
const expandedNotice = ref<string | null>(null)
const proactiveGreeting = ref<{ message: string; greeting_type: string; icon: string } | null>(null)
const healthTrends = ref<Array<{ metric: string; current_value: number; unit: string; trend: string; summary: string; is_normal: boolean | null }>>([])
const pendingOrders = ref<any[]>([])
const proactiveNotifications = ref<any[]>([])
const alertNotifications = ref<any[]>([])

// ==================== 通知生命周期管理 ====================
// Dismissed 缓存：记录用户主动忽略的通知，避免重复显示
// key: 通知标识, value: 忽略时间戳(ms)
const DISMISS_STORAGE_KEY = 'pregnant_dismissed_notices'
const DISMISS_TTL_ACTION_CENTER = 4 * 60 * 60 * 1000  // 行动中心：4小时后重新提醒
const DISMISS_TTL_PROACTIVE = 24 * 60 * 60 * 1000      // 主动提醒：24小时后重新提醒

function loadDismissedNotices(): Record<string, number> {
  try {
    const raw = localStorage.getItem(DISMISS_STORAGE_KEY)
    if (!raw) return {}
    const map = JSON.parse(raw)
    // 清理过期条目（存储的值是过期时间戳）
    const now = Date.now()
    for (const [k, v] of Object.entries(map)) {
      if ((v as number) < now) delete map[k]
    }
    return map
  } catch { return {} }
}

function saveDismissNotice(key: string, ttl: number) {
  const map = loadDismissedNotices()
  map[key] = Date.now() + ttl  // 存储过期时间而非当前时间
  localStorage.setItem(DISMISS_STORAGE_KEY, JSON.stringify(map))
}

function isDismissed(key: string): boolean {
  const map = loadDismissedNotices()
  const expires = map[key]
  return !!expires && Date.now() < expires
}

// ---- 行动中心忽略 ----
function dismissActionCenter(type: 'followup' | 'order' | 'greeting') {
  const pid = localStorage.getItem('currentPregnantId') || ''
  if (type === 'followup') {
    saveDismissNotice(`ac_followup_${pid}`, DISMISS_TTL_ACTION_CENTER)
    pendingFollowUps.value = []
  } else if (type === 'order') {
    saveDismissNotice(`ac_order_${pid}`, DISMISS_TTL_ACTION_CENTER)
    pendingOrders.value = []
  } else if (type === 'greeting') {
    saveDismissNotice(`ac_greeting_${pid}`, DISMISS_TTL_ACTION_CENTER)
    proactiveGreeting.value = null
  }
}

// ---- 预警通知：标记已读 + 导航 ----
async function onAlertNoticeClick(item: any) {
  const pid = localStorage.getItem('currentPregnantId') || ''
  // 先从列表中移除，提供即时反馈
  alertNotifications.value = alertNotifications.value.filter((n: any) => n.id !== item.id)
  // 调用后端标记已读（fire-and-forget，不阻塞导航）
  if (pid) {
    alertNotificationApi.markRead(item.id, pid).catch(() => {})
  }
  // 导航
  if (item.action_route) {
    router.push(item.action_route)
  }
}

// ---- 主动提醒：记录忽略 + 导航 ----
function onProactiveNoticeClick(item: any) {
  // 用 type + action_route 作为去重 key（id 是随机 UUID，不可靠）
  const dismissKey = `pro_${item.type}_${item.action_route || ''}`
  saveDismissNotice(dismissKey, DISMISS_TTL_PROACTIVE)
  proactiveNotifications.value = proactiveNotifications.value.filter(
    (n: any) => `pro_${n.type}_${n.action_route || ''}` !== dismissKey
  )
  if (item.action_route) {
    router.push(item.action_route)
  }
}

const hasNotices = computed(() => pendingFollowUps.value.length > 0 || pendingOrders.value.length > 0 || proactiveGreeting.value)

const pregnantName = computed(() => homeData.value?.pregnant?.nickname || homeData.value?.pregnant?.display_name || '准妈妈')
const gestWeek = computed(() => Math.floor((homeData.value?.gestational_day || 0) / 7))
const gestDay = computed(() => (homeData.value?.gestational_day || 0) % 7)
const remainDays = computed(() => Math.max(0, 280 - (homeData.value?.gestational_day || 0)))
const babyInfo = computed(() => homeData.value?.baby_info || {})
const babySize = computed(() => babyInfo.value?.size || '未知')
const babyDesc = computed(() => babyInfo.value?.milestone || '正在健康发育中')

/** 根据当前时间动态生成问候语 */
const greetingText = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const momChanges = computed(() => {
  const w = gestWeek.value
  if (w <= 12) return '可能出现早孕反应，乳房胀痛，尿频。记得补充叶酸。'
  if (w <= 28) return '腹部逐渐隆起，可能感受到胎动。胃口变好，注意均衡营养。'
  return '腹部明显增大，可能感到腰酸背痛。建议左侧卧位休息，准备待产包。'
})

// ---- 快捷操作：5 个独立入口，每个直达不同功能页 ----
const tools = [
  { label: '健康录入', icon: 'Edit', color: 'text-rose', desc: '体重/血压/胎动', action: () => router.push('/pregnant/tools/health-record') },
  { label: '胎动计数', icon: 'Opportunity', color: 'text-indigo', desc: '记录宝宝每次踢动', action: () => router.push('/pregnant/tools/fetal-movement') },
  { label: '健康趋势', icon: 'TrendCharts', color: 'text-emerald', desc: '数据曲线一目了然', action: () => router.push('/pregnant/tools/health-trend') },
  { label: '检查日程', icon: 'Calendar', color: 'text-amber', desc: '产检安排早知道', action: () => router.push('/pregnant/schedule') },
  { label: '问小安', icon: 'ChatDotSquare', color: 'text-indigo', desc: 'AI 孕期百科问答', action: () => router.push('/pregnant/chat') },
]

// ---- 今日待办：动态完成状态，数据已记录则自动标记 ----
interface DailyTask {
  title: string
  icon: string
  color: string
  done: boolean
  hint: string
  route: string
}
const todayTasks = ref<DailyTask[]>([
  { title: '记录体重', icon: 'ScaleToOriginal', color: 'bg-rose', done: false, hint: '今日未记录', route: '/pregnant/tools/health-record' },
  { title: '记录血压', icon: 'Odometer', color: 'bg-sky', done: false, hint: '今日未记录', route: '/pregnant/tools/health-record' },
  { title: '数胎动', icon: 'Opportunity', color: 'bg-indigo', done: false, hint: '今日未记录', route: '/pregnant/tools/fetal-movement' },
  { title: '补充叶酸', icon: 'Check', color: 'bg-orange', done: false, hint: '点击标记已完成', route: '' },
])

function toggleTask(task: any) {
  task.done = !task.done
}

/** 点击待办项：有对应页面的跳转，纯打卡项直接切换状态 */
function handleTaskClick(task: any) {
  if (task.route) {
    router.push(task.route)
  } else {
    toggleTask(task)
  }
}

async function fetchFollowUps() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      // 检查是否被用户忽略
      if (isDismissed(`ac_followup_${pid}`)) {
        pendingFollowUps.value = []
        return
      }
      const [draftRes, inProgressRes] = await Promise.all([
        followUpApi.list({ status: 'draft', pregnant_id: pid }),
        followUpApi.list({ status: 'in_progress', pregnant_id: pid })
      ])
      pendingFollowUps.value = [...((draftRes.data as any[]) || []), ...((inProgressRes.data as any[]) || [])]
        .sort((a: any, b: any) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
    }
  } catch (e) { console.warn('[Home] fetchFollowUps failed:', e) }
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
      // 检查是否被用户忽略
      if (isDismissed(`ac_greeting_${pid}`)) {
        proactiveGreeting.value = null
        return
      }
      const res = await chatApi.getProactive(pid)
      proactiveGreeting.value = res.data
    }
  } catch (e) { console.warn('[Home] fetchProactiveGreeting failed:', e) }
}

async function fetchHealthTrends() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await chatApi.getTrends(pid)
      healthTrends.value = res.data?.trends || []
    }
  } catch (e) { console.warn('[Home] fetchHealthTrends failed:', e) }
}

const loadPregnantOrders = async () => {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      // 检查是否被用户忽略
      if (isDismissed(`ac_order_${pid}`)) {
        pendingOrders.value = []
        return
      }
      const res = await orderApi.getPregnantOrders(pid)
      pendingOrders.value = (res.data || []).filter((o: any) => o.status === 'signed' && !o.acknowledged_at)
    }
  } catch (e) { console.warn('[Home] loadPregnantOrders failed:', e) }
}

async function fetchNotifications() {
  const pid = localStorage.getItem('currentPregnantId') || ''
  if (!pid) return
  const [alertRes, proactiveRes] = await Promise.all([
    alertNotificationApi.getNotifications(pid, true).catch(() => ({ data: [] })),
    proactiveApi.getNotifications(pid).catch(() => ({ data: [] })),
  ])
  // 预警通知：仅保留 alert 类型（随访/医嘱由行动中心展示）
  alertNotifications.value = (alertRes.data || []).filter((n: any) => n.type === 'alert')
  // 主动提醒：仅保留重要事项（血压异常、产检），过滤日常记录提醒和已忽略的
  proactiveNotifications.value = (proactiveRes.data || []).filter((n: any) => {
    // 日常数据记录提醒属于「今日待办」，不在通知栏显示
    if (n.type === 'missed_record') return false
    // 随访/医嘱由行动中心展示，不在通知列表重复
    if (n.type === 'followup_pending' || n.type === 'order_pending') return false
    const dismissKey = `pro_${n.type}_${n.action_route || ''}`
    return !isDismissed(dismissKey)
  })
}


function formatOrderDate(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function getTrendIcon(metric: string): string {
  const icons: Record<string, string> = {
    weight: 'ScaleToOriginal', systolic: 'Odometer', diastolic: 'Odometer',
    fetal_movement: 'Opportunity', blood_sugar: 'Sunny', blood_sugar_fasting: 'Sunny',
    blood_sugar_postprandial: 'Sunny', heart_rate: 'Odometer',
    sleep_hours: 'Moon', steps: 'Odometer', emotion_score: 'ChatRound'
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

async function fetchDailyTaskStatus() {
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (!pid) return
    const res = await pregnantApi.getDailyTaskStatus(pid)
    const status = res.data
    // 动态更新今日待办的完成状态和提示
    for (const task of todayTasks.value) {
      if (task.title === '记录体重') {
        task.done = status.weight
        task.hint = status.weight ? '✅ 今日已记录' : '今日未记录'
      } else if (task.title === '记录血压') {
        task.done = status.blood_pressure
        task.hint = status.blood_pressure ? '✅ 今日已记录' : '今日未记录'
      } else if (task.title === '数胎动') {
        task.done = status.fetal_movement
        task.hint = status.fetal_movement ? '✅ 今日已记录' : '今日未记录'
      }
    }
  } catch (e) { console.warn('[Home] fetchDailyTaskStatus failed:', e) }
}

async function fetchRecommend(pregnantId: string, retries = 2) {
  recommendError.value = false
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await recommendApi.get(pregnantId)
      recommend.value = res.data
      return
    } catch (e) {
      if (attempt < retries) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))  // 指数退避: 1s, 2s
      }
    }
  }
  recommendError.value = true
  console.warn('[Recommend] 所有重试均失败, pregnantId:', pregnantId)
}

function retryRecommend() {
  const pid = localStorage.getItem('currentPregnantId') || ''
  if (pid) fetchRecommend(pid)
}

async function fetchData() {
  loading.value = true
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const homeRes = await pregnantApi.getHome(pid).catch(() => null)
      if (homeRes) homeData.value = homeRes.data
      
      loading.value = false
      fetchRecommend(pid)
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
  fetchNotifications()
  fetchDailyTaskStatus()
})

onActivated(() => {
  fetchFollowUps()
  loadPregnantOrders()
  fetchNotifications()
  fetchDailyTaskStatus()
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
.compact-notice:not(.ai-notice):not(.order-notice) { flex-direction: row; justify-content: space-between; align-items: center; }

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
.c-notice-right { font-size: 12px; color: var(--c-slate-500); gap: 8px; }
.followup-notice .c-notice-right { color: var(--c-rose); font-weight: 600; }

.dismiss-btn {
  font-size: 11px;
  color: var(--c-slate-400);
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(148, 163, 184, 0.1);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.dismiss-btn:active {
  background: rgba(148, 163, 184, 0.2);
  transform: scale(0.95);
}
.go-link {
  display: flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
}

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

.order-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
  background: rgba(255,255,255,0.6);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s;
}
.order-list-item:last-child { margin-bottom: 0; }
.order-list-item:active { background: rgba(255,255,255,0.9); }
.order-item-type { flex: 1; font-size: 13px; font-weight: 500; color: var(--c-slate-800); }
.order-item-date { font-size: 12px; color: var(--c-slate-400); }

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

/* ========== 通用工具类 ========== */
.mt-4 { margin-top: 16px; }

/* ========== 3. 通用区块标题 + 区块头部 ========== */
.section-container { margin-bottom: 28px; }
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--c-slate-800); }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.section-header .section-title { margin-bottom: 0; }
.section-action {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; font-weight: 600; color: var(--c-rose);
  cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.section-action:active { opacity: 0.7; }

/* ========== 4. 快捷操作区 (Bento Grid 3×2) ========== */
.bento-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}
.bento-item {
  border-radius: 16px; padding: 16px 8px 12px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  box-shadow: var(--card-shadow); min-height: 96px; justify-content: center;
}
.bento-label { font-size: 13px; font-weight: 600; text-align: center; }
.bento-desc { font-size: 11px; color: var(--c-slate-400); text-align: center; line-height: 1.3; }

/* 文本颜色助手 */
.text-rose { color: var(--c-rose); }
.text-sky { color: var(--c-sky); }
.text-indigo { color: var(--c-indigo); }
.text-emerald { color: var(--c-emerald); }
.text-amber { color: var(--c-amber); }
.text-slate { color: var(--c-slate-600); }

/* ========== 5. 今日待办 ========== */
.task-grid { display: flex; flex-direction: column; gap: 10px; }
.task-item {
  border-radius: 16px; padding: 14px 16px;
  display: flex; align-items: center; gap: 12px; min-height: 64px;
  box-shadow: var(--card-shadow);
}
.task-icon {
  width: 40px; height: 40px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center; color: white;
  flex-shrink: 0;
}
.bg-rose { background: var(--c-rose); }
.bg-sky { background: var(--c-sky); }
.bg-indigo { background: var(--c-indigo); }
.bg-orange { background: var(--c-orange); }
.task-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.task-text { font-size: 14px; font-weight: 600; transition: color 0.3s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.task-hint { font-size: 11px; color: var(--c-slate-400); }
.task-checkbox {
  width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--c-slate-400);
  display: flex; align-items: center; justify-content: center; transition: all 0.3s;
  background: rgba(255,255,255,0.5);
  flex-shrink: 0;
}
.task-item.is-done .task-text { color: var(--c-slate-400); text-decoration: line-through; }
.task-item.is-done .task-hint { color: var(--c-slate-300); }
.task-item.is-done .task-checkbox { background: var(--c-emerald); border-color: var(--c-emerald); }
.task-arrow { color: var(--c-slate-400); font-size: 14px; flex-shrink: 0; }

/* ========== 6. 健康趋势 ========== */
.trend-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 8px;
}
.trend-card {
  border-radius: 14px; padding: 12px;
  box-shadow: 0 4px 16px rgba(148, 163, 184, 0.08);
  border: 1px solid rgba(255,255,255,0.8);
  display: flex; flex-direction: column; gap: 6px;
}
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 32px 16px; border-radius: 16px; gap: 12px;
  color: var(--c-slate-400); font-size: 14px;
}
.empty-cta {
  margin-top: 4px; padding: 8px 20px; border: none; border-radius: 20px;
  background: linear-gradient(135deg, var(--c-rose), #E11D48); color: #fff;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: transform 0.2s;
}
.empty-cta:active { transform: scale(0.96); }
.trend-card.is-warning { background: linear-gradient(135deg, rgba(255,247,237,0.9), rgba(255,255,255,0.7)) !important; border-color: rgba(251,146,60,0.3); }

/* 奇数卡片最后一张跨满整行 */
.trend-card:last-child:nth-child(odd) {
  grid-column: 1 / -1;
}

.trend-header { display: flex; justify-content: space-between; align-items: center; }
.trend-title-wrap { display: flex; align-items: center; gap: 6px; }
.trend-icon-wrap {
  width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
  background: var(--c-bg); color: var(--c-slate-600);
  font-size: 14px;
}
.icon-weight { color: var(--c-rose); background: var(--c-rose-light); }
.icon-systolic, .icon-diastolic { color: var(--c-sky); background: var(--c-sky-light); }
.icon-fetal_movement { color: var(--c-indigo); background: rgba(129,140,248,0.15); }
.icon-blood_sugar, .icon-blood_sugar_fasting, .icon-blood_sugar_postprandial { color: var(--c-amber); background: rgba(251,191,36,0.15); }
.icon-heart_rate { color: var(--c-rose); background: var(--c-rose-light); }
.icon-sleep_hours { color: var(--c-indigo); background: rgba(129,140,248,0.15); }
.icon-steps { color: var(--c-emerald); background: rgba(52,211,153,0.15); }
.icon-emotion_score { color: var(--c-indigo); background: rgba(129,140,248,0.15); }

.trend-name { font-size: 12px; font-weight: 600; color: var(--c-slate-600); }
.trend-status { font-size: 10px; padding: 3px 8px; border-radius: 20px; font-weight: 600; }
.status-ok { background: rgba(52,211,153,0.15); color: var(--c-emerald); }
.status-warn { background: rgba(251,146,60,0.15); color: var(--c-orange); }

.trend-body { display: flex; align-items: baseline; gap: 3px; }
.trend-value { font-size: 20px; font-weight: 700; color: var(--c-slate-800); font-family: 'Nunito Sans', sans-serif; }
.trend-unit { font-size: 11px; font-weight: 500; color: var(--c-slate-400); }

.trend-summary { font-size: 11px; color: var(--c-slate-500); line-height: 1.3; }

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

/* 骨架屏 */
.recommend-skeleton {
  border-radius: 16px; padding: 20px 16px; display: flex; flex-direction: column; gap: 14px;
}
.skeleton-line {
  height: 16px; border-radius: 8px;
  background: linear-gradient(90deg, rgba(148,163,184,0.1) 25%, rgba(148,163,184,0.2) 50%, rgba(148,163,184,0.1) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
}
.skeleton-line:nth-child(1) { width: 40%; }
.skeleton-line:nth-child(2) { width: 100%; }
.skeleton-line:nth-child(3) { width: 70%; }
@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 孕期日记入口 */
.diary-entry-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: 16px;
  margin-top: 16px;
  box-shadow: var(--card-shadow);
  background: linear-gradient(135deg, rgba(253, 242, 248, 0.8), rgba(255, 255, 255, 0.7)) !important;
  border: 1px solid rgba(251, 113, 133, 0.2);
}
.diary-entry-icon { flex-shrink: 0; }
.diary-entry-content { flex: 1; }
.diary-entry-title { font-size: 15px; font-weight: 600; color: var(--c-slate-800); margin-bottom: 2px; }
.diary-entry-desc { font-size: 12px; color: var(--c-slate-400); }
.diary-entry-arrow { color: var(--c-slate-400); font-size: 16px; }

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

/* ========== 通知消息列表 ========== */
.notifications-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.notice-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 4px 12px rgba(148, 163, 184, 0.05);
}
.notice-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  color: var(--c-slate-600);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
  flex-shrink: 0;
}
/* 温馨提示风格：柔和的粉橙色背景，友好图标 */
.notice-icon-gentle {
  background: rgba(251, 191, 36, 0.12);
  color: var(--c-amber);
}
.notice-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.notice-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--c-slate-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.notice-body {
  font-size: 12px;
  color: var(--c-slate-500);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notice-arrow {
  color: var(--c-slate-400);
  font-size: 14px;
  flex-shrink: 0;
}
/* 温馨提示卡片：柔和背景，无预警分级色 */
.notice-gentle {
  background: linear-gradient(135deg, rgba(254, 249, 195, 0.6), rgba(255, 255, 255, 0.7));
  border-color: rgba(251, 191, 36, 0.15);
}
</style>
