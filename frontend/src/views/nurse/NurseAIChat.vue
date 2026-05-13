<template>
  <div class="nurse-chat">
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
          :size="28"
        />
        <div class="nurse-chat__bubble" :class="{ 'nurse-chat__bubble--user': msg.role === 'user' }">
          <div v-if="msg.loading && !msg.content" class="nurse-chat__loading">
            <span class="loading-dot" /><span class="loading-dot" /><span class="loading-dot" />
          </div>
          <div v-else class="nurse-chat__text" v-html="renderMarkdown(msg.content)" />
        </div>
      </div>
    </div>
    <div class="nurse-chat__input">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="1"
        placeholder="向小护提问..."
        @keydown.enter.exact.prevent="handleSend"
        :disabled="isStreaming"
      />
      <el-button
        type="primary"
        :icon="Promotion"
        circle
        :disabled="!inputText.trim() || isStreaming"
        @click="handleSend"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { nurseAiApi } from '@/api/endpoints'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { marked } from 'marked'

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  loading?: boolean
}

const messages = ref<ChatMsg[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

let msgCounter = 0
function genId() { return `nurse_${Date.now()}_${++msgCounter}` }

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string
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

  // 添加用户消息
  messages.value.push({ id: genId(), role: 'user', content: text })
  scrollToBottom()

  // 添加助手消息占位
  const assistantMsg: ChatMsg = { id: genId(), role: 'assistant', content: '', loading: true }
  messages.value.push(assistantMsg)
  isStreaming.value = true
  scrollToBottom()

  const pregnantId = localStorage.getItem('currentPregnantId') || ''

  try {
    await nurseAiApi.chatStream(
      { message: text, pregnant_id: pregnantId || undefined },
      {
        onChunk(chunk: string) {
          assistantMsg.content += chunk
          scrollToBottom()
        },
        onDone() {
          assistantMsg.loading = false
          isStreaming.value = false
        },
        onError() {
          assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
          assistantMsg.loading = false
          isStreaming.value = false
        },
      }
    )
  } catch {
    if (!assistantMsg.content) {
      assistantMsg.content = '抱歉，小护暂时无法回复。请稍后再试。'
    }
    assistantMsg.loading = false
    isStreaming.value = false
  }
}

onMounted(() => {
  messages.value.push({
    id: genId(),
    role: 'assistant',
    content: '您好！我是小护，您的AI护理助手。可以问我关于孕妇数据分析、护理建议、随访计划等问题。',
  })
})
</script>

<style scoped>
.nurse-chat {
  display: flex;
  flex-direction: column;
  height: 400px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}
.nurse-chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.nurse-chat__msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.nurse-chat__msg--user {
  flex-direction: row-reverse;
}
.nurse-chat__bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #f5f5f5;
  font-size: 13px;
  line-height: 1.5;
}
.nurse-chat__bubble--user {
  background: #409eff;
  color: white;
}
.nurse-chat__text :deep(p) { margin: 0 0 6px; }
.nurse-chat__text :deep(p:last-child) { margin-bottom: 0; }
.nurse-chat__loading {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #999;
  animation: dotBounce 1.4s infinite ease-in-out both;
}
.loading-dot:nth-child(2) { animation-delay: 0.16s; }
.loading-dot:nth-child(3) { animation-delay: 0.32s; }
@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.35; }
  40% { transform: scale(1); opacity: 1; }
}
.nurse-chat__input {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid #e4e7ed;
  align-items: flex-end;
}
</style>
