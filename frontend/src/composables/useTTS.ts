import { ref, readonly, onUnmounted } from 'vue'

export type TTSMode = 'browser' | 'backend'

export interface TTSOptions {
  mode?: TTSMode
  lang?: string
  rate?: number
  pitch?: number
  speed?: number
  role?: 'pregnant' | 'nurse' | 'doctor'
}

export function useTTS(options: TTSOptions = {}) {
  const mode = options.mode ?? 'browser'
  const lang = options.lang ?? 'zh-CN'
  const rate = options.rate ?? 1.1
  const pitch = options.pitch ?? 1.0
  const speed = options.speed ?? 1.0
  const role = options.role ?? 'pregnant'

  const isSpeaking = ref(false)
  const isSupported = ref(typeof window !== 'undefined' && 'speechSynthesis' in window)

  let currentAudio: HTMLAudioElement | null = null
  let abortController: AbortController | null = null
  let audioContext: AudioContext | null = null
  let scheduledSources: AudioBufferSourceNode[] = []

  function speakBrowser(text: string): void {
    if (!isSupported.value) return
    speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang; utterance.rate = rate; utterance.pitch = pitch
    const voices = speechSynthesis.getVoices()
    const zhVoice = voices.find(v => v.lang.startsWith('zh'))
    if (zhVoice) utterance.voice = zhVoice
    utterance.onstart = () => { isSpeaking.value = true }
    utterance.onend = () => { isSpeaking.value = false }
    utterance.onerror = () => { isSpeaking.value = false }
    speechSynthesis.speak(utterance)
  }

  async function playStreamingWav(response: Response, signal: AbortSignal): Promise<void> {
    if (!response.body) throw new Error('No body')
    const reader = response.body.getReader()
    const chunks: Uint8Array[] = []

    // 收集全部字节（流式传输使生成与网络重叠，总延迟仍远低于非流式端点）
    while (true) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      const { done, value } = await reader.read()
      if (done) break
      if (value) chunks.push(value)
    }

    // 拼装 ArrayBuffer
    const totalLen = chunks.reduce((s, c) => s + c.length, 0)
    if (totalLen < 44) throw new Error(`WAV too short: ${totalLen} bytes`)

    const wavBuf = new ArrayBuffer(totalLen)
    const wavView = new Uint8Array(wavBuf)
    let off = 0
    for (const c of chunks) { wavView.set(c, off); off += c.length }

    // 修复 WAV header（0xFFFFFFFF → 实际大小）
    const dv = new DataView(wavBuf)
    dv.setUint32(4, totalLen - 8, true)
    dv.setUint32(40, totalLen - 44, true)

    // 用原始采样率创建 AudioContext，避免浏览器上采样
    const nativeRate = dv.getUint32(24, true)
    audioContext = new AudioContext({ sampleRate: nativeRate })
    if (audioContext.state === 'suspended') await audioContext.resume()

    // 浏览器原生解码 — 保证语序绝对正确，无调度竞态
    const audioBuffer = await audioContext.decodeAudioData(wavBuf)

    const source = audioContext.createBufferSource()
    source.buffer = audioBuffer; source.connect(audioContext.destination)
    source.start()
    scheduledSources.push(source)

    await new Promise<void>(resolve => {
      let resolved = false
      const done = () => { if (!resolved) { resolved = true; resolve() } }
      const fallback = setTimeout(done, audioBuffer.duration * 1000 + 2000)
      source.onended = () => { clearTimeout(fallback); done() }
    })

    console.log(
      `[TTS] 流式播放完成: ${totalLen}B, ` +
      `${audioBuffer.sampleRate}Hz/${audioBuffer.numberOfChannels}ch/${audioBuffer.duration.toFixed(1)}s`
    )
  }

  async function playBlob(blob: Blob): Promise<void> {
    return new Promise<void>(resolve => {
      const url = URL.createObjectURL(blob)
      currentAudio = new Audio(url)
      const cleanup = () => { URL.revokeObjectURL(url); currentAudio = null; resolve() }
      currentAudio.onended = cleanup; currentAudio.onerror = cleanup
      currentAudio.play().catch(cleanup)
    })
  }

  async function extractError(resp: Response, fallback: string): Promise<string> {
    try { const body = await resp.json(); return body.detail || body.message || fallback }
    catch { return fallback }
  }

  async function speakBackend(text: string): Promise<void> {
    stop()
    abortController = new AbortController()
    isSpeaking.value = true

    try {
      const token = localStorage.getItem('token')
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }
      const body = JSON.stringify({ text, role, speed })

      let streamFailed = false
      try {
        const resp = await fetch('/api/v1/tts/stream', { method: 'POST', headers, body, signal: abortController.signal })
        if (!resp.ok) throw new Error(`流式接口 ${resp.status}: ${await extractError(resp, `HTTP ${resp.status}`)}`)
        await playStreamingWav(resp, abortController.signal)
      } catch (streamErr) {
        if ((streamErr as Error).name === 'AbortError') throw streamErr
        console.warn('[TTS] 流式合成失败，降级到非流式:', (streamErr as Error).message)
        streamFailed = true
      }

      if (streamFailed) {
        let resp: Response
        try {
          resp = await fetch('/api/v1/tts/synthesize', { method: 'POST', headers, body, signal: abortController.signal })
          if (!resp.ok) throw new Error(`非流式接口 ${resp.status}: ${await extractError(resp, `HTTP ${resp.status}`)}`)
        } catch (synthErr) {
          if ((synthErr as Error).name === 'AbortError') throw synthErr
          console.warn('[TTS] 非流式合成也失败，降级到浏览器 TTS:', (synthErr as Error).message)
          speakBrowser(text); return
        }
        const blob = await resp.blob()
        await playBlob(blob)
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('[TTS] 后端播放失败:', err)
        speakBrowser(text)
      }
    } finally { isSpeaking.value = false }
  }

  async function speak(text: string): Promise<void> {
    const cleaned = cleanForTTS(text)
    if (!cleaned) return
    if (mode === 'browser') speakBrowser(cleaned)
    else await speakBackend(cleaned)
  }

  function stop(): void {
    if (isSupported.value) speechSynthesis.cancel()
    if (currentAudio) {
      currentAudio.pause()
      if (currentAudio.src?.startsWith('blob:')) URL.revokeObjectURL(currentAudio.src)
      currentAudio = null
    }
    if (abortController) { abortController.abort(); abortController = null }
    if (audioContext) {
      scheduledSources.forEach(s => { try { s.stop() } catch { /* */ } })
      scheduledSources = []
      audioContext.close().catch(() => {})
      audioContext = null
    }
    isSpeaking.value = false
  }

  function cleanForTTS(text: string): string {
    if (!text) return ''
    let cleaned = text
    cleaned = cleaned.replace(/```[\s\S]*?```/g, '')
    cleaned = cleaned.replace(/`[^`]*`/g, '')
    cleaned = cleaned.replace(/\*\*(.*?)\*\*/g, '$1')
    cleaned = cleaned.replace(/\*(.*?)\*/g, '$1')
    cleaned = cleaned.replace(/__(.*?)__/g, '$1')
    cleaned = cleaned.replace(/_(.*?)_/g, '$1')
    cleaned = cleaned.replace(/<[^>]*>/g, '')
    cleaned = cleaned.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    cleaned = cleaned.replace(/^#{1,6}\s+/gm, '')
    cleaned = cleaned.replace(/^[\s]*[-*+]\s+/gm, '')
    cleaned = cleaned.replace(/^[\s]*\d+\.\s+/gm, '')
    cleaned = cleaned.replace(/[\u{1F600}-\u{1F64F}]/gu, '')
    cleaned = cleaned.replace(/[\u{1F300}-\u{1F5FF}]/gu, '')
    cleaned = cleaned.replace(/[\u{1F680}-\u{1F6FF}]/gu, '')
    cleaned = cleaned.replace(/[\u{1F1E0}-\u{1F1FF}]/gu, '')
    cleaned = cleaned.replace(/[\u{2600}-\u{26FF}]/gu, '')
    cleaned = cleaned.replace(/[\u{2700}-\u{27BF}]/gu, '')
    cleaned = cleaned.replace(/[\u{FE00}-\u{FE0F}]/gu, '')
    cleaned = cleaned.replace(/[\u{200D}]/gu, '')
    cleaned = cleaned.replace(/[\u{1F900}-\u{1F9FF}]/gu, '')
    cleaned = cleaned.replace(/[\u{1FA00}-\u{1FA6F}]/gu, '')
    cleaned = cleaned.replace(/[\u{1FA70}-\u{1FAFF}]/gu, '')
    cleaned = cleaned.replace(/\n{2,}/g, '。')
    cleaned = cleaned.replace(/\n/g, '，')
    cleaned = cleaned.trim()
    if (cleaned.length > 500) cleaned = cleaned.slice(0, 500)
    return cleaned
  }

  onUnmounted(() => { stop() })

  return { isSpeaking: readonly(isSpeaking), isSupported: readonly(isSupported), speak, stop, cleanForTTS }
}
