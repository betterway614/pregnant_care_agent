/* API 端点封装 */
import client from './client'
import type {
  Pregnant, FollowUpRecord, Alert, ScheduleNode,
  FgrAssessment, FgrTrendPoint, MedicalOrder,
  DashboardStats, HardwareMonitor, ChatRequest, ChatResponse,
  HomeResponse, RecommendResponse,
} from '@/types'

// 对话
export const chatApi = {
  send: (data: ChatRequest) => client.post<ChatResponse>('/chat/send', data),
  getMemory: (pregnantId: string) => client.get('/chat/history', { params: { pregnant_id: pregnantId } }),
  clearMemory: (pregnantId: string) => client.delete('/chat/memory', { params: { pregnant_id: pregnantId } }),
  getContext: (pregnantId: string) => client.get(`/chat/context/${pregnantId}`),
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
  list: (params?: { status?: string; pregnant_id?: string }) =>
    client.get<FollowUpRecord[]>('/followup/records', { params }),
  confirm: (recordId: string, status: string = 'confirmed') =>
    client.put(`/followup/records/${recordId}/confirm`, { status }),
  update: (recordId: string, data: any) =>
    client.put(`/followup/records/${recordId}`, data),
  getPending: (pregnantId: string) =>
    client.get<any>(`/followup/pending/${pregnantId}`),
  respond: (recordId: string, answers: Record<string, any>) =>
    client.post('/followup/respond', { record_id: recordId, answers }),
}

// 预警
export const alertApi = {
  list: (params?: { status?: string; level?: string; pregnant_id?: string }) =>
    client.get<Alert[]>('/alerts', { params }),
  evaluate: (pregnantId: string, data: any) =>
    client.get('/alerts/evaluate', { params: { pregnant_id: pregnantId }, data }),
  review: (alertId: string, action: string, reason?: string) =>
    client.put(`/alerts/${alertId}/review`, { action, reason }),
}

// FGR
export const fgrApi = {
  assess: (data: { pregnant_id: string; gestational_weeks: number; image_type?: string }) =>
    client.post<FgrAssessment>('/fgr/assess', data),
  trend: (pregnantId: string) =>
    client.get<FgrTrendPoint[]>(`/fgr/trend/${pregnantId}`),
}

// 医嘱
export const orderApi = {
  generate: (data: { pregnant_id: string; alert_id?: string; risk_level: string; gestational_weeks: number }) =>
    client.post<MedicalOrder>('/orders/generate', data),
  list: (params?: { status?: string; pregnant_id?: string }) =>
    client.get<MedicalOrder[]>('/orders', { params }),
  sign: (orderId: string, doctorId: string) =>
    client.put(`/orders/${orderId}/sign`, { doctor_id: doctorId }),
  update: (orderId: string, data: any) =>
    client.put(`/orders/${orderId}`, data),
  templates: () => client.get('/orders/templates'),
}

// 统计
export const dashboardApi = {
  stats: () => client.get<DashboardStats>('/dashboard/stats'),
  pregnant: () => client.get<Pregnant[]>('/dashboard/pregnant'),
  pregnantDetail: (pregnantId: string) => client.get(`/dashboard/pregnant/${pregnantId}`),
}

// 孕妇
export const pregnantApi = {
  get: (pregnantId: string) => client.get<Pregnant>(`/pregnant/${pregnantId}`),
  update: (pregnantId: string, data: Partial<Pregnant>) => client.put<Pregnant>(`/pregnant/${pregnantId}`, data),
  getHome: (pregnantId: string) => client.get<HomeResponse>(`/pregnant/${pregnantId}/home`),
}

// AI 推荐
export const recommendApi = {
  get: (pregnantId: string) => client.get<RecommendResponse>(`/recommend/${pregnantId}`),
}

// 护士AI
export const nurseAiApi = {
  analyze: (pregnantId: string) => client.post<any>('/nurse/analyze', { pregnant_id: pregnantId }),
  generateFollowUp: (pregnantId: string, templateId: string = 'standard') =>
    client.post<any>('/nurse/followup/generate', { pregnant_id: pregnantId, template_id: templateId }),
}

// 医生AI
export const doctorAiApi = {
  analyze: (pregnantId: string, query: string = '') =>
    client.post<any>(`/doctor/analyze/${pregnantId}`, { pregnant_id: pregnantId, query }),
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

// 监控
export const monitorApi = {
  hardware: () => client.get<HardwareMonitor>('/monitor/hardware'),
}

/* ========== SSE 流式聊天 ========== */

import { fetchEventSource } from '@microsoft/fetch-event-source'

export interface SSEStreamCallbacks {
  onChunk?: (text: string) => void
  onDone?: (metadata: any) => void
  onError?: (err: Error) => void
}

/**
 * 基于 @microsoft/fetch-event-source 库的 SSE 流式聊天
 */
export async function postChatStream(
  data: ChatRequest,
  callbacks: SSEStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  await fetchEventSource('/api/v1/chat/send/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
    async onopen(response) {
      if (!response.ok) {
        const errText = await response.text().catch(() => '')
        throw new Error(`HTTP ${response.status}: ${errText}`)
      }
    },
    onmessage(msg) {
      if (msg.event === 'chunk') {
        callbacks.onChunk?.(msg.data)
      } else if (msg.event === 'done') {
        callbacks.onDone?.(JSON.parse(msg.data))
      }
    },
    onerror(err) {
      callbacks.onError?.(err)
      // 阻止自动重试
      class FatalError extends Error { }
      throw new FatalError(String(err))
    },
  })
}
