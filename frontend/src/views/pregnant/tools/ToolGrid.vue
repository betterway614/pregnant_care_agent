<template>
  <div class="page-container">
    <!-- 渐变头部 -->
    <div class="patient-header-card" style="min-height: 80px; padding: 20px">
      <div class="patient-header-card__name">健康工具</div>
      <div class="patient-header-card__week">选择工具开始记录</div>
    </div>

    <!-- 工具网格 -->
    <div class="tool-grid">
      <div
        v-for="tool in tools"
        :key="tool.name"
        class="tool-card"
        :style="{ background: tool.bg }"
        @click="$router.push(tool.route)"
      >
        <div class="tool-card__icon">{{ tool.icon }}</div>
        <div class="tool-card__name">{{ tool.label }}</div>
        <div class="tool-card__desc">{{ tool.desc }}</div>
      </div>
    </div>

    <!-- 今日健康摘要 -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #42A5F5"></span>
        今日健康摘要
      </div>
      <div v-if="summaryLoading" class="empty-tip">加载中...</div>
      <div v-else class="summary-grid">
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.weight_kg || '--' }}</div>
          <div class="summary-item__label">体重 kg</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.bp || '--' }}</div>
          <div class="summary-item__label">血压 mmHg</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.fetal_movement || '--' }}</div>
          <div class="summary-item__label">胎动/时</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { pregnantApi } from '@/api/endpoints'

const tools = [
  { name: 'fetal-movement', icon: '👶', label: '胎动计数', desc: '记录宝宝每一次踢动', bg: 'linear-gradient(135deg, #fce4ec, #f8bbd0)', route: '/pregnant/tools/fetal-movement' },
  { name: 'health-record', icon: '📝', label: '快速录入', desc: '体重/血压/血糖', bg: 'linear-gradient(135deg, #e8f5e9, #c8e6c9)', route: '/pregnant/tools/health-record' },
  { name: 'health-trend', icon: '📊', label: '健康趋势', desc: '数据曲线一目了然', bg: 'linear-gradient(135deg, #e3f2fd, #bbdefb)', route: '/pregnant/tools/health-trend' },
  { name: 'mental-health', icon: '🧠', label: '心理筛查', desc: 'EPDS 情绪评估', bg: 'linear-gradient(135deg, #f3e5f5, #e1bee7)', route: '/pregnant/tools/mental-health' },
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
.page-container {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  height: 100%;
  box-sizing: border-box;
  padding-bottom: 24px;
}

.tool-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px;
}

.tool-card {
  border-radius: 16px;
  padding: 20px 16px;
  text-align: center;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.tool-card:active {
  transform: scale(0.96);
}

.tool-card__icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.tool-card__name {
  font-size: 15px;
  font-weight: 700;
  color: #333;
}

.tool-card__desc {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.summary-grid {
  display: flex;
  justify-content: space-around;
  text-align: center;
}

.summary-item__value {
  font-size: 20px;
  font-weight: 700;
  color: #333;
}

.summary-item__label {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.empty-tip {
  text-align: center;
  padding: 16px 0;
  font-size: 13px;
  color: #999;
}
</style>
