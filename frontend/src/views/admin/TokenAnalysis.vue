<template>
  <div class="token-analysis">
    <el-card shadow="never">
      <template #header>按日 Token 消耗汇总</template>
      <el-table :data="dailyData" stripe size="small" v-loading="loading">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="call_count" label="调用次数" width="100" />
        <el-table-column prop="input_tokens" label="输入 Token" width="120">
          <template #default="{ row }">{{ row.input_tokens.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="output_tokens" label="输出 Token" width="120">
          <template #default="{ row }">{{ row.output_tokens.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="总 Token" width="120">
          <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="avg_latency_ms" label="平均延迟" width="100">
          <template #default="{ row }">{{ row.avg_latency_ms }}ms</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>按 Agent 变体 Token 消耗对比</template>
      <el-table :data="agentData" stripe size="small" v-loading="loading" style="margin-bottom: 16px;">
        <el-table-column prop="agent_role" label="角色" width="100" />
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
      </el-table>
      <VChart :option="barChartOption" autoresize style="height: 300px;" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminTokenDaily, AdminTokenByAgent } from '@/types'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent])

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const loading = ref(false)
const dailyData = ref<AdminTokenDaily[]>([])
const agentData = ref<AdminTokenByAgent[]>([])

const barChartOption = computed(() => ({
  color: ['#3b82f6'],
  tooltip: { trigger: 'axis' as const },
  grid: { left: 60, right: 20, top: 10, bottom: 30 },
  xAxis: { type: 'category' as const, data: agentData.value.map(d => d.agent_variant) },
  yAxis: { type: 'value' as const },
  series: [{
    name: '总 Token', type: 'bar', data: agentData.value.map(d => d.total_tokens),
    itemStyle: { borderRadius: [4, 4, 0, 0], color: '#3b82f6' },
  }],
}))

async function fetchData() {
  loading.value = true
  try {
    const [dailyRes, agentRes] = await Promise.all([
      adminApi.getTokenDaily(dateRange.from.value, dateRange.to.value),
      adminApi.getTokenByAgent(dateRange.from.value, dateRange.to.value),
    ])
    dailyData.value = dailyRes.data.data
    agentData.value = agentRes.data.data
  } finally {
    loading.value = false
  }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>
