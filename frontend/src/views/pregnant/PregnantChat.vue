<template>
  <div class="chat-wrapper" :class="{ 'chat-wrapper--ios': isIOS }">
    <!-- ==================== 紧急警告横幅 ==================== -->
    <transition name="banner-slide">
      <div v-if="urgentDetected" class="emergency-banner" role="alert">
        <el-icon :size="18"><WarningFilled /></el-icon>
        <span>检测到紧急关键词，请立即联系医生或拨打急救电话</span>
        <el-button size="small" text class="banner-close" @click="urgentDetected = false">
          <el-icon :size="14"><Close /></el-icon>
        </el-button>
      </div>
    </transition>

    <!-- ==================== 随访模式横幅 ==================== -->
    <transition name="banner-slide">
      <div v-if="isFollowupMode" class="followup-banner">
        <div class="followup-banner__inner">
          <div class="followup-banner__header">
            <span class="followup-banner__icon">📋</span>
            <span>小护发来随访对话</span>
            <el-tag
              v-if="followupProgress?.status === 'confirmed'"
              type="success"
              size="small"
              effect="dark"
              style="margin-left: auto"
            >
              已完成
            </el-tag>
          </div>
          <div v-if="followupProgress && followupProgress.total > 0 && followupProgress.status !== 'confirmed'" class="followup-banner__progress">
            <div class="followup-banner__bar">
              <div
                class="followup-banner__fill"
                :style="{ width: (followupProgress.answered / followupProgress.total * 100) + '%' }"
              />
            </div>
            <span class="followup-banner__count">
              {{ followupProgress.answered }}/{{ followupProgress.total }}
            </span>
          </div>
        </div>
      </div>
    </transition>

    <!-- ==================== 1. 顶部导航栏 ==================== -->
    <nav class="chat-navbar">
      <button class="navbar-btn navbar-btn--back" @click="handleBack" aria-label="返回">
        <el-icon :size="18"><ArrowLeft /></el-icon>
      </button>
      <h1 class="navbar-title">孕期温暖陪伴</h1>
      <div class="navbar-actions">
        <button class="navbar-btn" @click="handleNewChat" aria-label="新建对话" title="新建对话">
          <el-icon :size="18"><ChatLineRound /></el-icon>
        </button>
        <button class="navbar-btn" @click="handleClearMemory" aria-label="清除记录" title="清除记录">
          <el-icon :size="18"><Delete /></el-icon>
        </button>
      </div>
    </nav>

    <!-- ==================== 2. 用户信息栏 ==================== -->
    <div class="user-info-bar">
      <span class="user-name">{{ displayName || '孕妈' }}</span>
      <button class="switch-btn" @click="handleSwitchUser">
        <el-icon :size="12"><RefreshRight /></el-icon> 切换
      </button>
      <div class="user-actions">
        <button class="user-action-btn" :class="{ active: isMuted }" @click="toggleMute" :aria-label="isMuted ? '取消静音' : '静音'">
          <el-icon :size="16"><Mute v-if="isMuted" /><Microphone v-else /></el-icon>
        </button>
        <button class="user-action-btn" @click="scrollToBottom()" aria-label="滚动到底部">
          <el-icon :size="16"><ChatDotRound /></el-icon>
        </button>
      </div>
    </div>

    <!-- ==================== 主滚动区域 ==================== -->
    <div ref="messagesRef" class="messages-container" role="log" aria-live="polite">
      <div class="messages-inner">

        <!-- ---- 欢迎信息 ---- -->
        <div v-if="showWelcome" class="welcome-section">
          <div class="welcome-header">
            <AgentAvatar agent="xiaan" :size="64" />
          </div>
          <h2 class="welcome-title">您好，我是孕期助手小安</h2>
          <p class="welcome-desc">在这里，我将为您提供全方位的孕产知识支持，陪伴您度过一个安心、健康的孕期旅程~</p>
        </div>

        <!-- ---- 孕周指南 ---- -->
        <div v-if="gestWeek && showWelcome" class="pregnancy-guide">
          <h3 class="section-title">孕周指南</h3>
          <div class="week-card">
            <div class="week-main">
              <div class="week-number">孕{{ gestWeek }}周{{ gestDay || 0 }}天</div>
              <div class="days-remaining">还有{{ Math.max(0, (40 - gestWeek) * 7 - (gestDay || 0)) }}天出生</div>
            </div>
            <div class="fetus-visual">
              <div class="fetus-circle">
                <span class="fetus-size">{{ fetusSize }}</span>
              </div>
              <span class="fetus-label">宝宝现在这么大</span>
            </div>
            <div class="measurements">
              <div class="measurement">
                <span class="measurement-label">身长</span>
                <span class="measurement-value">{{ fetusLength }}</span>
              </div>
              <div class="measurement-divider" />
              <div class="measurement">
                <span class="measurement-label">体重</span>
                <span class="measurement-value">{{ fetusWeight }}</span>
              </div>
            </div>
            <div class="pagination-dots">
              <span class="dot active" />
              <span class="dot" />
              <span class="dot" />
            </div>
          </div>
        </div>

        <!-- ---- 功能导航 ---- -->
        <div v-if="showWelcome" class="function-nav">
          <div
            v-for="fn in functionItems"
            :key="fn.id"
            class="function-item"
            :class="'function-item--' + fn.color"
            @click="handleFunctionClick(fn)"
            role="button"
            :aria-label="fn.name"
          >
            <div class="function-icon"><span>{{ fn.icon }}</span></div>
            <span class="function-name">{{ fn.name }}</span>
          </div>
        </div>

        <!-- ---- 消息列表 ---- -->
        <div class="msg-list">
          <div
            v-for="msg in chatStore.messages"
            :key="msg.id"
            class="message-row"
            :class="{
              'message-row--user': msg.role === 'user',
              'message-row--assistant': msg.role === 'assistant',
            }"
          >
            <AgentAvatar
              v-if="msg.role === 'assistant'"
              agent="xiaan"
              :size="34"
            />

            <div class="message-body">
              <!-- 思考中 -->
              <div
                v-if="msg.loading && msg.thinking"
                class="message-bubble message-bubble--assistant message-bubble--thinking"
              >
                <AgentAvatar agent="xiaan" :size="20" :thinking="true" />
                <span class="thinking-text">{{ msg.thinkingMessage || '小安正在思考...' }}</span>
              </div>
              <!-- 加载中 -->
              <div
                v-else-if="msg.loading"
                class="message-bubble message-bubble--assistant message-bubble--loading"
              >
                <span class="loading-dot" />
                <span class="loading-dot" />
                <span class="loading-dot" />
              </div>

              <!-- 消息气泡 -->
              <div
                v-else
                class="message-bubble"
                :class="{
                  'message-bubble--user': msg.role === 'user',
                  'message-bubble--assistant': msg.role === 'assistant',
                  'message-bubble--urgent': msg.isUrgent,
                }"
              >
                <!-- 用户消息：纯文本 -->
                <div v-if="msg.role === 'user'" class="bubble-text">{{ msg.content }}</div>
                <!-- 助手消息：Markdown 渲染 -->
                <div
                  v-else
                  class="bubble-text bubble-markdown"
                  v-html="renderMarkdown(msg.content)"
                />
                <!-- 流式打字光标 -->
                <span v-if="msg.role === 'assistant' && isStreamingMessage(msg)" class="typing-cursor" />
              </div>

              <!-- 时间戳 -->
              <div
                class="message-time"
                :class="{ 'message-time--user': msg.role === 'user' }"
              >
                <span>{{ formatTime(msg.timestamp) }}</span>
                <el-tag
                  v-if="msg.isUrgent"
                  size="small"
                  type="danger"
                  class="urgent-tag"
                  effect="dark"
                >
                  紧急
                </el-tag>
              </div>

              <!-- 消息操作栏 -->
              <div
                v-if="!msg.loading && chatStore.messages.length > 0"
                class="message-actions"
                :class="{ 'message-actions--user': msg.role === 'user' }"
              >
                <button
                  v-if="msg.role === 'assistant'"
                  class="msg-action-btn"
                  @click="handleCopyMessage(msg.content)"
                  title="复制"
                >
                  <el-icon :size="13"><CopyDocument /></el-icon>
                </button>
                <button
                  v-if="msg.role === 'assistant' && !chatStore.streaming"
                  class="msg-action-btn"
                  @click="handleRetry(msg)"
                  title="重新生成"
                >
                  <el-icon :size="13"><RefreshRight /></el-icon>
                </button>
                <button
                  v-if="msg.role === 'assistant' && !chatStore.streaming && !msg.loading"
                  class="msg-action-btn"
                  :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_up' }"
                  @click="handleFeedback(msg, 'thumbs_up')"
                  title="有帮助"
                >
                  👍
                </button>
                <button
                  v-if="msg.role === 'assistant' && !chatStore.streaming && !msg.loading"
                  class="msg-action-btn"
                  :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_down' }"
                  @click="handleFeedback(msg, 'thumbs_down')"
                  title="需改进"
                >
                  👎
                </button>
                <button
                  v-if="msg.role === 'user'"
                  class="msg-action-btn"
                  @click="handleEditMessage(msg)"
                  title="编辑"
                >
                  <el-icon :size="13"><Edit /></el-icon>
                </button>
              </div>
            </div>

            <div v-if="msg.role === 'user'" class="user-avatar-spacer" />
          </div>
        </div>

        <!-- ---- 兴趣推荐 ---- -->
        <transition name="suggest-fade">
          <div v-if="!chatStore.loading && !isFollowupMode" class="interests-area">
            <h3 class="interests-title">您可能感兴趣：</h3>
            <div class="interests-list">
              <div
                v-for="item in SUGGESTED_QUESTIONS"
                :key="item"
                class="interest-item"
                @click="handleSuggestionClick(item)"
                role="button"
              >
                <span class="interest-hashtag">#</span>
                <span class="interest-text">{{ item }}</span>
              </div>
            </div>
          </div>
        </transition>

        <div ref="scrollAnchorRef" class="scroll-anchor" />
      </div>
    </div>

    <!-- ==================== 3. 底部输入区 ==================== -->
    <div class="input-area">
      <transition name="banner-slide">
        <div v-if="isRecording" class="recording-bar">
          <span class="recording-dot" />
          <span class="recording-text">{{ recordingText }}</span>
          <el-button size="small" type="danger" text @click="cancelRecording">取消</el-button>
        </div>
      </transition>

      <div class="input-row">
        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn--recording': isRecording }"
          @click="toggleRecording"
          :aria-label="isRecording ? '停止录音' : '语音输入'"
        >
          <el-icon :size="20"><Microphone /></el-icon>
        </button>

        <!-- 停止生成按钮（流式输出时显示） -->
        <button
          v-if="chatStore.streaming"
          class="toolbar-btn toolbar-btn--stop"
          @click="handleStopGeneration"
          aria-label="停止生成"
        >
          <el-icon :size="18"><VideoPause /></el-icon>
        </button>

        <el-input
          v-else
          ref="inputRef"
          v-model="inputText"
          type="textarea"
          :rows="1"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入您的问题…"
          resize="none"
          class="chat-input"
          @keydown.enter.exact.prevent="handleSend"
        />

        <button
          v-if="!chatStore.streaming"
          class="send-btn"
          :disabled="!inputText.trim() || chatStore.loading"
          @click="handleSend"
          aria-label="发送"
        >
          <el-icon :size="20"><Promotion /></el-icon>
        </button>
      </div>

      <div class="input-hint">
        <span>Enter 发送 · Shift+Enter 换行</span>
      </div>
    </div>

    <!-- ==================== 编辑消息弹窗 ==================== -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑消息"
      width="90%"
      :style="{ maxWidth: '420px' }"
      append-to-body
    >
      <el-input
        v-model="editText"
        type="textarea"
        :rows="3"
        placeholder="编辑消息内容…"
      />
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEdit">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Delete,
  Promotion,
  ArrowLeft,
  WarningFilled,
  Close,
  Microphone,
  Mute,
  RefreshRight,
  ChatDotRound,
  ChatLineRound,
  CopyDocument,
  Edit,
  VideoPause,
} from '@element-plus/icons-vue'
import { chatApi, postChatStream, feedbackApi } from '@/api/endpoints'
import type { ChatRequest } from '@/types'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { useChatStore } from '@/stores/chat'
import type { ChatMessage } from '@/stores/chat'
import { renderMarkdown } from '@/utils/markdown'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useScroll } from '@vueuse/core'

/* ==================== 类型 ==================== */
interface PregnantContext {
  gestational_week?: number
  gestational_day?: number
  display_name?: string
}

/* ==================== 常量 ==================== */
const EMERGENCY_KEYWORDS = [
  '大出血', '剧烈腹痛', '见红', '破水', '胎动消失',
  '严重头痛', '视力模糊', '抽搐', '呼吸困难', '高热', '昏迷', '失去意识',
]

const SUGGESTED_QUESTIONS = [
  '孕期可以喝咖啡吗',
  '孕期体重增长标准',
  '孕期运动推荐',
  '孕期饮食注意事项',
]

const FUNCTION_ITEMS = [
  { id: 1, name: '深度思考', icon: '🧠', color: 'pink' },
  { id: 2, name: '数胎动', icon: '💓', color: 'orange' },
  { id: 3, name: '超声报告', icon: '📄', color: 'yellow' },
]

const FETUS_DATA: Record<number, { length: string; weight: string; size: string }> = {
  6: { length: '4-6mm', weight: '0.5-1g', size: '1cm' },
  8: { length: '1.6-2cm', weight: '1-2g', size: '2cm' },
  10: { length: '3-4cm', weight: '5-10g', size: '3cm' },
  12: { length: '5-6cm', weight: '10-15g', size: '5cm' },
  16: { length: '10-12cm', weight: '100-150g', size: '10cm' },
  20: { length: '15-17cm', weight: '250-300g', size: '16cm' },
  24: { length: '20-22cm', weight: '550-650g', size: '21cm' },
  28: { length: '25-27cm', weight: '1000-1200g', size: '26cm' },
  32: { length: '30-32cm', weight: '1800-2000g', size: '31cm' },
  36: { length: '34-36cm', weight: '2600-2800g', size: '35cm' },
  40: { length: '48-50cm', weight: '3000-3500g', size: '49cm' },
}

/* ==================== 状态 ==================== */
const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()

const pregnantId = ref(localStorage.getItem('currentPregnantId') || '')
const displayName = ref('')
const gestWeek = ref<number | null>(null)
const gestDay = ref<number | null>(null)

const inputText = ref('')
const urgentDetected = ref(false)
const isMuted = ref(false)

// 随访
const followupRecordId = ref<string | null>(null)
const isFollowupMode = ref(false)
const followupProgress = ref<{ answered: number; total: number; status: string } | null>(null)

// ASR
const isRecording = ref(false)
const recordingText = ref('正在录音，请说话...')
let mediaRecorder: any = null
let audioChunks: Blob[] = []

// 编辑
const editDialogVisible = ref(false)
const editText = ref('')
let editingMsgId = ''

// DOM
const messagesRef = ref<HTMLElement | null>(null)
const scrollAnchorRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLElement | null>(null)

// 移动端
const isIOS = ref(/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1))

// 滚动状态（@vueuse 自动管理）
let isAtBottom = true
const functionItems = ref(FUNCTION_ITEMS)

/* ==================== 计算属性 ==================== */
const showWelcome = computed(() => chatStore.messages.length === 0)

const fetusData = computed(() => {
  const week = gestWeek.value || 8
  const keys = Object.keys(FETUS_DATA).map(Number).sort((a, b) => a - b)
  let matched = keys[0]
  for (const k of keys) {
    if (k <= week) matched = k
  }
  return FETUS_DATA[matched]
})

const fetusLength = computed(() => fetusData.value.length)
const fetusWeight = computed(() => fetusData.value.weight)
const fetusSize = computed(() => fetusData.value.size)

/* ==================== 工具函数 ==================== */
function formatTime(ts: string): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function checkUrgent(content: string): boolean {
  return EMERGENCY_KEYWORDS.some((kw) => content.includes(kw))
}

/** 判断消息是否正在流式输出 */
function isStreamingMessage(msg: ChatMessage): boolean {
  if (!chatStore.streaming) return false
  // 最后一条助手消息且内容不为空
  const msgs = chatStore.messages
  return msgs.length > 0 && msgs[msgs.length - 1].id === msg.id && msg.role === 'assistant'
}

/* ==================== 滚动 ==================== */
function scrollToBottom(smooth = true) {
  nextTick(() => {
    scrollAnchorRef.value?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
      block: 'end',
    })
  })
}

// @vueuse 自动追踪滚动位置（arrivedState 不是响应式，手动检查 bottom）
useScroll(messagesRef, {
  onScroll() {
    const el = messagesRef.value
    if (el) {
      isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    }
  },
})

/* ==================== 导航 ==================== */
function handleBack() {
  router.options.history.state.back ? router.back() : router.push('/')
}

function handleSwitchUser() {
  ElMessage.info('孕妇切换功能即将上线')
}

function toggleMute() {
  isMuted.value = !isMuted.value
  ElMessage.info(isMuted.value ? '已静音' : '已取消静音')
}

function handleFunctionClick(fn: { id: number; name: string }) {
  const hints: Record<number, string> = { 1: '深度思考模式即将上线', 2: '数胎动功能即将上线', 3: '超声报告解读功能即将上线' }
  ElMessage.info(hints[fn.id] || '功能即将上线')
}

/* ==================== 新建对话 ==================== */
function handleNewChat() {
  if (chatStore.messages.length === 0) return
  chatStore.newConversation()
  urgentDetected.value = false
  followupRecordId.value = null
  isFollowupMode.value = false
  followupProgress.value = null
  ElMessage.success('已开始新对话')
}

/* ==================== 消息操作 ==================== */
async function handleCopyMessage(content: string) {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('已复制')
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = content
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    ElMessage.success('已复制')
  }
}

async function handleFeedback(msg: ChatMessage, rating: 'thumbs_up' | 'thumbs_down') {
  // 切换反馈状态
  const newRating = msg.feedback === rating ? null : rating
  chatStore.updateMessage(msg.id, { feedback: newRating })

  // 发送到后端
  if (newRating) {
    try {
      const pregnantId = localStorage.getItem('currentPregnantId') || ''
      await feedbackApi.submit({
        pregnant_id: pregnantId,
        message_id: msg.id,
        rating: newRating,
        session_id: chatStore.sessionId || undefined,
      })
    } catch {
      // 静默失败
    }
  }
}

function handleRetry(msg: ChatMessage) {
  const prevUser = chatStore.getPreviousUserMessage(msg.id)
  if (!prevUser) return
  // 删除这条助手消息，用用户消息重新发送
  chatStore.deleteMessageFrom(msg.id)
  inputText.value = prevUser.content
  nextTick(() => handleSend())
}

function handleEditMessage(msg: ChatMessage) {
  editingMsgId = msg.id
  editText.value = msg.content
  editDialogVisible.value = true
}

function confirmEdit() {
  const text = editText.value.trim()
  if (!text) return
  editDialogVisible.value = false

  // 更新用户消息内容
  chatStore.updateMessage(editingMsgId, { content: text })

  // 删除该消息之后的所有消息（包括助手回复）
  chatStore.deleteMessageFrom(editingMsgId)

  // 重新发送
  inputText.value = text
  nextTick(() => handleSend())
}

/* ==================== 核心：发送消息 ==================== */
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.loading) return

  inputText.value = ''
  urgentDetected.value = false

  chatStore.addMessage('user', text)
  chatStore.loading = true

  const loadingMsg = chatStore.addMessage('assistant', '', { loading: true })
  scrollToBottom()

  const req: ChatRequest = {
    pregnant_id: pregnantId.value,
    message: text,
    session_id: chatStore.sessionId || undefined,
    message_type: 'text',
    ...(followupRecordId.value ? { record_id: followupRecordId.value } : {}),
  }

  if (followupRecordId.value) {
    try {
      const res = await chatApi.send(req)
      const data = res.data
      if (data.followup_progress) {
        followupProgress.value = data.followup_progress
        if (data.followup_progress.status === 'confirmed') followupRecordId.value = null
      }
      chatStore.sessionId = data.session_id
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        content: data.content || '抱歉，我暂时无法回复，请稍后再试。',
        isUrgent: checkUrgent(data.content || ''),
        timestamp: new Date().toISOString(),
      })
    } catch {
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        content: '抱歉，我暂时无法回复。请稍后再试，或联系您的孕期管理师。',
        isUrgent: false,
      })
    }
  } else {
    // SSE 流式
    chatStore.updateMessage(loadingMsg.id, { loading: false, content: '' })
    chatStore.streaming = true

    const controller = new AbortController()
    chatStore.setAbortController(controller)

    try {
      await postChatStream(req, {
        onThinking(message: string) {
          chatStore.updateMessage(loadingMsg.id, {
            thinking: true,
            thinkingMessage: message,
          })
        },
        onChunk(chunk: string) {
          const msg = chatStore.messages.find((m) => m.id === loadingMsg.id)
          if (msg) {
            msg.content += chunk
            msg.thinking = false
            chatStore.persist?.()
          }
          if (isAtBottom) scrollToBottom()
        },
        onDone(metadata: any) {
          chatStore.sessionId = metadata.session_id
          chatStore.updateMessage(loadingMsg.id, {
            isUrgent: checkUrgent(loadingMsg.content),
            timestamp: new Date().toISOString(),
          })
        },
        onError(err: Error) {
          console.error('SSE error:', err)
          if (!loadingMsg.content) {
            chatStore.updateMessage(loadingMsg.id, {
              content: '抱歉，我暂时无法回复。请稍后再试，或联系您的孕期管理师。',
            })
          }
        },
      }, controller.signal)
    } catch {
      if (!loadingMsg.content) {
        try {
          const res = await chatApi.send(req)
          const data = res.data
          chatStore.sessionId = data.session_id
          chatStore.updateMessage(loadingMsg.id, {
            content: data.content || '抱歉，我暂时无法回复，请稍后再试。',
            isUrgent: checkUrgent(data.content || ''),
          })
        } catch {
          chatStore.updateMessage(loadingMsg.id, {
            content: '抱歉，我暂时无法回复。请稍后再试，或联系您的孕期管理师。',
            isUrgent: false,
          })
        }
      }
    } finally {
      chatStore.streaming = false
      chatStore.setAbortController(null)
    }

    // 流式结束后内容仍为空（如非SSE响应无声消耗）时的兜底
    if (!loadingMsg.content) {
      chatStore.updateMessage(loadingMsg.id, {
        content: '抱歉，我暂时无法回复。请稍后再试，或联系您的孕期管理师。',
        isUrgent: false,
      })
    }
  }

  chatStore.loading = false
  scrollToBottom()
}

function handleSuggestionClick(question: string) {
  inputText.value = question
  handleSend()
}

function handleStopGeneration() {
  chatStore.stopGeneration()
  ElMessage.info('已停止生成')
}

async function handleClearMemory() {
  try {
    await ElMessageBox.confirm('确定要清除所有对话记录吗？', '确认操作', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  try {
    if (pregnantId.value) await chatApi.clearMemory(pregnantId.value)
    chatStore.clearAll()
    urgentDetected.value = false
    ElMessage.success('对话已清除')
  } catch {
    ElMessage.error('清除失败，请稍后重试')
  }
}

/* ==================== ASR ==================== */
async function toggleRecording() {
  isRecording.value ? await stopRecording() : await startRecording()
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(stream)
    audioChunks = []
    mediaRecorder.ondataavailable = (e: BlobEvent) => { if (e.data.size > 0) audioChunks.push(e.data) }
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      if (audioChunks.length === 0) { isRecording.value = false; return }
      recordingText.value = '语音识别中...'
      setTimeout(() => { ElMessage.success('语音识别完成（ASR 预留）'); isRecording.value = false }, 800)
    }
    mediaRecorder.start()
    isRecording.value = true
    recordingText.value = '正在录音，请说话...'
  } catch {
    ElMessage.warning('无法访问麦克风，请检查权限')
    isRecording.value = false
  }
}

async function stopRecording() {
  mediaRecorder?.state === 'recording' ? mediaRecorder.stop() : (isRecording.value = false)
}

function cancelRecording() {
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.stream.getTracks().forEach((t: MediaStreamTrack) => t.stop())
    mediaRecorder.stop()
  }
  audioChunks = []
  isRecording.value = false
}

/* ==================== 上下文 ==================== */
async function loadPregnantContext() {
  const pid = pregnantId.value
  if (!pid) return
  try {
    const res = await chatApi.getContext(pid)
    const data = res.data as PregnantContext
    if (data) {
      gestWeek.value = data.gestational_week ?? null
      gestDay.value = data.gestational_day ?? null
      displayName.value = data.display_name || ''
    }
  } catch { /* ignore */ }
}

/* ==================== 生命周期 ==================== */
onMounted(async () => {
  const fupId = route.query.followup as string | undefined
  if (fupId) {
    followupRecordId.value = fupId
    isFollowupMode.value = true
  }

  await loadPregnantContext()

  // 从后端同步对话历史
  if (pregnantId.value) {
    await chatStore.loadFromBackend(pregnantId.value)
  }

  if (chatStore.messages.length > 0) {
    scrollToBottom(false)
  }

  if (isFollowupMode.value && chatStore.messages.length === 0) {
    const req: ChatRequest = {
      pregnant_id: pregnantId.value,
      message: '您好，我来接受随访了。',
      session_id: '',
      message_type: 'text',
      record_id: followupRecordId.value!,
    }
    try {
      const res = await chatApi.send(req)
      const data = res.data
      chatStore.sessionId = data.session_id
      if (data.content) chatStore.addMessage('assistant', data.content)
      if (data.followup_progress) followupProgress.value = data.followup_progress
    } catch {
      chatStore.addMessage('assistant', '随访对话加载失败，请稍后重试。')
    }
  }
})
</script>

<style scoped>
/* ==================== 容器 ==================== */
.chat-wrapper {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  grid-template-columns: 100%;
  height: 100%;
  background: var(--pt-gradient);
  overflow: hidden;
  position: relative;
}

.chat-wrapper--ios {
  height: 100%;
}

/* ==================== 紧急警告横幅 ==================== */
.emergency-banner {
  grid-row: 1;
  grid-column: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #ffebee, #ffcdd2);
  border-left: 4px solid #e53935;
  color: #b71c1c;
  font-size: 13px;
  font-weight: 600;
  z-index: 20;
  animation: bannerPulse 2s ease-in-out infinite;
}

@keyframes bannerPulse {
  0%, 100% { background: linear-gradient(135deg, #ffebee, #ffcdd2); }
  50% { background: linear-gradient(135deg, #ffcdd2, #ef9a9a); }
}

.emergency-banner .banner-close { margin-left: auto; color: #c62828; flex-shrink: 0; }

.banner-slide-enter-active, .banner-slide-leave-active { transition: all 0.3s ease; }
.banner-slide-enter-from, .banner-slide-leave-to { opacity: 0; transform: translateY(-100%); }

/* ==================== 随访模式横幅 ==================== */
.followup-banner { grid-row: 1; grid-column: 1; background: linear-gradient(135deg, #F3E5F5, #E1BEE7); border-bottom: 1px solid rgba(206, 147, 216, 0.3); padding: 10px 16px; }
.followup-banner__inner { max-width: 720px; margin: 0 auto; }
.followup-banner__header { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #4A148C; }
.followup-banner__icon { font-size: 18px; }
.followup-banner__progress { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.followup-banner__bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.5); overflow: hidden; }
.followup-banner__fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #CE93D8, #AB47BC); transition: width 0.4s ease; }
.followup-banner__count { font-size: 12px; font-weight: 600; color: #7B1FA2; min-width: 32px; text-align: right; }

/* ==================== 1. 顶部导航栏 ==================== */
.chat-navbar { grid-row: 1; grid-column: 1; display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; padding-top: max(10px, env(safe-area-inset-top, 10px)); background: rgba(255, 255, 255, 0.92); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-bottom: 1px solid rgba(244, 143, 177, 0.1); z-index: 10; }
.navbar-btn { display: flex; align-items: center; justify-content: center; min-width: 40px; min-height: 40px; border-radius: 50%; border: none; background: transparent; color: var(--pt-text); cursor: pointer; transition: all 0.2s ease; -webkit-tap-highlight-color: transparent; }
.navbar-btn:hover { background: var(--pt-primary-light); color: var(--pt-primary-dark); }
.navbar-title { font-family: 'Figtree', 'PingFang SC', sans-serif; font-size: 16px; font-weight: 700; color: var(--pt-text); margin: 0; }
.navbar-actions { display: flex; gap: 4px; }

/* ==================== 2. 用户信息栏 ==================== */
.user-info-bar { grid-row: 2; grid-column: 1; display: flex; align-items: center; gap: 10px; padding: 6px 14px; background: var(--pt-card-bg); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border-bottom: 1px solid rgba(244, 143, 177, 0.08); }
.user-name { font-size: 13px; font-weight: 600; color: var(--pt-text); }
.switch-btn { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; border-radius: 10px; border: 1px solid rgba(244, 143, 177, 0.25); background: rgba(255, 255, 255, 0.6); color: var(--pt-primary-dark); font-size: 11px; font-weight: 500; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.switch-btn:hover { background: var(--pt-primary-light); border-color: var(--pt-primary); }
.user-actions { display: flex; gap: 2px; margin-left: auto; }
.user-action-btn { display: flex; align-items: center; justify-content: center; min-width: 32px; min-height: 32px; border-radius: 50%; border: none; background: transparent; color: var(--pt-text-muted); cursor: pointer; transition: all 0.2s ease; -webkit-tap-highlight-color: transparent; }
.user-action-btn:hover { background: var(--pt-primary-light); color: var(--pt-primary-dark); }
.user-action-btn.active { color: var(--pt-primary-dark); background: var(--pt-primary-light); }

/* ==================== 消息区域 ==================== */
.messages-container { grid-row: 3; grid-column: 1; min-height: 0; overflow-y: auto; padding: 12px 12px 8px; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; }
.messages-inner { display: flex; flex-direction: column; gap: 12px; max-width: 720px; margin: 0 auto; }

/* ---- 欢迎 ---- */
.welcome-section { text-align: center; padding: 16px 12px 6px; animation: welcomeFadeIn 0.5s ease-out; }
@keyframes welcomeFadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.welcome-header { margin-bottom: 12px; }
.doctor-avatar { background: linear-gradient(135deg, #fff 0%, #fce4ec 100%); box-shadow: 0 4px 20px rgba(244, 143, 177, 0.25); border: 3px solid rgba(255, 255, 255, 0.8); }
.doctor-emoji { font-size: 32px; line-height: 1; }
.welcome-title { font-size: 18px; font-weight: 700; color: var(--pt-text); margin: 0 0 6px; font-family: 'Figtree', 'PingFang SC', sans-serif; }
.welcome-desc { font-size: 13px; line-height: 1.6; color: var(--pt-text-secondary); margin: 0 auto; max-width: 360px; }

/* ---- 孕周指南 ---- */
.pregnancy-guide { animation: welcomeFadeIn 0.5s ease-out 0.1s both; }
.section-title { font-size: 14px; font-weight: 600; color: var(--pt-text); margin: 0 0 8px; }
.week-card { background: var(--pt-card-bg-solid); border-radius: var(--pt-radius); padding: 14px; box-shadow: var(--pt-shadow); display: flex; flex-direction: column; align-items: center; gap: 10px; }
.week-main { text-align: center; }
.week-number { font-size: 18px; font-weight: 700; color: var(--pt-primary-dark); font-family: 'Figtree', sans-serif; }
.days-remaining { font-size: 12px; color: var(--pt-text-muted); margin-top: 2px; }
.fetus-visual { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.fetus-circle { width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, var(--pt-primary-light), #F8BBD0); display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 16px rgba(244, 143, 177, 0.2); }
.fetus-size { font-size: 15px; font-weight: 700; color: var(--pt-primary-dark); font-family: 'Figtree', sans-serif; }
.fetus-label { font-size: 11px; color: var(--pt-text-muted); }
.measurements { display: flex; align-items: center; gap: 20px; justify-content: center; }
.measurement { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.measurement-label { font-size: 11px; color: var(--pt-text-muted); }
.measurement-value { font-size: 14px; font-weight: 600; color: var(--pt-text); font-family: 'Figtree', sans-serif; }
.measurement-divider { width: 1px; height: 24px; background: var(--pt-border); }
.pagination-dots { display: flex; gap: 5px; justify-content: center; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pt-border); }
.dot.active { width: 16px; border-radius: 3px; background: var(--pt-primary); }

/* ---- 功能导航 ---- */
.function-nav { display: flex; gap: 8px; animation: welcomeFadeIn 0.5s ease-out 0.2s both; }
.function-item { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 6px; border-radius: var(--pt-radius-sm); background: var(--pt-card-bg-solid); box-shadow: var(--pt-shadow); cursor: pointer; transition: all 0.2s ease; border: 1px solid transparent; -webkit-tap-highlight-color: transparent; }
.function-item:active { transform: scale(0.96); }
.function-item--pink { border-bottom: 3px solid #F48FB1; }
.function-item--orange { border-bottom: 3px solid #FFB74D; }
.function-item--yellow { border-bottom: 3px solid #FFD54F; }
.function-icon { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; background: var(--pt-primary-light); }
.function-item--orange .function-icon { background: #FFF3E0; }
.function-item--yellow .function-icon { background: #FFFDE7; }
.function-name { font-size: 12px; font-weight: 600; color: var(--pt-text); }

/* ---- 消息列表 ---- */
.msg-list { display: flex; flex-direction: column; gap: 12px; }

.message-row { display: flex; align-items: flex-start; gap: 8px; max-width: 90%; animation: msgSlideIn 0.3s ease-out; }
@keyframes msgSlideIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.message-row--assistant { align-self: flex-start; }
.message-row--user { align-self: flex-end; flex-direction: row-reverse; }

.msg-avatar--assistant { flex-shrink: 0; background: linear-gradient(135deg, #fff 0%, #fce4ec 100%); border: 1.5px solid rgba(255, 255, 255, 0.6); }
.avatar-emoji-sm { font-size: 16px; line-height: 1; }
.user-avatar-spacer { width: 34px; flex-shrink: 0; }

.message-body { display: flex; flex-direction: column; gap: 3px; max-width: 100%; }
.message-row--user .message-body { align-items: flex-end; }

/* ---- 气泡 ---- */
.message-bubble { padding: 9px 14px; border-radius: 16px; font-size: 14px; line-height: 1.55; word-break: break-word; white-space: pre-wrap; position: relative; }
.message-bubble--assistant { background: #fce4ec; color: var(--pt-text); border-bottom-left-radius: 6px; box-shadow: 0 1px 4px rgba(244, 143, 177, 0.08); }
.message-bubble--user { background: #fff; color: var(--pt-text); border: 1px solid rgba(244, 143, 177, 0.2); border-bottom-right-radius: 6px; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04); }
.message-bubble--urgent.message-bubble--assistant, .message-bubble--urgent.message-bubble--user { background: linear-gradient(135deg, #ffebee, #ffcdd2); border: 1px solid #ef9a9a; box-shadow: 0 2px 12px rgba(229, 57, 53, 0.18); animation: urgentPulse 1.5s ease-in-out 3; }
@keyframes urgentPulse { 0%, 100% { box-shadow: 0 2px 12px rgba(229, 57, 53, 0.18); } 50% { box-shadow: 0 2px 20px rgba(229, 57, 53, 0.35); } }

.message-bubble--loading { display: flex; align-items: center; gap: 5px; padding: 12px 18px; min-width: 50px; }
.loading-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--pt-primary); animation: dotBounce 1.4s infinite ease-in-out both; }
.loading-dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dot:nth-child(2) { animation-delay: -0.16s; }
.loading-dot:nth-child(3) { animation-delay: 0s; }
@keyframes dotBounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.35; } 40% { transform: scale(1); opacity: 1; } }

/* 思考状态指示器 */
.message-bubble--thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: linear-gradient(135deg, #fce4ec, #fff);
  border: 1px solid #f8bbd0;
  animation: thinking-pulse 2s ease-in-out infinite;
}
.thinking-text {
  font-size: 13px;
  color: #e91e63;
  font-weight: 500;
}
@keyframes thinking-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.bubble-text { font-size: 14px; line-height: 1.55; }

/* ---- Markdown 样式 ---- */
.bubble-markdown :deep(p) { margin: 0 0 6px; }
.bubble-markdown :deep(p:last-child) { margin-bottom: 0; }
.bubble-markdown :deep(ul), .bubble-markdown :deep(ol) { margin: 4px 0; padding-left: 18px; }
.bubble-markdown :deep(li) { margin: 2px 0; }
.bubble-markdown :deep(code) { background: rgba(0, 0, 0, 0.06); padding: 1px 5px; border-radius: 4px; font-size: 13px; font-family: 'Menlo', 'Consolas', monospace; }
.bubble-markdown :deep(pre) { background: #2d2d2d; color: #f8f8f2; padding: 10px 12px; border-radius: 8px; overflow-x: auto; margin: 6px 0; font-size: 12.5px; line-height: 1.5; }
.bubble-markdown :deep(pre code) { background: none; padding: 0; color: inherit; }
.bubble-markdown :deep(strong) { font-weight: 700; color: var(--pt-primary-dark); }
.bubble-markdown :deep(a) { color: var(--pt-primary-dark); text-decoration: underline; }
.bubble-markdown :deep(blockquote) { border-left: 3px solid var(--pt-primary); margin: 6px 0; padding: 4px 10px; background: rgba(244, 143, 177, 0.06); border-radius: 0 6px 6px 0; }
.bubble-markdown :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 13px; width: 100%; }
.bubble-markdown :deep(th), .bubble-markdown :deep(td) { border: 1px solid var(--pt-border); padding: 5px 8px; text-align: left; }
.bubble-markdown :deep(th) { background: var(--pt-primary-light); font-weight: 600; }

/* ---- 打字光标 ---- */
.typing-cursor { display: inline-block; width: 2px; height: 1em; background: var(--pt-primary-dark); margin-left: 2px; vertical-align: text-bottom; animation: cursorBlink 0.8s step-end infinite; }
@keyframes cursorBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* ---- 时间戳 ---- */
.message-time { font-size: 10px; color: var(--pt-text-muted); padding: 0 4px; display: flex; align-items: center; gap: 5px; }
.message-time--user { flex-direction: row-reverse; }
.urgent-tag { font-size: 10px; height: 16px; line-height: 16px; padding: 0 5px; }

/* ---- 消息操作栏 ---- */
.message-actions { display: flex; gap: 2px; margin-top: 2px; opacity: 0; transition: opacity 0.2s ease; }
.message-row:hover .message-actions { opacity: 1; }
.message-actions--user { justify-content: flex-end; }
.msg-action-btn { display: flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 6px; border: none; background: transparent; color: var(--pt-text-muted); cursor: pointer; transition: all 0.15s ease; -webkit-tap-highlight-color: transparent; font-size: 13px; }
.msg-action-btn:hover { background: var(--pt-primary-light); color: var(--pt-primary-dark); }
.msg-action-btn:active { transform: scale(0.9); }
.msg-action-btn--active { background: var(--pt-primary-light); color: var(--pt-primary); }

/* 移动端常驻显示操作栏 */
@media (hover: none) {
  .message-actions { opacity: 0.6; }
}

.scroll-anchor { height: 1px; }

/* ==================== 3. 兴趣推荐 ==================== */
.interests-area { padding: 6px 0 4px; }
.interests-title { font-size: 13px; font-weight: 600; color: var(--pt-text); margin: 0 0 8px; }
.interests-list { display: flex; flex-direction: column; gap: 6px; }
.interest-item { display: flex; align-items: center; gap: 6px; padding: 9px 12px; border-radius: 10px; background: var(--pt-card-bg-solid); border: 1px solid rgba(244, 143, 177, 0.1); cursor: pointer; transition: all 0.2s ease; -webkit-tap-highlight-color: transparent; }
.interest-item:active { transform: scale(0.98); background: var(--pt-primary-light); }
.interest-hashtag { font-size: 15px; font-weight: 700; color: var(--pt-primary); flex-shrink: 0; }
.interest-text { font-size: 13px; color: var(--pt-text-secondary); }
.suggest-fade-enter-active, .suggest-fade-leave-active { transition: all 0.3s ease; }
.suggest-fade-enter-from, .suggest-fade-leave-to { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; }

/* ==================== 4. 底部输入区 ==================== */
.input-area { grid-row: 4; grid-column: 1; padding: 4px 12px 8px; padding-bottom: max(8px, env(safe-area-inset-bottom, 8px)); background: rgba(255, 255, 255, 0.92); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-top: 1px solid rgba(244, 143, 177, 0.12); position: relative; z-index: 10; }

.input-row { display: flex; align-items: flex-end; gap: 8px; max-width: 720px; margin: 0 auto; }

.toolbar-btn { display: flex; align-items: center; justify-content: center; min-width: 40px; min-height: 40px; border-radius: 50%; border: none; background: var(--pt-primary-light); color: var(--pt-primary-dark); cursor: pointer; transition: all 0.2s ease; flex-shrink: 0; -webkit-tap-highlight-color: transparent; }
.toolbar-btn:active { transform: scale(0.92); }
.toolbar-btn--recording { background: #ffebee; color: #e53935; animation: recPulse 1.5s ease-in-out infinite; }
.toolbar-btn--stop { background: #e53935; color: #fff; }
.toolbar-btn--stop:hover { background: #c62828; }
@keyframes recPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(229, 57, 53, 0.3); } 50% { box-shadow: 0 0 0 8px rgba(229, 57, 53, 0); } }

.chat-input { flex: 1; }
.chat-input :deep(.el-textarea__inner) { border-radius: 20px; border: 1.5px solid rgba(244, 143, 177, 0.2); padding: 9px 16px; font-size: 14px; line-height: 1.45; transition: all 0.25s ease; background: #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03); font-family: inherit; }
.chat-input :deep(.el-textarea__inner:focus) { border-color: var(--pt-primary); box-shadow: 0 0 0 3px rgba(244, 143, 177, 0.12); }
.chat-input :deep(.el-textarea__inner::placeholder) { color: var(--pt-text-muted); }

.send-btn { flex-shrink: 0; width: 42px; height: 42px; border-radius: 50%; background: linear-gradient(135deg, var(--pt-primary), var(--pt-primary-dark)); border: none; color: #fff; box-shadow: 0 4px 14px rgba(244, 143, 177, 0.35); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s ease; -webkit-tap-highlight-color: transparent; }
.send-btn:active:not(:disabled) { transform: scale(0.92); }
.send-btn:disabled { background: #e0e0e0; box-shadow: none; color: #bdbdbd; cursor: default; }

.input-hint { text-align: center; font-size: 10px; color: var(--pt-text-muted); opacity: 0.5; margin-top: 4px; padding-bottom: env(safe-area-inset-bottom, 0); }

/* ---- 录音 ---- */
.recording-bar { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: #fff0f0; border-radius: 10px; max-width: 720px; margin: 0 auto 8px; border: 1px solid rgba(229, 57, 53, 0.15); }
.recording-dot { width: 8px; height: 8px; border-radius: 50%; background: #e53935; animation: dotBlink 0.8s ease-in-out infinite; }
@keyframes dotBlink { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }
.recording-text { flex: 1; font-size: 13px; color: #c62828; }

/* ==================== 动画 ==================== */
.msg-enter-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.msg-leave-active { transition: all 0.15s ease; }
.msg-enter-from { opacity: 0; transform: translateY(10px) scale(0.97); }
.msg-leave-to { opacity: 0; transform: translateX(-16px); }

/* ==================== 滚动条 ==================== */
.messages-container::-webkit-scrollbar { width: 3px; }
.messages-container::-webkit-scrollbar-track { background: transparent; }
.messages-container::-webkit-scrollbar-thumb { background: rgba(244, 143, 177, 0.15); border-radius: 2px; }

/* ==================== 移动端 ==================== */

/* --- 所有移动端通用 --- */
@media (max-width: 430px) {
  /* 导航栏 */
  .chat-navbar { padding: 6px 10px; padding-top: max(6px, env(safe-area-inset-top, 6px)); }
  .navbar-title { font-size: 14px; }
  .navbar-btn { min-width: 36px; min-height: 36px; }
  .navbar-actions { gap: 2px; }

  /* 用户栏 */
  .user-info-bar { padding: 3px 10px; }

  /* 消息区 */
  .messages-container { padding: 6px 8px 4px; }
  .messages-inner { gap: 6px; }
  .msg-list { gap: 6px; }
  .message-body { gap: 2px; }
  .message-bubble { padding: 6px 10px; font-size: 13px; line-height: 1.4; }
  .bubble-text { line-height: 1.4; }

  /* Markdown 移动端间距收紧 */
  .bubble-markdown :deep(p) { margin: 0 0 3px; }
  .bubble-markdown :deep(p:last-child) { margin-bottom: 0; }
  .bubble-markdown :deep(ul), .bubble-markdown :deep(ol) { margin: 2px 0; padding-left: 16px; }
  .bubble-markdown :deep(li) { margin: 1px 0; }
  .message-time { font-size: 9px; padding: 0 2px; }
  .message-actions { margin-top: 1px; }

  /* 欢迎区 - 紧凑 */
  .welcome-section { padding: 10px 8px 2px; text-align: center; }
  .welcome-header { margin-bottom: 4px; }
  .doctor-avatar { width: 40px !important; height: 40px !important; }
  .doctor-emoji { font-size: 20px; }
  .welcome-title { font-size: 15px; margin-bottom: 2px; }
  .welcome-desc { font-size: 12px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

  /* 孕周指南 - 移动端隐藏 */
  .pregnancy-guide { display: none; }

  /* 功能导航 - 横向滚动 */
  .function-nav { gap: 8px; overflow-x: auto; flex-wrap: nowrap; padding-bottom: 4px; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
  .function-nav::-webkit-scrollbar { display: none; }
  .function-item { flex: 0 0 auto; min-width: 80px; padding: 8px 10px; }
  .function-icon { width: 32px; height: 32px; font-size: 16px; }
  .function-name { font-size: 11px; }

  /* 输入区 */
  .send-btn { width: 40px; height: 40px; }
  .toolbar-btn { min-width: 38px; min-height: 38px; }
  .input-area { padding: 3px 10px 6px; }
  .input-hint { display: none; }
}

/* --- 桌面端 --- */
@media (min-width: 431px) {
  .messages-container { padding: 14px 16px 8px; }
  .messages-inner { max-width: 600px; }
}
</style>
