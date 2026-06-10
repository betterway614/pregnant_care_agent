/* 系统资源管理 API */
import client from './client'

// ==================== TypeScript 接口 ====================

/** 系统资源状态 */
export interface ResourceState {
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
  timestamp: number
}

/** 服务配置 */
export interface ServiceConfig {
  name: string
  port: number
  accelerator: 'gpu' | 'npu' | 'cpu'
  batch_size: number
  min_batch_size: number
  max_batch_size: number
  priority: number
  can_offload_to_cpu: boolean
  can_offload_to_npu: boolean
  current_load: number
}

/** 资源策略 */
export interface ResourcePolicy {
  name: string
  description: string
  vram_threshold_high: number
  vram_threshold_critical: number
  gpu_threshold_high: number
  enable_npu_offload: boolean
  enable_cpu_offload: boolean
  enable_batch_adjustment: boolean
}

/** 优化建议 */
export interface Adjustment {
  service: string
  name: string
  current: ServiceConfig
  optimal: ServiceConfig
  changes: string[]
  needs_update: boolean
}

/** 历史指标 */
export interface ResourceMetric {
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
  timestamp: number
}

/** 系统状态响应 */
export interface SystemStatusResponse {
  state: ResourceState
  load_level: 'low' | 'medium' | 'high' | 'critical'
  policy: ResourcePolicy
  history_count: number
}

/** 策略切换请求 */
export interface PolicyUpdate {
  policy: string
  reason?: string
}

/** 服务配置更新请求 */
export interface ServiceConfigUpdate {
  enabled?: boolean
  replicas?: number
  memory_limit?: string
  cpu_limit?: string
  env_overrides?: Record<string, string>
  description?: string
}

/** 监控控制请求 */
export interface MonitoringControl {
  interval_seconds?: number
  targets?: string[]
}

/** LLM 分析响应 */
export interface LlmAnalysisResponse {
  analysis: string
  recommendations: string[]
  timestamp: string
}

// ==================== API 方法 ====================

export const resourceApi = {
  // ── 系统资源状态 ──
  getStatus: () =>
    client.get<SystemStatusResponse>('/admin/resource/status'),

  // ── 服务配置 ──
  getServices: () =>
    client.get<{ data: Record<string, ServiceConfig> }>('/admin/resource/services'),

  updateService: (serviceName: string, config: ServiceConfigUpdate) =>
    client.put<{ message: string; service: ServiceConfig }>(
      `/admin/resource/services/${serviceName}`,
      config,
    ),

  // ── 策略管理 ──
  getPolicy: () =>
    client.get<ResourcePolicy>('/admin/resource/policy'),

  setPolicy: (policyName: string, reason?: string) =>
    client.put<{ message: string; policy: ResourcePolicy }>(
      '/admin/resource/policy',
      { policy: policyName, reason },
    ),

  // ── 优化建议 ──
  getAdjustments: () =>
    client.get<{ data: Adjustment[] }>('/admin/resource/adjustments'),

  // ── 历史数据 ──
  getHistory: (limit: number = 100) =>
    client.get<{ data: ResourceMetric[] }>('/admin/resource/history', {
      params: { limit },
    }),

  // ── 监控控制 ──
  startMonitoring: (intervalSeconds?: number) =>
    client.post<{ message: string; monitoring: boolean }>(
      '/admin/resource/monitoring/start',
      { interval_seconds: intervalSeconds },
    ),

  stopMonitoring: () =>
    client.post<{ message: string; monitoring: boolean }>(
      '/admin/resource/monitoring/stop',
    ),

  // ── LLM 分析 ──
  getLlmAnalysis: () =>
    client.get<LlmAnalysisResponse>('/admin/resource/llm-analysis'),
}
