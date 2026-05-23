/* Admin 审计日志 API */
import client from './client'
import type {
  AdminDashboardResponse,
  AdminTokenDaily,
  AdminTokenByAgent,
  AdminSessionListResponse,
  AdminSessionDetail,
} from '@/types'

export const adminApi = {
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
    agent_variant?: string
    date_from?: string
    date_to?: string
  }) => client.get<AdminSessionListResponse>('/admin/audit/sessions', { params }),

  getSessionDetail: (sessionId: string) =>
    client.get<AdminSessionDetail>(`/admin/audit/sessions/${sessionId}`),
}
