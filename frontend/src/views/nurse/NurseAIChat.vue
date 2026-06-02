<template>
  <div class="nurse-chat">
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
          <div v-else-if="msg.messageType === 'audio'" class="nurse-chat__audio">
            <button class="audio-play-btn" @click="playAudio(msg)">
              <el-icon :size="16"><VideoPlay v-if="!msg.isPlaying" /><VideoPause v-else /></el-icon>
            </button>
            <div class="audio-waveform">
              <span v-for="i in 12" :key="i" class="audio-bar" :style="{ animationDelay: `${i * 0.05}s` }" />
            </div>
            <span class="audio-duration">{{ formatAudioDuration(msg.audioDuration || 0) }}</span>
          </div>
          <div v-else class="nurse-chat__text">
            <StructuredAnalysisCard
              v-if="isStructuredAnalysis(msg.content)"
              :data="parseStructuredAnalysis(msg.content)!"
              role="nurse"
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
      <div v-if="currentToolStep" class="nurse-chat__tool-indicator">
        <div class="tool-indicator__icon">
          <el-icon :size="14"><Loading /></el-icon>
        </div>
        <span class="tool-indicator__text">{{ currentToolStep }}</span>
      </div>
    </transition>

    <!-- 已完成的工具步骤 -->
    <transition name="fade">
      <div v-if="completedToolSteps.length > 0" class="nurse-chat__tool-steps">
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
import { Promotion, Loading, Check, Microphone, VideoPlay, VideoPause, Headset } from '@element-plus/icons-vue'
import { nurseAiApi } from '@/api/endpoints'
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
}

const messages = ref<ChatMsg[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

// 工具调用状态
const currentToolStep = ref<string | null>(null)
const completedToolSteps = ref<string[]>([])

let msgCounter = 0
function genId() { return `nurse_${Date.now()}_${++msgCounter}` }

// ---- 语音录制 ----
const { isRecording, isInCancelZone, recordingText, startRecording } = useAudioRecorder({
  onComplete: async (result) => {
    await sendAudioMessage(result.base64, result.format, result.blob, result.duration)
  },
})

// ---- TTS 播报 ----
const { isSpeaking, speak, stop: stopTTS, cleanForTTS } = useTTS({ role: 'nurse' })
const ttsSpeakingId = ref<string | null>(null)
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
    thinkingMessage: '小护正在听取语音...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

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
    thinkingMessage: '小护正在思考...',
    toolSteps: [],
  }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await nurseAiApi.chatStream(
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
        },
        onError() {
          assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
          assistantMsg.loading = false
          assistantMsg.thinking = false
          currentToolStep.value = null
          isStreaming.value = false
        },
      }
    )
  } catch {
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
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
  box-shadow: 0 2px 8px rgba(92, 107, 192, 0.08);
  color: #1e293b;
  border-radius: 4px 16px 16px 16px;
}

/* 用户气泡 */
.nurse-chat__bubble--user {
  background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
  color: white;
  border-radius: 16px 4px 16px 16px;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.25);
}

.nurse-chat__text :deep(p) { margin: 0 0 8px; }
.nurse-chat__text :deep(p:last-child) { margin-bottom: 0; }
.nurse-chat__text :deep(strong) { font-weight: 600; color: #1e293b; }
.nurse-chat__text :deep(ul),
.nurse-chat__text :deep(ol) { padding-left: 18px; margin: 4px 0; }
.nurse-chat__text :deep(li) { margin: 2px 0; }
.nurse-chat__text :deep(code) {
  background: rgba(99, 102, 241, 0.1);
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
  background: linear-gradient(135deg, #818cf8, #6366f1);
  animation: pulse-ring 1.5s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  position: relative;
}

.thinking-pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid rgba(99, 102, 241, 0.3);
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
  color: #6366f1;
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
  background: #a5b4fc;
  animation: dotBounce 1.4s infinite ease-in-out both;
}

.loading-dot:nth-child(2) { animation-delay: 0.16s; }
.loading-dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* 工具调用指示器 */
.nurse-chat__tool-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin: 0 16px;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.tool-indicator__icon {
  color: #6366f1;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.tool-indicator__text {
  font-size: 12px;
  color: #6366f1;
  font-weight: 500;
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
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.15);
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
  background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

.send-btn--active:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
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
  background: linear-gradient(135deg, #c7d2fe 0%, #a5b4fc 100%);
  color: #6366f1;
}

.mic-btn--active:hover {
  background: linear-gradient(135deg, #a5b4fc 0%, #818cf8 100%);
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
  background: rgba(99, 102, 241, 0.95);
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
  border: 1px solid #e2e8f0;
  background: white;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  align-self: flex-end;
}

.tts-btn:hover {
  color: #6366f1;
  border-color: #c7d2fe;
}

.tts-btn--speaking {
  color: #6366f1;
  border-color: #818cf8;
  background: #eef2ff;
  animation: ttsPulse 1s ease-in-out infinite;
}

@keyframes ttsPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
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
  background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
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
  background: #a5b4fc;
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
</style>
