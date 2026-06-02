<template>
  <div class="route-monitor">
    <el-radio-group v-model="selectedRole" size="small" style="margin-bottom: 16px;" @change="onRoleFilterChange">
      <el-radio-button value="">全部</el-radio-button>
      <el-radio-button value="pregnant">孕妇端</el-radio-button>
      <el-radio-button value="nurse">护士端</el-radio-button>
      <el-radio-button value="doctor">医生端</el-radio-button>
    </el-radio-group>

    <el-row :gutter="16">
      <el-col v-for="v in variantCards" :key="v.role + ':' + v.name" :span="4">
        <el-card shadow="never" class="variant-card">
          <div class="variant-card__name">{{ v.roleLabel }} · {{ v.name }}</div>
          <div class="variant-card__count">{{ v.count }}</div>
          <div class="variant-card__tokens">{{ v.tokens }} tokens</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>变体调用分布</template>
          <VChart :option="pieOption" autoresize style="height: 300px;" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>平均 Token 消耗对比</template>
          <VChart :option="barOption" autoresize style="height: 300px;" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>变体详细数据</template>
      <el-table :data="filteredData" stripe size="small" v-loading="loading">
        <el-table-column prop="agent_role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.agent_role === 'nurse' ? 'success' : row.agent_role === 'doctor' ? 'warning' : ''" size="small">
              {{ ROLE_LABELS[row.agent_role] ?? row.agent_role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="agent_variant" label="变体" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="call_count" label="调用次数" width="100" />
        <el-table-column prop="total_tokens" label="总 Token" width="120">
          <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="avg_input_tokens" label="平均输入" width="100" />
        <el-table-column prop="avg_output_tokens" label="平均输出" width="100" />
        <el-table-column prop="avg_latency_ms" label="平均延迟" width="100">
          <template #default="{ row }">{{ row.avg_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column label="占比" width="120">
          <template #default="{ row }">
            <el-progress :percentage="getPercent(row.call_count)" :stroke-width="8" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminTokenByAgent } from '@/types'

use([CanvasRenderer, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const ROLE_LABELS: Record<string, string> = { pregnant: '孕妇', nurse: '护士', doctor: '医生' }

const loading = ref(false)
const agentData = ref<AdminTokenByAgent[]>([])
const selectedRole = ref('')

// 按角色过滤后的数据
const filteredData = computed(() =>
  selectedRole.value
    ? agentData.value.filter(d => d.agent_role === selectedRole.value)
    : agentData.value,
)

const totalCalls = computed(() => filteredData.value.reduce((s, d) => s + d.call_count, 0) || 1)

function getPercent(count: number) { return Math.round((count / totalCalls.value) * 100) }

const variantCards = computed(() =>
  filteredData.value.map(d => ({
    role: d.agent_role,
    roleLabel: ROLE_LABELS[d.agent_role] ?? d.agent_role,
    name: d.agent_variant,
    count: d.call_count,
    tokens: d.total_tokens >= 1000 ? (d.total_tokens / 1000).toFixed(1) + 'K' : String(d.total_tokens),
  })),
)

function onRoleFilterChange() { /* filteredData 自动响应 */ }

const CHART_COLORS = ['#3b82f6', '#f97316', '#10b981', '#8b5cf6', '#60a5fa']

const pieOption = computed(() => ({
  color: CHART_COLORS,
  tooltip: { trigger: 'item' as const },
  series: [{
    type: 'pie', radius: ['40%', '70%'],
    data: filteredData.value.map(d => ({ name: `${ROLE_LABELS[d.agent_role] ?? d.agent_role}·${d.agent_variant}`, value: d.call_count })),
    emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.12)' } },
    label: { show: false },
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
  }],
}))

const barOption = computed(() => ({
  color: ['#3b82f6', '#10b981'],
  tooltip: { trigger: 'axis' as const },
  grid: { left: 60, right: 20, top: 30, bottom: 30 },
  xAxis: { type: 'category' as const, data: filteredData.value.map(d => d.agent_variant), axisLabel: { rotate: 30 } },
  yAxis: { type: 'value' as const },
  legend: { data: ['平均输入', '平均输出'] },
  series: [
    { name: '平均输入', type: 'bar' as const, data: filteredData.value.map(d => d.avg_input_tokens), itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] } },
    { name: '平均输出', type: 'bar' as const, data: filteredData.value.map(d => d.avg_output_tokens), itemStyle: { color: '#10b981', borderRadius: [4, 4, 0, 0] } },
  ],
}))

async function fetchData() {
  loading.value = true
  try {
    const res = await adminApi.getTokenByAgent(dateRange.from.value, dateRange.to.value)
    agentData.value = res.data.data
  } finally { loading.value = false }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>

<style scoped>
.variant-card { text-align: center; transition: box-shadow 0.2s; }
.variant-card:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06); }
.variant-card :deep(.el-card__body) { padding: 16px; }
.variant-card__name { font-size: 12px; color: #64748b; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px; }
.variant-card__count { font-size: 28px; font-weight: 700; color: #0f172a; }
.variant-card__tokens { font-size: 12px; color: #94a3b8; margin-top: 4px; }
</style>
