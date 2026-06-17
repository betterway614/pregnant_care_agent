<template>
  <div class="diary-page">
    <!-- 顶部导航 -->
    <div class="diary-nav">
      <el-page-header @back="$router.back()">
        <template #content>
          <span class="diary-nav-title">
            <el-icon :size="18" style="vertical-align: middle; margin-right: 4px;"><Notebook /></el-icon>
            孕期日记
          </span>
        </template>
      </el-page-header>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="diary-loading">
      <el-icon class="is-loading" :size="36" color="#FB7185"><Loading /></el-icon>
      <p>正在为你书写孕期故事...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!entries.length" class="diary-empty">
      <div class="diary-empty-icon">
        <el-icon :size="64" color="#FB7185"><Notebook /></el-icon>
      </div>
      <p class="diary-empty-title">还没有日记哦</p>
      <p class="diary-empty-desc">记录你的健康数据，我会帮你生成温馨的孕期周记</p>
      <button class="diary-empty-btn" @click="$router.push('/pregnant/tools/health-record')">去记录数据</button>
    </div>

    <!-- 日记内容 -->
    <div v-else class="diary-content">
      <!-- 头部信息 -->
      <div class="diary-hero">
        <div class="diary-hero-week">孕 {{ currentWeek }} 周</div>
        <div class="diary-hero-desc">
          这是属于你和宝宝的专属记忆
          <el-icon :size="14" style="vertical-align: middle;"><MagicStick /></el-icon>
        </div>
      </div>

      <!-- 周记列表 -->
      <div class="diary-timeline">
        <div
          v-for="entry in entries"
          :key="entry.week"
          class="diary-entry"
        >
          <!-- 时间线节点 -->
          <div class="timeline-dot" :class="isMoodWarn(entry.mood_emoji) ? 'dot-warn' : 'dot-normal'">
            <span class="timeline-icon" v-html="getMoodIconSvg(entry.mood_emoji)"></span>
          </div>

          <!-- 卡片内容 -->
          <div class="diary-card glass-card">
            <div class="diary-card-header">
              <span class="diary-week-label">第 {{ entry.week }} 周</span>
              <span class="diary-date-range">{{ entry.date_range }}</span>
            </div>

            <!-- AI 叙述 -->
            <div class="diary-narrative" v-if="entry.ai_narrative">
              {{ entry.ai_narrative }}
            </div>

            <!-- 健康摘要 -->
            <div class="diary-metrics">
              <div class="metric-item" v-if="entry.weight_summary">
                <el-icon class="metric-icon" :size="16"><ScaleToOriginal /></el-icon>
                <span class="metric-text">{{ entry.weight_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.bp_summary">
                <span class="metric-icon" v-html="HEART_SVG"></span>
                <span class="metric-text">{{ entry.bp_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.fetal_movement_summary">
                <span class="metric-icon" v-html="FOOTPRINTS_SVG"></span>
                <span class="metric-text">{{ entry.fetal_movement_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.mood_summary">
                <span class="metric-icon" v-html="SMILE_SVG"></span>
                <span class="metric-text">{{ entry.mood_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.blood_sugar_summary">
                <span class="metric-icon" v-html="DROPLETS_SVG"></span>
                <span class="metric-text">{{ entry.blood_sugar_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.heart_rate_summary">
                <span class="metric-icon" v-html="HEARTBEAT_SVG"></span>
                <span class="metric-text">{{ entry.heart_rate_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.sleep_summary">
                <el-icon class="metric-icon" :size="16"><MoonNight /></el-icon>
                <span class="metric-text">{{ entry.sleep_summary }}</span>
              </div>
              <div class="metric-item" v-if="entry.steps_summary">
                <el-icon class="metric-icon" :size="16"><Odometer /></el-icon>
                <span class="metric-text">{{ entry.steps_summary }}</span>
              </div>
            </div>

            <!-- 本周亮点 -->
            <div class="diary-highlights" v-if="entry.highlights && entry.highlights.length">
              <div class="highlight-tag" v-for="(h, i) in entry.highlights" :key="i">
                {{ h }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部 -->
      <div class="diary-footer">
        <p>数据来源：每日健康记录 · AI 智能生成</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { diaryApi } from '@/api/endpoints'
import {
  getMoodIconSvg,
  isMoodWarn,
  HEART_SVG,
  FOOTPRINTS_SVG,
  SMILE_SVG,
  DROPLETS_SVG,
  HEARTBEAT_SVG,
} from '@/utils/diaryIcons'

interface DiaryWeekSummary {
  week: number
  date_range: string
  weight_summary?: string
  bp_summary?: string
  fetal_movement_summary?: string
  mood_summary?: string
  blood_sugar_summary?: string
  heart_rate_summary?: string
  sleep_summary?: string
  steps_summary?: string
  highlights: string[]
  ai_narrative: string
  mood_emoji: string
}

const loading = ref(true)
const currentWeek = ref(0)
const entries = ref<DiaryWeekSummary[]>([])

async function fetchDiary() {
  loading.value = true
  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (!pid) return
    const res = await diaryApi.get(pid, 4)
    currentWeek.value = res.data?.current_week || 0
    entries.value = res.data?.entries || []
  } catch (e) {
    console.warn('[Diary] 加载失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => { fetchDiary() })
</script>

<style scoped>
.diary-page {
  min-height: 100dvh;
  background: linear-gradient(180deg, #FFF1F2 0%, #F8FAFC 30%);
  padding-bottom: 32px;
}

.diary-nav {
  padding: 12px 16px;
  padding-top: max(12px, env(safe-area-inset-top));
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.diary-nav-title {
  font-size: 18px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
}

/* 加载 */
.diary-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  gap: 16px;
  color: #64748B;
}

/* 空状态 */
.diary-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 32px;
  text-align: center;
}
.diary-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}
.diary-empty-title { font-size: 18px; font-weight: 600; color: #1E293B; margin-bottom: 8px; }
.diary-empty-desc { font-size: 14px; color: #94A3B8; margin-bottom: 24px; }
.diary-empty-btn {
  padding: 10px 28px;
  border: none;
  border-radius: 24px;
  background: linear-gradient(135deg, #FB7185, #E11D48);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

/* 头部 */
.diary-hero {
  text-align: center;
  padding: 24px 16px 16px;
}
.diary-hero-week {
  font-size: 28px;
  font-weight: 700;
  color: #1E293B;
}
.diary-hero-desc {
  font-size: 14px;
  color: #94A3B8;
  margin-top: 4px;
}

/* 时间线 */
.diary-timeline {
  padding: 0 16px;
  position: relative;
}
.diary-timeline::before {
  content: '';
  position: absolute;
  left: 31px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(180deg, #FECDD3, #E2E8F0);
}

.diary-entry {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  position: relative;
}

.timeline-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  z-index: 1;
  margin-top: 16px;
}
.dot-normal { background: #FDF2F8; border: 2px solid #FB7185; color: #FB7185; }
.dot-warn { background: #FFF7ED; border: 2px solid #F59E0B; color: #F59E0B; }
.timeline-icon {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.timeline-icon :deep(svg) { width: 100%; height: 100%; }

/* 日记卡片 */
.diary-card {
  flex: 1;
  border-radius: 16px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 2px 12px rgba(148, 163, 184, 0.08);
}

.diary-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.diary-week-label {
  font-size: 16px;
  font-weight: 700;
  color: #1E293B;
}
.diary-date-range {
  font-size: 12px;
  color: #94A3B8;
}

.diary-narrative {
  font-size: 14px;
  color: #475569;
  line-height: 1.7;
  margin-bottom: 14px;
  padding: 12px;
  background: rgba(253, 242, 248, 0.5);
  border-radius: 12px;
  border-left: 3px solid #FB7185;
}

/* 健康指标 */
.diary-metrics {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.metric-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #64748B;
}
.metric-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #FB7185;
}
.metric-icon :deep(svg) { width: 100%; height: 100%; }

/* 亮点标签 */
.diary-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.highlight-tag {
  padding: 4px 10px;
  border-radius: 12px;
  background: rgba(129, 140, 248, 0.1);
  color: #6366F1;
  font-size: 12px;
  font-weight: 500;
}

.glass-card {
  background: rgba(255, 255, 255, 0.55) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
}

/* 底部 */
.diary-footer {
  text-align: center;
  padding: 24px 16px;
  font-size: 12px;
  color: #CBD5E1;
}

/* -------------------- 移动端适配 -------------------- */
@media (max-width: 768px) {
  .diary-page {
    padding-bottom: max(32px, env(safe-area-inset-bottom));
  }

  .diary-nav {
    padding: 10px 12px;
    padding-top: max(10px, env(safe-area-inset-top));
  }
  .diary-nav-title {
    font-size: 16px;
  }

  .diary-hero {
    padding: 16px 12px 12px;
  }
  .diary-hero-week {
    font-size: 22px;
  }
  .diary-hero-desc {
    font-size: 13px;
  }

  .diary-timeline {
    padding: 0 12px;
  }
  .diary-timeline::before {
    left: 15px;
  }

  .diary-entry {
    gap: 10px;
    margin-bottom: 16px;
  }

  .timeline-dot {
    width: 28px;
    height: 28px;
    margin-top: 12px;
  }
  .timeline-icon {
    width: 14px;
    height: 14px;
  }

  .diary-card {
    border-radius: 12px;
    padding: 12px;
  }

  .diary-card-header {
    margin-bottom: 10px;
  }
  .diary-week-label {
    font-size: 15px;
  }
  .diary-date-range {
    font-size: 11px;
  }

  .diary-narrative {
    font-size: 13px;
    padding: 10px;
    margin-bottom: 10px;
  }

  .metric-item {
    font-size: 12px;
    gap: 6px;
  }

  .highlight-tag {
    font-size: 11px;
    padding: 3px 8px;
  }
}
</style>
