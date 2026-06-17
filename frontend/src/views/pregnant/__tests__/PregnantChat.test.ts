// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PregnantChat from '../PregnantChat.vue'

const mocks = vi.hoisted(() => ({
  route: { query: {} },
  router: {
    options: { history: { state: {} } },
    back: vi.fn(),
    push: vi.fn(),
  },
  chatStore: {
    messages: [] as Array<{
      id: string
      role: 'user' | 'assistant'
      content: string
      timestamp: string
      loading?: boolean
    }>,
    sessionId: null as string | null,
    loading: false,
    streaming: false,
    loadFromBackend: vi.fn(),
    newConversation: vi.fn(),
    updateMessage: vi.fn(),
    deleteMessageFrom: vi.fn(),
    getPreviousUserMessage: vi.fn(),
    addMessage: vi.fn(),
    clearAll: vi.fn(),
    stopGeneration: vi.fn(),
    setAbortController: vi.fn(),
    persist: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

vi.mock('@/stores/chat', () => ({
  useChatStore: () => mocks.chatStore,
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => ({}),
}))

vi.mock('@/api/endpoints', () => ({
  chatApi: {
    getContext: vi.fn(),
    listSessions: vi.fn(),
    getConversation: vi.fn(),
    send: vi.fn(),
    clearMemory: vi.fn(),
    asr: vi.fn(),
  },
  postChatStream: vi.fn(),
  feedbackApi: {
    submit: vi.fn(),
  },
}))

vi.mock('@/utils/markdown', () => ({
  renderMarkdown: (content: string) => content,
  isStructuredAnalysis: () => false,
  parseStructuredAnalysis: () => null,
}))

vi.mock('@/composables/useTTS', () => ({
  useTTS: () => ({
    isSpeaking: { value: false },
    speak: vi.fn(),
    stop: vi.fn(),
    cleanForTTS: (content: string) => content,
  }),
}))

vi.mock('@vueuse/core', () => ({
  useScroll: vi.fn(),
}))

describe('PregnantChat', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 18, 10, 0))
    localStorage.clear()
    mocks.chatStore.messages = []
    mocks.chatStore.sessionId = null
    mocks.chatStore.loading = false
    mocks.chatStore.streaming = false
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('历史消息时间显示到具体日期', () => {
    mocks.chatStore.messages = [
      {
        id: 'msg-yesterday',
        role: 'user',
        content: '昨天有点腰酸',
        timestamp: new Date(2026, 5, 17, 9, 30).toISOString(),
      },
    ]

    const wrapper = mount(PregnantChat, {
      global: {
        stubs: {
          AgentAvatar: true,
          StructuredAnalysisCard: true,
          'el-button': true,
          'el-dialog': true,
          'el-drawer': true,
          'el-icon': true,
          'el-input': true,
          'el-tag': true,
          'el-upload': true,
        },
      },
    })

    expect(wrapper.get('.message-time').text()).toBe('昨天 09:30')
  })
})
