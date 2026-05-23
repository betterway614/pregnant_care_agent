import { describe, it, expect, vi, beforeEach } from 'vitest'
import { adminApi } from '../admin'
import client from '../client'

// Mock the axios client
vi.mock('../client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockClient = vi.mocked(client)

describe('adminApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getDashboard', () => {
    it('should call the dashboard endpoint with date params', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          summary: { total_calls: 100, total_tokens: 50000, avg_latency_ms: 1200, active_sessions: 20 },
          daily_trend: [],
          variant_distribution: [],
          recent_logs: [],
        },
      })

      const result = await adminApi.getDashboard('2026-05-01', '2026-05-23')

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/dashboard', {
        params: { date_from: '2026-05-01', date_to: '2026-05-23' },
      })
      expect(result.data.summary.total_calls).toBe(100)
      expect(result.data.summary.total_tokens).toBe(50000)
    })
  })

  describe('getTokenDaily', () => {
    it('should call the token daily endpoint with date params', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          data: [
            { date: '2026-05-23', total_tokens: 8000, input_tokens: 6000, output_tokens: 2000, call_count: 15, avg_latency_ms: 1100 },
          ],
        },
      })

      const result = await adminApi.getTokenDaily('2026-05-01', '2026-05-23')

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/token/daily', {
        params: { date_from: '2026-05-01', date_to: '2026-05-23' },
      })
      expect(result.data.data).toHaveLength(1)
      expect(result.data.data[0].date).toBe('2026-05-23')
    })

    it('should return empty data array when no records', async () => {
      mockClient.get.mockResolvedValue({ data: { data: [] } })

      const result = await adminApi.getTokenDaily('2026-01-01', '2026-01-02')

      expect(result.data.data).toEqual([])
    })
  })

  describe('getTokenByAgent', () => {
    it('should call the by-agent endpoint with date params', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          data: [
            { agent_role: 'pregnant', agent_variant: 'chat', total_tokens: 20000, call_count: 40, avg_input_tokens: 400, avg_output_tokens: 100, avg_latency_ms: 900 },
          ],
        },
      })

      const result = await adminApi.getTokenByAgent('2026-05-01', '2026-05-23')

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/token/by-agent', {
        params: { date_from: '2026-05-01', date_to: '2026-05-23' },
      })
      expect(result.data.data[0].agent_variant).toBe('chat')
    })
  })

  describe('getSessions', () => {
    it('should call sessions endpoint with required pagination params', async () => {
      mockClient.get.mockResolvedValue({
        data: { total: 0, page: 1, page_size: 20, data: [] },
      })

      await adminApi.getSessions({ page: 1, page_size: 20 })

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/sessions', {
        params: { page: 1, page_size: 20 },
      })
    })

    it('should pass optional filter params when provided', async () => {
      mockClient.get.mockResolvedValue({
        data: { total: 1, page: 1, page_size: 20, data: [] },
      })

      await adminApi.getSessions({
        page: 1,
        page_size: 20,
        user_id: 'P001',
        agent_variant: 'chat',
        date_from: '2026-05-01',
        date_to: '2026-05-23',
      })

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/sessions', {
        params: {
          page: 1,
          page_size: 20,
          user_id: 'P001',
          agent_variant: 'chat',
          date_from: '2026-05-01',
          date_to: '2026-05-23',
        },
      })
    })

    it('should omit undefined optional params', async () => {
      mockClient.get.mockResolvedValue({
        data: { total: 5, page: 1, page_size: 10, data: [] },
      })

      await adminApi.getSessions({ page: 1, page_size: 10 })

      const callArgs = mockClient.get.mock.calls[0][1] as { params: Record<string, unknown> }
      expect(callArgs.params).not.toHaveProperty('user_id')
      expect(callArgs.params).not.toHaveProperty('agent_variant')
      expect(callArgs.params).not.toHaveProperty('date_from')
      expect(callArgs.params).not.toHaveProperty('date_to')
    })

    it('should return paginated session list', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          total: 2,
          page: 1,
          page_size: 20,
          data: [
            { id: 1, session_id: 'sess-001', user_id: 'P001', agent_role: 'pregnant', agent_variant: 'chat', intent_classification: 'emotion', routed_agent: '小安-chat', input_tokens: 500, output_tokens: 200, total_tokens: 700, total_latency_ms: 1200, guardrail_triggered: false, response_preview: '你好', created_at: '2026-05-23T10:00:00' },
            { id: 2, session_id: 'sess-002', user_id: 'P002', agent_role: 'pregnant', agent_variant: 'record', intent_classification: 'record_weight', routed_agent: '小安-record', input_tokens: 600, output_tokens: 300, total_tokens: 900, total_latency_ms: 1500, guardrail_triggered: false, response_preview: '已记录', created_at: '2026-05-23T11:00:00' },
          ],
        },
      })

      const result = await adminApi.getSessions({ page: 1, page_size: 20 })

      expect(result.data.total).toBe(2)
      expect(result.data.data).toHaveLength(2)
      expect(result.data.data[0].session_id).toBe('sess-001')
      expect(result.data.data[1].agent_variant).toBe('record')
    })
  })

  describe('getSessionDetail', () => {
    it('should call session detail endpoint with session id', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          session_id: 'sess-001',
          run_count: 2,
          runs: [
            { id: 1, agent_role: 'pregnant', agent_variant: 'chat', intent_classification: null, routed_agent: '小安-chat', input_tokens: 500, output_tokens: 200, total_tokens: 700, tool_calls: null, model_id: 'qwen', total_latency_ms: 1200, guardrail_triggered: false, response_preview: '你好', created_at: '2026-05-23T10:00:00' },
          ],
        },
      })

      const result = await adminApi.getSessionDetail('sess-001')

      expect(mockClient.get).toHaveBeenCalledWith('/admin/audit/sessions/sess-001')
      expect(result.data.session_id).toBe('sess-001')
      expect(result.data.run_count).toBe(2)
    })

    it('should handle session with tool calls in runs', async () => {
      mockClient.get.mockResolvedValue({
        data: {
          session_id: 'sess-003',
          run_count: 1,
          runs: [
            { id: 3, agent_role: 'pregnant', agent_variant: 'qa', intent_classification: 'ask_knowledge', routed_agent: '小安-qa', input_tokens: 700, output_tokens: 400, total_tokens: 1100, tool_calls: [{ name: 'agno_search_knowledge', success: true, result_preview: '' }], model_id: 'qwen', total_latency_ms: 2000, guardrail_triggered: false, response_preview: '根据资料...', created_at: '2026-05-23T12:00:00' },
          ],
        },
      })

      const result = await adminApi.getSessionDetail('sess-003')

      expect(result.data.runs[0].tool_calls).toHaveLength(1)
      expect(result.data.runs[0].tool_calls![0].name).toBe('agno_search_knowledge')
    })
  })
})
