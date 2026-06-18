<template>
  <div class="nurse-chat" :class="{ 'nurse-chat--fullscreen': isFullscreen }">
    <!-- 顶部工具栏 -->
    <div class="nurse-chat__toolbar">
      <span class="toolbar-title">小护 AI 助手</span>
      <div class="toolbar-actions">
        <button class="toolbar-action-btn" :class="{ 'toolbar-action-btn--active': autoPlayTTS }" @click="toggleAutoPlayTTS" :title="autoPlayTTS ? '关闭自动播报' : '开启自动播报'">
          <el-icon :size="14"><Headset /></el-icon>
        </button>
        <button class="toolbar-action-btn" :class="{ 'toolbar-action-btn--active': isMuted }" @click="toggleMute" :title="isMuted ? '取消静音' : '静音'">
          <el-icon :size="14"><Mute v-if="isMuted" /><Microphone v-else /></el-icon>
        </button>
        <button class="toolbar-action-btn" @click="handleClearChat" title="清除聊天记录">
          <el-icon :size="14"><Delete /></el-icon>
        </button>
        <button class="toolbar-action-btn" @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '放大全屏'">
          <el-icon :size="14"><FullScreen v-if="!isFullscreen" /><Aim v-else /></el-icon>
        </button>
      </div>
    </div>

    <!-- 消息区域 -->
    <div class="nurse-chat__messages" ref="messagesRef">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="nurse-chat__msg"
        :class="{ 'nurse-chat__msg--user': msg.role === 'user' }"
      >
        <AgentAvatar
          v-if="msg.role === 'assistant'"
          agent="xiaohu"
          :size="32"
          :thinking="msg.loading && msg.thinking"
        />
        <div class="nurse-chat__bubble" :class="{ 'nurse-chat__bubble--user': msg.role === 'user' }">
          <!-- 思考中状态 -->
          <div v-if="msg.loading && msg.thinking" class="nurse-chat__thinking">
            <div class="thinking-pulse"></div>
            <span class="thinking-text">{{ msg.thinkingMessage || '小护正在思考...' }}</span>
          </div>
          <!-- 加载中 -->
          <div v-else-if="msg.loading && !msg.content" class="nurse-chat__loading">
            <span class="loading-dot" /><span class="loading-dot" /><span class="loading-dot" />
          </div>
          <!-- 消息内容 -->
          <div v-else-if="msg.messageType === 'audio'" class="nurse-chat__audio-wrapper">
            <div class="nurse-chat__audio">
              <button class="audio-play-btn" @click="playAudio(msg)">
                <el-icon :size="16"><VideoPlay v-if="!msg.isPlaying" /><VideoPause v-else /></el-icon>
              </button>
              <div class="audio-waveform">
                <span v-for="i in 12" :key="i" class="audio-bar" :style="{ animationDelay: `${i * 0.05}s` }" />
              </div>
              <span class="audio-duration">{{ formatAudioDuration(msg.audioDuration || 0) }}</span>
              <button class="audio-transcribe-btn" @click="handleAudioTranscribe(msg)" :title="msg.transcriptionVisible ? '隐藏文字' : '转文字'">
                <el-icon :size="13"><Document /></el-icon>
              </button>
            </div>
            <div v-if="msg.transcriptionVisible && msg.transcribedText" class="audio-transcription">
              {{ msg.transcribedText }}
            </div>
            <div v-else-if="msg.transcribing" class="audio-transcription audio-transcription--loading">
              正在识别语音...
            </div>
          </div>
          <div v-else class="nurse-chat__text">
            <StructuredAnalysisCard
              v-if="isStructuredAnalysis(msg.content)"
              :data="parseStructuredAnalysis(msg.content)!"
              role="nurse"
            />
            <div v-else v-html="renderMarkdown(msg.content)" />
          </div>
          <!-- 工具结果卡片（仅在流式过程中展示，完成后隐藏避免与最终回复重复） -->
          <div v-if="msg.toolResults?.length && msg.loading" class="tool-results">
            <div
              v-for="(tr, idx) in msg.toolResults"
              :key="idx"
              class="tool-result-card"
            >
              <!-- 患者数据 -->
              <template v-if="tr.toolName === 'agno_query_patient_data' && tr.result?.basic_info">
                <div class="tr-header">
                  <span class="tr-icon">📋</span>
                  <span class="tr-title">患者数据</span>
                </div>
                <div class="tr-body">
                  <div class="tr-row">
                    <span class="tr-label">姓名</span>
                    <span class="tr-value">{{ tr.result.basic_info.name || tr.result.basic_info.display_name }}</span>
                  </div>
                  <div v-if="tr.result.basic_info.gestational_age" class="tr-row">
                    <span class="tr-label">孕周</span>
                    <span class="tr-value">{{ tr.result.basic_info.gestational_age }}</span>
                  </div>
                  <div v-if="tr.result.recent_health?.length" class="tr-chips">
                    <span v-for="h in tr.result.recent_health.slice(0, 5)" :key="h.metric"
                          class="tr-chip" :class="{ 'tr-chip--alert': h.is_abnormal }">
                      {{ h.metric }}: {{ h.value }}{{ h.unit }}
                    </span>
                  </div>
                  <div v-if="tr.result.active_alerts?.length" class="tr-alerts">
                    <span v-for="a in tr.result.active_alerts.slice(0, 3)" :key="a.id"
                          class="tr-alert" :class="'tr-alert--' + (a.level || 'yellow').toLowerCase()">
                      [{{ a.level }}] {{ a.message }}
                    </span>
                  </div>
                </div>
              </template>

              <!-- 趋势分析 -->
              <template v-else-if="tr.toolName === 'agno_analyze_health_trends' && tr.result?.trends">
                <div class="tr-header">
                  <span class="tr-icon">📈</span>
                  <span class="tr-title">趋势分析</span>
                </div>
                <div class="tr-body">
                  <div v-for="t in tr.result.trends.slice(0, 4)" :key="t.metric" class="tr-trend-row">
                    <span class="tr-metric">{{ t.metric }}</span>
                    <span class="tr-trend" :class="'tr-trend--' + (t.trend || 'stable')">
                      {{ trendArrow(t.trend) }}
                    </span>
                    <span class="tr-summary">{{ t.summary }}</span>
                  </div>
                </div>
              </template>

              <!-- 体征评估 -->
              <template v-else-if="tr.toolName === 'agno_evaluate_vital_rules' && tr.result">
                <div class="tr-header">
                  <span class="tr-icon">🩺</span>
                  <span class="tr-title">体征评估</span>
                </div>
                <div class="tr-body">
                  <div v-if="tr.result.triggered_rules?.length" class="tr-rules">
                    <span v-for="r in tr.result.triggered_rules.slice(0, 3)" :key="r.rule_id"
                          class="tr-rule" :class="'tr-rule--' + (r.severity || 'info')">
                      {{ r.message || r.rule_id }}
                    </span>
                  </div>
                  <div v-else class="tr-empty">各项指标正常</div>
                </div>
              </template>

              <!-- 患者列表 -->
              <template v-else-if="tr.toolName === 'agno_list_patients' && tr.result">
                <div class="tr-header">
                  <span class="tr-icon">👥</span>
                  <span class="tr-title">患者列表</span>
                </div>
                <div class="tr-body">
                  <span class="tr-done">已查询 {{ Array.isArray(tr.result) ? tr.result.length : '' }} 位患者</span>
                </div>
              </template>

              <!-- 通用兜底 -->
              <template v-else>
                <div class="tr-header">
                  <span class="tr-icon">⚙️</span>
                  <span class="tr-title">{{ toolNameToLabel(tr.toolName) }}</span>
                </div>
                <div class="tr-body">
                  <span class="tr-done">✓ 已完成</span>
                </div>
              </template>
            </div>
          </div>
        </div>
        <!-- 消息操作按钮组（助手消息） -->
        <div v-if="msg.role === 'assistant' && !msg.loading && msg.content" class="msg-actions">
          <button
            class="msg-action-btn"
            :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_up' }"
            @click="handleFeedback(msg, 'thumbs_up')"
            title="有帮助"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
          <button
            class="msg-action-btn"
            :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_down' }"
            @click="handleFeedback(msg, 'thumbs_down')"
            title="需改进"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
          <button
            class="msg-action-btn"
            :class="{ 'msg-action-btn--active': ttsSpeakingId === msg.id }"
            @click="toggleTTS(msg)"
            title="语音播报"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 已完成的工具步骤（自动消失） -->
    <transition name="fade">
      <div v-if="completedToolSteps.length > 0" class="nurse-chat__tool-steps">
        <div
          v-for="(step, idx) in completedToolSteps"
          :key="idx"
          class="tool-step"
        >
          <el-icon :size="12" class="tool-step__check"><CircleCheck /></el-icon>
          <span class="tool-step__text">{{ step }}</span>
        </div>
      </div>
    </transition>

    <!-- 录音覆盖层 -->
    <transition name="record-fade">
      <div v-if="isRecording" class="nurse-chat__record-overlay">
        <div class="record-center">
          <div class="record-ring" :class="{ 'record-ring--cancel': isInCancelZone }">
            <el-icon :size="28" color="#fff"><Microphone /></el-icon>
          </div>
          <span class="record-timer">{{ recordingText }}</span>
          <span class="record-hint" :class="{ 'record-hint--cancel': isInCancelZone }">
            {{ isInCancelZone ? '松手取消' : '松手发送' }}
          </span>
        </div>
      </div>
    </transition>

    <!-- 输入区域 -->
    <div class="nurse-chat__input">
      <button
        class="mic-btn"
        :class="{ 'mic-btn--active': !isStreaming }"
        @pointerdown.prevent="startRecording"
        :disabled="isStreaming"
      >
        <el-icon :size="18"><Microphone /></el-icon>
      </button>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="1"
        placeholder="向小护提问护理问题..."
        @keydown.enter.exact.prevent="handleSend"
        :disabled="isStreaming"
        resize="none"
        :autosize="{ minRows: 1, maxRows: 3 }"
      />
      <button
        class="send-btn"
        :class="{ 'send-btn--active': inputText.trim() && !isStreaming }"
        :disabled="!inputText.trim() || isStreaming"
        @click="handleSend"
      >
        <el-icon :size="18"><Promotion /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { Promotion, CircleCheck, Microphone, VideoPlay, VideoPause, Mute, Document, FullScreen, Aim, Delete, Headset } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { nurseAiApi, chatApi, feedbackApi } from '@/api/endpoints'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { renderMarkdown, isStructuredAnalysis, parseStructuredAnalysis } from '@/utils/markdown'
import { useAudioRecorder } from '@/composables/useAudioRecorder'
import { useTTS } from '@/composables/useTTS'
import { StructuredAnalysisCard } from '@/components/agent-fab'

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  loading?: boolean
  thinking?: boolean
  thinkingMessage?: string
  toolSteps?: string[]
  currentStep?: string
  toolResults?: { toolName: string; result: any }[]
  messageType?: 'text' | 'audio'
  audioUrl?: string
  audioDuration?: number
  isPlaying?: boolean
  transcribedText?: string
  transcribing?: boolean
  transcriptionVisible?: boolean
  feedback?: 'thumbs_up' | 'thumbs_down' | null
}

const messages = ref<ChatMsg[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const isFullscreen = ref(false)

// 工具调用状态
const completedToolSteps = ref<string[]>([])
let toolStepsDismissTimer: ReturnType<typeof setTimeout> | null = null

// 会话 ID：在同一次对话中保持一致，让后端 Agent 能管理多轮上下文
let currentSessionId: string | null = null
// AbortController：用于组件卸载时取消正在进行的 SSE 请求
let activeAbortController: AbortController | null = null
// 安全超时：防止 isStreaming 永久卡死
let streamSafetyTimer: ReturnType<typeof setTimeout> | null = null

const STREAM_SAFETY_TIMEOUT_MS = 130_000  // 130s（略大于后端 120s 超时）

function startStreamSafetyTimer(assistantMsg: ChatMsg) {
  clearStreamSafetyTimer()
  streamSafetyTimer = setTimeout(() => {
    console.warn('[NurseAIChat] Stream safety timeout, forcing reset')
    if (assistantMsg.loading) {
      if (!assistantMsg.content) {
        assistantMsg.content = '抱歉，AI处理超时，请稍后再试。'
      }
      assistantMsg.loading = false
      assistantMsg.thinking = false
    }
    isStreaming.value = false
    completedToolSteps.value = []
    activeAbortController?.abort()
    activeAbortController = null
  }, STREAM_SAFETY_TIMEOUT_MS)
}

function clearStreamSafetyTimer() {
  if (streamSafetyTimer) {
    clearTimeout(streamSafetyTimer)
    streamSafetyTimer = null
  }
}

/** 自动隐藏已完成工具步骤（8 秒后） */
function dismissToolStepsAfterDelay() {
  clearToolStepsDismissTimer()
  toolStepsDismissTimer = setTimeout(() => {
    completedToolSteps.value = []
  }, 8000)
}

function clearToolStepsDismissTimer() {
  if (toolStepsDismissTimer) {
    clearTimeout(toolStepsDismissTimer)
    toolStepsDismissTimer = null
  }
}

let msgCounter = 0
function genId() { return `nurse_${Date.now()}_${++msgCounter}` }

/** 趋势方向 → 箭头符号 */
function trendArrow(trend: string): string {
  const map: Record<string, string> = { rising: '↑', falling: '↓', stable: '→', increasing: '↑', decreasing: '↓' }
  return map[trend] || '→'
}

/** 工具名称 → 中文标签 */
function toolNameToLabel(name: string): string {
  const map: Record<string, string> = {
    agno_query_patient_data: '患者数据',
    agno_analyze_health_trends: '趋势分析',
    agno_evaluate_vital_rules: '体征评估',
    agno_list_patients: '患者列表',
    agno_create_followup_record: '随访记录',
    agno_report_issue_to_doctor: '问题上报',
    agno_analyze_patient_comprehensive: '综合分析',
    agno_generate_medical_order: '医嘱生成',
    agno_handle_issue: '问题处理',
    agno_query_clinical_guideline: '临床指南',
    agno_save_health_data: '数据保存',
    agno_get_patient_context: '患者信息',
    agno_get_nlu_result: '意图分析',
    agno_check_emergency: '紧急检测',
    search_knowledge_base: '知识检索',
  }
  return map[name] || name
}

// ---- 语音录制 ----
const { isRecording, isInCancelZone, recordingText, startRecording } = useAudioRecorder({
  onComplete: async (result) => {
    await sendAudioMessage(result.base64, result.format, result.blob, result.duration)
  },
})

// ---- TTS 播报 ----
const { isSpeaking, speak, stop: stopTTS, cleanForTTS } = useTTS({ mode: 'backend', role: 'nurse' })
const ttsSpeakingId = ref<string | null>(null)
const autoPlayTTS = ref(false)
const isMuted = ref(false)
let currentAudioEl: HTMLAudioElement | null = null
let ttsCheckInterval: ReturnType<typeof setInterval> | null = null

function toggleTTS(msg: ChatMsg) {
  if (ttsSpeakingId.value === msg.id) {
    stopTTS()
    ttsSpeakingId.value = null
    if (ttsCheckInterval) { clearInterval(ttsCheckInterval); ttsCheckInterval = null }
  } else {
    if (ttsCheckInterval) { clearInterval(ttsCheckInterval); ttsCheckInterval = null }
    ttsSpeakingId.value = msg.id
    speak(cleanForTTS(msg.content))
    ttsCheckInterval = setInterval(() => {
      if (!isSpeaking.value) {
        ttsSpeakingId.value = null
        if (ttsCheckInterval) { clearInterval(ttsCheckInterval); ttsCheckInterval = null }
      }
    }, 500)
  }
}

function toggleAutoPlayTTS() {
  autoPlayTTS.value = !autoPlayTTS.value
  if (!autoPlayTTS.value) {
    stopTTS()
    ttsSpeakingId.value = null
  }
}

function toggleMute() {
  isMuted.value = !isMuted.value
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

/** 清除聊天记录：清空本地消息 + 后端会话，重置 session_id */
async function handleClearChat() {
  try {
    await ElMessageBox.confirm('确定要清除所有聊天记录吗？', '确认操作', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch { return }

  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    if (pregnantId && currentSessionId) {
      await chatApi.clearConversation(pregnantId, currentSessionId)
    } else if (pregnantId) {
      await chatApi.clearConversation(pregnantId)
    }
    // 重置本地状态
    currentSessionId = null
    messages.value = []
    completedToolSteps.value = []
    // 重新添加欢迎消息
    messages.value.push({
      id: genId(),
      role: 'assistant',
      content: '您好！我是**小护**，您的AI护理助手。\n\n可以问我关于：\n- 孕妇数据分析\n- 护理建议\n- 随访计划\n- 健康趋势评估',
    })
    ElMessage.success('聊天记录已清除')
  } catch {
    ElMessage.error('清除失败，请稍后重试')
  }
}

/** 自动播报助手消息 */
function autoSpeakAssistant(msg: ChatMsg) {
  if (autoPlayTTS.value && msg.content && !isMuted.value) {
    ttsSpeakingId.value = msg.id
    speak(cleanForTTS(msg.content))
    const check = setInterval(() => {
      if (!isSpeaking.value) {
        ttsSpeakingId.value = null
        clearInterval(check)
      }
    }, 500)
  }
}

// ---- 用户反馈 ----
async function handleFeedback(msg: ChatMsg, rating: 'thumbs_up' | 'thumbs_down') {
  const newRating = msg.feedback === rating ? null : rating
  msg.feedback = newRating
  if (newRating) {
    try {
      await feedbackApi.submit({
        message_id: msg.id,
        rating: newRating,
        feedback_role: 'nurse',
      })
    } catch {}
  }
}

// ---- ASR 转录 ----
async function handleAudioTranscribe(msg: ChatMsg) {
  if (msg.transcribedText) {
    msg.transcriptionVisible = !msg.transcriptionVisible
    return
  }
  if (!msg.audioUrl) return

  msg.transcribing = true
  try {
    const resp = await fetch(msg.audioUrl)
    const blob = await resp.blob()
    const reader = new FileReader()
    reader.onloadend = async () => {
      const dataUrl = reader.result as string
      const base64 = dataUrl.split(',')[1]
      const format = msg.audioUrl?.includes('ogg') ? 'ogg' : msg.audioUrl?.includes('webm') ? 'webm' : 'wav'
      try {
        const res = await chatApi.asr({ audio_data: base64, audio_format: format })
        msg.transcribedText = res.data.text || '（语音识别为空）'
        msg.transcriptionVisible = true
      } catch {
        msg.transcribedText = '（语音识别失败）'
        msg.transcriptionVisible = true
      } finally {
        msg.transcribing = false
      }
    }
    reader.readAsDataURL(blob)
  } catch {
    msg.transcribing = false
  }
}

onUnmounted(() => {
  if (ttsCheckInterval) { clearInterval(ttsCheckInterval); ttsCheckInterval = null }
  stopTTS()
  // 取消正在进行的 SSE 请求
  activeAbortController?.abort()
  activeAbortController = null
  clearStreamSafetyTimer()
  clearToolStepsDismissTimer()
})

function playAudio(msg: ChatMsg) {
  if (!msg.audioUrl) return
  if (msg.isPlaying) {
    currentAudioEl?.pause()
    msg.isPlaying = false
    return
  }
  if (currentAudioEl) {
    currentAudioEl.pause()
    const prev = messages.value.find(m => m.isPlaying)
    if (prev) prev.isPlaying = false
  }
  currentAudioEl = new Audio(msg.audioUrl)
  msg.isPlaying = true
  currentAudioEl.onended = () => { msg.isPlaying = false; currentAudioEl = null }
  currentAudioEl.onerror = () => { msg.isPlaying = false; currentAudioEl = null }
  currentAudioEl.play()
}

function formatAudioDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m + ':' + s.toString().padStart(2, '0')
}

async function sendAudioMessage(base64: string, audioFormat: string, audioBlob: Blob, duration: number) {
  const audioUrl = URL.createObjectURL(audioBlob)
  messages.value.push({
    id: genId(),
    role: 'user',
    content: '',
    messageType: 'audio',
    audioUrl,
    audioDuration: duration,
  })
  scrollToBottom()

  const assistantMsg: ChatMsg = {
    id: genId(),
    role: 'assistant',
    content: '',
    loading: true,
    thinking: true,
    thinkingMessage: '小护正在听取语音...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  // AbortController 用于组件卸载时取消请求
  activeAbortController?.abort()
  activeAbortController = new AbortController()
  startStreamSafetyTimer(assistantMsg)

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await nurseAiApi.chatStream(
      {
        message: '请听取以下语音并给出回复',
        pregnant_id: pregnantId || undefined,
        message_type: 'AUDIO',
        audio_data: base64,
        audio_format: audioFormat,
      },
      {
        onThinking(message: string) {
          assistantMsg.thinkingMessage = message
          scrollToBottom()
        },
        onToolResult(toolName: string, result: any) {
          if (!assistantMsg.toolResults) assistantMsg.toolResults = []
          assistantMsg.toolResults.push({ toolName, result })
        },
        onChunk(chunk: string) {
          assistantMsg.content += chunk
          assistantMsg.thinking = false
          scrollToBottom()
        },
        onDone(metadata: any) {
          clearStreamSafetyTimer()
          assistantMsg.loading = false
          assistantMsg.thinking = false
          assistantMsg.toolSteps = metadata?.tool_steps || []
          completedToolSteps.value = metadata?.tool_steps || []
          dismissToolStepsAfterDelay()
          isStreaming.value = false
          // 保存后端返回的 session_id，后续消息复用
          if (metadata?.session_id) currentSessionId = metadata.session_id
          // 保存 ASR 转录文本到用户语音消息
          if (metadata?.transcribed_text) {
            const userAudioMsg = messages.value.find(m => m.role === 'user' && m.messageType === 'audio' && !m.transcribedText)
            if (userAudioMsg) userAudioMsg.transcribedText = metadata.transcribed_text
          }
          scrollToBottom()
          autoSpeakAssistant(assistantMsg)
        },
        onError() {
          clearStreamSafetyTimer()
          assistantMsg.content = '抱歉，语音处理失败，请重试或使用文字输入。'
          assistantMsg.loading = false
          assistantMsg.thinking = false
          completedToolSteps.value = []
          isStreaming.value = false
        },
      },
      activeAbortController.signal,
    )
  } catch {
    clearStreamSafetyTimer()
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，语音处理失败，请重试或使用文字输入。'
    }
    assistantMsg.loading = false
    assistantMsg.thinking = false
    completedToolSteps.value = []
    isStreaming.value = false
  } finally {
    activeAbortController = null
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  completedToolSteps.value = []
  clearToolStepsDismissTimer()

  // 添加用户消息
  messages.value.push({ id: genId(), role: 'user', content: text })
  scrollToBottom()

  // 添加助手消息占位
  const assistantMsg: ChatMsg = {
    id: genId(),
    role: 'assistant',
    content: '',
    loading: true,
    thinking: true,
    thinkingMessage: '小护正在思考...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  // AbortController 用于组件卸载时取消请求
  activeAbortController?.abort()
  activeAbortController = new AbortController()
  startStreamSafetyTimer(assistantMsg)

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await nurseAiApi.chatStream(
      {
        message: text,
        pregnant_id: pregnantId || undefined,
        session_id: currentSessionId || undefined,
      },
      {
        onThinking(message: string) {
          assistantMsg.thinkingMessage = message
          scrollToBottom()
        },
        onToolResult(toolName: string, result: any) {
          if (!assistantMsg.toolResults) assistantMsg.toolResults = []
          assistantMsg.toolResults.push({ toolName, result })
        },
        onChunk(chunk: string) {
          assistantMsg.content += chunk
          assistantMsg.thinking = false
          scrollToBottom()
        },
        onDone(metadata: any) {
          clearStreamSafetyTimer()
          assistantMsg.loading = false
          assistantMsg.thinking = false
          assistantMsg.toolSteps = metadata?.tool_steps || []
          completedToolSteps.value = metadata?.tool_steps || []
          dismissToolStepsAfterDelay()
          isStreaming.value = false
          // 保存后端返回的 session_id，后续消息复用
          if (metadata?.session_id) currentSessionId = metadata.session_id
          scrollToBottom()
          autoSpeakAssistant(assistantMsg)
        },
        onError() {
          clearStreamSafetyTimer()
          assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
          assistantMsg.loading = false
          assistantMsg.thinking = false
          completedToolSteps.value = []
          isStreaming.value = false
        },
      },
      activeAbortController.signal,
    )
  } catch {
    clearStreamSafetyTimer()
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
    }
    assistantMsg.loading = false
    assistantMsg.thinking = false
    completedToolSteps.value = []
    isStreaming.value = false
  } finally {
    activeAbortController = null
  }
}

onMounted(() => {
  messages.value.push({
    id: genId(),
    role: 'assistant',
    content: '您好！我是**小护**，您的AI护理助手。\n\n可以问我关于：\n- 孕妇数据分析\n- 护理建议\n- 随访计划\n- 健康趋势评估',
  })
})
</script>

<style scoped>
.nurse-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  position: relative;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

/* 全屏模式 */
.nurse-chat--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  border-radius: 0;
  height: 100vh;
  width: 100vw;
  max-width: 100vw;
  max-height: 100vh;
}

.nurse-chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.nurse-chat__messages::-webkit-scrollbar {
  width: 4px;
}

.nurse-chat__messages::-webkit-scrollbar-track {
  background: transparent;
}

.nurse-chat__messages::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}

.nurse-chat__msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  animation: msgSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes msgSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.nurse-chat__msg--user {
  flex-direction: row-reverse;
}

.nurse-chat__bubble {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.6;
  position: relative;
}

/* 助手气泡 - 玻璃态 */
.nurse-chat__bubble:not(.nurse-chat__bubble--user) {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 2px 8px rgba(46, 125, 50, 0.08);
  color: #1e293b;
  border-radius: 4px 16px 16px 16px;
}

/* 用户气泡 */
.nurse-chat__bubble--user {
  background: linear-gradient(135deg, #66BB6A 0%, #2E7D32 100%);
  color: white;
  border-radius: 16px 4px 16px 16px;
  box-shadow: 0 2px 12px rgba(46, 125, 50, 0.25);
}

.nurse-chat__text :deep(p) { margin: 0 0 8px; }
.nurse-chat__text :deep(p:last-child) { margin-bottom: 0; }
.nurse-chat__text :deep(strong) { font-weight: 600; color: #1e293b; }
.nurse-chat__text :deep(ul),
.nurse-chat__text :deep(ol) { padding-left: 18px; margin: 4px 0; }
.nurse-chat__text :deep(li) { margin: 2px 0; }
.nurse-chat__text :deep(code) {
  background: rgba(46, 125, 50, 0.1);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12px;
}

/* 思考中状态 */
.nurse-chat__thinking {
  display: flex;
  align-items: center;
  gap: 10px;
}

.thinking-pulse {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #66BB6A, #2E7D32);
  animation: pulse-ring 1.5s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  position: relative;
}

.thinking-pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid rgba(46, 125, 50, 0.3);
  animation: pulse-ripple 1.5s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}

@keyframes pulse-ring {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.85); opacity: 0.7; }
}

@keyframes pulse-ripple {
  0% { transform: scale(1); opacity: 0.6; }
  100% { transform: scale(1.8); opacity: 0; }
}

.thinking-text {
  font-size: 13px;
  font-weight: 500;
  color: #2E7D32;
}

/* 加载动画 */
.nurse-chat__loading {
  display: flex;
  gap: 6px;
  padding: 4px 0;
}

.loading-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #A5D6A7;
  animation: dotBounce 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(2) { animation-delay: 0.16s; }
.loading-dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 已完成的工具步骤 */
.nurse-chat__tool-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 16px;
  margin-bottom: 8px;
}

.tool-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(34, 197, 94, 0.06);
  border-radius: 8px;
  border: 1px solid rgba(34, 197, 94, 0.12);
}

.tool-step__check {
  color: #22c55e;
  flex-shrink: 0;
}

.tool-step__text {
  font-size: 11px;
  color: #16a34a;
  font-weight: 500;
}

/* 输入区域 */
.nurse-chat__input {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-top: 1px solid rgba(226, 232, 240, 0.8);
  align-items: flex-end;
}

.nurse-chat__input :deep(.el-textarea__inner) {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
  resize: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.nurse-chat__input :deep(.el-textarea__inner:focus) {
  border-color: #66BB6A;
  box-shadow: 0 0 0 3px rgba(102, 187, 106, 0.15);
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: #e2e8f0;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
}

.send-btn--active {
  background: linear-gradient(135deg, #66BB6A 0%, #2E7D32 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(46, 125, 50, 0.3);
}

.send-btn--active:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(46, 125, 50, 0.4);
}

.send-btn--active:active {
  transform: scale(0.95);
}

.send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* 过渡动画 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---- 麦克风按钮 ---- */
.mic-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: #e2e8f0;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.mic-btn--active {
  background: linear-gradient(135deg, #A5D6A7 0%, #66BB6A 100%);
  color: #2E7D32;
}

.mic-btn--active:hover {
  background: linear-gradient(135deg, #66BB6A 0%, #2E7D32 100%);
  color: white;
}

.mic-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* ---- 录音覆盖层 ---- */
.nurse-chat__record-overlay {
  position: absolute;
  inset: 0;
  background: rgba(46, 125, 50, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  border-radius: 16px;
}

.record-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.record-ring {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: recordPulse 1.2s ease-in-out infinite;
}

.record-ring--cancel {
  background: rgba(239, 68, 68, 0.6);
  animation: none;
}

@keyframes recordPulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.3); }
  50% { transform: scale(1.08); box-shadow: 0 0 0 12px rgba(255, 255, 255, 0); }
}

.record-timer {
  font-size: 20px;
  font-weight: 600;
  color: white;
  font-variant-numeric: tabular-nums;
}

.record-hint {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.record-hint--cancel {
  color: #fca5a5;
}

.record-fade-enter-active,
.record-fade-leave-active {
  transition: opacity 0.2s;
}

.record-fade-enter-from,
.record-fade-leave-to {
  opacity: 0;
}

/* ---- 消息操作按钮组 ---- */
.msg-actions {
  display: flex;
  gap: 2px;
  align-self: flex-end;
  opacity: 0;
  transition: opacity 0.2s;
}

.nurse-chat__msg:hover .msg-actions { opacity: 1; }
@media (hover: none) { .msg-actions { opacity: 0.7; } }

.msg-action-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.msg-action-btn:hover {
  background: white;
  color: #1e293b;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
}

.msg-action-btn--active {
  color: #2E7D32;
  background: #E8F5E9;
}

/* ---- 音频消息气泡 ---- */
.nurse-chat__audio {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 160px;
}

.audio-play-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #66BB6A 0%, #2E7D32 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.15s;
}

.audio-play-btn:active {
  transform: scale(0.9);
}

.audio-waveform {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 24px;
}

.audio-bar {
  width: 3px;
  height: 100%;
  background: #A5D6A7;
  border-radius: 2px;
  animation: audioWave 1.2s ease-in-out infinite;
}

.audio-bar:nth-child(even) { animation-delay: 0.15s; }

@keyframes audioWave {
  0%, 100% { transform: scaleY(0.4); }
  50% { transform: scaleY(1); }
}

.audio-duration {
  font-size: 11px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ---- 顶部工具栏 ---- */
.nurse-chat__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
  z-index: 10;
}

.toolbar-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.toolbar-actions {
  display: flex;
  gap: 4px;
}

.toolbar-action-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-action-btn:hover {
  background: rgba(46, 125, 50, 0.08);
  color: #2E7D32;
}

.toolbar-action-btn--active {
  color: #2E7D32;
  background: #E8F5E9;
}

/* ---- 音频消息包装器 ---- */
.nurse-chat__audio-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ---- 音频转录按钮 ---- */
.audio-transcribe-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: none;
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-left: 4px;
}

.audio-transcribe-btn:hover {
  background: rgba(46, 125, 50, 0.15);
  color: #2E7D32;
}

.audio-transcribe-btn:active {
  transform: scale(0.9);
}

/* ---- 音频转录文本 ---- */
.audio-transcription {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(100, 116, 139, 0.06);
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
  border: 1px solid rgba(100, 116, 139, 0.1);
}

.audio-transcription--loading {
  color: #94a3b8;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.audio-transcription--loading::before {
  content: '';
  width: 12px;
  height: 12px;
  border: 2px solid #cbd5e1;
  border-top-color: #66BB6A;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ---- 工具结果卡片 ---- */
.tool-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  animation: toolCardIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes toolCardIn {
  from { opacity: 0; transform: translateY(6px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.tool-result-card {
  background: rgba(102, 187, 106, 0.04);
  border: 1px solid rgba(102, 187, 106, 0.15);
  border-radius: 10px;
  overflow: hidden;
  font-size: 12px;
}

.tr-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(102, 187, 106, 0.06);
  border-bottom: 1px solid rgba(102, 187, 106, 0.08);
}

.tr-icon { font-size: 12px; }
.tr-title {
  font-size: 11px;
  font-weight: 600;
  color: #43A047;
}

.tr-body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tr-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tr-label {
  color: #64748b;
  font-size: 11px;
}

.tr-value {
  color: #1e293b;
  font-weight: 500;
  font-size: 12px;
}

.tr-value--high, .tr-value--critical { color: #ef4444; }
.tr-value--medium, .tr-value--moderate { color: #f59e0b; }
.tr-value--low { color: #22c55e; }

.tr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.tr-chip {
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(102, 187, 106, 0.1);
  color: #43A047;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.tr-chip--alert {
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
}

.tr-alerts {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 2px;
}

.tr-alert {
  padding: 3px 6px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.4;
}

.tr-alert--red { background: rgba(239, 68, 68, 0.08); color: #ef4444; }
.tr-alert--orange { background: rgba(249, 115, 22, 0.08); color: #f97316; }
.tr-alert--yellow { background: rgba(245, 158, 11, 0.08); color: #d97706; }

.tr-trend-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tr-metric {
  color: #475569;
  font-size: 11px;
  min-width: 60px;
}

.tr-trend {
  font-weight: 600;
  font-size: 13px;
  width: 16px;
  text-align: center;
}

.tr-trend--rising, .tr-trend--increasing { color: #ef4444; }
.tr-trend--falling, .tr-trend--decreasing { color: #3b82f6; }
.tr-trend--stable { color: #22c55e; }

.tr-summary {
  color: #64748b;
  font-size: 11px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tr-rules {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tr-rule {
  padding: 3px 6px;
  border-radius: 6px;
  font-size: 11px;
}

.tr-rule--critical, .tr-rule--high { background: rgba(239, 68, 68, 0.08); color: #ef4444; }
.tr-rule--medium, .tr-rule--warning { background: rgba(245, 158, 11, 0.08); color: #d97706; }
.tr-rule--info, .tr-rule--low { background: rgba(59, 130, 246, 0.06); color: #3b82f6; }

.tr-empty {
  color: #94a3b8;
  font-size: 11px;
  font-style: italic;
}

.tr-summary-text {
  color: #475569;
  font-size: 11px;
  line-height: 1.5;
}

.tr-knowledge {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tr-knowledge-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tr-knowledge-title {
  font-weight: 600;
  color: #1e293b;
  font-size: 11px;
}

.tr-knowledge-snippet {
  color: #64748b;
  font-size: 10px;
  line-height: 1.4;
}

.tr-done {
  color: #22c55e;
  font-size: 11px;
  font-weight: 500;
}
</style>
