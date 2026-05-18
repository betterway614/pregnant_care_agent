<template>
  <div class="tool-grid-container">
    <div class="content-wrapper">
      <!-- 1. 顶部沉浸式问候卡片 (Hero) -->
      <div class="hero-card">
        <div class="hero-header">
          <div>
            <div class="hero-greeting">健康工具</div>
            <div class="hero-week">孕期管理好帮手</div>
          </div>
          <div class="hero-avatar">
            <el-icon :size="28" color="#FB7185"><Grid /></el-icon>
          </div>
        </div>
      </div>

      <!-- 今日健康摘要 -->
      <div class="section-container">
        <h3 class="section-title">今日记录</h3>
        <div v-if="summaryLoading" class="summary-card glass-card skeleton-card">
          <el-icon class="is-loading" :size="28" color="#FB7185"><Loading /></el-icon>
        </div>
        <div v-else class="summary-card glass-card interactive-card">
          <div class="summary-item">
            <div class="summary-item__value">{{ healthSummary.weight_kg || '--' }}</div>
            <div class="summary-item__label">体重 kg</div>
          </div>
          <div class="summary-divider"></div>
          <div class="summary-item">
            <div class="summary-item__value">{{ healthSummary.bp || '--' }}</div>
            <div class="summary-item__label">血压 mmHg</div>
          </div>
          <div class="summary-divider"></div>
          <div class="summary-item">
            <div class="summary-item__value">{{ healthSummary.fetal_movement || '--' }}</div>
            <div class="summary-item__label">胎动/时</div>
          </div>
        </div>
      </div>

      <!-- 工具网格 -->
      <div class="section-container">
        <h3 class="section-title">常用工具</h3>
        <div class="tool-grid">
          <div
            v-for="tool in tools"
            :key="tool.name"
            class="bento-item glass-card interactive-card"
            @click="$router.push(tool.route)"
          >
            <div class="bento-icon-wrap" :class="'bg-' + tool.colorName">
              <el-icon :size="32" :class="'text-' + tool.colorName"><component :is="tool.icon" /></el-icon>
            </div>
            <div class="bento-info">
              <div class="bento-label">{{ tool.label }}</div>
              <div class="bento-desc">{{ tool.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { pregnantApi } from '@/api/endpoints'
import { Loading, Grid, Opportunity, Document, DataLine, HelpFilled } from '@element-plus/icons-vue'

const tools = [
  { name: 'fetal-movement', icon: 'Opportunity', label: '胎动计数', desc: '记录宝宝每一次踢动', colorName: 'rose', route: '/pregnant/tools/fetal-movement' },
  { name: 'health-record', icon: 'Document', label: '快速录入', desc: '体重/血压/血糖', colorName: 'emerald', route: '/pregnant/tools/health-record' },
  { name: 'health-trend', icon: 'DataLine', label: '健康趋势', desc: '数据曲线一目了然', colorName: 'sky', route: '/pregnant/tools/health-trend' },
  { name: 'mental-health', icon: 'HelpFilled', label: '心理筛查', desc: 'EPDS 情绪评估', colorName: 'indigo', route: '/pregnant/tools/mental-health' },
]

const healthSummary = ref<any>({})
const summaryLoading = ref(false)

async function loadSummary() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) return
  summaryLoading.value = true
  try {
    const res = await pregnantApi.getHome(pid)
    healthSummary.value = res.data?.health_summary || {}
  } catch { /* ignore */ } finally {
    summaryLoading.value = false
  }
}

onMounted(() => { loadSummary() })
</script>

<style scoped>
.tool-grid-container {
  position: relative;
}

.content-wrapper {
  position: relative;
  z-index: 1;
  padding: 16px;
  padding-bottom: 32px;
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

/* 通用区块标题 */
.section-container { margin-bottom: 24px; }
.section-title { font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--c-slate-800); }

/* 今日摘要 */
.summary-card {
  border-radius: 20px;
  padding: 20px 16px;
  display: flex;
  justify-content: space-around;
  align-items: center;
  box-shadow: var(--card-shadow);
}
.skeleton-card {
  min-height: 100px;
  justify-content: center;
}

.summary-item {
  text-align: center;
  flex: 1;
}
.summary-item__value {
  font-size: 24px;
  font-weight: 700;
  color: var(--c-slate-800);
  margin-bottom: 4px;
  font-family: 'Nunito Sans', sans-serif;
}
.summary-item__label {
  font-size: 13px;
  color: var(--c-slate-600);
}
.summary-divider {
  width: 1px;
  height: 40px;
  background-color: rgba(148, 163, 184, 0.2);
}

/* 工具网格 */
.tool-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.bento-item {
  border-radius: 20px;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  box-shadow: var(--card-shadow);
  min-height: 140px;
}
.bento-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}
.bento-label {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-slate-800);
  margin-bottom: 6px;
}
.bento-desc {
  font-size: 12px;
  color: var(--c-slate-500);
  line-height: 1.4;
}

/* 颜色类 */
.bg-rose { background: var(--c-rose-light); }
.text-rose { color: var(--c-rose); }

.bg-emerald { background: var(--c-emerald-light); }
.text-emerald { color: var(--c-emerald); }

.bg-sky { background: var(--c-sky-light); }
.text-sky { color: var(--c-sky); }

.bg-indigo { background: var(--c-indigo-light); }
.text-indigo { color: var(--c-indigo); }
</style>
