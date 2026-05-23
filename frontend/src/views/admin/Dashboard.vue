<template>
  <div class="dashboard">
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #eff6ff;">
              <el-icon :size="24" color="#3b82f6"><PhoneFilled /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">总调用次数</div>
              <div class="stat-card__value">{{ summary.total_calls.toLocaleString() }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #fff7ed;">
              <el-icon :size="24" color="#f97316"><Coin /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">Token 总消耗</div>
              <div class="stat-card__value">{{ formatTokens(summary.total_tokens) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #ecfdf5;">
              <el-icon :size="24" color="#10b981"><Timer /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">平均延迟</div>
              <div class="stat-card__value">{{ summary.avg_latency_ms }}ms</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #f5f3ff;">
              <el-icon :size="24" color="#8b5cf6"><ChatDotRound /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">活跃会话数</div>
              <div class="stat-card__value">{{ summary.active_sessions }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>近 7 天 Token 消耗趋势</template>
          <VChart :option="trendChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>Agent 变体调用分布</template>
          <VChart :option="pieChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>最近调用记录</template>
      <el-table :data="recentLogs" stripe size="small" @row-click="goToSession">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="agent_variant" label="变体" width="90">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="intent_classification" label="意图" width="120" />
        <el-table-column prop="total_tokens" label="Token" width="90" />
        <el-table-column prop="total_latency_ms" label="延迟" width="90">
          <template #default="{ row }">{{ row.total_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="guardrail_triggered" label="护栏" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.guardrail_triggered" type="danger" size="small">触发</el-tag>
            <span v-else style="color: #cbd5e1;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="response_preview" label="回复预览" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminRecentLog } from '@/types'

use([CanvasRenderer, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const router = useRouter()

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const summary = ref({ total_calls: 0, total_tokens: 0, avg_latency_ms: 0, active_sessions: 0 })
const dailyTrend = ref<Array<{ date: string; total_tokens: number; call_count: number }>>([])
const variantDist = ref<Array<{ agent_variant: string; count: number; total_tokens: number }>>([])
const recentLogs = ref<AdminRecentLog[]>([])

// ECharts professional palette
const CHART_COLORS = ['#3b82f6', '#f97316', '#10b981', '#8b5cf6', '#60a5fa']

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

const trendChartOption = computed(() => ({
  color: CHART_COLORS,
  tooltip: { trigger: 'axis' as const },
  grid: { left: 60, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category' as const, data: dailyTrend.value.map(d => d.date.slice(5)) },
  yAxis: { type: 'value' as const },
  series: [{
    name: 'Token', type: 'line', data: dailyTrend.value.map(d => d.total_tokens),
    smooth: true, areaStyle: { opacity: 0.1 },
    itemStyle: { color: '#3b82f6' },
  }],
}))

const pieChartOption = computed(() => ({
  color: CHART_COLORS,
  tooltip: { trigger: 'item' as const },
  series: [{
    type: 'pie', radius: ['45%', '75%'], center: ['50%', '50%'],
    data: variantDist.value.map(v => ({ name: v.agent_variant, value: v.count })),
    emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.12)' } },
    label: { show: false },
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
  }],
}))

function goToSession(row: AdminRecentLog) {
  router.push({ name: 'AdminAuditTrail', query: { session_id: row.session_id } })
}

async function fetchData() {
  try {
    const res = await adminApi.getDashboard(dateRange.from.value, dateRange.to.value)
    summary.value = res.data.summary
    dailyTrend.value = res.data.daily_trend
    variantDist.value = res.data.variant_distribution
    recentLogs.value = res.data.recent_logs
  } catch { /* ignore */ }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>

<style scoped>
.stat-cards :deep(.el-card__body) { padding: 20px; }
.stat-card-wrapper { transition: box-shadow 0.2s; cursor: default; }
.stat-card-wrapper:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06); }
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-card__icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-card__label { font-size: 13px; color: #64748b; margin-bottom: 4px; }
.stat-card__value { font-size: 24px; font-weight: 700; color: #0f172a; }
:deep(.el-table__row) { cursor: pointer; transition: background 0.15s; }
</style>
