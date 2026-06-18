// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTTS } from '../../composables/useTTS'

// Mock SpeechSynthesis
const mockSpeak = vi.fn()
const mockCancel = vi.fn()
const mockGetVoices = vi.fn().mockReturnValue([])

Object.defineProperty(window, 'speechSynthesis', {
  value: {
    speak: mockSpeak,
    cancel: mockCancel,
    getVoices: mockGetVoices,
  },
  writable: true,
})

;(globalThis as any).SpeechSynthesisUtterance = class {
  text: string
  lang = ''
  rate = 1
  pitch = 1
  voice: any = null
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(text: string) { this.text = text }
}

describe('useTTS', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('should initialize with default state', () => {
    const tts = useTTS()
    expect(tts.isSpeaking.value).toBe(false)
    expect(tts.isSupported.value).toBe(true)
  })

  it('should have speak function', () => {
    const tts = useTTS()
    expect(typeof tts.speak).toBe('function')
  })

  it('should have stop function', () => {
    const tts = useTTS()
    expect(typeof tts.stop).toBe('function')
  })

  it('should have cleanForTTS function', () => {
    const tts = useTTS()
    expect(typeof tts.cleanForTTS).toBe('function')
  })

  describe('cleanForTTS', () => {
    it('should strip markdown bold', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('**你好**')).toBe('你好')
    })

    it('should strip markdown italic', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('*你好*')).toBe('你好')
    })

    it('should strip code blocks', () => {
      const tts = useTTS()
      const input = '前文\n```python\nprint("hi")\n```\n后文'
      const result = tts.cleanForTTS(input)
      expect(result).not.toContain('```')
      expect(result).not.toContain('print')
    })

    it('should strip inline code', () => {
      const tts = useTTS()
      const result = tts.cleanForTTS('使用 `code` 工具')
      expect(result).not.toContain('`')
      expect(result).toContain('工具')
    })

    it('should strip HTML tags', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('<p>你好</p>')).toBe('你好')
    })

    it('should strip markdown links', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('[链接](https://example.com)')).toBe('链接')
    })

    it('should strip heading markers', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('## 标题')).toBe('标题')
    })

    it('should handle empty string', () => {
      const tts = useTTS()
      expect(tts.cleanForTTS('')).toBe('')
    })

    it('should truncate to 500 chars', () => {
      const tts = useTTS()
      const longText = '你'.repeat(600)
      const result = tts.cleanForTTS(longText)
      expect(result.length).toBeLessThanOrEqual(500)
    })

    it('should replace newlines with punctuation', () => {
      const tts = useTTS()
      const result = tts.cleanForTTS('第一行\n第二行')
      expect(result).not.toContain('\n')
    })
  })

  describe('speak', () => {
    it('should call speechSynthesis.speak in browser mode', async () => {
      const tts = useTTS({ mode: 'browser' })
      await tts.speak('你好')
      expect(mockCancel).toHaveBeenCalled()
      expect(mockSpeak).toHaveBeenCalled()
    })

    it('should use streaming backend synthesis first', async () => {
      localStorage.setItem('token', 'test-token')

      const wavHeader = new Uint8Array(44)
      const view = new DataView(wavHeader.buffer)
      wavHeader.set([82, 73, 70, 70], 0) // RIFF
      wavHeader.set([87, 65, 86, 69], 8) // WAVE
      view.setUint16(20, 1, true)
      view.setUint16(22, 1, true)
      view.setUint32(24, 24000, true)
      view.setUint16(34, 16, true)
      const pcm = new Uint8Array([0, 0, 255, 127])
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(wavHeader)
          controller.enqueue(pcm)
          controller.close()
        },
      })

      const starts: number[] = []
      class MockAudioBuffer {
        duration: number
        private data: Float32Array
        constructor(length: number, sampleRate: number) {
          this.duration = length / sampleRate
          this.data = new Float32Array(length)
        }
        getChannelData() { return this.data }
      }
      class MockSource {
        buffer: MockAudioBuffer | null = null
        onended: (() => void) | null = null
        connect() {}
        start(when: number) {
          starts.push(when)
          this.onended?.()
        }
        stop() {}
      }
      class MockAudioContext {
        currentTime = 0
        state = 'running'
        destination = {}
        createBuffer(channels: number, length: number, sampleRate: number) {
          expect(channels).toBe(1)
          return new MockAudioBuffer(length, sampleRate)
        }
        createBufferSource() { return new MockSource() }
        resume() { return Promise.resolve() }
        close() { return Promise.resolve() }
      }
      class MockAudio {
        src: string
        onended: (() => void) | null = null
        onerror: (() => void) | null = null
        constructor(src: string) { this.src = src }
        play() {
          this.onended?.()
          return Promise.resolve()
        }
        pause() {}
      }

      vi.stubGlobal('AudioContext', MockAudioContext)
      vi.stubGlobal('Audio', MockAudio)
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:tts')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
      const fetchMock = vi.fn(async () => new Response(new Blob(['wav-bytes'], { type: 'audio/wav' }), {
        status: 200,
        headers: { 'Content-Type': 'audio/wav' },
      }))
      fetchMock.mockResolvedValueOnce(new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'audio/wav' },
      }))
      vi.stubGlobal('fetch', fetchMock)

      const tts = useTTS({ mode: 'backend', role: 'pregnant' })
      await tts.speak('你好')

      expect(fetchMock).toHaveBeenCalledTimes(1)
      const fetchCalls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
      expect(fetchCalls[0][0]).toBe('/api/v1/tts/stream')
      const [, requestInit] = fetchCalls[0]
      expect(JSON.parse(String(requestInit.body))).toMatchObject({
        text: '你好',
        role: 'pregnant',
      })
      expect(starts.length).toBeGreaterThan(0)
    })

    it('should fall back to non-stream synthesis when streaming audio is silent', async () => {
      const wavHeader = new Uint8Array(44)
      const view = new DataView(wavHeader.buffer)
      wavHeader.set([82, 73, 70, 70], 0) // RIFF
      wavHeader.set([87, 65, 86, 69], 8) // WAVE
      view.setUint16(20, 1, true)
      view.setUint16(22, 1, true)
      view.setUint32(24, 24000, true)
      view.setUint16(34, 16, true)
      const silentPcm = new Uint8Array([0, 0, 0, 0, 0, 0, 0, 0])
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(wavHeader)
          controller.enqueue(silentPcm)
          controller.close()
        },
      })

      class MockAudioBuffer {
        length: number
        duration: number
        private data: Float32Array
        constructor(length: number, sampleRate: number) {
          this.length = length
          this.duration = length / sampleRate
          this.data = new Float32Array(length)
        }
        getChannelData() { return this.data }
      }
      class MockSource {
        buffer: MockAudioBuffer | null = null
        onended: (() => void) | null = null
        connect() {}
        start() { this.onended?.() }
        stop() {}
      }
      class MockAudioContext {
        currentTime = 0
        state = 'running'
        destination = {}
        createBuffer(channels: number, length: number, sampleRate: number) {
          return new MockAudioBuffer(length, sampleRate)
        }
        createBufferSource() { return new MockSource() }
        resume() { return Promise.resolve() }
        close() { return Promise.resolve() }
      }
      class MockAudio {
        src: string
        onended: (() => void) | null = null
        onerror: (() => void) | null = null
        constructor(src: string) { this.src = src }
        play() {
          this.onended?.()
          return Promise.resolve()
        }
        pause() {}
      }

      vi.stubGlobal('AudioContext', MockAudioContext)
      vi.stubGlobal('Audio', MockAudio)
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:tts')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(new Response(stream, {
          status: 200,
          headers: { 'Content-Type': 'audio/wav' },
        }))
        .mockResolvedValueOnce(new Response(new Blob(['wav-bytes'], { type: 'audio/wav' }), {
          status: 200,
          headers: { 'Content-Type': 'audio/wav' },
        }))
      vi.stubGlobal('fetch', fetchMock)

      const tts = useTTS({ mode: 'backend', role: 'pregnant' })
      await tts.speak('你好')

      const fetchCalls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
      expect(fetchCalls.map(call => call[0])).toEqual([
        '/api/v1/tts/stream',
        '/api/v1/tts/synthesize',
      ])
    })

    it('should fall back to browser speech when backend audio playback is rejected', async () => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:tts')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

      class MockAudio {
        src: string
        onended: (() => void) | null = null
        onerror: (() => void) | null = null
        constructor(src: string) { this.src = src }
        play() {
          return Promise.reject(new DOMException('NotAllowedError', 'NotAllowedError'))
        }
        pause() {}
      }

      vi.stubGlobal('Audio', MockAudio)
      vi.stubGlobal('fetch', vi.fn(async () => new Response(new Blob(['wav-bytes'], { type: 'audio/wav' }), {
        status: 200,
        headers: { 'Content-Type': 'audio/wav' },
      })))

      const tts = useTTS({ mode: 'backend' })
      await tts.speak('你好')

      expect(mockSpeak).toHaveBeenCalled()
    })

    it('should not speak empty text', async () => {
      const tts = useTTS({ mode: 'browser' })
      await tts.speak('')
      expect(mockSpeak).not.toHaveBeenCalled()
    })

    it('should not speak whitespace-only text', async () => {
      const tts = useTTS({ mode: 'browser' })
      await tts.speak('   ')
      expect(mockSpeak).not.toHaveBeenCalled()
    })
  })

  describe('stop', () => {
    it('should call speechSynthesis.cancel', () => {
      const tts = useTTS()
      tts.stop()
      expect(mockCancel).toHaveBeenCalled()
    })

    it('should set isSpeaking to false', () => {
      const tts = useTTS()
      tts.stop()
      expect(tts.isSpeaking.value).toBe(false)
    })
  })

  describe('options', () => {
    it('should accept custom role', () => {
      const tts = useTTS({ role: 'nurse' })
      expect(tts).toBeDefined()
    })

    it('should accept custom lang', () => {
      const tts = useTTS({ lang: 'en-US' })
      expect(tts).toBeDefined()
    })

    it('should accept custom rate', () => {
      const tts = useTTS({ rate: 1.5 })
      expect(tts).toBeDefined()
    })
  })
})
