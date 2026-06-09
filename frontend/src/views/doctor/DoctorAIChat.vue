<template>
  <div class="doctor-chat">
    <!-- 顶部工具栏 -->
    <div class="doctor-chat__toolbar">
      <span class="toolbar-title">Dr.智 AI 助手</span>
      <div class="toolbar-actions">
        <button class="toolbar-action-btn" :class="{ 'toolbar-action-btn--active': autoPlayTTS }" @click="toggleAutoPlayTTS" :title="autoPlayTTS ? '关闭自动播报' : '开启自动播报'">
          <el-icon :size="14"><Headset /></el-icon>
        </button>
        <button class="toolbar-action-btn" :class="{ 'toolbar-action-btn--active': isMuted }" @click="toggleMute" :title="isMuted ? '取消静音' : '静音'">
          <el-icon :size="14"><Mute v-if="isMuted" /><Microphone v-else /></el-icon>
        </button>
      </div>
    </div>

    <!-- 消息区域 -->
    <div class="doctor-chat__messages" ref="messagesRef">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="doctor-chat__msg"
        :class="{ 'doctor-chat__msg--user': msg.role === 'user' }"
      >
        <AgentAvatar
          v-if="msg.role === 'assistant'"
          agent="zhiyi"
          :size="32"
          :thinking="msg.loading && msg.thinking"
        />
        <div class="doctor-chat__bubble" :class="{ 'doctor-chat__bubble--user': msg.role === 'user' }">
          <!-- 思考中状态 -->
          <div v-if="msg.loading && msg.thinking" class="doctor-chat__thinking">
            <div class="thinking-pulse"></div>
            <span class="thinking-text">{{ msg.thinkingMessage || 'Dr.智正在思考...' }}</span>
          </div>
          <!-- 加载中 -->
          <div v-else-if="msg.loading && !msg.content" class="doctor-chat__loading">
            <span class="loading-dot" /><span class="loading-dot" /><span class="loading-dot" />
          </div>
          <!-- 消息内容 -->
          <div v-else-if="msg.messageType === 'audio'" class="doctor-chat__audio-wrapper">
            <div class="doctor-chat__audio">
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
          <div v-else class="doctor-chat__text">
            <StructuredAnalysisCard
              v-if="isStructuredAnalysis(msg.content)"
              :data="parseStructuredAnalysis(msg.content)!"
              role="doctor"
            />
            <div v-else v-html="renderMarkdown(msg.content)" />
          </div>
        </div>
        <!-- TTS 播报按钮（助手消息） -->
        <button
          v-if="msg.role === 'assistant' && !msg.loading && msg.content"
          class="tts-btn"
          :class="{ 'tts-btn--speaking': ttsSpeakingId === msg.id }"
          @click="toggleTTS(msg)"
          title="语音播报"
        >
          <el-icon :size="13"><Headset /></el-icon>
        </button>
      </div>
    </div>

    <!-- 工具调用步骤指示器 -->
    <transition name="slide-up">
      <div v-if="currentToolStep" class="doctor-chat__tool-indicator">
        <div class="tool-indicator__icon">
          <el-icon :size="14"><Loading /></el-icon>
        </div>
        <span class="tool-indicator__text">{{ currentToolStep }}</span>
      </div>
    </transition>

    <!-- 已完成的工具步骤 -->
    <transition name="fade">
      <div v-if="completedToolSteps.length > 0" class="doctor-chat__tool-steps">
        <div
          v-for="(step, idx) in completedToolSteps"
          :key="idx"
          class="tool-step"
        >
          <el-icon :size="12" class="tool-step__check"><Check /></el-icon>
          <span class="tool-step__text">{{ step }}</span>
        </div>
      </div>
    </transition>

    <!-- 录音覆盖层 -->
    <transition name="record-fade">
      <div v-if="isRecording" class="doctor-chat__record-overlay">
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
    <div class="doctor-chat__input">
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
        placeholder="向 Dr.智 提问临床问题..."
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
import { Promotion, Loading, Check, Microphone, VideoPlay, VideoPause, Headset, Mute, Document } from '@element-plus/icons-vue'
import { doctorAiApi, chatApi } from '@/api/endpoints'
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
  messageType?: 'text' | 'audio'
  audioUrl?: string
  audioDuration?: number
  isPlaying?: boolean
  transcribedText?: string
  transcribing?: boolean
  transcriptionVisible?: boolean
}

const messages = ref<ChatMsg[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

// 工具调用状态
const currentToolStep = ref<string | null>(null)
const completedToolSteps = ref<string[]>([])

let msgCounter = 0
function genId() { return `doctor_${Date.now()}_${++msgCounter}` }

// ---- 语音录制 ----
const { isRecording, isInCancelZone, recordingText, startRecording } = useAudioRecorder({
  onComplete: async (result) => {
    await sendAudioMessage(result.base64, result.format, result.blob, result.duration)
  },
})

// ---- TTS 播报 ----
const { isSpeaking, speak, stop: stopTTS, cleanForTTS } = useTTS({ role: 'doctor' })
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
    thinkingMessage: 'Dr.智正在听取语音...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await doctorAiApi.chatStream(
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
          currentToolStep.value = message
          scrollToBottom()
        },
        onChunk(chunk: string) {
          assistantMsg.content += chunk
          assistantMsg.thinking = false
          currentToolStep.value = null
          scrollToBottom()
        },
        onDone(metadata: any) {
          assistantMsg.loading = false
          assistantMsg.thinking = false
          assistantMsg.toolSteps = metadata?.tool_steps || []
          completedToolSteps.value = metadata?.tool_steps || []
          currentToolStep.value = null
          isStreaming.value = false
          // 保存 ASR 转录文本到用户语音消息
          if (metadata?.transcribed_text) {
            const userAudioMsg = messages.value.find(m => m.role === 'user' && m.messageType === 'audio' && !m.transcribedText)
            if (userAudioMsg) userAudioMsg.transcribedText = metadata.transcribed_text
          }
          scrollToBottom()
          autoSpeakAssistant(assistantMsg)
        },
        onError() {
          assistantMsg.content = '抱歉，语音处理失败，请重试或使用文字输入。'
          assistantMsg.loading = false
          assistantMsg.thinking = false
          currentToolStep.value = null
          isStreaming.value = false
        },
      }
    )
  } catch {
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，语音处理失败，请重试或使用文字输入。'
    }
    assistantMsg.loading = false
    assistantMsg.thinking = false
    currentToolStep.value = null
    isStreaming.value = false
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
  currentToolStep.value = null
  completedToolSteps.value = []

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
    thinkingMessage: 'Dr.智正在思考...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await doctorAiApi.chatStream(
      { message: text, pregnant_id: pregnantId || undefined },
      {
        onThinking(message: string) {
          assistantMsg.thinkingMessage = message
          currentToolStep.value = message
          scrollToBottom()
        },
        onChunk(chunk: string) {
          assistantMsg.content += chunk
          assistantMsg.thinking = false
          currentToolStep.value = null
          scrollToBottom()
        },
        onDone(metadata: any) {
          assistantMsg.loading = false
          assistantMsg.thinking = false
          assistantMsg.toolSteps = metadata?.tool_steps || []
          completedToolSteps.value = metadata?.tool_steps || []
          currentToolStep.value = null
          isStreaming.value = false
          scrollToBottom()
          autoSpeakAssistant(assistantMsg)
        },
        onError() {
          assistantMsg.content = '抱歉，Dr.智暂时无法回复。请稍后再试。'
          assistantMsg.loading = false
          assistantMsg.thinking = false
          currentToolStep.value = null
          isStreaming.value = false
        },
      }
    )
  } catch {
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，Dr.智暂时无法回复。请稍后再试。'
    }
    assistantMsg.loading = false
    assistantMsg.thinking = false
    currentToolStep.value = null
    isStreaming.value = false
  }
}

onMounted(() => {
  messages.value.push({
    id: genId(),
    role: 'assistant',
    content: '您好！我是 **Dr.智**，您的AI临床助手。\n\n可以向我咨询：\n- 风险评估\n- 治疗方案参考\n- 指南解读\n- 病例分析\n- 用药参考',
  })
})
</script>

<style scoped>
.doctor-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(180deg, #f0fdf4 0%, #ecfdf5 100%);
  position: relative;
}

.doctor-chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.doctor-chat__messages::-webkit-scrollbar {
  width: 4px;
}

.doctor-chat__messages::-webkit-scrollbar-track {
  background: transparent;
}

.doctor-chat__messages::-webkit-scrollbar-thumb {
  background: #a7f3d0;
  border-radius: 2px;
}

.doctor-chat__msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  animation: msgSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes msgSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.doctor-chat__msg--user {
  flex-direction: row-reverse;
}

.doctor-chat__bubble {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.6;
  position: relative;
}

/* 助手气泡 - 玻璃态 */
.doctor-chat__bubble:not(.doctor-chat__bubble--user) {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.08);
  color: #1e293b;
  border-radius: 4px 16px 16px 16px;
}

/* 用户气泡 */
.doctor-chat__bubble--user {
  background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
  color: white;
  border-radius: 16px 4px 16px 16px;
  box-shadow: 0 2px 12px rgba(16, 185, 129, 0.25);
}

.doctor-chat__text :deep(p) { margin: 0 0 8px; }
.doctor-chat__text :deep(p:last-child) { margin-bottom: 0; }
.doctor-chat__text :deep(strong) { font-weight: 600; color: #1e293b; }
.doctor-chat__text :deep(ul),
.doctor-chat__text :deep(ol) { padding-left: 18px; margin: 4px 0; }
.doctor-chat__text :deep(li) { margin: 2px 0; }
.doctor-chat__text :deep(code) {
  background: rgba(16, 185, 129, 0.1);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12px;
}

/* 思考中状态 */
.doctor-chat__thinking {
  display: flex;
  align-items: center;
  gap: 10px;
}

.thinking-pulse {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #34d399, #10b981);
  animation: pulse-ring 1.5s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  position: relative;
}

.thinking-pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid rgba(16, 185, 129, 0.3);
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
  color: #10b981;
}

/* 加载动画 */
.doctor-chat__loading {
  display: flex;
  gap: 6px;
  padding: 4px 0;
}

.loading-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6ee7b7;
  animation: dotBounce 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(2) { animation-delay: 0.16s; }
.loading-dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* 工具调用指示器 */
.doctor-chat__tool-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin: 0 16px;
  background: rgba(16, 185, 129, 0.08);
  border-radius: 10px;
  border: 1px solid rgba(16, 185, 129, 0.15);
}

.tool-indicator__icon {
  color: #10b981;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.tool-indicator__text {
  font-size: 12px;
  color: #10b981;
  font-weight: 500;
}

/* 已完成的工具步骤 */
.doctor-chat__tool-steps {
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
.doctor-chat__input {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-top: 1px solid rgba(209, 250, 229, 0.8);
  align-items: flex-end;
}

.doctor-chat__input :deep(.el-textarea__inner) {
  border: 1px solid #d1fae5;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
  resize: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.doctor-chat__input :deep(.el-textarea__inner:focus) {
  border-color: #34d399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.15);
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: #d1fae5;
  color: #6ee7b7;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
}

.send-btn--active {
  background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
}

.send-btn--active:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
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
  background: #d1fae5;
  color: #6ee7b7;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.mic-btn--active {
  background: linear-gradient(135deg, #a7f3d0 0%, #6ee7b7 100%);
  color: #10b981;
}

.mic-btn--active:hover {
  background: linear-gradient(135deg, #6ee7b7 0%, #34d399 100%);
  color: white;
}

.mic-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* ---- 录音覆盖层 ---- */
.doctor-chat__record-overlay {
  position: absolute;
  inset: 0;
  background: rgba(16, 185, 129, 0.95);
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

/* ---- TTS 播报按钮 ---- */
.tts-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid #d1fae5;
  background: white;
  color: #6ee7b7;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  align-self: flex-end;
}

.tts-btn:hover {
  color: #10b981;
  border-color: #a7f3d0;
}

.tts-btn--speaking {
  color: #10b981;
  border-color: #34d399;
  background: #ecfdf5;
  animation: ttsPulse 1s ease-in-out infinite;
}

@keyframes ttsPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

/* ---- 音频消息气泡 ---- */
.doctor-chat__audio {
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
  background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
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
  background: #6ee7b7;
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
.doctor-chat__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(209, 250, 229, 0.6);
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
  background: rgba(16, 185, 129, 0.08);
  color: #10b981;
}

.toolbar-action-btn--active {
  color: #10b981;
  background: #ecfdf5;
}

/* ---- 音频消息包装器 ---- */
.doctor-chat__audio-wrapper {
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
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
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
  border: 2px solid #d1fae5;
  border-top-color: #10b981;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>
