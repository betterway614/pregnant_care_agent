/* Admin 审计日志 + 知识库管理 + API配置 API */
import client from './client'
import type {
  AdminDashboardResponse,
  AdminTokenDaily,
  AdminTokenByAgent,
  AdminSessionListResponse,
  AdminSessionDetail,
  KnowledgeStats,
  KnowledgeDocListResponse,
  KnowledgeUploadResponse,
  KnowledgeIngestResponse,
  RagConfig,
  RagConfigUpdate,
  KnowledgeSearchResponse,
  KnowledgeChunkListResponse,
  ChunkStatsResponse,
  AutoTagResponse,
  ApiConfig,
  ApiConfigUpdate,
  ApiTestResult,
} from '@/types'

export const adminApi = {
  // ── 审计日志 ──
  getDashboard: (dateFrom: string, dateTo: string) =>
    client.get<AdminDashboardResponse>('/admin/audit/dashboard', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  getTokenDaily: (dateFrom: string, dateTo: string) =>
    client.get<{ data: AdminTokenDaily[] }>('/admin/audit/token/daily', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  getTokenByAgent: (dateFrom: string, dateTo: string) =>
    client.get<{ data: AdminTokenByAgent[] }>('/admin/audit/token/by-agent', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  getSessions: (params: {
    page: number
    page_size: number
    user_id?: string
    agent_role?: string
    agent_variant?: string
    date_from?: string
    date_to?: string
  }) => client.get<AdminSessionListResponse>('/admin/audit/sessions', { params }),

  getSessionDetail: (sessionId: string) =>
    client.get<AdminSessionDetail>(`/admin/audit/sessions/${sessionId}`),

  // ── 知识库管理 ──
  getKnowledgeStats: () =>
    client.get<KnowledgeStats>('/admin/knowledge/stats'),

  getKnowledgeDocs: () =>
    client.get<KnowledgeDocListResponse>('/admin/knowledge/docs'),

  uploadKnowledgeDoc: (file: File, name?: string, autoIngest: boolean = true) => {
    const formData = new FormData()
    formData.append('file', file)
    if (name) formData.append('name', name)
    formData.append('auto_ingest', String(autoIngest))
    return client.post<KnowledgeUploadResponse>('/admin/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000, // 上传+入库可能耗时较长
    })
  },

  deleteKnowledgeDoc: (filename: string) =>
    client.delete<{ deleted: string; message: string }>(`/admin/knowledge/docs/${encodeURIComponent(filename)}`),

  ingestAllDocs: (force: boolean = false) =>
    client.post<KnowledgeIngestResponse>('/admin/knowledge/ingest', null, {
      params: { force },
      timeout: 300000, // 全量入库可能耗时较长
    }),

  ingestSingleDoc: (filename: string, force: boolean = false) =>
    client.post<{ message: string; filename: string; name: string }>(
      `/admin/knowledge/ingest/${encodeURIComponent(filename)}`,
      null,
      { params: { force }, timeout: 120000 },
    ),

  // ── RAG 配置管理 ──
  getRagConfig: () =>
    client.get<RagConfig>('/admin/knowledge/config'),

  updateRagConfig: (config: RagConfigUpdate) =>
    client.put<{ message: string; config: RagConfig }>('/admin/knowledge/config', config),

  getKnowledgeTags: () =>
    client.get<{ tags: string[]; description: Record<string, string> }>('/admin/knowledge/tags'),

  // ── 知识库检索 ──
  searchKnowledge: (query: string, filters?: Record<string, string>, maxResults?: number) =>
    client.post<KnowledgeSearchResponse>('/admin/knowledge/search', {
      query,
      filters,
      max_results: maxResults,
    }, { timeout: 30000 }),

  // ── 带元数据的上传 ──
  uploadKnowledgeDocWithMeta: (
    file: File, name?: string, autoIngest: boolean = true,
    metadata?: Record<string, string>, autoTag: boolean = true,
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    if (name) formData.append('name', name)
    formData.append('auto_ingest', String(autoIngest))
    formData.append('auto_tag', String(autoTag))
    if (metadata && Object.keys(metadata).length > 0) {
      formData.append('metadata_json', JSON.stringify(metadata))
    }
    return client.post<KnowledgeUploadResponse>('/admin/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000, // AI 打标签可能耗时
    })
  },

  // ── AI 自动打标签 ──
  autoTagDocument: (filename: string) =>
    client.post<AutoTagResponse>(`/admin/knowledge/auto-tag`, null, {
      params: { filename },
      timeout: 60000,
    }),

  // ── 嵌入文本块浏览 ──
  getKnowledgeChunks: (page: number = 1, pageSize: number = 20, name?: string) =>
    client.get<KnowledgeChunkListResponse>('/admin/knowledge/chunks', {
      params: { page, page_size: pageSize, ...(name ? { name } : {}) },
    }),

  getChunkStats: () =>
    client.get<ChunkStatsResponse>('/admin/knowledge/chunks/stats'),

  // ── API 配置管理 ──
  getApiConfig: () =>
    client.get<ApiConfig>('/admin/api-config'),

  updateApiConfig: (config: ApiConfigUpdate) =>
    client.put<{ message: string; config: ApiConfig }>('/admin/api-config', config),

  testApiConnection: (mode: 'local' | 'cloud' | 'asr' | 'tts' | 'embedding', provider?: string) =>
    client.post<ApiTestResult>('/admin/api-config/test', { mode, provider }),
}

// ── 资源监控 API ──
export const resourceApi = {
  getStatus: () =>
    client.get<{
      state: {
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
      load_level: 'low' | 'medium' | 'high' | 'critical'
      policy: {
        name: string
        description: string
        vram_threshold_high: number
        vram_threshold_critical: number
        gpu_threshold_high: number
        enable_npu_offload: boolean
        enable_cpu_offload: boolean
        enable_batch_adjustment: boolean
      }
      history_count: number
    }>('/admin/resource/status'),

  getServices: () =>
    client.get<Record<string, {
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
    }>>('/admin/resource/services'),

  updateService: (serviceName: string, data: {
    enabled?: boolean
    replicas?: number
    memory_limit?: string
    cpu_limit?: string
    env_overrides?: Record<string, string>
    description?: string
  }) => client.put(`/admin/resource/services/${serviceName}`, data),

  getPolicy: () =>
    client.get<{
      current_policy: string
      policies: Record<string, {
        name: string
        description: string
        vram_threshold_high: number
        vram_threshold_critical: number
        gpu_threshold_high: number
        enable_npu_offload: boolean
        enable_cpu_offload: boolean
        enable_batch_adjustment: boolean
      }>
      services: Record<string, {
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
      }>
    }>('/admin/resource/policy'),

  switchPolicy: (policy: string, reason?: string) =>
    client.put('/admin/resource/policy', { policy, reason }),

  getAdjustments: () =>
    client.get<Array<{
      service: string
      name: string
      current: {
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
      optimal: {
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
      changes: string[]
      needs_update: boolean
    }>>('/admin/resource/adjustments'),

  getHistory: (params?: { date_from?: string; date_to?: string; metric?: string }) =>
    client.get<Array<{
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
    }>>('/admin/resource/history', { params }),

  startMonitoring: (intervalSeconds?: number) =>
    client.post('/admin/resource/monitoring/start', { interval_seconds: intervalSeconds }),

  stopMonitoring: () =>
    client.post('/admin/resource/monitoring/stop'),

  getLlmAnalysis: () =>
    client.get<any>('/admin/resource/llm-analysis'),
}
