import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAudioRecorder } from '../../composables/useAudioRecorder'

// Mock MediaRecorder
class MockMediaRecorder {
  mimeType = 'audio/webm;codecs=opus'
  state = 'inactive'
  stream = { getTracks: () => [{ stop: vi.fn() }] }
  ondataavailable: ((e: any) => void) | null = null
  onstop: (() => void) | null = null

  start() { this.state = 'recording' }
  stop() { this.state = 'inactive'; this.onstop?.() }
}

// Mock getUserMedia
Object.defineProperty(navigator, 'mediaDevices', {
  value: {
    getUserMedia: vi.fn().mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }],
    }),
  },
})

// Mock MediaRecorder globally
;(globalThis as any).MediaRecorder = MockMediaRecorder
;(globalThis as any).MediaRecorder.isTypeSupported = vi.fn().mockReturnValue(true)

describe('useAudioRecorder', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should initialize with default state', () => {
    const recorder = useAudioRecorder()
    expect(recorder.isRecording.value).toBe(false)
    expect(recorder.isInCancelZone.value).toBe(false)
    expect(recorder.recordingText.value).toBe('0:00')
  })

  it('should have startRecording function', () => {
    const recorder = useAudioRecorder()
    expect(typeof recorder.startRecording).toBe('function')
  })

  it('should have formatDuration function', () => {
    const recorder = useAudioRecorder()
    expect(recorder.formatDuration(0)).toBe('0:00')
    expect(recorder.formatDuration(5)).toBe('0:05')
    expect(recorder.formatDuration(65)).toBe('1:05')
    expect(recorder.formatDuration(125)).toBe('2:05')
  })

  it('should accept onComplete callback', () => {
    const onComplete = vi.fn()
    const recorder = useAudioRecorder({ onComplete })
    expect(recorder).toBeDefined()
  })

  it('should accept onCancel callback', () => {
    const onCancel = vi.fn()
    const recorder = useAudioRecorder({ onCancel })
    expect(recorder).toBeDefined()
  })

  it('should accept custom options', () => {
    const recorder = useAudioRecorder({
      minDuration: 2,
      cancelZoneThreshold: 0.5,
    })
    expect(recorder).toBeDefined()
  })

  it('should return readonly refs', () => {
    const recorder = useAudioRecorder()
    // readonly refs should not have .value setter issues
    expect(recorder.isRecording.value).toBe(false)
    expect(recorder.isInCancelZone.value).toBe(false)
    expect(typeof recorder.recordingText.value).toBe('string')
  })
})
