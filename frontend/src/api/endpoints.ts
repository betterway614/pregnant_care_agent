/* API 端点封装 */
import client from './client'
import type {
  Pregnant, FollowUpRecord, Alert, ScheduleNode,
  FgrAssessment, FgrTrendPoint, PatientImageInfo, MedicalOrder, OrderDocument,
  DashboardStats, ChatRequest, ChatResponse,
  HomeResponse, RecommendResponse,
  HealthTrendResponse, FollowUpHistoryResponse, LabTrendResponse,
  FollowUpPendingResponse,
} from '@/types'

// 对话
export const chatApi = {
  send: (data: ChatRequest) => client.post<ChatResponse>('/chat/send', data),
  asr: (data: { audio_data: string; audio_format: string }) =>
    client.post<{ text: string; success: boolean }>('/chat/asr', data),
  getMemory: (pregnantId: string) => client.get('/chat/history', { params: { pregnant_id: pregnantId } }),
  clearMemory: (pregnantId: string) => client.delete('/chat/memory', { params: { pregnant_id: pregnantId } }),
  getContext: (pregnantId: string) => client.get(`/chat/context/${pregnantId}`),
  getProactive: (pregnantId: string) => client.get<{ message: string; greeting_type: string; icon: string }>(`/chat/proactive/${pregnantId}`),
  getTrends: (pregnantId: string) => client.get<{ trends: Array<{ metric: string; current_value: number; unit: string; trend: string; summary: string; is_normal: boolean | null }> }>(`/chat/trends/${pregnantId}`),
  getConversation: (pregnantId: string, sessionId?: string) =>
    client.get<{ session_id: string; messages: Array<{ role: string; content: string; session_id?: string; created_at?: string }> }>(
      `/chat/conversation/${pregnantId}`,
      { params: { session_id: sessionId } }
    ),
  listSessions: (pregnantId: string) =>
    client.get<{ sessions: Array<{ session_id: string; message_count: number; started_at: string; last_message_at: string; preview: string }> }>(
      `/chat/sessions/${pregnantId}`
    ),
  clearConversation: (pregnantId: string, sessionId?: string) =>
    client.delete(`/chat/conversation/${pregnantId}`, { params: { session_id: sessionId } }),
}

// 用户反馈（支持孕妇/护士/医生三端）
export const feedbackApi = {
  submit: (data: {
    message_id: string
    rating: string
    pregnant_id?: string
    feedback_role?: 'pregnant' | 'nurse' | 'doctor'
    comment?: string
    session_id?: string
    audit_log_id?: number
  }) => client.post('/feedback', data),
  getStats: (pregnantId?: string, feedbackRole?: string) =>
    client.get('/feedback/stats', { params: { pregnant_id: pregnantId, feedback_role: feedbackRole } }),
}

// 排期
export const scheduleApi = {
  get: (pregnantId: string) => client.get<ScheduleNode[]>(`/schedule/${pregnantId}`),
  generate: (pregnantId: string) => client.post(`/schedule/generate/${pregnantId}`),
  publish: (pregnantId: string) => client.put(`/schedule/${pregnantId}/publish`),
  updateNode: (nodeId: string, data: any) => client.put(`/schedule/node/${nodeId}`, data),
}

// 随访
export const followUpApi = {
  trigger: (pregnantId: string, templateId?: string) =>
    client.post('/followup/trigger', { pregnant_id: pregnantId, template_id: templateId }),
  list: (params?: { status?: string; pregnant_id?: string; today_only?: boolean }) =>
    client.get<FollowUpRecord[]>('/followup/records', { params }),
  confirm: (recordId: string, status: string = 'confirmed', extra?: { reviewer_id?: string; review_comment?: string; ai_snapshot?: Record<string, any> }) =>
    client.put(`/followup/records/${recordId}/confirm`, { status, ...(extra || {}) }),
  update: (recordId: string, data: any) =>
    client.put(`/followup/records/${recordId}`, data),
  getPending: (pregnantId: string) =>
    client.get<FollowUpPendingResponse>(`/followup/pending/${pregnantId}`),
  respond: (recordId: string, answers: Record<string, any>, totalCount?: number) =>
    client.post('/followup/respond', { record_id: recordId, answers, total_count: totalCount || 0 }),
  // 流式 AI 分析（SSE）
  analyzeStream: (
    recordId: string,
    callbacks: SSEStreamCallbacks,
    signal?: AbortSignal,
  ): Promise<void> => _sseFetch('/api/v1/followup/respond/analyze/stream', { record_id: recordId }, callbacks, signal),
  aiReview: (recordId: string) =>
    client.get<any>(`/followup/records/${recordId}/ai-review`),
  getDocument: (recordId: string) =>
    client.get<{ record_id: string; patient_name: string; snapshot: any; text: string; signature: any; has_document: boolean }>(`/followup/records/${recordId}/document`),
  sign: (recordId: string, signature_image: string, signer_name: string) =>
    client.post<{ message: string; signed_at: string }>(`/followup/records/${recordId}/sign`, { signature_image, signer_name }),
}

// 预警
export const alertApi = {
  list: (params?: { status?: string; level?: string; pregnant_id?: string }) =>
    client.get<Alert[]>('/alerts', { params }),
  evaluate: (pregnantId: string, data: any) =>
    client.post('/alerts/evaluate', { data }, { params: { pregnant_id: pregnantId } }),
  review: (alertId: string, action: string, reason?: string, targetLevel?: string) =>
    client.put(`/alerts/${alertId}/review`, { action, reason, target_level: targetLevel }),
}

// FGR
export const fgrApi = {
  // 评估已绑定图片的患者
  assess: (pregnantId: string, data: { gestational_weeks: number; image_type?: string }) =>
    client.post<FgrAssessment>(`/fgr/assess/${pregnantId}`, data),
  // 上传图片 + 自动分割 + 评估
  upload: (pregnantId: string, formData: FormData) =>
    client.post<FgrAssessment>(`/fgr/upload/${pregnantId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,  // nnU-Net 5折推理 + FGR 预测需要较长时间
    }),
  // 获取患者绑定的超声图信息
  patientImages: (pregnantId: string) =>
    client.get<PatientImageInfo>(`/fgr/patient-images/${pregnantId}`),
  // 批量获取所有映射患者的图片绑定状态，可选过滤指定ID
  patientImagesAll: (pregnantIds?: string) =>
    client.get<{ data: PatientImageInfo[] }>('/fgr/patient-images', {
      params: { pregnant_ids: pregnantIds },
    }),
  // 获取超声原图 Blob URL (通过 fetch + Authorization header 安全加载)
  loadImageBlobUrl: async (pregnantId: string): Promise<string | null> => {
    try {
      const token = localStorage.getItem('token')
      const resp = await fetch(`/api/v1/fgr/image/${pregnantId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!resp.ok) return null
      const blob = await resp.blob()
      return URL.createObjectURL(blob)
    } catch {
      return null
    }
  },
  // 趋势
  trend: (pregnantId: string) =>
    client.get<FgrTrendPoint[]>(`/fgr/trend/${pregnantId}`),
}

// 医嘱
export const orderApi = {
  get: (orderId: string) =>
    client.get<MedicalOrder>(`/orders/${orderId}`),
  generate: (data: { pregnant_id: string; alert_id?: string; risk_level: string; gestational_weeks: number }) =>
    client.post<MedicalOrder>('/orders/generate', data),
  list: (params?: { status?: string; pregnant_id?: string }) =>
    client.get<MedicalOrder[]>('/orders', { params }),
  sign: (orderId: string, data: { doctor_id: string; signature_image?: string; signer_name?: string }) =>
    client.put(`/orders/${orderId}/sign`, data),
  update: (orderId: string, data: any) =>
    client.put(`/orders/${orderId}`, data),
  templates: () => client.get('/orders/templates'),
  getPregnantOrders: (pregnantId: string) =>
    client.get(`/orders/pregnant/${pregnantId}`),
  acknowledge: (orderId: string) =>
    client.put(`/orders/${orderId}/acknowledge`),
  getDocument: (orderId: string) =>
    client.get<OrderDocument>(`/orders/${orderId}/document`),
}

// 统计
export const dashboardApi = {
  stats: () => client.get<DashboardStats>('/dashboard/stats'),
  pregnant: (params?: { search?: string; risk_tag?: string; has_alert?: boolean; page?: number; page_size?: number }) =>
    client.get<{ total: number; page: number; page_size: number; data: Pregnant[] }>('/dashboard/pregnant', { params }),
  pregnantDetail: (pregnantId: string) => client.get(`/dashboard/pregnant/${pregnantId}`),
}

// 孕妇
export const pregnantApi = {
  get: (pregnantId: string) => client.get<Pregnant>(`/pregnant/${pregnantId}`),
  update: (pregnantId: string, data: Partial<Pregnant>) => client.put<Pregnant>(`/pregnant/${pregnantId}`, data),
  getHome: (pregnantId: string) => client.get<HomeResponse>(`/pregnant/${pregnantId}/home`),
  getDailyTaskStatus: (pregnantId: string) =>
    client.get<{ weight: boolean; blood_pressure: boolean; fetal_movement: boolean }>(
      `/pregnant/${pregnantId}/daily-task-status`
    ),
  submitHealthData: (pregnantId: string, data: {
    weight?: number
    systolic?: number
    diastolic?: number
    fetal_movement?: number
    blood_sugar?: number
    blood_sugar_type?: 'fasting' | 'postprandial'
    heart_rate?: number
    sleep_hours?: number
    steps?: number
    mood?: 'good' | 'neutral' | 'bad'
  }) => client.post<{ success: boolean; saved_metrics: string[]; count: number; message: string }>(
    `/pregnant/${pregnantId}/health-data`, data
  ),
  getHealthTrends: (pregnantId: string, params: {
    metrics: string
    start_date?: string
    end_date?: string
    axis_mode?: 'date' | 'gestational_week'
    granularity?: 'daily' | 'weekly'
  }) => client.get<HealthTrendResponse>(
    `/pregnant/${pregnantId}/health-trends`,
    { params }
  ),
  getFollowUpHistory: (pregnantId: string, params?: {
    status?: string
    limit?: number
  }) => client.get<FollowUpHistoryResponse>(
    `/pregnant/${pregnantId}/follow-up-history`,
    { params }
  ),
  getLabTrends: (pregnantId: string, limit?: number) =>
    client.get<LabTrendResponse>(`/pregnant/${pregnantId}/lab-trends`, { params: { limit } }),
}

// AI 推荐
export const recommendApi = {
  get: (pregnantId: string) => client.get<RecommendResponse>(`/recommend/${pregnantId}`),
}

// AI 分析相关
export const aiAnalysisApi = {
  save: (data: { pregnant_id: string; result_data: any; analysis_type: string }) =>
    client.post('/nurse/ai-analysis', data),
  getHistory: (pregnantId: string) =>
    client.get<Array<{ id: string; pregnant_id: string; result_data: any; analysis_type: string; created_at: string }>>(
      `/nurse/ai-analysis/${pregnantId}`
    ),
}

// 护士AI
export const nurseAiApi = {
  analyze: (pregnantId: string) => client.post<any>('/nurse/analyze', { pregnant_id: pregnantId }),
  generateFollowUp: (pregnantId: string, templateId: string = 'standard') =>
    client.post<any>('/nurse/followup/generate', { pregnant_id: pregnantId, template_id: templateId }),
  getFollowupRecommendations: () =>
    client.get<{ recommendations: any[] }>('/nurse/followup-recommendations'),
  chatStream: (
    data: { message: string; pregnant_id?: string; message_type?: string; audio_data?: string; audio_format?: string; session_id?: string },
    callbacks: SSEStreamCallbacks,
    signal?: AbortSignal,
  ) => nurseChatStream(data, callbacks, signal),
}

/* ========== 护士 AI 流式对话 ========== */
async function nurseChatStream(
  data: { message: string; pregnant_id?: string; message_type?: string; audio_data?: string; audio_format?: string; session_id?: string },
  callbacks: SSEStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  await _sseFetch('/api/v1/nurse/chat/stream', data, callbacks, signal)
}

// 医生AI
export const doctorAiApi = {
  analyze: (pregnantId: string, query: string = '') =>
    client.post<any>(`/doctor/analyze/${pregnantId}`, { pregnant_id: pregnantId, query }, { timeout: 180000 }),
  chatStream: (
    data: { message: string; pregnant_id?: string; message_type?: string; audio_data?: string; audio_format?: string; session_id?: string },
    callbacks: SSEStreamCallbacks,
    signal?: AbortSignal,
  ) => doctorChatStream(data, callbacks, signal),
  generateReport: (pregnantId: string) =>
    client.post<any>(`/doctor/report/${pregnantId}`, null, { timeout: 120000 }),
}

// 医护协作
export const collaborationApi = {
  reportIssue: (data: { pregnant_id: string; issue_type: string; title: string; description: string; priority: string }) =>
    client.post<any>('/nurse/issues/report', data),
  listNurseIssues: (status: string = 'pending') =>
    client.get<any[]>('/nurse/issues', { params: { status } }),
  listDoctorIssues: (status: string = 'pending') =>
    client.get<any[]>('/doctor/issues', { params: { status } }),
  resolveIssue: (issueId: string, resolution: string) =>
    client.put<any>(`/doctor/issues/${issueId}/resolve`, null, { params: { resolution } }),
}

/* ========== 医生 AI 流式对话 ========== */
async function doctorChatStream(
  data: { message: string; pregnant_id?: string; message_type?: string; audio_data?: string; audio_format?: string; session_id?: string },
  callbacks: SSEStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  await _sseFetch('/api/v1/doctor/chat/stream', data, callbacks, signal)
}

// 医嘱解释
export const orderExplainApi = {
  explain: (orderId: string) => client.post<any>(`/orders/${orderId}/explain`),
}

// 胎动计数
export const fetalMovementApi = {
  createSession: (pregnantId: string) =>
    client.post<{ id: string; pregnant_id: string; start_time: string; total_count: number; kick_times: string[] }>
      ('/fetal-movement/sessions', { pregnant_id: pregnantId }),
  updateSession: (sessionId: string, data: { total_count: number; kick_times: string[]; notes?: string }) =>
    client.put<{ id: string; total_count: number; kick_times: string[]; duration_minutes?: number }>
      (`/fetal-movement/sessions/${sessionId}`, data),
  listSessions: (pregnantId: string, limit?: number) =>
    client.get<Array<{ id: string; start_time: string; end_time?: string; duration_minutes?: number; total_count: number; kick_times: string[]; notes?: string }>>
      (`/fetal-movement/sessions/${pregnantId}`, { params: { limit } }),
  deleteSession: (sessionId: string) =>
    client.delete(`/fetal-movement/sessions/${sessionId}`),
}


/* ========== 流式聊天（SSE + 非 SSE 降级） ========== */

import { fetchEventSource } from '@microsoft/fetch-event-source'

export interface SSEStreamCallbacks {
  onChunk?: (text: string) => void
  onDone?: (metadata: any) => void
  onError?: (err: Error) => void
  onThinking?: (message: string) => void
}

/**
 * SSE 流式请求内部实现（自动兼容非 SSE 响应）
 *
 * 关键设计：
 * - 收到 done 事件后禁止自动重连（防止 POST 重复触发 Agent）
 * - 连接异常断开时仍允许一次重连（应对网络抖动）
 */
async function _sseFetch(
  url: string,
  body: object,
  callbacks: SSEStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  let doneReceived = false
  await fetchEventSource(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
    async onopen(response) {
      if (!response.ok) {
        const errText = await response.text().catch(() => '')
        throw new Error(`HTTP ${response.status}: ${errText}`)
      }
      const ct = response.headers.get('content-type') || ''
      const hasBody = !!response.body
      console.log('[SSE] onopen content-type:', ct, 'hasBody:', hasBody, 'url:', url)
      if (!ct.includes('text/event-stream') || !response.body) {
        const text = await response.text()
        if (text) {
          try {
            const json = JSON.parse(text)
            if (json.content) callbacks.onChunk?.(json.content)
            callbacks.onDone?.(json)
          } catch {
            if (text) callbacks.onChunk?.(text)
            callbacks.onDone?.({})
          }
        } else {
          callbacks.onDone?.({})
        }
        throw new Error('HANDLED_NON_SSE')
      }
    },
    onmessage(msg) {
      if (msg.event === 'thinking' || msg.event === 'phase') callbacks.onThinking?.(msg.data)
      else if (msg.event === 'chunk') callbacks.onChunk?.(msg.data)
      else if (msg.event === 'error') callbacks.onError?.(new Error(msg.data))
      else if (msg.event === 'done') {
        doneReceived = true
        try { callbacks.onDone?.(JSON.parse(msg.data)) } catch { callbacks.onDone?.({}) }
      }
    },
    onclose() {
      // 收到 done 后服务器正常关闭：不抛错，让 fetchEventSource 正常 resolve
      // 未收到 done 的连接断开：抛出以触发 onerror，按网络错误处理
      if (!doneReceived) {
        throw new Error('SSE_UNEXPECTED_CLOSE')
      }
      // doneReceived === true: 正常结束，静默返回
    },
    onerror(err) {
      // 非 SSE 响应（降级处理）：已手动读取 response body，无需重连
      if ((err as Error).message === 'HANDLED_NON_SSE') {
        class FatalError extends Error { }
        throw new FatalError(String(err))
      }
      // 其他错误（网络异常、服务端 5xx 等）：通知上层并终止
      callbacks.onError?.(err as Error)
      class FatalError extends Error { }
      throw new FatalError(String(err))
    },
  })
}

/** 孕妇聊天流式接口 */
export async function postChatStream(
  data: ChatRequest,
  callbacks: SSEStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  await _sseFetch('/api/v1/chat/send/stream', data, callbacks, signal)
}

// 心理健康筛查
export const mentalHealthApi = {
  getQuestions: () => client.get<{ questions: Array<{ id: number; text: string; options: string[] }>; total: number }>('/mental-health/epds/questions'),
  submit: (data: { pregnant_id: string; answers: Record<number, number> }) =>
    client.post<{ id: string; total_score: number; risk_level: string; risk_description: string; recommendations: string[] }>('/mental-health/epds/submit', data),
  getHistory: (pregnantId: string) => client.get<{ screenings: Array<{ id: string; total_score: number; risk_level: string; created_at: string }> }>(`/mental-health/epds/history/${pregnantId}`),
}

// 主动推送通知
export const proactiveApi = {
  getNotifications: (pregnantId: string) =>
    client.get<any[]>(`/pregnant/${pregnantId}/proactive-notifications`),
}

// 孕期日记
export const diaryApi = {
  get: (pregnantId: string, weeks?: number) =>
    client.get<any>(`/pregnant/${pregnantId}/diary`, { params: { weeks } }),
}

// 护士晨间简报
export const nurseBriefingApi = {
  getMorningBriefing: () =>
    client.get<any>('/nurse/morning-briefing'),
  batchTriggerFollowups: (pregnantIds: string[], templateId: string) =>
    client.post<any>('/nurse/followup/batch-trigger', { pregnant_ids: pregnantIds, template_id: templateId }),
}

// 预警通知
export const alertNotificationApi = {
  getNotifications: (pregnantId: string, unreadOnly?: boolean) =>
    client.get<any[]>(`/alerts/pregnant/${pregnantId}/notifications`, { params: { unread_only: unreadOnly } }),
  markAllRead: (pregnantId: string) =>
    client.put(`/alerts/pregnant/${pregnantId}/notifications/read-all`),
  markRead: (alertId: string, pregnantId: string) =>
    client.put(`/alerts/notifications/${alertId}/read`, { pregnant_id: pregnantId }),
}
