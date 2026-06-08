import { ref, readonly, onUnmounted } from 'vue'

export type TTSMode = 'browser' | 'backend'

export interface TTSOptions {
  mode?: TTSMode
  lang?: string
  rate?: number
  pitch?: number
  role?: 'pregnant' | 'nurse' | 'doctor'
}

export function useTTS(options: TTSOptions = {}) {
  const mode = options.mode ?? 'browser'
  const lang = options.lang ?? 'zh-CN'
  const rate = options.rate ?? 1.1
  const pitch = options.pitch ?? 1.0
  const role = options.role ?? 'pregnant'

  const isSpeaking = ref(false)
  const isSupported = ref(typeof window !== 'undefined' && 'speechSynthesis' in window)

  let currentAudio: HTMLAudioElement | null = null
  let abortController: AbortController | null = null

  function speakBrowser(text: string): void {
    if (!isSupported.value) return

    speechSynthesis.cancel()

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang
    utterance.rate = rate
    utterance.pitch = pitch

    // 尝试选择中文语音
    const voices = speechSynthesis.getVoices()
    const zhVoice = voices.find(v => v.lang.startsWith('zh'))
    if (zhVoice) utterance.voice = zhVoice

    utterance.onstart = () => { isSpeaking.value = true }
    utterance.onend = () => { isSpeaking.value = false }
    utterance.onerror = () => { isSpeaking.value = false }

    speechSynthesis.speak(utterance)
  }

  async function speakBackend(text: string): Promise<void> {
    stop()
    abortController = new AbortController()
    isSpeaking.value = true

    try {
      const token = localStorage.getItem('token')
      const resp = await fetch('/api/v1/tts/synthesize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ text, role }),
        signal: abortController.signal,
      })

      if (!resp.ok) {
        // 后端 TTS 不可用时降级到浏览器
        console.warn('[TTS] 后端合成失败，降级到浏览器 TTS')
        speakBrowser(text)
        return
      }

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      currentAudio = new Audio(url)

      currentAudio.onended = () => {
        isSpeaking.value = false
        URL.revokeObjectURL(url)
        currentAudio = null
      }
      currentAudio.onerror = () => {
        isSpeaking.value = false
        URL.revokeObjectURL(url)
        currentAudio = null
      }

      await currentAudio.play()
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('[TTS] 后端播放失败:', err)
        speakBrowser(text)
      } else {
        isSpeaking.value = false
      }
    }
  }

  async function speak(text: string): Promise<void> {
    const cleaned = cleanForTTS(text)
    if (!cleaned) return

    if (mode === 'browser') {
      speakBrowser(cleaned)
    } else {
      await speakBackend(cleaned)
    }
  }

  function stop(): void {
    if (isSupported.value) speechSynthesis.cancel()
    if (currentAudio) {
      currentAudio.pause()
      // 释放 blob URL 避免内存泄漏
      if (currentAudio.src && currentAudio.src.startsWith('blob:')) {
        URL.revokeObjectURL(currentAudio.src)
      }
      currentAudio = null
    }
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isSpeaking.value = false
  }

  function cleanForTTS(text: string): string {
    if (!text) return ''
    let cleaned = text
    // 移除代码块
    cleaned = cleaned.replace(/```[\s\S]*?```/g, '')
    cleaned = cleaned.replace(/`[^`]*`/g, '')
    // 移除 markdown 格式
    cleaned = cleaned.replace(/\*\*(.*?)\*\*/g, '$1')
    cleaned = cleaned.replace(/\*(.*?)\*/g, '$1')
    cleaned = cleaned.replace(/__(.*?)__/g, '$1')
    cleaned = cleaned.replace(/_(.*?)_/g, '$1')
    // 移除 HTML 标签
    cleaned = cleaned.replace(/<[^>]*>/g, '')
    // 移除 markdown 链接
    cleaned = cleaned.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    // 移除标题标记
    cleaned = cleaned.replace(/^#{1,6}\s+/gm, '')
    // 移除列表标记
    cleaned = cleaned.replace(/^[\s]*[-*+]\s+/gm, '')
    cleaned = cleaned.replace(/^[\s]*\d+\.\s+/gm, '')
    // 移除 emoji 表情（Unicode 范围）
    cleaned = cleaned.replace(/[\u{1F600}-\u{1F64F}]/gu, '')  // 情感符号
    cleaned = cleaned.replace(/[\u{1F300}-\u{1F5FF}]/gu, '')  // 符号和象形文字
    cleaned = cleaned.replace(/[\u{1F680}-\u{1F6FF}]/gu, '')  // 交通和地图符号
    cleaned = cleaned.replace(/[\u{1F1E0}-\u{1F1FF}]/gu, '')  // 旗帜
    cleaned = cleaned.replace(/[\u{2600}-\u{26FF}]/gu, '')    // 杂项符号
    cleaned = cleaned.replace(/[\u{2700}-\u{27BF}]/gu, '')    // 装饰符号
    cleaned = cleaned.replace(/[\u{FE00}-\u{FE0F}]/gu, '')    // 变体选择符
    cleaned = cleaned.replace(/[\u{200D}]/gu, '')              // 零宽连接符
    cleaned = cleaned.replace(/[\u{1F900}-\u{1F9FF}]/gu, '')  // 补充符号
    cleaned = cleaned.replace(/[\u{1FA00}-\u{1FA6F}]/gu, '')  // 棋子符号
    cleaned = cleaned.replace(/[\u{1FA70}-\u{1FAFF}]/gu, '')  // 符号扩展
    // 清理多余空白
    cleaned = cleaned.replace(/\n{2,}/g, '。')
    cleaned = cleaned.replace(/\n/g, '，')
    cleaned = cleaned.trim()
    // 截断到 500 字符
    if (cleaned.length > 500) cleaned = cleaned.slice(0, 500)
    return cleaned
  }

  onUnmounted(() => { stop() })

  return {
    isSpeaking: readonly(isSpeaking),
    isSupported: readonly(isSupported),
    speak,
    stop,
    cleanForTTS,
  }
}
