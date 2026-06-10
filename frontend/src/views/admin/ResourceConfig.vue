<template>
  <div class="resource-config">
    <!-- 左右布局 -->
    <div class="resource-layout">
      <!-- 左侧: 策略选择 -->
      <div class="resource-layout__left">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div>
                <h3>资源调度策略</h3>
                <p class="section-desc">选择资源分配策略以优化系统性能</p>
              </div>
            </div>
          </template>

          <div class="policy-grid">
            <div
              v-for="p in policyOptions"
              :key="p.value"
              class="policy-card"
              :class="{ active: currentPolicy === p.value }"
              @click="selectPolicy(p.value)"
            >
              <div class="policy-card__header">
                <el-icon :size="20" :color="currentPolicy === p.value ? '#3b82f6' : '#94a3b8'">
                  <component :is="p.icon" />
                </el-icon>
                <span class="policy-card__name">{{ p.label }}</span>
                <el-icon v-if="currentPolicy === p.value" :size="16" color="#3b82f6"><CircleCheck /></el-icon>
              </div>
              <p class="policy-card__desc">{{ p.description }}</p>
            </div>
          </div>

          <!-- 策略详情 -->
          <div v-if="currentPolicyDetail" class="policy-detail">
            <h4>策略阈值</h4>
            <el-descriptions :column="1" size="small" border>
              <el-descriptions-item label="VRAM 高负载阈值">
                {{ (currentPolicyDetail.vram_threshold_high * 100).toFixed(0) }}%
              </el-descriptions-item>
              <el-descriptions-item label="VRAM 紧急阈值">
                {{ (currentPolicyDetail.vram_threshold_critical * 100).toFixed(0) }}%
              </el-descriptions-item>
              <el-descriptions-item label="GPU 高负载阈值">
                {{ (currentPolicyDetail.gpu_threshold_high * 100).toFixed(0) }}%
              </el-descriptions-item>
              <el-descriptions-item label="NPU 卸载">
                <el-tag :type="currentPolicyDetail.enable_npu_offload ? 'success' : 'info'" size="small">
                  {{ currentPolicyDetail.enable_npu_offload ? '启用' : '禁用' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="CPU 卸载">
                <el-tag :type="currentPolicyDetail.enable_cpu_offload ? 'success' : 'info'" size="small">
                  {{ currentPolicyDetail.enable_cpu_offload ? '启用' : '禁用' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="批处理调整">
                <el-tag :type="currentPolicyDetail.enable_batch_adjustment ? 'success' : 'info'" size="small">
                  {{ currentPolicyDetail.enable_batch_adjustment ? '启用' : '禁用' }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>
      </div>

      <!-- 右侧: 服务配置表格 -->
      <div class="resource-layout__right">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div>
                <h3>服务配置</h3>
                <p class="section-desc">编辑各服务的批处理大小和加速器类型</p>
              </div>
              <el-button type="primary" plain size="small" :loading="loading" @click="fetchData">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>

          <el-table :data="serviceList" stripe class="service-table">
            <el-table-column label="服务名称" prop="name" min-width="160">
              <template #default="{ row }">
                <div class="service-name-cell">
                  <el-icon :size="16" :color="getServiceColor(row.service_key)">
                    <component :is="getServiceIcon(row.service_key)" />
                  </el-icon>
                  <span>{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="端口" prop="port" width="80" align="center" />
            <el-table-column label="加速器类型" width="140">
              <template #default="{ row }">
                <el-select
                  v-model="row.accelerator"
                  size="small"
                  @change="onServiceChange(row)"
                >
                  <el-option label="GPU" value="gpu" />
                  <el-option label="NPU" value="npu" />
                  <el-option label="CPU" value="cpu" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="批处理大小" width="180">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.batch_size"
                  :min="row.min_batch_size"
                  :max="row.max_batch_size"
                  size="small"
                  @change="onServiceChange(row)"
                />
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="getPriorityType(row.priority)" size="small">
                  {{ row.priority }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可卸载" width="120">
              <template #default="{ row }">
                <div class="offload-tags">
                  <el-tag v-if="row.can_offload_to_cpu" size="small" type="info">CPU</el-tag>
                  <el-tag v-if="row.can_offload_to_npu" size="small" type="warning">NPU</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  link
                  size="small"
                  :disabled="!row._dirty"
                  @click="saveService(row)"
                >
                  保存
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 优化建议 -->
        <el-card v-if="adjustments.length > 0" shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div>
                <h3>优化建议</h3>
                <p class="section-desc">根据当前资源状态生成的配置优化建议</p>
              </div>
            </div>
          </template>

          <div v-for="adj in adjustments" :key="adj.service" class="adjustment-item">
            <div class="adjustment-item__header">
              <span class="adjustment-item__name">{{ adj.name }}</span>
              <el-tag v-if="adj.needs_update" type="warning" size="small">需要调整</el-tag>
              <el-tag v-else type="success" size="small">最优</el-tag>
            </div>
            <div v-if="adj.changes.length > 0" class="adjustment-item__changes">
              <p v-for="(change, idx) in adj.changes" :key="idx" class="change-line">
                <el-icon><Right /></el-icon>
                {{ change }}
              </p>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 保存栏 -->
    <div class="save-bar">
      <el-button @click="resetAll" :disabled="!isDirty">
        <el-icon><RefreshLeft /></el-icon>
        重置
      </el-button>
      <el-button type="primary" :loading="saving" :disabled="!isDirty" @click="saveAll">
        <el-icon><Check /></el-icon>
        保存全部
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CircleCheck, Refresh, RefreshLeft, Check, Right,
  Cpu, Monitor, Connection, DataBoard,
} from '@element-plus/icons-vue'
import client from '@/api/client'

// ==================== 类型 ====================

interface PolicyInfo {
  name: string
  description: string
  vram_threshold_high: number
  vram_threshold_critical: number
  gpu_threshold_high: number
  enable_npu_offload: boolean
  enable_cpu_offload: boolean
  enable_batch_adjustment: boolean
}

interface ServiceConfig {
  name: string
  service_key: string
  port: number
  accelerator: string
  batch_size: number
  min_batch_size: number
  max_batch_size: number
  priority: number
  can_offload_to_cpu: boolean
  can_offload_to_npu: boolean
  current_load: number
  _dirty: boolean
}

interface AdjustmentItem {
  service: string
  name: string
  current: Record<string, any>
  optimal: Record<string, any>
  changes: string[]
  needs_update: boolean
}

// ==================== 策略选项 ====================

const policyOptions = [
  {
    value: 'performance',
    label: '性能优先',
    icon: 'Monitor',
    description: '所有服务使用 GPU，高批处理大小，最大化吞吐量',
  },
  {
    value: 'balanced',
    label: '平衡模式',
    icon: 'Connection',
    description: 'ASR 使用 NPU，其他 GPU，兼顾性能与资源',
  },
  {
    value: 'conservative',
    label: '保守模式',
    icon: 'DataBoard',
    description: 'VRAM 紧张时积极卸载，确保系统稳定',
  },
  {
    value: 'llm_priority',
    label: 'LLM 优先',
    icon: 'Cpu',
    description: '其他服务让步给 LLM，保证对话质量',
  },
]

// ==================== 状态 ====================

const currentPolicy = ref('balanced')
const policies = ref<Record<string, PolicyInfo>>({})
const serviceList = ref<ServiceConfig[]>([])
const adjustments = ref<AdjustmentItem[]>([])
const loading = ref(false)
const saving = ref(false)
const isDirty = ref(false)

// ==================== 计算属性 ====================

const currentPolicyDetail = computed(() => {
  return policies.value[currentPolicy.value] || null
})

// ==================== 数据获取 ====================

async function fetchPolicy() {
  try {
    const res = await client.get('/admin/resource/policy')
    const data = res.data
    currentPolicy.value = data.name
    policies.value = { [data.name]: data }
    // 如果返回了所有策略，也保存
    if (data.policies) {
      policies.value = data.policies
    }
  } catch (err: any) {
    console.error('fetchPolicy error:', err)
  }
}

async function fetchServices() {
  try {
    const res = await client.get('/admin/resource/services')
    const data = res.data
    // 后端返回以 service_key 为键的字典
    const list: ServiceConfig[] = []
    for (const [key, config] of Object.entries(data)) {
      list.push({
        ...(config as any),
        service_key: key,
        _dirty: false,
      })
    }
    serviceList.value = list
  } catch (err: any) {
    console.error('fetchServices error:', err)
  }
}

async function fetchAdjustments() {
  try {
    const res = await client.get('/admin/resource/adjustments')
    adjustments.value = res.data
  } catch (err: any) {
    console.error('fetchAdjustments error:', err)
  }
}

async function fetchData() {
  loading.value = true
  try {
    await Promise.all([fetchPolicy(), fetchServices(), fetchAdjustments()])
  } finally {
    loading.value = false
  }
}

// ==================== 策略操作 ====================

async function selectPolicy(policy: string) {
  if (policy === currentPolicy.value) return
  try {
    await client.put('/admin/resource/policy', { policy })
    currentPolicy.value = policy
    ElMessage.success(`策略已切换为: ${policyOptions.find(p => p.value === policy)?.label || policy}`)
    // 切换策略后刷新建议
    await fetchAdjustments()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '策略切换失败')
  }
}

// ==================== 服务配置操作 ====================

function onServiceChange(row: ServiceConfig) {
  row._dirty = true
  isDirty.value = true
}

async function saveService(row: ServiceConfig) {
  try {
    await client.put(`/admin/resource/services/${row.service_key}`, {
      batch_size: row.batch_size,
      accelerator: row.accelerator,
    })
    row._dirty = false
    // 检查是否还有未保存的
    isDirty.value = serviceList.value.some(s => s._dirty)
    ElMessage.success(`${row.name} 配置已保存`)
    await fetchAdjustments()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || `${row.name} 配置保存失败`)
  }
}

async function saveAll() {
  saving.value = true
  try {
    const dirtyServices = serviceList.value.filter(s => s._dirty)
    await Promise.all(
      dirtyServices.map(s =>
        client.put(`/admin/resource/services/${s.service_key}`, {
          batch_size: s.batch_size,
          accelerator: s.accelerator,
        })
      )
    )
    serviceList.value.forEach(s => { s._dirty = false })
    isDirty.value = false
    ElMessage.success('所有配置已保存')
    await fetchAdjustments()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  await fetchData()
  isDirty.value = false
  ElMessage.info('已重置为服务端配置')
}

// ==================== 辅助函数 ====================

function getServiceIcon(key: string) {
  const map: Record<string, string> = {
    llm: 'Cpu',
    bge_m3: 'DataBoard',
    tts: 'Monitor',
    asr: 'Connection',
  }
  return map[key] || 'Monitor'
}

function getServiceColor(key: string) {
  const map: Record<string, string> = {
    llm: '#3b82f6',
    bge_m3: '#10b981',
    tts: '#f97316',
    asr: '#8b5cf6',
  }
  return map[key] || '#94a3b8'
}

function getPriorityType(priority: number): '' | 'success' | 'warning' | 'danger' {
  if (priority >= 9) return 'danger'
  if (priority >= 7) return 'warning'
  if (priority >= 5) return 'success'
  return ''
}

// ==================== 初始化 ====================

onMounted(fetchData)
</script>

<style scoped>
.resource-config {
  max-width: 1200px;
}

/* 左右布局 */
.resource-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.resource-layout__left {
  width: 360px;
  flex-shrink: 0;
}

.resource-layout__right {
  flex: 1;
  min-width: 0;
}

/* 区块卡片 */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-header h3 {
  margin: 0 0 4px 0;
  font-size: 15px;
  color: #0f172a;
}

.section-desc {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

/* 策略卡片网格 */
.policy-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.policy-card {
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
}

.policy-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.policy-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
}

.policy-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.policy-card__name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.policy-card__desc {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

/* 策略详情 */
.policy-detail {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.policy-detail h4 {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #334155;
}

/* 服务表格 */
.service-table {
  width: 100%;
}

.service-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.offload-tags {
  display: flex;
  gap: 4px;
}

/* 优化建议 */
.adjustment-item {
  padding: 12px 0;
  border-bottom: 1px solid #f1f5f9;
}

.adjustment-item:last-child {
  border-bottom: none;
}

.adjustment-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.adjustment-item__name {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.adjustment-item__changes {
  margin-top: 6px;
}

.change-line {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 4px 0;
  font-size: 13px;
  color: #64748b;
}

/* 保存栏 */
.save-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
  position: sticky;
  bottom: 0;
  background: #f1f5f9;
  z-index: 10;
}
</style>
