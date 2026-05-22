/* 聊天状态管理 - 支持跨页面持久化 + 用户隔离 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { chatApi } from '@/api/endpoints'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isUrgent?: boolean
  loading?: boolean
  thinking?: boolean
  thinkingMessage?: string
  toolSteps?: string[]  // Agent 工具调用步骤（已完成的中文描述列表）
  currentStep?: string  // 当前正在执行的步骤描述
  feedback?: 'thumbs_up' | 'thumbs_down' | null
  // 音频消息
  audioUrl?: string       // blob URL，用于播放录音
  audioDuration?: number  // 录音时长（秒）
  messageType?: 'text' | 'audio'
  // ASR 转录文本
  transcribedText?: string  // 语音转文字结果
  transcribing?: boolean    // 正在转录中
}

const MAX_MESSAGES = 200

/** 获取当前孕妇ID */
function getCurrentPregnantId(): string {
  return localStorage.getItem('currentPregnantId') || 'anonymous'
}

/** 按用户隔离的存储 key */
function getStorageKey(pid?: string): string {
  return `chat_history_${pid || getCurrentPregnantId()}`
}

function getSessionKey(pid?: string): string {
  return `chat_session_${pid || getCurrentPregnantId()}`
}

function loadFromStorage(pid?: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(getStorageKey(pid))
    if (!raw) return []
    return (JSON.parse(raw) as ChatMessage[]).filter((m) => !m.loading)
  } catch {
    return []
  }
}

function saveToStorage(messages: ChatMessage[], pid?: string) {
  try {
    const toSave = messages
      .filter((m) => !m.loading)
      .slice(-MAX_MESSAGES)
    localStorage.setItem(getStorageKey(pid), JSON.stringify(toSave))
  } catch { /* quota exceeded */ }
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>(loadFromStorage())
  const sessionId = ref<string | null>(localStorage.getItem(getSessionKey()))
  const loading = ref(false)
  const streaming = ref(false)

  // SSE abort controller
  let abortController: AbortController | null = null

  /** 切换用户时重新加载数据 */
  function switchUser(newPregnantId: string) {
    // 保存当前用户数据
    persist()
    // 加载新用户数据
    messages.value = loadFromStorage(newPregnantId)
    sessionId.value = localStorage.getItem(getSessionKey(newPregnantId))
    loading.value = false
    streaming.value = false
    abortController?.abort()
    abortController = null
  }

  function persist() {
    saveToStorage(messages.value)
    if (sessionId.value) localStorage.setItem(getSessionKey(), sessionId.value)
    else localStorage.removeItem(getSessionKey())
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

  /** 清除当前用户的所有数据 */
  function clearAll() {
    messages.value = []
    sessionId.value = null
    loading.value = false
    streaming.value = false
    abortController?.abort()
    abortController = null
    localStorage.removeItem(getStorageKey())
    localStorage.removeItem(getSessionKey())
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

  /** 从后端加载对话历史（persist_chat_messages 开启时有效） */
  async function loadFromBackend(pregnantId: string) {
    try {
      const res = await chatApi.getConversation(pregnantId, sessionId.value || undefined)
      const backendMessages = res.data?.messages || []
      if (backendMessages.length > 0) {
        // 以后端数据为准，合并到本地（去重：相同内容的相邻消息）
        const synced: ChatMessage[] = backendMessages.map((m, idx) => ({
          id: `backend_${idx}_${Date.now()}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: m.created_at || new Date().toISOString(),
        }))
        // 如果本地消息为空或后端消息更多，以后端为准
        if (messages.value.length === 0 || backendMessages.length >= messages.value.length) {
          messages.value = synced
          persist()
        }
      }
    } catch {
      // 加载失败不影响使用
    }
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
    loadFromBackend,
    switchUser,
  }
})
