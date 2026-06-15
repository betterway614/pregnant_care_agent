<template>
  <div class="chat-wrapper" :class="{ 'chat-wrapper--ios': isIOS }">
    <!-- ==================== 动态光晕背景 ==================== -->
    <div class="halo-bg">
      <div class="halo-orb halo-orb-1"></div>
      <div class="halo-orb halo-orb-2"></div>
      <div class="halo-orb halo-orb-3"></div>
      <div class="halo-backdrop"></div>
    </div>

    <!-- ==================== 紧急警告横幅 ==================== -->
    <transition name="banner-slide">
      <div v-if="urgentDetected" class="emergency-banner" role="alert">
        <el-icon :size="18"><WarningFilled /></el-icon>
        <span>您描述的内容可能涉及需及时就医的情况，建议尽快联系产检医生或拨打急救电话</span>
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
            <el-icon :size="18" class="followup-banner__icon"><DocumentChecked /></el-icon>
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
      <button class="navbar-btn navbar-btn--back interactive-card" @click="handleBack" aria-label="返回">
        <el-icon :size="20"><ArrowLeft /></el-icon>
      </button>
      <h1 class="navbar-title">孕期温暖陪伴</h1>
      <div class="navbar-actions">
        <button class="navbar-btn interactive-card" @click="openSessionDrawer" aria-label="历史会话" title="历史会话">
          <el-icon :size="20"><Clock /></el-icon>
        </button>
        <button class="navbar-btn interactive-card" @click="handleNewChat" aria-label="新建对话" title="新建对话">
          <el-icon :size="20"><ChatLineRound /></el-icon>
        </button>
        <button class="navbar-btn interactive-card" @click="handleClearMemory" aria-label="清除记录" title="清除记录">
          <el-icon :size="20"><Delete /></el-icon>
        </button>
      </div>
    </nav>

    <!-- ==================== 2. 用户信息栏 ==================== -->
    <div class="user-info-bar">
      <span class="user-name">{{ displayName || '孕妈' }}</span>
      <div class="user-actions">
        <button class="user-action-btn interactive-card" :class="{ active: autoPlayTTS }" @click="toggleAutoPlayTTS" :aria-label="autoPlayTTS ? '关闭自动播报' : '开启自动播报'" :title="autoPlayTTS ? '自动播报已开启' : '自动播报已关闭'">
          <el-icon :size="16"><Headset /></el-icon>
        </button>
        <button class="user-action-btn interactive-card" :class="{ active: isMuted }" @click="toggleMute" :aria-label="isMuted ? '取消静音' : '静音'">
          <el-icon :size="16"><Mute v-if="isMuted" /><Microphone v-else /></el-icon>
        </button>
      </div>
    </div>

    <!-- ==================== 主滚动区域 ==================== -->
    <div ref="messagesRef" class="messages-container" role="log" aria-live="polite">
      <div class="messages-inner">

        <!-- ---- 欢迎信息 ---- -->
        <div v-if="showWelcome" class="welcome-section">
          <div class="welcome-header">
            <div class="ai-avatar-wrapper">
              <div class="ai-halo"></div>
              <AgentAvatar agent="xiaan" :size="72" />
            </div>
          </div>
          <h2 class="welcome-title">您好，我是孕期助手小安</h2>
          <p class="welcome-desc">我在这里为您提供全方位的孕产知识支持，陪伴您度过安心、健康的孕期旅程。</p>
        </div>

        <!-- ---- 轻量化孕周指南 ---- -->
        <div v-if="gestWeek && showWelcome" class="pregnancy-guide">
          <div class="soft-card week-card interactive-card" @click="$router.push('/pregnant/tools')">
            <div class="week-mini-info">
              <span class="week-number">孕{{ gestWeek }}周{{ gestDay || 0 }}天</span>
              <span class="days-remaining">距预产期还有 {{ Math.max(0, (40 - gestWeek) * 7 - (gestDay || 0)) }} 天</span>
            </div>
            <div class="fetus-mini">
              <el-icon :size="18" class="fetus-icon"><Avatar /></el-icon>
              <span class="fetus-size">{{ fetusSize }}</span>
              <el-icon :size="14" color="#94A3B8"><ArrowRight /></el-icon>
            </div>
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
              :size="32"
              class="assistant-avatar"
            />

            <div class="message-body">
              <!-- 思考中 (Agent Zero Interface) -->
              <div
                v-if="msg.loading && msg.thinking"
                class="message-bubble message-bubble--assistant message-bubble--thinking"
              >
                <div class="thinking-indicator">
                  <span class="ripple"></span>
                  <span class="ripple-delay"></span>
                </div>
                <span class="thinking-text">{{ msg.thinkingMessage || '小安正在思考...' }}</span>
              </div>
              
              <!-- 加载中（仅内容为空时显示） -->
              <div
                v-else-if="msg.loading && !msg.content"
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
                  'message-bubble--urgent': msg.role === 'user' && msg.isUrgent,
                }"
              >
                <!-- 用户消息：柔和圆角气泡 -->
                <div v-if="msg.role === 'user'" class="bubble-text">
                  <!-- 音频消息：可播放的音频条 -->
                  <div v-if="msg.messageType === 'audio' && msg.audioUrl" class="audio-bubble"
                    @pointerdown.prevent="onAudioBubblePointerDown(msg)"
                    @pointerup.prevent="onAudioBubblePointerUp"
                    @pointerleave="onAudioBubblePointerUp"
                    @contextmenu.prevent
                  >
                    <button class="audio-bubble__btn" @click.stop="toggleAudioPlay(msg)">
                      <el-icon :size="18">
                        <VideoPause v-if="playingMsgId === msg.id" />
                        <VideoPlay v-else />
                      </el-icon>
                    </button>
                    <div class="audio-bubble__waveform">
                      <span v-for="i in 16" :key="i" class="audio-bubble__bar" :style="{ height: (12 + Math.sin(i * 0.9) * 14 + Math.cos(i * 2.1) * 6) + 'px' }" :class="{ 'audio-bubble__bar--play': playingMsgId === msg.id, 'audio-bubble__bar--played': playingMsgId === msg.id && i <= 8 }" />
                    </div>
                    <span class="audio-bubble__dur">{{ formatDuration(msg.audioDuration || 0) }}</span>
                    <!-- 转录文本按钮 -->
                    <button class="audio-bubble__transcribe-btn" @click.stop="handleAudioTranscribe(msg)" :title="isTranscriptionVisible(msg) ? '隐藏文字' : '转文字'">
                      <el-icon :size="14"><Document /></el-icon>
                    </button>
                  </div>
                  <!-- ASR 转录文本 -->
                  <div v-if="msg.messageType === 'audio' && isTranscriptionVisible(msg)" class="audio-transcription">
                    <span v-if="msg.transcribing" class="audio-transcription__loading">正在识别语音...</span>
                    <span v-else>{{ msg.transcribedText }}</span>
                  </div>
                  <div v-else-if="msg.messageType === 'audio' && msg.transcribing" class="audio-transcription">
                    <span class="audio-transcription__loading">正在识别语音...</span>
                  </div>
                  <!-- 图片消息：预览 -->
                  <div v-else-if="(msg as any).messageType === 'image' && (msg as any).audioUrl" class="image-bubble">
                    <img :src="(msg as any).audioUrl" alt="上传的图片" class="image-bubble__img" @load="" />
                  </div>
                  <template v-else>{{ msg.content }}</template>
                </div>
                <!-- 助手消息：无边框阅读流 Markdown 渲染 -->
                <div
                  v-else
                  class="bubble-text bubble-markdown"
                >
                  <StructuredAnalysisCard
                    v-if="isStructuredAnalysis(msg.content)"
                    :data="parseStructuredAnalysis(msg.content)!"
                    role="pregnant"
                  />
                  <div v-else v-html="renderMarkdown(msg.content)" />
                </div>
                <!-- 流式打字光标 -->
                <span v-if="msg.role === 'assistant' && isStreamingMessage(msg)" class="typing-cursor" />
              </div>

              <!-- 时间戳与操作栏 -->
              <div
                class="message-footer"
                :class="{ 'message-footer--user': msg.role === 'user' }"
              >
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                <el-tag
                  v-if="msg.role === 'user' && msg.isUrgent"
                  size="small"
                  type="warning"
                  class="urgent-tag"
                  effect="plain"
                >
                  建议咨询医护
                </el-tag>
                
                <div
                  v-if="!msg.loading && chatStore.messages.length > 0"
                  class="message-actions"
                >
                  <button v-if="msg.role === 'assistant'" class="msg-action-btn" @click="handleCopyMessage(msg.content)" title="复制">
                    <el-icon :size="14"><CopyDocument /></el-icon>
                  </button>
                  <button v-if="msg.role === 'assistant' && !chatStore.streaming" class="msg-action-btn" @click="handleRetry(msg)" title="重新生成">
                    <el-icon :size="14"><RefreshRight /></el-icon>
                  </button>
                  <button v-if="msg.role === 'assistant' && !chatStore.streaming && !msg.loading" class="msg-action-btn" :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_up' }" @click="handleFeedback(msg, 'thumbs_up')" title="有帮助">
                    <el-icon :size="14"><Check /></el-icon>
                  </button>
                  <button v-if="msg.role === 'assistant' && !chatStore.streaming && !msg.loading" class="msg-action-btn" :class="{ 'msg-action-btn--active': msg.feedback === 'thumbs_down' }" @click="handleFeedback(msg, 'thumbs_down')" title="需改进">
                    <el-icon :size="14"><Close /></el-icon>
                  </button>
                  <button v-if="msg.role === 'user'" class="msg-action-btn" @click="handleEditMessage(msg)" title="编辑">
                    <el-icon :size="14"><Edit /></el-icon>
                  </button>
                  <button v-if="msg.role === 'assistant' && msg.content && !msg.loading" class="msg-action-btn" :class="{ 'msg-action-btn--active': ttsSpeakingId === msg.id }" @click="handleToggleTTS(msg)" title="语音播报">
                    <el-icon :size="14"><Headset /></el-icon>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div ref="scrollAnchorRef" class="scroll-anchor" />
      </div>
    </div>

    <!-- ==================== 3. 底部输入区 (灵动岛) ==================== -->
    <div class="input-container">
      <!-- ---- 兴趣推荐 (Prompt Chips) ---- -->
      <transition name="suggest-fade">
        <div v-if="!chatStore.loading && !isFollowupMode && showWelcome" class="prompt-chips">
          <div
            v-for="item in SUGGESTED_QUESTIONS"
            :key="item"
            class="prompt-chip interactive-card"
            @click="handleSuggestionClick(item)"
            role="button"
          >
            {{ item }}
          </div>
        </div>
      </transition>

      <div class="input-pill-wrapper">
        <!-- 待发送图片预览 -->
        <div v-if="pendingImages.length > 0" class="pending-images-bar">
          <div
            v-for="img in pendingImages"
            :key="img.uid"
            class="pending-image-item"
          >
            <img :src="getPreviewUrl(img)" class="pending-image-thumb" />
            <button class="pending-image-remove" @click="removePendingImage(img.uid)">
              <el-icon :size="12"><Close /></el-icon>
            </button>
          </div>
        </div>

        <!-- 录音浮层（按住录制时显示） -->
        <transition name="record-overlay-fade">
          <div v-if="isRecording" class="record-overlay">
            <!-- 取消区域（上滑至此取消） -->
            <div
              class="cancel-zone"
              :class="{ 'cancel-zone--active': isInCancelZone }"
            >
              <div class="cancel-zone__icon">
                <el-icon :size="24"><DeleteFilled v-if="isInCancelZone" /><Delete v-else /></el-icon>
              </div>
              <span class="cancel-zone__text">{{ isInCancelZone ? '松开取消' : '上滑取消' }}</span>
            </div>
            <!-- 录音中心图标 + 状态条 -->
            <div class="record-center" :class="{ 'record-center--cancel': isInCancelZone }">
              <div class="record-center__ring">
                <div class="record-center__icon">
                  <el-icon :size="36"><Microphone /></el-icon>
                </div>
              </div>
            </div>
            <div class="record-bar" :class="{ 'record-bar--cancel': isInCancelZone }">
              <div class="record-bar__wave">
                <span v-for="i in 7" :key="i" class="record-bar__wave-line" :style="{ animationDelay: i * 0.08 + 's' }" />
              </div>
              <span class="record-bar__time">{{ recordingText }}</span>
              <span class="record-bar__hint">{{ isInCancelZone ? '松手取消' : '松手发送 上滑取消' }}</span>
            </div>
          </div>
        </transition>

        <div class="input-pill">
          <button
            class="toolbar-btn interactive-card"
            :class="{ 'toolbar-btn--recording': isRecording }"
            @pointerdown.prevent="startRecording"
            aria-label="语音输入"
          >
            <el-icon :size="20"><Microphone /></el-icon>
          </button>

          <!-- 图片上传（el-upload，不自动上传，支持多选） -->
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :show-file-list="false"
            accept="image/*"
            multiple
            :on-change="handleImageChanged"
          >
            <button
              class="toolbar-btn interactive-card"
              aria-label="上传图片"
            >
              <el-icon :size="20"><Picture /></el-icon>
            </button>
          </el-upload>

          <el-input
            ref="inputRef"
            v-model="inputText"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="随时向我提问..."
            resize="none"
            class="chat-input"
            @keydown.enter.exact.prevent="handleSend"
            :disabled="chatStore.streaming"
          />

          <!-- 停止生成按钮 -->
          <button
            v-if="chatStore.streaming"
            class="send-btn stop-btn interactive-card"
            @click="handleStopGeneration"
            aria-label="停止生成"
          >
            <div class="stop-icon-box"></div>
          </button>

          <button
            v-else
            class="send-btn interactive-card"
            :disabled="(!inputText.trim() && pendingImages.length === 0) || chatStore.loading"
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

    <!-- ==================== 历史会话抽屉 ==================== -->
    <el-drawer
      v-model="sessionDrawerVisible"
      title="历史会话"
      direction="rtl"
      size="85%"
      :style="{ maxWidth: '400px' }"
    >
      <div class="session-list">
        <div v-if="sessionLoading" class="session-loading">
          <span class="loading-dot" />
          <span class="loading-dot" />
          <span class="loading-dot" />
        </div>
        <div v-else-if="sessions.length === 0" class="session-empty">
          <el-icon :size="48" color="#CBD5E1"><ChatDotRound /></el-icon>
          <p>暂无历史会话</p>
        </div>
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item interactive-card"
          :class="{ 'session-item--active': s.session_id === chatStore.sessionId }"
          @click="handleLoadSession(s.session_id)"
        >
          <div class="session-item__header">
            <span class="session-item__date">{{ formatSessionDate(s.last_message_at) }}</span>
            <span class="session-item__count">{{ s.message_count }} 条消息</span>
          </div>
          <p class="session-item__preview">{{ s.preview || '新对话' }}</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Delete, DeleteFilled, Promotion, ArrowLeft, WarningFilled, Close, Microphone,
  Mute, RefreshRight, ChatDotRound, ChatLineRound, CopyDocument, Edit, VideoPlay, VideoPause, ArrowRight, DocumentChecked, Avatar, Check, Picture, Camera, Headset, Document, Clock
} from '@element-plus/icons-vue'
import { chatApi, postChatStream, feedbackApi } from '@/api/endpoints'
import type { ChatRequest } from '@/types'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { useChatStore } from '@/stores/chat'
import type { ChatMessage } from '@/stores/chat'
import { renderMarkdown, isStructuredAnalysis, parseStructuredAnalysis } from '@/utils/markdown'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import { useScroll } from '@vueuse/core'
import { useTTS } from '@/composables/useTTS'
import { StructuredAnalysisCard } from '@/components/agent-fab'

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
  '孕晚期需要注意什么？',
  '推荐一份健康食谱',
  '腰酸背痛怎么办？',
  '如何数胎动？',
  '临产征兆有哪些？'
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

// 历史会话
const sessionDrawerVisible = ref(false)
const sessionLoading = ref(false)
const sessions = ref<Array<{ session_id: string; message_count: number; started_at: string; last_message_at: string; preview: string }>>([])

// 音频录制
const isRecording = ref(false)
const isInCancelZone = ref(false)
const recordingText = ref('0:00')
let mediaRecorder: any = null
let audioChunks: Blob[] = []
let recordingTimer: ReturnType<typeof setInterval> | null = null
let recordingSeconds = 0

// 音频播放
const playingMsgId = ref<string | null>(null)
let audioEl: HTMLAudioElement | null = null

// TTS 播报（使用后端 CosyVoice 服务）
const { isSpeaking, speak, stop: stopTTS, cleanForTTS } = useTTS({ mode: 'backend', role: 'pregnant' })
const ttsSpeakingId = ref<string | null>(null)
const autoPlayTTS = ref(true) // 自动播报开关

// 图片上传（基于 el-upload）
const uploadRef = ref<UploadInstance | null>(null)
const pendingImages = ref<UploadFile[]>([])
const MAX_IMAGE_COUNT = 9

// 编辑
const editDialogVisible = ref(false)
const editText = ref('')
let editingMsgId = ''

// DOM
const messagesRef = ref<HTMLElement | null>(null)
const scrollAnchorRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLElement | null>(null)

const isIOS = ref(/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1))
let isAtBottom = true

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

const fetusSize = computed(() => fetusData.value.size)

/* ==================== 工具函数 ==================== */
function formatTime(ts: string): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function checkUrgent(content: string): boolean {
  return EMERGENCY_KEYWORDS.some((kw) => content.includes(kw))
}

function isStreamingMessage(msg: ChatMessage): boolean {
  if (!chatStore.streaming) return false
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

function toggleMute() {
  isMuted.value = !isMuted.value
  ElMessage.info(isMuted.value ? '已静音' : '已取消静音')
}

function toggleAutoPlayTTS() {
  autoPlayTTS.value = !autoPlayTTS.value
  ElMessage.info(autoPlayTTS.value ? '自动播报已开启' : '自动播报已关闭')
  if (!autoPlayTTS.value) {
    stopTTS()
    ttsSpeakingId.value = null
  }
}

/* ==================== 新建对话 ==================== */
function handleNewChat() {
  if (chatStore.messages.length === 0 && !chatStore.sessionId) return
  chatStore.newConversation()
  urgentDetected.value = false
  followupRecordId.value = null
  isFollowupMode.value = false
  followupProgress.value = null
  ElMessage.success('已开始新对话')
}

/* ==================== 历史会话 ==================== */
async function openSessionDrawer() {
  sessionDrawerVisible.value = true
  sessionLoading.value = true
  try {
    const res = await chatApi.listSessions(pregnantId.value)
    sessions.value = res.data.sessions || []
  } catch {
    sessions.value = []
  } finally {
    sessionLoading.value = false
  }
}

async function handleLoadSession(targetSessionId: string) {
  if (targetSessionId === chatStore.sessionId) {
    sessionDrawerVisible.value = false
    return
  }
  await chatStore.loadSession(pregnantId.value, targetSessionId)
  sessionDrawerVisible.value = false
  urgentDetected.value = false
  followupRecordId.value = null
  isFollowupMode.value = false
  followupProgress.value = null
  nextTick(() => scrollToBottom(false))
}

function formatSessionDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const isYesterday = d.toDateString() === yesterday.toDateString()

  const time = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  if (isToday) return `今天 ${time}`
  if (isYesterday) return `昨天 ${time}`
  return `${d.getMonth() + 1}月${d.getDate()}日 ${time}`
}

/* ==================== 消息操作 ==================== */
async function handleCopyMessage(content: string) {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('已复制')
  } catch {
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
  const newRating = msg.feedback === rating ? null : rating
  chatStore.updateMessage(msg.id, { feedback: newRating })

  if (newRating) {
    try {
      const pregnantId = localStorage.getItem('currentPregnantId') || ''
      await feedbackApi.submit({
        pregnant_id: pregnantId,
        message_id: msg.id,
        rating: newRating,
        feedback_role: 'pregnant',
        session_id: chatStore.sessionId || undefined,
      })
    } catch {}
  }
}

function handleRetry(msg: ChatMessage) {
  const prevUser = chatStore.getPreviousUserMessage(msg.id)
  if (!prevUser) return
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

  chatStore.updateMessage(editingMsgId, { content: text })
  chatStore.deleteMessageFrom(editingMsgId)

  inputText.value = text
  nextTick(() => handleSend())
}

function handleToggleTTS(msg: ChatMessage) {
  if (ttsSpeakingId.value === msg.id) {
    stopTTS()
    ttsSpeakingId.value = null
  } else {
    ttsSpeakingId.value = msg.id
    speak(cleanForTTS(msg.content))
    const checkEnd = setInterval(() => {
      if (!isSpeaking.value) {
        ttsSpeakingId.value = null
        clearInterval(checkEnd)
      }
    }, 500)
  }
}

/* ==================== 发送消息 ==================== */
async function handleSend() {
  const text = inputText.value.trim()
  const images = pendingImages.value

  // 需要有文字或图片才能发送
  if ((!text && images.length === 0) || chatStore.loading) return

  // 如果有待发送图片，走图片+文字组合发送
  if (images.length > 0) {
    await sendImageWithText(text, images)
    return
  }

  inputText.value = ''
  urgentDetected.value = false

  const userMentionedEmergency = checkUrgent(text)
  if (userMentionedEmergency) urgentDetected.value = true

  chatStore.addMessage('user', text, { isUrgent: userMentionedEmergency })
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
        timestamp: new Date().toISOString(),
      })
      // 自动播报助手消息
      if (autoPlayTTS.value && data.content && !isMuted.value) {
        ttsSpeakingId.value = loadingMsg.id
        speak(cleanForTTS(data.content))
        const checkEnd = setInterval(() => {
          if (!isSpeaking.value) {
            ttsSpeakingId.value = null
            clearInterval(checkEnd)
          }
        }, 500)
      }
    } catch {
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        content: '抱歉，我暂时无法回复。请稍后再试，或联系您的孕期管理师。',
      })
    }
  } else {
    // 初始化消息为思考状态，等待 SSE 流返回
    chatStore.updateMessage(loadingMsg.id, {
      loading: true,
      thinking: true,
      thinkingMessage: '小安正在思考...',
      content: '',
    })
    chatStore.streaming = true

    const controller = new AbortController()
    chatStore.setAbortController(controller)

    try {
      await postChatStream(req, {
        onThinking(message: string) {
          chatStore.updateMessage(loadingMsg.id, {
            thinking: true,
            thinkingMessage: message,
            currentStep: message !== '小安正在思考...' ? message : undefined,
          })
        },
        onChunk(chunk: string) {
          const msg = chatStore.messages.find((m) => m.id === loadingMsg.id)
          if (msg) {
            msg.content += chunk
            msg.thinking = false
            msg.currentStep = undefined
            chatStore.persist?.()
          }
          if (isAtBottom) scrollToBottom()
        },
        onDone(metadata: any) {
          chatStore.sessionId = metadata.session_id
          chatStore.updateMessage(loadingMsg.id, {
            loading: false,
            thinking: false,
            currentStep: undefined,
            toolSteps: metadata?.tool_steps || [],
            timestamp: new Date().toISOString(),
          })
          // 自动播报助手消息
          if (autoPlayTTS.value && loadingMsg.content && !isMuted.value) {
            ttsSpeakingId.value = loadingMsg.id
            speak(cleanForTTS(loadingMsg.content))
            const checkEnd = setInterval(() => {
              if (!isSpeaking.value) {
                ttsSpeakingId.value = null
                clearInterval(checkEnd)
              }
            }, 500)
          }
        },
        onError(err: Error) {
          console.error('SSE error:', err)
          if (!loadingMsg.content) {
            chatStore.updateMessage(loadingMsg.id, {
              loading: false,
              thinking: false,
              content: '抱歉，我暂时无法回复。请稍后再试。',
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
            loading: false,
            thinking: false,
            content: data.content || '抱歉，我暂时无法回复，请稍后再试。',
          })
        } catch {
          chatStore.updateMessage(loadingMsg.id, {
            loading: false,
            thinking: false,
            content: '抱歉，我暂时无法回复。请稍后再试。',
          })
        }
      }
    } finally {
      chatStore.streaming = false
      chatStore.setAbortController(null)
    }

    if (!loadingMsg.content) {
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        thinking: false,
        content: '抱歉，我暂时无法回复。请稍后再试。',
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

/* ==================== 音频录制与发送（按住录制 / 松开发送 / 上滑取消） ==================== */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const result = reader.result as string
      const base64 = result.split(',')[1] || result
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m + ':' + s.toString().padStart(2, '0')
}

// ---- 按住录制 ----
let shouldSendAudio = false  // 标记是否需要发送音频（true=正常结束，false=取消）

/** 检查麦克风权限 */
async function checkMicPermission(): Promise<boolean> {
  // 1. 安全上下文检查
  if (!navigator.mediaDevices?.getUserMedia) {
    ElMessage.warning('当前环境不支持录音，请使用 HTTPS 访问')
    return false
  }

  // 2. 使用 Permissions API 预检查（非所有浏览器支持）
  try {
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName })
    if (status.state === 'denied') {
      ElMessage.warning('麦克风权限已被拒绝，请在浏览器设置中允许麦克风访问')
      return false
    }
  } catch { /* Permissions API 不支持，跳过预检查 */ }

  return true
}

async function startRecording(e: PointerEvent) {
  // 权限预检
  if (!(await checkMicPermission())) return

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 44100,
        channelCount: 1,
      },
    })
    // 优先 ogg/opus（兼容性更好），降级 webm/opus，最后 mp4
    const mimeType = MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
      ? 'audio/ogg;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

    mediaRecorder = new MediaRecorder(stream, { mimeType })
    audioChunks = []
    shouldSendAudio = false
    isRecording.value = true
    isInCancelZone.value = false
    recordingSeconds = 0
    recordingText.value = '0:00'

    mediaRecorder.ondataavailable = (e: BlobEvent) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    // 在 start 之前就设置 onstop，确保不会丢失事件
    mediaRecorder.onstop = async () => {
      // 停止所有音频轨道
      mediaRecorder.stream.getTracks().forEach((t: MediaStreamTrack) => t.stop())
      clearInterval(recordingTimer!)

      // 取消、无数据或录制时间过短：仅重置状态
      if (!shouldSendAudio || isInCancelZone.value || audioChunks.length === 0 || recordingSeconds < 1) {
        audioChunks = []
        isRecording.value = false
        isInCancelZone.value = false
        return
      }

      const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' })
      const mt = mediaRecorder.mimeType || ''
      const audioFormat = mt.includes('ogg') ? 'ogg' : mt.includes('webm') ? 'webm' : mt.includes('mp4') ? 'mp4' : 'wav'

      // 检查音频数据是否有效
      if (audioBlob.size === 0) {
        console.warn('音频数据为空，跳过发送')
        audioChunks = []
        isRecording.value = false
        isInCancelZone.value = false
        return
      }

      recordingText.value = '处理中...'

      try {
        const base64 = await blobToBase64(audioBlob)
        if (!base64) {
          throw new Error('音频编码失败')
        }
        isRecording.value = false
        isInCancelZone.value = false
        await sendAudioMessage(base64, audioFormat, audioBlob, recordingSeconds)
      } catch (err) {
        console.error('音频处理失败:', err)
        ElMessage.error('音频处理失败，请重试')
        isRecording.value = false
        isInCancelZone.value = false
      }
    }

    // 使用 timeslice 每秒触发 ondataavailable，确保数据被逐步收集
    mediaRecorder.start(1000)
    recordingTimer = setInterval(() => {
      recordingSeconds++
      recordingText.value = formatDuration(recordingSeconds)
    }, 1000)

    document.addEventListener('pointermove', onPointerMove)
    document.addEventListener('pointerup', onPointerUp)
    document.addEventListener('pointercancel', onPointerUp)
  } catch (err: any) {
    console.error('麦克风访问失败:', err)
    if (err?.name === 'NotAllowedError' || err?.name === 'PermissionDeniedError') {
      ElMessage.warning('请允许麦克风权限后再试。可点击浏览器地址栏🔒图标设置权限')
    } else if (err?.name === 'NotFoundError') {
      ElMessage.warning('未检测到麦克风设备')
    } else if (err?.name === 'NotReadableError') {
      ElMessage.warning('麦克风被其他应用占用，请关闭后重试')
    } else {
      ElMessage.warning('无法访问麦克风，请检查设备和浏览器设置')
    }
    isRecording.value = false
  }
}

function onPointerMove(e: PointerEvent) {
  if (!isRecording.value) return
  isInCancelZone.value = e.clientY < window.innerHeight * 0.3
}

async function onPointerUp(e: PointerEvent) {
  if (!isRecording.value) return
  document.removeEventListener('pointermove', onPointerMove)
  document.removeEventListener('pointerup', onPointerUp)
  document.removeEventListener('pointercancel', onPointerUp)

  if (mediaRecorder?.state !== 'recording') {
    isRecording.value = false
    isInCancelZone.value = false
    return
  }

  // 标记是否需要发送音频（非取消区域时才发送）
  shouldSendAudio = !isInCancelZone.value
  mediaRecorder.stop()
}

/** 发送音频消息到后端 */
async function sendAudioMessage(base64: string, audioFormat: string, audioBlob: Blob, duration: number) {
  const audioUrl = URL.createObjectURL(audioBlob)

  chatStore.addMessage('user', '', {
    isUrgent: false,
    messageType: 'audio',
    audioUrl,
    audioDuration: duration,
  })

  chatStore.loading = true
  const loadingMsg = chatStore.addMessage('assistant', '', { loading: true })
  scrollToBottom()

  const req: ChatRequest = {
    pregnant_id: pregnantId.value,
    message: '请听取以下语音并给出回复',
    session_id: chatStore.sessionId || undefined,
    message_type: 'AUDIO',
    audio_data: base64,
    audio_format: audioFormat,
    ...(followupRecordId.value ? { record_id: followupRecordId.value } : {}),
  }

  chatStore.updateMessage(loadingMsg.id, {
    loading: true,
    thinking: true,
    thinkingMessage: '小安正在听取语音...',
    content: '',
  })
  chatStore.streaming = true

  const controller = new AbortController()
  chatStore.setAbortController(controller)

  try {
    await postChatStream(req, {
      onThinking(message: string) {
        chatStore.updateMessage(loadingMsg.id, {
          thinking: true,
          thinkingMessage: message,
          currentStep: message !== '小安正在思考...' ? message : undefined,
        })
      },
      onChunk(chunk: string) {
        const msg = chatStore.messages.find((m) => m.id === loadingMsg.id)
        if (msg) {
          msg.content += chunk
          msg.thinking = false
          msg.currentStep = undefined
          chatStore.persist?.()
        }
        if (isAtBottom) scrollToBottom()
      },
      onDone(metadata: any) {
        chatStore.sessionId = metadata.session_id
        chatStore.updateMessage(loadingMsg.id, {
          loading: false,
          thinking: false,
          timestamp: new Date().toISOString(),
          toolSteps: metadata.tool_steps || [],
          currentStep: undefined,
        })
        // 保存 ASR 转录文本到用户语音消息
        if (metadata.transcribed_text) {
          const userAudioMsg = chatStore.messages.find(
            (m) => m.role === 'user' && m.messageType === 'audio' && !m.transcribedText
          )
          if (userAudioMsg) {
            chatStore.updateMessage(userAudioMsg.id, { transcribedText: metadata.transcribed_text })
          }
        }
        // 自动播报助手消息
        if (autoPlayTTS.value && loadingMsg.content && !isMuted.value) {
          ttsSpeakingId.value = loadingMsg.id
          speak(cleanForTTS(loadingMsg.content))
          const checkEnd = setInterval(() => {
            if (!isSpeaking.value) {
              ttsSpeakingId.value = null
              clearInterval(checkEnd)
            }
          }, 500)
        }
      },
      onError(err: Error) {
        console.error('Audio SSE error:', err)
        if (!loadingMsg.content) {
          chatStore.updateMessage(loadingMsg.id, {
            content: '抱歉，语音处理失败，请稍后重试或使用文字输入。',
          })
        }
      },
    }, controller.signal)
  } catch {
    if (!loadingMsg.content) {
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        thinking: false,
        content: '抱歉，语音处理失败，请稍后重试或使用文字输入。',
      })
    }
  } finally {
    chatStore.streaming = false
    chatStore.setAbortController(null)
  }

  chatStore.loading = false
  scrollToBottom()
}

// ---- 图片上传（基于 el-upload）----
function getPreviewUrl(img: UploadFile): string {
  if (img.url) return img.url
  if (img.raw) return URL.createObjectURL(img.raw)
  return ''
}

/** el-upload on-change 回调：文件选择后自动加入暂存区 */
function handleImageChanged(uploadFile: UploadFile) {
  if (pendingImages.value.length >= MAX_IMAGE_COUNT) {
    ElMessage.warning(`最多选择 ${MAX_IMAGE_COUNT} 张图片`)
    return
  }
  if (uploadFile.raw && uploadFile.raw.size > 10 * 1024 * 1024) {
    ElMessage.warning(`"${uploadFile.name}" 超过 10MB，已跳过`)
    return
  }
  pendingImages.value.push(uploadFile)
}

function removePendingImage(uid: number | string) {
  const idx = pendingImages.value.findIndex((f) => f.uid === uid)
  if (idx !== -1) pendingImages.value.splice(idx, 1)
}

/** 将 File 对象转为 base64（不含 data: 前缀） */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const result = reader.result as string
      resolve(result.split(',')[1] || result)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/** 发送图片+文字组合消息 */
async function sendImageWithText(text: string, images: UploadFile[]) {
  const imgCount = images.length

  // 1. 先在 UI 中添加用户消息（图片预览 + 文字）
  for (const img of images) {
    const previewUrl = img.url || URL.createObjectURL(img.raw!)
    chatStore.addMessage('user', '', {
      isUrgent: false,
      messageType: 'image' as any,
      audioUrl: previewUrl,
    })
  }
  if (text) {
    chatStore.addMessage('user', text, { isUrgent: false })
  }

  // 2. 清空输入区
  inputText.value = ''
  pendingImages.value = []
  urgentDetected.value = false

  // 3. 构建请求（将 File 转 base64）
  chatStore.loading = true
  const loadingMsg = chatStore.addMessage('assistant', '', { loading: true })
  scrollToBottom()

  const imageItems = await Promise.all(
    images.map(async (img) => {
      const raw = img.raw!
      const base64 = await fileToBase64(raw)
      const ext = raw.name.split('.').pop()?.toLowerCase() || 'jpeg'
      return { data: base64, format: ext === 'jpg' ? 'jpeg' : ext }
    }),
  )

  const defaultMsg = imgCount > 1 ? `请分析这${imgCount}张图片并给出回复` : '请分析这张图片并给出回复'
  const req: ChatRequest = {
    pregnant_id: pregnantId.value,
    message: text || defaultMsg,
    session_id: chatStore.sessionId || undefined,
    message_type: 'IMAGE',
    images: imageItems,
    ...(followupRecordId.value ? { record_id: followupRecordId.value } : {}),
  }

  // 4. 发送 SSE 流式请求
  chatStore.updateMessage(loadingMsg.id, {
    loading: true,
    thinking: true,
    thinkingMessage: '小安正在分析图片...',
    content: '',
  })
  chatStore.streaming = true

  const controller = new AbortController()
  chatStore.setAbortController(controller)

  try {
    await postChatStream(req, {
      onThinking(message: string) {
        chatStore.updateMessage(loadingMsg.id, {
          thinking: true,
          thinkingMessage: message,
          currentStep: message !== '小安正在思考...' ? message : undefined,
        })
      },
      onChunk(chunk: string) {
        const msg = chatStore.messages.find((m) => m.id === loadingMsg.id)
        if (msg) {
          msg.content += chunk
          msg.thinking = false
          msg.currentStep = undefined
          chatStore.persist?.()
        }
        if (isAtBottom) scrollToBottom()
      },
      onDone(metadata: any) {
        chatStore.sessionId = metadata.session_id
        chatStore.updateMessage(loadingMsg.id, {
          loading: false,
          thinking: false,
          timestamp: new Date().toISOString(),
          toolSteps: metadata.tool_steps || [],
          currentStep: undefined,
        })
        if (autoPlayTTS.value && loadingMsg.content && !isMuted.value) {
          ttsSpeakingId.value = loadingMsg.id
          speak(cleanForTTS(loadingMsg.content))
          const checkEnd = setInterval(() => {
            if (!isSpeaking.value) {
              ttsSpeakingId.value = null
              clearInterval(checkEnd)
            }
          }, 500)
        }
      },
      onError(err: Error) {
        console.error('Image SSE error:', err)
        if (!loadingMsg.content) {
          chatStore.updateMessage(loadingMsg.id, {
            content: '抱歉，图片处理失败，请稍后重试。',
          })
        }
      },
    }, controller.signal)
  } catch {
    if (!loadingMsg.content) {
      chatStore.updateMessage(loadingMsg.id, {
        loading: false,
        thinking: false,
        content: '抱歉，图片处理失败，请稍后重试。',
      })
    }
  } finally {
    chatStore.streaming = false
    chatStore.setAbortController(null)
  }

  chatStore.loading = false
  scrollToBottom()
}

// ---- 音频播放 ----
function toggleAudioPlay(msg: ChatMessage) {
  if (playingMsgId.value === msg.id) {
    audioEl?.pause()
    audioEl = null
    playingMsgId.value = null
    return
  }
  audioEl?.pause()
  audioEl = new Audio(msg.audioUrl)
  audioEl.onended = () => { playingMsgId.value = null; audioEl = null }
  audioEl.onerror = () => { playingMsgId.value = null; audioEl = null }
  audioEl.play()
  playingMsgId.value = msg.id
}

// ---- 语音长按转文字 ----
let longPressTimer: ReturnType<typeof setTimeout> | null = null
const hiddenTranscriptions = ref<Set<string>>(new Set())

function onAudioBubblePointerDown(msg: ChatMessage) {
  longPressTimer = setTimeout(() => {
    longPressTimer = null
    handleAudioTranscribe(msg)
  }, 600)
}

function onAudioBubblePointerUp() {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
  }
}

function isTranscriptionVisible(msg: ChatMessage): boolean {
  return !!msg.transcribedText && !hiddenTranscriptions.value.has(msg.id)
}

function toggleTranscriptionVisibility(msg: ChatMessage) {
  const set = hiddenTranscriptions.value
  if (set.has(msg.id)) {
    set.delete(msg.id)
  } else {
    set.add(msg.id)
  }
}

async function handleAudioTranscribe(msg: ChatMessage) {
  // 已有转录文本，切换显示/隐藏
  if (msg.transcribedText) {
    toggleTranscriptionVisibility(msg)
    return
  }

  // 需要从音频 blob 获取 base64
  if (!msg.audioUrl) return

  chatStore.updateMessage(msg.id, { transcribing: true })

  try {
    const resp = await fetch(msg.audioUrl)
    const blob = await resp.blob()
    const reader = new FileReader()
    reader.onloadend = async () => {
      const dataUrl = reader.result as string
      const base64 = dataUrl.split(',')[1]
      // 从 blob URL 推断格式
      const format = msg.audioUrl?.includes('ogg') ? 'ogg' : msg.audioUrl?.includes('webm') ? 'webm' : 'wav'

      try {
        const res = await chatApi.asr({ audio_data: base64, audio_format: format })
        const text = res.data.text || '（语音识别为空）'
        chatStore.updateMessage(msg.id, { transcribedText: text, transcribing: false })
      } catch (err) {
        console.error('ASR failed:', err)
        chatStore.updateMessage(msg.id, { transcribedText: '（语音识别失败）', transcribing: false })
      }
    }
    reader.readAsDataURL(blob)
  } catch (err) {
    console.error('Audio blob read failed:', err)
    chatStore.updateMessage(msg.id, { transcribing: false })
  }
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

/* ==================== 移动端键盘适配 ==================== */
function setupMobileKeyboard() {
  const vv = window.visualViewport
  if (!vv) return

  const wrapper = document.querySelector('.chat-wrapper') as HTMLElement
  if (!wrapper) return

  function onViewportResize() {
    // 计算键盘弹出时的高度差
    const offset = window.innerHeight - vv!.height - vv!.offsetTop
    wrapper.style.setProperty('--keyboard-offset', `${Math.max(0, offset)}px`)
    // 键盘弹出时滚动到底部
    if (offset > 100) {
      setTimeout(() => scrollToBottom(false), 100)
    }
  }

  vv.addEventListener('resize', onViewportResize)
  vv.addEventListener('scroll', onViewportResize)
}

/* ==================== 生命周期 ==================== */
onMounted(async () => {
  setupMobileKeyboard()
  const fupId = route.query.followup as string | undefined
  if (fupId) {
    followupRecordId.value = fupId
    isFollowupMode.value = true
  }

  await loadPregnantContext()

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
/* ==================== 容器与字体 ==================== */
.chat-wrapper {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  grid-template-columns: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  font-family: 'Nunito Sans', 'PingFang SC', sans-serif;
  color: #1E293B;
  background-color: #F8FAFC;
  /* 键盘弹出时的底部偏移 */
  --keyboard-offset: 0px;
}
.chat-wrapper--ios {
  height: 100%;
}

/* ==================== 动态光晕背景 (Halo) ==================== */
.halo-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}
.halo-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.85;
  animation: halo-float 20s infinite ease-in-out alternate;
}
.halo-orb-1 {
  top: -10%; left: -10%;
  width: 120vw; height: 120vw;
  background: radial-gradient(circle, #FECDD3 0%, transparent 70%);
}
.halo-orb-2 {
  bottom: -10%; right: -20%;
  width: 140vw; height: 140vw;
  background: radial-gradient(circle, #FCE7F3 0%, transparent 70%);
  animation-delay: -5s;
}
.halo-orb-3 {
  top: 30%; left: 40%;
  width: 100vw; height: 100vw;
  background: radial-gradient(circle, #FFE4E6 0%, transparent 70%);
  animation-delay: -10s;
}
.halo-backdrop {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
}
@keyframes halo-float {
  0% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(15vw, 15vh) scale(1.1); }
  100% { transform: translate(-10vw, 10vh) scale(0.9); }
}

/* 尊重用户减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  .halo-orb, .record-center__ring, .record-bar__wave-line,
  .audio-bubble__bar--play, .step-dot, .ripple, .ripple-delay,
  .toolbar-btn--recording, .ai-halo { animation: none !important; }
  .interactive-card:active { transform: none; }
}

/* ==================== 交互动效 ==================== */
.interactive-card {
  cursor: pointer;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.25s;
  -webkit-tap-highlight-color: transparent;
}
.interactive-card:active {
  transform: scale(0.95);
}

/* ==================== 1. 顶部导航栏 ==================== */
.chat-navbar {
  grid-row: 1; grid-column: 1;
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; padding-top: max(10px, env(safe-area-inset-top, 10px));
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  z-index: 10;
  border-bottom: 1px solid rgba(255, 255, 255, 0.4);
}
.navbar-btn {
  display: flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; border-radius: 50%; border: none;
  background: transparent; color: #475569;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.navbar-btn:hover { background: rgba(251, 113, 133, 0.08); color: #E11D48; }
.navbar-title {
  font-size: 16px; font-weight: 700; color: #1E293B; margin: 0;
}
.navbar-actions { display: flex; gap: 4px; }

/* ==================== 2. 用户信息栏 ==================== */
.user-info-bar {
  grid-row: 2; grid-column: 1;
  display: flex; align-items: center; gap: 10px;
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.3);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  z-index: 9;
}
.user-name { font-size: 13px; font-weight: 600; color: #475569; }
.user-actions { margin-left: auto; display: flex; }
.user-action-btn {
  width: 36px; height: 36px; border-radius: 50%; border: none;
  background: transparent; color: #94A3B8; display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.user-action-btn:hover { background: rgba(251, 113, 133, 0.08); color: #E11D48; }
.user-action-btn.active { color: #FB7185; background: #FFF1F2; }
.user-action-btn.active:hover { background: #FFE4E6; }

/* ==================== 主区域 ==================== */
.messages-container {
  grid-row: 3; grid-column: 1;
  min-height: 0; overflow-y: auto; padding: 20px 16px 8px;
  -webkit-overflow-scrolling: touch;
  z-index: 5;
}
.messages-inner {
  display: flex; flex-direction: column; gap: 24px;
  max-width: 768px; margin: 0 auto;
}

/* ---- 沉浸式欢迎区 ---- */
.welcome-section {
  text-align: center; padding: 40px 16px 20px;
  animation: slideUpFade 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.ai-avatar-wrapper {
  position: relative; display: inline-flex; justify-content: center; align-items: center;
  margin-bottom: 24px;
}
.ai-halo {
  position: absolute;
  width: 120%; height: 120%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(251, 113, 133, 0.4) 0%, transparent 70%);
  animation: breathing 4s ease-in-out infinite alternate;
  z-index: -1;
}
@keyframes breathing {
  0% { transform: scale(0.9); opacity: 0.6; }
  100% { transform: scale(1.2); opacity: 1; }
}
.welcome-title { font-size: 20px; font-weight: 700; color: #1E293B; margin-bottom: 8px; }
.welcome-desc { font-size: 14px; line-height: 1.6; color: #64748B; max-width: 280px; margin: 0 auto; }

/* ---- 轻量化孕周指南 ---- */
.pregnancy-guide { animation: slideUpFade 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.1s backwards; }
.soft-card { background: rgba(255, 255, 255, 0.55); backdrop-filter: blur(16px); border-radius: 20px; border: 1px solid rgba(255,255,255,0.8); box-shadow: 0 4px 16px rgba(148, 163, 184, 0.1); }
.week-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; }
.week-mini-info { display: flex; flex-direction: column; gap: 4px; }
.week-number { font-size: 16px; font-weight: 700; color: #FB7185; }
.days-remaining { font-size: 12px; color: #64748B; }
.fetus-mini { display: flex; align-items: center; gap: 8px; background: white; padding: 6px 12px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
.fetus-icon { font-size: 18px; }
.fetus-size { font-size: 14px; font-weight: 600; color: #334155; }

/* ---- 消息列表 (Zero Interface) ---- */
.msg-list { display: flex; flex-direction: column; gap: 28px; }
.message-row { display: flex; gap: 12px; max-width: 100%; animation: slideUpFade 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes slideUpFade { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

.message-row--assistant { align-self: flex-start; padding-right: 16px; }
.message-row--user { align-self: flex-end; flex-direction: row-reverse; padding-left: 16px; }

.assistant-avatar { margin-top: 4px; }

.message-body { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.message-row--user .message-body { align-items: flex-end; }

/* 气泡样式重构 */
.message-bubble { position: relative; font-size: 15px; line-height: 1.6; word-wrap: break-word; }
.message-bubble--user {
  background: rgba(255, 241, 242, 0.75);
  backdrop-filter: blur(12px);
  color: #1E293B;
  padding: 12px 18px;
  border-radius: 20px 20px 4px 20px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 2px 8px rgba(251, 113, 133, 0.1);
}
.message-bubble--assistant {
  /* Zero Interface: 去除背景边框，类似流式阅读 */
  background: transparent;
  color: #1E293B;
  padding: 4px 0;
}

/* Markdown 排版优化 */
.bubble-markdown { font-size: 15px; line-height: 1.65; color: #334155; }
.bubble-markdown :deep(p) { margin: 0 0 10px; }
.bubble-markdown :deep(p:last-child) { margin-bottom: 0; }
.bubble-markdown :deep(strong) { font-weight: 700; color: #1E293B; }
.bubble-markdown :deep(li) { margin: 4px 0; }
.bubble-markdown :deep(ul), .bubble-markdown :deep(ol) { padding-left: 20px; }

/* 思考中特效 */
.message-bubble--thinking { display: flex; align-items: center; gap: 12px; }
.thinking-indicator { position: relative; width: 20px; height: 20px; }
.ripple, .ripple-delay {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  border-radius: 50%; border: 2px solid #FB7185; opacity: 0;
  animation: ripple-anim 2s cubic-bezier(0.16, 1, 0.3, 1) infinite;
}
.ripple-delay { animation-delay: 1s; }
@keyframes ripple-anim {
  0% { transform: scale(0.5); opacity: 0.8; }
  100% { transform: scale(1.5); opacity: 0; }
}
.thinking-text { font-size: 14px; font-weight: 600; color: #FB7185; }

/* 操作栏与时间 */
.message-footer { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
.message-footer--user { flex-direction: row-reverse; }
.message-time { font-size: 11px; color: #94A3B8; }
.message-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 0.2s; }
.message-row:hover .message-actions { opacity: 1; }
@media (hover: none) { .message-actions { opacity: 0.7; } }
.msg-action-btn {
  width: 28px; height: 28px; border-radius: 8px; border: none; background: transparent;
  color: #94A3B8; display: flex; align-items: center; justify-content: center;
  transition: background 0.2s, color 0.2s; cursor: pointer;
}
.msg-action-btn:hover { background: white; color: #1E293B; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }

.scroll-anchor { height: 20px; }

/* ==================== 3. 底部输入区 (灵动输入岛) ==================== */
.input-container {
  grid-row: 4; grid-column: 1;
  position: relative; z-index: 10;
  display: flex; flex-direction: column; align-items: center;
  padding: 0 16px 12px;
  padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));
  /* 防止被移动端浏览器底部导航栏遮挡 */
  transform: translateY(calc(-1 * var(--keyboard-offset, 0px)));
}

.prompt-chips {
  display: flex; gap: 8px;
  overflow-x: auto; scrollbar-width: none;
  width: 100%; max-width: 768px; padding-bottom: 12px;
  -webkit-overflow-scrolling: touch;
}
.prompt-chips::-webkit-scrollbar { display: none; }
.prompt-chip {
  flex: 0 0 auto;
  padding: 8px 16px; border-radius: 20px;
  background: rgba(255, 255, 255, 0.6); backdrop-filter: blur(10px);
  border: 1px solid white; box-shadow: 0 4px 12px rgba(148, 163, 184, 0.08);
  font-size: 13px; font-weight: 600; color: #0284C7;
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s, transform 0.15s;
}
.prompt-chip:hover {
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 6px 16px rgba(148, 163, 184, 0.12);
}

.input-pill-wrapper {
  width: 100%; max-width: 768px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

/* 胶囊灵动岛 */
.input-pill {
  width: 100%;
  display: flex; align-items: flex-end; gap: 6px;
  background: rgba(255, 255, 255, 0.75); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 28px;
  padding: 6px;
  box-shadow: 0 8px 32px rgba(148, 163, 184, 0.12), 0 2px 8px rgba(148, 163, 184, 0.06);
}

.toolbar-btn {
  width: 40px; height: 40px; border-radius: 50%; border: none;
  background: white; color: #475569; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); flex-shrink: 0;
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s, color 0.2s;
}
.toolbar-btn:hover {
  background: #FFF1F2; color: #E11D48;
  box-shadow: 0 4px 12px rgba(251, 113, 133, 0.15);
}
.toolbar-btn--recording {
  background: #FFE4E6; color: #E11D48;
  animation: pulse-record 1.5s ease-in-out infinite;
}
@keyframes pulse-record {
  0%, 100% { box-shadow: 0 0 0 0 rgba(251, 113, 133, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(251, 113, 133, 0); }
}
.toolbar-btn--stop { background: #1E293B; color: white; }

/* ==================== 录音浮层 ==================== */
.record-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  padding-bottom: 120px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.record-overlay-fade-enter-active { transition: all 0.25s ease-out; }
.record-overlay-fade-leave-active { transition: all 0.2s ease-in; }
.record-overlay-fade-enter-from,
.record-overlay-fade-leave-to { opacity: 0; }

/* 取消区域 */
.cancel-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 32px;
  border-radius: 20px;
  margin-bottom: 40px;
  transition: all 0.25s ease;
  background: rgba(255, 255, 255, 0.1);
}
.cancel-zone--active {
  background: rgba(239, 68, 68, 0.25);
  border: 2px solid rgba(239, 68, 68, 0.6);
  transform: scale(1.08);
}
.cancel-zone__icon {
  width: 48px; height: 48px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  transition: all 0.25s ease;
}
.cancel-zone--active .cancel-zone__icon {
  background: #EF4444;
  color: #fff;
}
.cancel-zone__text {
  font-size: 14px; font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  transition: color 0.25s;
}
.cancel-zone--active .cancel-zone__text { color: #FCA5A5; }

/* 录音状态条 */
.record-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 40px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.12);
  transition: all 0.25s ease;
  min-width: 200px;
}
.record-bar--cancel {
  background: rgba(239, 68, 68, 0.2);
}
.record-bar__wave {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 32px;
}
.record-bar__wave-line {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: #FB7185;
  animation: wave-pulse 0.6s ease-in-out infinite alternate;
}
.record-bar--cancel .record-bar__wave-line {
  background: #EF4444;
}
@keyframes wave-pulse {
  0% { height: 8px; opacity: 0.5; }
  100% { height: 28px; opacity: 1; }
}
.record-bar__time {
  font-size: 18px; font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.record-bar__hint {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
}

/* 录音中心图标 */
.record-center {
  margin-bottom: 24px;
}
.record-center__ring {
  width: 88px; height: 88px;
  border-radius: 50%;
  background: rgba(251, 113, 133, 0.2);
  display: flex; align-items: center; justify-content: center;
  animation: ring-pulse 1.5s ease-in-out infinite;
}
.record-center__icon {
  width: 64px; height: 64px;
  border-radius: 50%;
  background: rgba(251, 113, 133, 0.3);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  color: #fff;
}
.record-center--cancel .record-center__ring {
  background: rgba(239, 68, 68, 0.2);
  animation: none;
}
.record-center--cancel .record-center__icon {
  background: rgba(239, 68, 68, 0.4);
}
@keyframes ring-pulse {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.15); opacity: 1; }
}

/* ==================== 音频播放气泡 ==================== */
.audio-bubble {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 160px;
}
.audio-bubble__btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(251, 113, 133, 0.15);
  color: #E11D48;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.audio-bubble__btn:active { transform: scale(0.9); }
.audio-bubble__waveform {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  height: 36px;
}
.audio-bubble__bar {
  flex: 1;
  min-width: 2px;
  border-radius: 2px;
  background: #CBD5E1;
  transition: background 0.2s;
}
.audio-bubble__bar--play {
  background: #FB7185;
  animation: bar-bounce 0.6s ease-in-out infinite alternate;
}
.audio-bubble__bar--played {
  background: #FDA4AF;
}
@keyframes bar-bounce {
  0% { opacity: 0.6; }
  100% { opacity: 1; }
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.audio-bubble__dur {
  font-size: 12px;
  font-weight: 600;
  color: #64748B;
  flex-shrink: 0;
  min-width: 36px;
}
.audio-bubble__transcribe-btn {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(100, 116, 139, 0.12);
  color: #64748B;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-left: 2px;
}
.audio-bubble__transcribe-btn:hover {
  background: rgba(251, 113, 133, 0.15);
  color: #E11D48;
}
.audio-bubble__transcribe-btn:active { transform: scale(0.9); }

/* ==================== 语音转录文本 ==================== */
.audio-transcription {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(100, 116, 139, 0.06);
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
  border: 1px solid rgba(100, 116, 139, 0.1);
  user-select: text;
}
.audio-transcription__loading {
  color: #94A3B8;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.audio-transcription__loading::before {
  content: '';
  width: 12px; height: 12px;
  border: 2px solid #CBD5E1;
  border-top-color: #FB7185;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ==================== 图片消息气泡 ==================== */
.image-bubble {
  max-width: 240px;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(148, 163, 184, 0.15);
}
.image-bubble__img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 16px;
  object-fit: cover;
}

.chat-input { flex: 1; }
.chat-input :deep(.el-textarea__inner) {
  border: none; background: transparent; box-shadow: none;
  padding: 10px 8px; font-size: 15px; color: #1E293B; line-height: 1.4;
}
.chat-input :deep(.el-textarea__inner:focus) { box-shadow: none; }
.chat-input :deep(.el-textarea__inner::placeholder) { color: #94A3B8; }

.send-btn {
  width: 40px; height: 40px; border-radius: 50%; border: none;
  background: #FB7185; color: white; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 12px rgba(251, 113, 133, 0.3); flex-shrink: 0;
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s, transform 0.15s;
}
.send-btn:hover:not(:disabled) {
  background: #E11D48;
  box-shadow: 0 6px 16px rgba(225, 29, 72, 0.35);
}
.send-btn:active:not(:disabled) { transform: scale(0.92); }
.send-btn:disabled { background: #E2E8F0; box-shadow: none; color: #94A3B8; cursor: not-allowed; }

.stop-btn {
  background: #1E293B;
  box-shadow: 0 4px 12px rgba(30, 41, 59, 0.3);
}

.stop-icon-box {
  width: 14px;
  height: 14px;
  background-color: white;
  border-radius: 3px;
}

.input-hint { font-size: 11px; color: #94A3B8; }

/* ==================== 待发送图片预览 ==================== */
.pending-images-bar {
  display: flex;
  gap: 8px;
  padding: 8px 4px;
  overflow-x: auto;
  scrollbar-width: none;
  width: 100%;
}
.pending-images-bar::-webkit-scrollbar { display: none; }
.pending-image-item {
  position: relative;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(148, 163, 184, 0.2);
  border: 2px solid rgba(255, 255, 255, 0.8);
  animation: slideUpFade 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.pending-image-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.pending-image-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: background 0.2s;
}
.pending-image-remove:hover {
  background: rgba(239, 68, 68, 0.8);
}

/* ==================== 图片来源选择菜单 ==================== */
.image-source-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.image-source-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #334155;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s;
}
.image-source-item:hover {
  background: #FFF1F2;
  color: #E11D48;
}
.image-source-item:active {
  background: #FFE4E6;
}

/* ==================== 历史会话列表 ==================== */
.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}
.session-loading {
  display: flex; justify-content: center; align-items: center; gap: 6px;
  padding: 40px 0;
}
.session-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 60px 0; color: #94A3B8;
}
.session-empty p { font-size: 14px; margin: 0; }
.session-item {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s;
}
.session-item:hover {
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 2px 8px rgba(148, 163, 184, 0.1);
}
.session-item--active {
  background: #FFF1F2;
  border-color: #FECDD3;
}
.session-item__header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.session-item__date { font-size: 13px; font-weight: 600; color: #334155; }
.session-item__count { font-size: 11px; color: #94A3B8; }
.session-item__preview {
  font-size: 13px; color: #64748B; line-height: 1.4;
  margin: 0; overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}

/* ==================== 紧急/随访横幅 ==================== */
.emergency-banner {
  grid-row: 1; grid-column: 1;
  z-index: 20;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  padding-top: max(10px, env(safe-area-inset-top, 10px));
  background: linear-gradient(135deg, #FEF2F2 0%, #FECACA 100%);
  color: #991B1B;
  font-size: 13px; font-weight: 500;
  border-bottom: 1px solid #FECACA;
}
.emergency-banner .banner-close {
  margin-left: auto;
  flex-shrink: 0;
}
.followup-banner {
  grid-row: 2; grid-column: 1;
  z-index: 19;
  padding: 10px 16px;
  background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
  border-bottom: 1px solid #C7D2FE;
}
.followup-banner__inner {
  display: flex; flex-direction: column; gap: 8px;
  font-size: 13px; font-weight: 500; color: #3730A3;
}
.followup-banner__header {
  display: flex; align-items: center; gap: 8px;
}
.followup-banner__icon {
  color: #6366F1;
}
.followup-banner__progress {
  display: flex; align-items: center; gap: 10px;
}
.followup-banner__bar {
  flex: 1;
  height: 6px;
  background: #C7D2FE;
  border-radius: 3px;
  overflow: hidden;
}
.followup-banner__fill {
  height: 100%;
  background: linear-gradient(90deg, #6366F1, #818CF8);
  border-radius: 3px;
  transition: width 0.4s ease;
}
.followup-banner__count {
  font-size: 11px; color: #6366F1; font-weight: 600;
  white-space: nowrap;
}
.banner-slide-enter-active,
.banner-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.banner-slide-enter-from,
.banner-slide-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}

/* ==================== 📱 移动端响应式适配 ==================== */

/* ---- 平板 / 小屏设备 (≤768px) ---- */
@media (max-width: 768px) {
  /* 导航栏 */
  .chat-navbar {
    padding: 8px 12px;
    padding-top: max(8px, env(safe-area-inset-top, 8px));
  }
  .navbar-title { font-size: 15px; }
  .navbar-btn { width: 40px; height: 40px; }

  /* 用户信息栏 */
  .user-info-bar {
    padding: 6px 14px;
    gap: 8px;
  }
  .user-name { font-size: 12px; }
  .switch-btn { font-size: 10px; padding: 3px 8px; }

  /* 消息容器：减少横向 padding，释放更多阅读空间 */
  .messages-container {
    padding: 12px 8px 6px;
  }
  .messages-inner {
    gap: 18px;
  }

  /* 消息行：取消两侧强制留白 */
  .message-row--assistant {
    padding-right: 4px;
  }
  .message-row--user {
    padding-left: 4px;
  }
  .message-row {
    gap: 8px;
  }
  .assistant-avatar {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
  }

  /* 消息气泡 */
  .message-bubble { font-size: 14px; }
  .message-bubble--user {
    padding: 10px 14px;
    border-radius: 16px 16px 4px 16px;
  }
  .bubble-markdown { font-size: 14px; }

  /* 欢迎区域 */
  .welcome-section { padding: 24px 8px 12px; }
  .welcome-title { font-size: 18px; }
  .welcome-desc { font-size: 13px; max-width: 260px; }

  /* 孕周卡片 */
  .week-card { padding: 12px 16px; }
  .week-number { font-size: 14px; }
  .days-remaining { font-size: 11px; }
  .fetus-size { font-size: 12px; }
  .fetus-mini { padding: 4px 10px; gap: 4px; }

  /* 提示词 chips */
  .prompt-chips {
    gap: 6px;
    padding-bottom: 10px;
  }
  .prompt-chip {
    padding: 6px 12px;
    font-size: 12px;
    border-radius: 16px;
  }

  /* 输入胶囊岛 */
  .input-container {
    padding: 0 10px 8px;
    padding-bottom: max(8px, env(safe-area-inset-bottom, 8px));
  }
  .input-pill {
    padding: 4px;
    border-radius: 24px;
    gap: 4px;
  }
  .toolbar-btn {
    width: 36px; height: 36px;
  }
  .send-btn {
    width: 36px; height: 36px;
  }
  .chat-input :deep(.el-textarea__inner) {
    font-size: 14px;
    padding: 8px 4px;
  }
  .input-hint { font-size: 10px; }

  /* 图片气泡 */
  .image-bubble { max-width: 200px; }

  /* 待发送图片预览 */
  .pending-image-item { width: 56px; height: 56px; border-radius: 10px; }

  /* 消息操作栏：触摸设备始终可见 */
  .message-actions { opacity: 0.6; }
  .msg-action-btn { width: 32px; height: 32px; }

  /* 横幅：移动端紧凑 */
  .emergency-banner { padding: 8px 12px; font-size: 12px; }
  .followup-banner { padding: 8px 12px; }
  .followup-banner__inner { font-size: 12px; }
  .followup-banner__bar { height: 5px; }

  /* 编辑弹窗 */
  .el-dialog { width: 95% !important; }
}

/* ---- 小屏手机 (≤480px) ---- */
@media (max-width: 480px) {
  .chat-navbar {
    padding: 6px 10px;
    padding-top: max(6px, env(safe-area-inset-top, 6px));
  }
  .navbar-title { font-size: 14px; }
  .navbar-btn { width: 36px; height: 36px; }

  /* 用户信息栏：更紧凑 */
  .user-info-bar { padding: 4px 10px; gap: 6px; }
  .user-action-btn { width: 32px; height: 32px; }

  /* 消息容器 */
  .messages-container {
    padding: 10px 4px 4px;
  }
  .messages-inner { gap: 14px; }

  .message-row { gap: 6px; }
  .message-row--assistant { padding-right: 0; }
  .message-row--user { padding-left: 0; }

  .message-bubble { font-size: 13px; line-height: 1.55; }
  .message-bubble--user {
    padding: 8px 12px;
    border-radius: 14px 14px 4px 14px;
  }
  .bubble-markdown { font-size: 13px; line-height: 1.55; }
  .bubble-markdown :deep(ul),
  .bubble-markdown :deep(ol) { padding-left: 16px; }

  /* 欢迎区域 */
  .welcome-section { padding: 16px 4px 8px; }
  .welcome-title { font-size: 16px; }
  .welcome-desc { font-size: 12px; max-width: 240px; }
  .ai-avatar-wrapper { margin-bottom: 16px; }
  .ai-halo { width: 100%; height: 100%; }

  /* 孕周卡片 */
  .week-card { padding: 10px 12px; border-radius: 16px; }
  .week-number { font-size: 13px; }
  .fetus-mini { padding: 3px 8px; border-radius: 10px; }

  /* 提示词 chips */
  .prompt-chip {
    padding: 5px 10px;
    font-size: 11px;
    border-radius: 14px;
  }

  /* 输入胶囊岛 */
  .input-container {
    padding: 0 6px 6px;
    padding-bottom: max(6px, env(safe-area-inset-bottom, 6px));
  }
  .input-pill {
    padding: 3px;
    border-radius: 22px;
    gap: 2px;
  }
  .toolbar-btn {
    width: 32px; height: 32px;
  }
  .send-btn {
    width: 32px; height: 32px;
  }
  .chat-input :deep(.el-textarea__inner) {
    font-size: 13px;
    padding: 7px 2px;
  }
  .input-hint { font-size: 10px; }

  /* 图片气泡：全宽适配 */
  .image-bubble { max-width: 180px; }

  /* 待发送图片预览：小屏 */
  .pending-images-bar { gap: 6px; padding: 6px 2px; }
  .pending-image-item { width: 48px; height: 48px; border-radius: 8px; }
  .pending-image-remove { width: 16px; height: 16px; top: 1px; right: 1px; }

  /* 消息操作按钮：更小 tap target */
  .msg-action-btn { width: 28px; height: 28px; }

  /* 思考中状态 */
  .thinking-text { font-size: 12px; }

  /* 消息时间 */
  .message-time { font-size: 10px; }

  /* 录音浮层：适配小屏高度 */
  .record-overlay {
    padding-bottom: 80px;
  }
  .cancel-zone {
    padding: 12px 24px;
    margin-bottom: 24px;
  }
  .cancel-zone__icon {
    width: 40px; height: 40px;
  }
  .record-center__ring {
    width: 72px; height: 72px;
  }
  .record-center__icon {
    width: 52px; height: 52px;
  }
  .record-bar {
    padding: 14px 28px;
    min-width: 160px;
  }
  .record-bar__time { font-size: 16px; }

  /* 音频气泡 */
  .audio-bubble { gap: 6px; min-width: 130px; }
  .audio-bubble__btn { width: 32px; height: 32px; }
  .audio-bubble__dur { font-size: 11px; min-width: 30px; }
  .audio-bubble__waveform { height: 30px; }
  .audio-bubble__transcribe-btn { width: 24px; height: 24px; }

  /* 语音转录文本 */
  .audio-transcription {
    margin-top: 6px;
    padding: 6px 10px;
    font-size: 12px;
  }
  /* 横幅：小屏最紧凑 */
  .emergency-banner { padding: 6px 10px; font-size: 11px; }
  .followup-banner { padding: 6px 10px; }
  .followup-banner__inner { font-size: 11px; }
  .followup-banner__bar { height: 4px; }
  .followup-banner__count { font-size: 10px; }
}

/* ---- 横屏手机 / 小屏设备高度优化 ---- */
@media (max-height: 480px) and (orientation: landscape) {
  .chat-wrapper {
    grid-template-rows: auto 1fr auto; /* 隐藏用户信息栏 */
  }
  .user-info-bar { display: none; }
  .welcome-section { padding: 8px 16px 4px; }
  .welcome-header { display: none; } /* 隐藏大头像以节省空间 */
  .welcome-title { font-size: 14px; margin-bottom: 2px; }
  .welcome-desc { font-size: 11px; margin-bottom: 0; }
  .pregnancy-guide { display: none; } /* 隐藏孕周卡片 */
  .messages-container { padding: 4px 8px 2px; }
  .messages-inner { gap: 10px; }
  .prompt-chips { padding-bottom: 6px; }
  .prompt-chip { padding: 4px 10px; font-size: 11px; }
  .input-container { padding: 0 8px 4px; }
}

</style>
