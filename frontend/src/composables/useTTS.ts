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

  function pcmToAudioBuffer(
    pcmBytes: Uint8Array, ctx: AudioContext,
    sampleRate: number, numChannels: number, bitsPerSample: number,
  ): AudioBuffer {
    const bytesPerFrame = (bitsPerSample / 8) * numChannels
    const numFrames = Math.floor(pcmBytes.length / bytesPerFrame)
    const buffer = ctx.createBuffer(numChannels, numFrames, sampleRate)
    if (bitsPerSample === 16) {
      const int16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset, numFrames * numChannels)
      for (let ch = 0; ch < numChannels; ch++) {
        const channel = buffer.getChannelData(ch)
        for (let i = 0; i < numFrames; i++) channel[i] = int16[i * numChannels + ch] / 32768.0
      }
    }
    return buffer
  }

  async function playStreamingWav(response: Response, signal: AbortSignal): Promise<void> {
    if (!response.body) throw new Error('No body')
    const reader = response.body.getReader()
    const HEADER_SIZE = 44

    let headerBuf = new Uint8Array(0)
    while (headerBuf.length < HEADER_SIZE) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      const { done, value } = await reader.read()
      if (done) throw new Error('Stream ended before WAV header')
      const merged = new Uint8Array(headerBuf.length + (value?.length || 0))
      merged.set(headerBuf)
      if (value) merged.set(value, headerBuf.length)
      headerBuf = merged
    }

    const hv = new DataView(headerBuf.buffer, 0, HEADER_SIZE)
    if (String.fromCharCode(hv.getUint8(0), hv.getUint8(1), hv.getUint8(2), hv.getUint8(3)) !== 'RIFF')
      throw new Error('Invalid WAV')

    const numChannels = hv.getUint16(22, true)
    const sampleRate = hv.getUint32(24, true)
    const bitsPerSample = hv.getUint16(34, true)
    const bytesPerFrame = (bitsPerSample / 8) * numChannels

    audioContext = new AudioContext({ sampleRate })
    if (audioContext.state === 'suspended') await audioContext.resume()

    let pcmRemaining = headerBuf.slice(HEADER_SIZE)
    let nextStartTime = audioContext.currentTime + 0.15
    let totalBytes = 0; let bufferCount = 0

    while (true) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      const { done, value } = await reader.read()
      if (done) break
      if (!value || value.length === 0) continue

      const combined = new Uint8Array(pcmRemaining.length + value.length)
      combined.set(pcmRemaining); combined.set(value, pcmRemaining.length)
      const frameBytes = Math.floor(combined.length / bytesPerFrame) * bytesPerFrame

      if (frameBytes > 0) {
        const frameData = combined.slice(0, frameBytes)
        pcmRemaining = combined.slice(frameBytes)
        totalBytes += frameData.length

        const ab = pcmToAudioBuffer(frameData, audioContext, sampleRate, numChannels, bitsPerSample)
        nextStartTime = Math.max(nextStartTime, audioContext.currentTime + 0.01)
        const source = audioContext.createBufferSource()
        source.buffer = ab; source.connect(audioContext.destination)
        source.start(nextStartTime)
        scheduledSources.push(source)
        nextStartTime += ab.duration
        bufferCount++
      }
    }

    if (pcmRemaining.length >= bytesPerFrame && !signal.aborted) {
      const frameBytes = Math.floor(pcmRemaining.length / bytesPerFrame) * bytesPerFrame
      const ab = pcmToAudioBuffer(pcmRemaining.slice(0, frameBytes), audioContext, sampleRate, numChannels, bitsPerSample)
      if (ab.length > 0) {
        nextStartTime = Math.max(nextStartTime, audioContext.currentTime + 0.01)
        const source = audioContext.createBufferSource()
        source.buffer = ab; source.connect(audioContext.destination)
        source.start(nextStartTime)
        scheduledSources.push(source)
        bufferCount++
      }
    }

    if (scheduledSources.length > 0 && !signal.aborted) {
      const last = scheduledSources[scheduledSources.length - 1]
      await new Promise<void>(resolve => {
        last.onended = () => resolve()
        const remaining = Math.max((nextStartTime - audioContext!.currentTime) * 1000 + 2000, 1000)
        setTimeout(resolve, remaining)
      })
    }
    console.log(`[TTS] 流式播放完成: ${totalBytes}B PCM, ${sampleRate}Hz/${numChannels}ch, ${bufferCount} buffers`)
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
