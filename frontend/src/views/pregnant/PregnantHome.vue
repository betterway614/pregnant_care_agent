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
import { pregnantApi, recommendApi, followUpApi } from '@/api/endpoints'

const router = useRouter()
const loading = ref(true)
const homeData = ref<any>(null)
const recommend = ref<any>(null)
const pendingFollowUps = ref<any[]>([])

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
      const res = await followUpApi.list({ status: 'draft', pregnant_id: pregnantId })
      pendingFollowUps.value = res.data || []
    }
  } catch {
    /* ignore */
  }
}

function goToFollowUp(recordId: string) {
  router.push(`/pregnant/chat?followup=${recordId}`)
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
</style>
