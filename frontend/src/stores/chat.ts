/* 聊天状态管理 - 支持跨页面持久化 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isUrgent?: boolean
  loading?: boolean
}

const STORAGE_KEY = 'pregnant_chat_history'
const SESSION_KEY = 'pregnant_chat_session'
const MAX_MESSAGES = 200

function loadFromStorage(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return (JSON.parse(raw) as ChatMessage[]).filter((m) => !m.loading)
  } catch {
    return []
  }
}

function saveToStorage(messages: ChatMessage[]) {
  try {
    const toSave = messages
      .filter((m) => !m.loading)
      .slice(-MAX_MESSAGES)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch { /* quota exceeded */ }
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>(loadFromStorage())
  const sessionId = ref<string | null>(localStorage.getItem(SESSION_KEY))
  const loading = ref(false)
  const streaming = ref(false)

  // SSE abort controller
  let abortController: AbortController | null = null

  function persist() {
    saveToStorage(messages.value)
    if (sessionId.value) localStorage.setItem(SESSION_KEY, sessionId.value)
    else localStorage.removeItem(SESSION_KEY)
  }

  let msgIdCounter = 0

  function genId(): string {
    msgIdCounter++
    return `msg_${Date.now()}_${msgIdCounter}`
  }

  function addMessage(
    role: 'user' | 'assistant',
    content: string,
    extra: Partial<ChatMessage> = {},
  ): ChatMessage {
    const msg: ChatMessage = {
      id: genId(),
      role,
      content,
      timestamp: new Date().toISOString(),
      ...extra,
    }
    messages.value.push(msg)
    persist()
    return msg
  }

  function updateMessage(id: string, patch: Partial<ChatMessage>) {
    const idx = messages.value.findIndex((m) => m.id === id)
    if (idx !== -1) {
      Object.assign(messages.value[idx], patch)
      persist()
    }
  }

  /** 删除指定消息及其之后的所有消息（用于重试） */
  function deleteMessageFrom(id: string) {
    const idx = messages.value.findIndex((m) => m.id === id)
    if (idx !== -1) {
      messages.value.splice(idx)
      persist()
    }
  }

  /** 获取指定消息的前一条用户消息（用于重试） */
  function getPreviousUserMessage(assistantId: string): ChatMessage | null {
    const idx = messages.value.findIndex((m) => m.id === assistantId)
    if (idx <= 0) return null
    // 往前找最近的 user 消息
    for (let i = idx - 1; i >= 0; i--) {
      if (messages.value[i].role === 'user') return messages.value[i]
    }
    return null
  }

  /** 新建对话（保留历史，开启新 session） */
  function newConversation() {
    sessionId.value = null
    messages.value = []
    loading.value = false
    streaming.value = false
    persist()
  }

  /** 清除所有数据 */
  function clearAll() {
    messages.value = []
    sessionId.value = null
    loading.value = false
    streaming.value = false
    abortController?.abort()
    abortController = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(SESSION_KEY)
  }

  /** 停止生成 */
  function stopGeneration() {
    abortController?.abort()
    abortController = null
    streaming.value = false
    loading.value = false
  }

  function setAbortController(controller: AbortController | null) {
    abortController = controller
  }

  return {
    messages,
    sessionId,
    loading,
    streaming,
    addMessage,
    updateMessage,
    deleteMessageFrom,
    getPreviousUserMessage,
    newConversation,
    clearAll,
    stopGeneration,
    setAbortController,
    persist,
  }
})
