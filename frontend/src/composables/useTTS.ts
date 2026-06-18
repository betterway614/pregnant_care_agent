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

  async function playBlob(blob: Blob): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const url = URL.createObjectURL(blob)
      currentAudio = new Audio(url)
      let settled = false
      const cleanup = () => {
        URL.revokeObjectURL(url)
        currentAudio = null
      }
      const finish = () => {
        if (settled) return
        settled = true
        cleanup()
        resolve()
      }
      const fail = (err: unknown) => {
        if (settled) return
        settled = true
        cleanup()
        reject(err instanceof Error ? err : new Error('音频播放失败'))
      }
      currentAudio.onended = finish
      currentAudio.onerror = () => fail(new Error('音频播放失败'))
      currentAudio.play().catch(fail)
    })
  }

  function appendBytes(a: Uint8Array, b: Uint8Array): Uint8Array {
    if (!a.length) return b
    if (!b.length) return a
    const out = new Uint8Array(a.length + b.length)
    out.set(a)
    out.set(b, a.length)
    return out
  }

  function parseWavHeader(header: Uint8Array): { sampleRate: number; channels: number; bitsPerSample: number } {
    if (header.length < 44) throw new Error('WAV header 不完整')
    const riff = String.fromCharCode(...header.slice(0, 4))
    const wave = String.fromCharCode(...header.slice(8, 12))
    if (riff !== 'RIFF' || wave !== 'WAVE') throw new Error('流式响应不是 WAV')

    const view = new DataView(header.buffer, header.byteOffset, header.byteLength)
    return {
      channels: view.getUint16(22, true),
      sampleRate: view.getUint32(24, true),
      bitsPerSample: view.getUint16(34, true),
    }
  }

  async function getAudioContext(sampleRate: number): Promise<AudioContext> {
    const AudioContextCtor = (
      window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
      (globalThis as typeof globalThis & { AudioContext?: typeof AudioContext }).AudioContext
    )
    if (!AudioContextCtor) throw new Error('浏览器不支持 AudioContext')
    if (!audioContext || audioContext.state === 'closed') {
      audioContext = new AudioContextCtor({ sampleRate })
    }
    if (audioContext.state === 'suspended') await audioContext.resume()
    return audioContext
  }

  function pcm16ToAudioBuffer(
    ctx: AudioContext,
    bytes: Uint8Array,
    sampleRate: number,
    channels: number
  ): AudioBuffer {
    const bytesPerSample = 2
    const frameCount = Math.floor(bytes.length / (bytesPerSample * channels))
    const buffer = ctx.createBuffer(channels, frameCount, sampleRate)
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)

    for (let ch = 0; ch < channels; ch += 1) {
      const channelData = buffer.getChannelData(ch)
      for (let frame = 0; frame < frameCount; frame += 1) {
        const offset = (frame * channels + ch) * bytesPerSample
        channelData[frame] = view.getInt16(offset, true) / 32768
      }
    }

    return buffer
  }

  function hasPcm16Signal(bytes: Uint8Array): boolean {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    for (let offset = 0; offset + 1 < bytes.length; offset += 2) {
      if (view.getInt16(offset, true) !== 0) return true
    }
    return false
  }

  async function playStreamingWav(response: Response, signal: AbortSignal): Promise<void> {
    if (!response.body) throw new Error('流式响应缺少 body')

    const reader = response.body.getReader()
    let headerBytes = new Uint8Array()
    let pending = new Uint8Array()
    let headerParsed = false
    let sampleRate = 24000
    let channels = 1
    let nextStartTime = 0
    let activeSources = 0
    let audioFrames = 0
    let streamDone = false
    let rejected = false
    let resolveDone!: () => void
    let rejectDone!: (reason?: unknown) => void

    const done = new Promise<void>((resolve, reject) => {
      resolveDone = resolve
      rejectDone = reject
    })

    const maybeDone = () => {
      if (!rejected && streamDone && activeSources === 0) resolveDone()
    }
    const fail = (err: unknown) => {
      if (rejected) return
      rejected = true
      rejectDone(err)
    }
    const abortHandler = () => fail(new DOMException('Aborted', 'AbortError'))
    signal.addEventListener('abort', abortHandler)

    const schedulePcm = async (bytes: Uint8Array) => {
      if (!bytes.length) return
      if (!hasPcm16Signal(bytes)) return
      const ctx = await getAudioContext(sampleRate)
      const audioBuffer = pcm16ToAudioBuffer(ctx, bytes, sampleRate, channels)
      if (audioBuffer.length === 0) return
      audioFrames += audioBuffer.length

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)
      source.onended = () => {
        scheduledSources = scheduledSources.filter(s => s !== source)
        activeSources -= 1
        maybeDone()
      }

      const startAt = Math.max(nextStartTime, ctx.currentTime + 0.05)
      nextStartTime = startAt + audioBuffer.duration
      activeSources += 1
      scheduledSources.push(source)
      source.start(startAt)
    }

    const handleBytes = async (chunk: Uint8Array) => {
      let bytes = chunk
      if (!headerParsed) {
        const needed = 44 - headerBytes.length
        if (bytes.length < needed) {
          headerBytes = appendBytes(headerBytes, bytes)
          return
        }

        headerBytes = appendBytes(headerBytes, bytes.slice(0, needed))
        const header = parseWavHeader(headerBytes)
        if (header.bitsPerSample !== 16) {
          throw new Error(`不支持的 WAV 位深: ${header.bitsPerSample}`)
        }
        sampleRate = header.sampleRate
        channels = header.channels
        headerParsed = true
        nextStartTime = (await getAudioContext(sampleRate)).currentTime + 0.08
        bytes = bytes.slice(needed)
      }

      if (pending.length) {
        bytes = appendBytes(pending, bytes)
        pending = new Uint8Array()
      }

      const frameBytes = channels * 2
      const playableLength = bytes.length - (bytes.length % frameBytes)
      if (playableLength <= 0) {
        pending = bytes
        return
      }

      await schedulePcm(bytes.slice(0, playableLength))
      if (playableLength < bytes.length) pending = bytes.slice(playableLength)
    }

    try {
      while (true) {
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
        const { done: readDone, value } = await reader.read()
        if (readDone) break
        if (value) await handleBytes(value)
      }
      if (!headerParsed) throw new Error('流式 WAV header 不完整')
      if (audioFrames === 0) throw new Error('流式音频为空')
      streamDone = true
      maybeDone()
      await done
    } catch (err) {
      fail(err)
      await done
    } finally {
      signal.removeEventListener('abort', abortHandler)
      reader.releaseLock()
    }
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

      try {
        const resp = await fetch('/api/v1/tts/stream', { method: 'POST', headers, body, signal: abortController.signal })
        if (!resp.ok) throw new Error(`流式接口 ${resp.status}: ${await extractError(resp, `HTTP ${resp.status}`)}`)
        await playStreamingWav(resp, abortController.signal)
        return
      } catch (streamErr) {
        if ((streamErr as Error).name === 'AbortError') throw streamErr
        console.warn('[TTS] 流式合成失败，降级到非流式:', (streamErr as Error).message)
      }

      try {
        const resp = await fetch('/api/v1/tts/synthesize', { method: 'POST', headers, body, signal: abortController.signal })
        if (!resp.ok) throw new Error(`非流式接口 ${resp.status}: ${await extractError(resp, `HTTP ${resp.status}`)}`)
        const blob = await resp.blob()
        await playBlob(blob)
      } catch (synthErr) {
        if ((synthErr as Error).name === 'AbortError') throw synthErr
        console.warn('[TTS] 后端合成失败，降级到浏览器 TTS:', (synthErr as Error).message)
        speakBrowser(text); return
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
      scheduledSources.forEach(s => { try { s.stop() } catch { /* already stopped */ } })
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
