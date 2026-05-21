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
