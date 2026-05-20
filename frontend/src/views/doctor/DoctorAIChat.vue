<template>
  <div class="doctor-chat">
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
          <div v-else class="doctor-chat__text" v-html="renderMarkdown(msg.content)" />
        </div>
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
      <div v-if="completedToolSteps.length > 0 && isStreaming" class="doctor-chat__tool-steps">
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

    <!-- 输入区域 -->
    <div class="doctor-chat__input">
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
import { ref, nextTick, onMounted } from 'vue'
import { Promotion, Loading, Check } from '@element-plus/icons-vue'
import { doctorAiApi } from '@/api/endpoints'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { renderMarkdown } from '@/utils/markdown'

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  loading?: boolean
  thinking?: boolean
  thinkingMessage?: string
  toolSteps?: string[]
  currentStep?: string
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
    content: '您好！我是 **Dr.智**，您的AI临床助手。\n\n可以向我咨询：\n- 鉴别诊断\n- 治疗方案\n- 指南解读\n- 病例分析\n- 用药参考',
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
</style>
