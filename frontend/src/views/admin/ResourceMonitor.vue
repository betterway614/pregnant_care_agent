<template>
  <div class="resource-monitor">
    <!-- 顶部统计卡片 (6 张) -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #eff6ff;">
              <el-icon :size="24" color="#3b82f6"><Monitor /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">VRAM 使用</div>
              <div class="stat-card__value">{{ state.vram_used_gb.toFixed(1) }} / {{ state.vram_total_gb.toFixed(1) }} GB</div>
              <el-progress
                :percentage="Math.round(state.vram_percent * 100)"
                :stroke-width="6"
                :color="progressColor(state.vram_percent)"
                :show-text="false"
                style="margin-top: 6px;"
              />
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #fff7ed;">
              <el-icon :size="24" color="#f97316"><Cpu /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">GPU 使用率</div>
              <div class="stat-card__value">{{ state.gpu_percent.toFixed(1) }}%</div>
              <el-progress
                :percentage="Math.round(state.gpu_percent)"
                :stroke-width="6"
                :color="progressColor(state.gpu_percent / 100)"
                :show-text="false"
                style="margin-top: 6px;"
              />
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #ecfdf5;">
              <el-icon :size="24" color="#10b981"><Odometer /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">CPU 使用率</div>
              <div class="stat-card__value">{{ state.cpu_percent.toFixed(1) }}%</div>
              <el-progress
                :percentage="Math.round(state.cpu_percent)"
                :stroke-width="6"
                :color="progressColor(state.cpu_percent / 100)"
                :show-text="false"
                style="margin-top: 6px;"
              />
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #f5f3ff;">
              <el-icon :size="24" color="#8b5cf6"><Connection /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">NPU 状态</div>
              <div class="stat-card__value">
                <el-tag :type="state.npu_available ? 'success' : 'info'" size="small" effect="plain">
                  {{ state.npu_available ? '可用' : '不可用' }}
                </el-tag>
              </div>
              <div class="stat-card__sub">{{ state.npu_available ? `${state.npu_columns} 列` : '未检测到设备' }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #fef2f2;">
              <el-icon :size="24" color="#ef4444"><Lightning /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">GPU 功率</div>
              <div class="stat-card__value">{{ (state.gpu_power_w ?? 0).toFixed(0) }} W</div>
              <div class="stat-card__sub">上限 {{ (state.gpu_power_cap_w ?? 0).toFixed(0) }} W</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" :style="{ background: gpuTempBgColor }">
              <el-icon :size="24" :color="gpuTempColor"><Sunny /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">GPU 温度</div>
              <div class="stat-card__value" :style="{ color: gpuTempColor }">{{ (state.gpu_temp_c ?? 0).toFixed(0) }}&deg;C</div>
              <div class="stat-card__sub">{{ gpuTempLabel }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 负载级别 + 策略信息 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>负载级别</span>
              <el-tag :type="loadLevelTagType" size="small" effect="dark">{{ loadLevelLabel }}</el-tag>
            </div>
          </template>
          <div class="load-level-detail">
            <div class="load-level-detail__item">
              <span class="label">GPU 型号</span>
              <span class="value">{{ state.gpu_model || 'AMD Radeon 8060S' }}</span>
            </div>
            <div class="load-level-detail__item">
              <span class="label">VRAM 总量</span>
              <span class="value">{{ state.vram_total_gb.toFixed(1) }} GB</span>
            </div>
            <div class="load-level-detail__item">
              <span class="label">NPU 型号</span>
              <span class="value">{{ state.npu_available ? 'XDNA Strix Halo' : '不可用' }}</span>
            </div>
            <el-divider style="margin: 8px 0;" />
            <div class="load-level-detail__item">
              <span class="label">当前策略</span>
              <el-tag size="small">{{ policyLabel }}</el-tag>
            </div>
            <div class="load-level-detail__item">
              <span class="label">策略描述</span>
              <span class="value">{{ currentPolicy?.description || '-' }}</span>
            </div>
            <div class="load-level-detail__item">
              <span class="label">RAM 使用</span>
              <span class="value">{{ state.ram_available_gb.toFixed(1) }} GB 可用 / {{ state.ram_total_gb.toFixed(1) }} GB</span>
            </div>
            <div class="load-level-detail__item">
              <span class="label">历史采样</span>
              <span class="value">{{ historyCount }} 条</span>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>优化建议</template>
          <el-table :data="adjustments" stripe size="small" v-loading="loading" empty-text="当前配置已最优，无需调整">
            <el-table-column prop="name" label="服务" width="160" />
            <el-table-column prop="current.accelerator" label="当前加速器" width="110">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ row.current.accelerator.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="current.batch_size" label="当前批处理" width="100" />
            <el-table-column prop="optimal.accelerator" label="建议加速器" width="110">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.current.accelerator !== row.optimal.accelerator ? 'warning' : 'info'"
                  effect="plain"
                >{{ row.optimal.accelerator.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="optimal.batch_size" label="建议批处理" width="100" />
            <el-table-column label="变更" min-width="200">
              <template #default="{ row }">
                <template v-if="row.changes.length > 0">
                  <el-tag
                    v-for="c in row.changes"
                    :key="c"
                    size="small"
                    type="warning"
                    effect="plain"
                    style="margin-right: 4px;"
                  >{{ c }}</el-tag>
                </template>
                <span v-else style="color: #cbd5e1;">无变更</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.needs_update" type="warning" size="small">待调整</el-tag>
                <el-tag v-else type="success" size="small">正常</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 预警摘要 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>预警摘要</span>
            <el-tag v-if="activeAlertCount > 0" type="danger" size="small" effect="dark">{{ activeAlertCount }} 条活跃</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">无活跃预警</el-tag>
          </div>
          <el-button type="primary" link size="small" @click="goToAlertList">
            查看全部
            <el-icon style="margin-left: 4px;"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </template>
      <div v-if="recentAlerts.length === 0" style="text-align: center; color: #94a3b8; padding: 12px 0;">
        暂无预警记录
      </div>
      <div v-else class="alert-summary-list">
        <div v-for="alert in recentAlerts" :key="alert.id" class="alert-summary-item">
          <el-tag :type="alertLevelTagType(alert.level)" size="small" effect="dark" style="flex-shrink: 0;">
            {{ alertLevelLabel(alert.level) }}
          </el-tag>
          <span class="alert-summary-item__msg">{{ alert.message }}</span>
          <span class="alert-summary-item__time">{{ formatAlertTime(alert.created_at ?? '') }}</span>
        </div>
      </div>
    </el-card>

    <!-- 实时资源图表 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>VRAM / GPU 实时监控</span>
              <el-tag size="small" effect="plain">每 5 秒刷新</el-tag>
            </div>
          </template>
          <VChart :option="vramGpuChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>CPU / RAM 实时监控</span>
              <el-tag size="small" effect="plain">每 5 秒刷新</el-tag>
            </div>
          </template>
          <VChart :option="cpuRamChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 服务状态表格 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>服务状态</template>
      <el-table :data="serviceList" stripe size="small" v-loading="loading">
        <el-table-column prop="name" label="服务名称" width="200">
          <template #default="{ row }">
            <span style="font-weight: 600;">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="accelerator" label="加速器" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.accelerator === 'gpu' ? 'danger' : row.accelerator === 'npu' ? 'warning' : 'info'"
              effect="plain"
            >{{ row.accelerator.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="batch_size" label="批处理大小" width="100" />
        <el-table-column prop="min_batch_size" label="最小批处理" width="100" />
        <el-table-column prop="max_batch_size" label="最大批处理" width="100" />
        <el-table-column prop="priority" label="优先级" width="80">
          <template #default="{ row }">
            <el-rate v-model="row.priority" disabled :max="10" :colors="['#99A9BF', '#F7BA2A', '#FF9900']" />
          </template>
        </el-table-column>
        <el-table-column label="CPU 卸载" width="90">
          <template #default="{ row }">
            <el-icon v-if="row.can_offload_to_cpu" color="#10b981"><CircleCheckFilled /></el-icon>
            <el-icon v-else color="#cbd5e1"><CircleCloseFilled /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="NPU 卸载" width="90">
          <template #default="{ row }">
            <el-icon v-if="row.can_offload_to_npu" color="#10b981"><CircleCheckFilled /></el-icon>
            <el-icon v-else color="#cbd5e1"><CircleCloseFilled /></el-icon>
          </template>
        </el-table-column>
        <el-table-column prop="current_load" label="当前负载" width="100">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round(row.current_load)"
              :stroke-width="8"
              :color="progressColor(row.current_load / 100)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { resourceApi } from '@/api/admin'
import { alertApi } from '@/api/endpoints'
import {
  Monitor, Cpu, Odometer, Connection,
  CircleCheckFilled, CircleCloseFilled,
  Lightning, Sunny, ArrowRight,
} from '@element-plus/icons-vue'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

// ==================== 类型 ====================

interface ResourceState {
  vram_total_gb: number
  vram_used_gb: number
  vram_free_gb: number
  vram_percent: number
  gpu_percent: number
  cpu_percent: number
  ram_total_gb: number
  ram_available_gb: number
  ram_percent: number
  npu_available: boolean
  npu_columns: number
  gpu_power_w?: number
  gpu_power_cap_w?: number
  gpu_temp_c?: number
  cpu_temp_c?: number
  gpu_model?: string
  timestamp: number
}

interface AlertItem {
  id: string
  level: string
  message: string
  status: string
  created_at?: string
}

interface ServiceConfig {
  name: string
  port: number
  accelerator: string
  batch_size: number
  min_batch_size: number
  max_batch_size: number
  priority: number
  can_offload_to_cpu: boolean
  can_offload_to_npu: boolean
  current_load: number
}

interface PolicyConfig {
  name: string
  description: string
  vram_threshold_high: number
  vram_threshold_critical: number
  gpu_threshold_high: number
  enable_npu_offload: boolean
  enable_cpu_offload: boolean
  enable_batch_adjustment: boolean
}

interface AdjustmentItem {
  service: string
  name: string
  current: ServiceConfig
  optimal: ServiceConfig
  changes: string[]
  needs_update: boolean
}

// ==================== 响应式状态 ====================

const router = useRouter()
const loading = ref(false)
const state = ref<ResourceState>({
  vram_total_gb: 0, vram_used_gb: 0, vram_free_gb: 0, vram_percent: 0,
  gpu_percent: 0, cpu_percent: 0,
  ram_total_gb: 0, ram_available_gb: 0, ram_percent: 0,
  npu_available: false, npu_columns: 0,
  gpu_power_w: 0, gpu_power_cap_w: 0,
  gpu_temp_c: 0, cpu_temp_c: 0,
  gpu_model: '',
  timestamp: 0,
})
const loadLevel = ref<string>('low')
const currentPolicy = ref<PolicyConfig | null>(null)
const historyCount = ref(0)
const services = ref<Record<string, ServiceConfig>>({})
const adjustments = ref<AdjustmentItem[]>([])
const alerts = ref<AlertItem[]>([])

// 历史数据用于图表
const historyData = ref<ResourceState[]>([])
const MAX_HISTORY_POINTS = 60

// 定时器
let refreshTimer: ReturnType<typeof setInterval> | null = null

// ==================== 计算属性 ====================

const serviceList = computed(() => Object.values(services.value))

const loadLevelLabel = computed(() => {
  const map: Record<string, string> = {
    low: 'LOW', medium: 'MEDIUM', high: 'HIGH', critical: 'CRITICAL',
  }
  return map[loadLevel.value] ?? loadLevel.value.toUpperCase()
})

const loadLevelTagType = computed(() => {
  const map: Record<string, '' | 'success' | 'warning' | 'danger'> = {
    low: 'success', medium: '', high: 'warning', critical: 'danger',
  }
  return map[loadLevel.value] ?? ''
})

const policyLabel = computed(() => {
  const map: Record<string, string> = {
    performance: '性能优先', balanced: '平衡模式',
    conservative: '保守模式', llm_priority: 'LLM 优先',
  }
  return map[currentPolicy.value?.name ?? ''] ?? currentPolicy.value?.name ?? '-'
})

// GPU 温度样式
const gpuTempColor = computed(() => {
  const t = state.value.gpu_temp_c ?? 0
  if (t >= 85) return '#ef4444'
  if (t >= 70) return '#f97316'
  if (t >= 55) return '#e6a23c'
  return '#10b981'
})

const gpuTempBgColor = computed(() => {
  const t = state.value.gpu_temp_c ?? 0
  if (t >= 85) return '#fef2f2'
  if (t >= 70) return '#fff7ed'
  if (t >= 55) return '#fffbeb'
  return '#ecfdf5'
})

const gpuTempLabel = computed(() => {
  const t = state.value.gpu_temp_c ?? 0
  if (t >= 85) return '过热'
  if (t >= 70) return '偏高'
  if (t >= 55) return '温热'
  return '正常'
})

// 预警相关
const activeAlertCount = computed(() => alerts.value.filter(a => a.status === 'active').length)
const recentAlerts = computed(() => alerts.value.slice(0, 3))

function alertLevelTagType(level: string): '' | 'success' | 'warning' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger'> = {
    critical: 'danger', high: 'danger', medium: 'warning', low: '',
  }
  return map[level] ?? ''
}

function alertLevelLabel(level: string): string {
  const map: Record<string, string> = {
    critical: '危急', high: '高', medium: '中', low: '低',
  }
  return map[level] ?? level
}

function formatAlertTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function goToAlertList() {
  router.push({ name: 'AdminAlerts' })
}

const CHART_COLORS = ['#3b82f6', '#f97316', '#10b981', '#8b5cf6']

const vramGpuChartOption = computed(() => ({
  color: CHART_COLORS,
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['VRAM %', 'GPU %'], top: 0 },
  grid: { left: 50, right: 20, top: 36, bottom: 30 },
  xAxis: {
    type: 'category' as const,
    data: historyData.value.map((_, i) => i),
    axisLabel: { show: false },
  },
  yAxis: {
    type: 'value' as const,
    max: 100,
    axisLabel: { formatter: '{value}%' },
  },
  series: [
    {
      name: 'VRAM %', type: 'line', data: historyData.value.map(d => (d.vram_percent * 100).toFixed(1)),
      smooth: true, areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#3b82f6' },
    },
    {
      name: 'GPU %', type: 'line', data: historyData.value.map(d => d.gpu_percent.toFixed(1)),
      smooth: true, areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#f97316' },
    },
  ],
}))

const cpuRamChartOption = computed(() => ({
  color: ['#10b981', '#8b5cf6'],
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['CPU %', 'RAM %'], top: 0 },
  grid: { left: 50, right: 20, top: 36, bottom: 30 },
  xAxis: {
    type: 'category' as const,
    data: historyData.value.map((_, i) => i),
    axisLabel: { show: false },
  },
  yAxis: {
    type: 'value' as const,
    max: 100,
    axisLabel: { formatter: '{value}%' },
  },
  series: [
    {
      name: 'CPU %', type: 'line', data: historyData.value.map(d => d.cpu_percent.toFixed(1)),
      smooth: true, areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#10b981' },
    },
    {
      name: 'RAM %', type: 'line', data: historyData.value.map(d => d.ram_percent.toFixed(1)),
      smooth: true, areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#8b5cf6' },
    },
  ],
}))

// ==================== 方法 ====================

function progressColor(ratio: number): string {
  if (ratio >= 0.85) return '#f56c6c'
  if (ratio >= 0.50) return '#e6a23c'
  return '#67c23a'
}

function appendHistory(s: ResourceState) {
  historyData.value.push(s)
  if (historyData.value.length > MAX_HISTORY_POINTS) {
    historyData.value = historyData.value.slice(-MAX_HISTORY_POINTS)
  }
}

async function fetchStatus() {
  try {
    const res = await resourceApi.getStatus()
    const data = res.data
    state.value = data.state
    loadLevel.value = data.load_level
    historyCount.value = data.history_count
    if (data.policy) {
      currentPolicy.value = data.policy
    }
    appendHistory(data.state)
  } catch (err: any) {
    console.error('ResourceMonitor fetchStatus error:', err)
  }
}

async function fetchServices() {
  try {
    const res = await resourceApi.getServices()
    services.value = res.data
  } catch (err: any) {
    console.error('ResourceMonitor fetchServices error:', err)
    // 如果是 401 错误，axios 拦截器会自动跳转登录页
    // 其他错误保持当前状态，不覆盖
  }
}

async function fetchAdjustments() {
  try {
    const res = await resourceApi.getAdjustments()
    // 后端返回 {adjustments: [...]} 对象，需要提取数组
    const data = res.data as any
    adjustments.value = Array.isArray(data) ? data : (data.adjustments || [])
  } catch (err: any) {
    console.error('ResourceMonitor fetchAdjustments error:', err)
  }
}

async function fetchAlerts() {
  try {
    const res = await alertApi.list({ status: 'active' })
    alerts.value = Array.isArray(res.data) ? res.data : []
  } catch (err: any) {
    console.error('ResourceMonitor fetchAlerts error:', err)
  }
}

async function fetchAll() {
  loading.value = true
  try {
    await Promise.all([fetchStatus(), fetchServices(), fetchAdjustments(), fetchAlerts()])
  } finally {
    loading.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  fetchAll()
  refreshTimer = setInterval(fetchAll, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.stat-cards :deep(.el-card__body) { padding: 20px; }
.stat-card-wrapper { transition: box-shadow 0.2s; cursor: default; }
.stat-card-wrapper:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06); }
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-card__icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-card__label { font-size: 13px; color: #64748b; margin-bottom: 4px; }
.stat-card__value { font-size: 20px; font-weight: 700; color: #0f172a; }
.stat-card__sub { font-size: 12px; color: #94a3b8; margin-top: 2px; }
.load-level-detail { display: flex; flex-direction: column; gap: 12px; }
.load-level-detail__item { display: flex; align-items: center; gap: 12px; }
.load-level-detail__item .label { font-size: 13px; color: #64748b; min-width: 80px; flex-shrink: 0; }
.load-level-detail__item .value { font-size: 13px; color: #0f172a; }
.alert-summary-list { display: flex; flex-direction: column; gap: 10px; }
.alert-summary-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 8px; background: #f8fafc; }
.alert-summary-item__msg { flex: 1; font-size: 13px; color: #0f172a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-summary-item__time { font-size: 12px; color: #94a3b8; flex-shrink: 0; }
</style>
