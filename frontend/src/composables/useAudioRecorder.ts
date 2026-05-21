import { ref, readonly } from 'vue'

export interface AudioRecorderResult {
  base64: string
  format: string
  duration: number
  blob: Blob
}

export interface AudioRecorderOptions {
  minDuration?: number
  cancelZoneThreshold?: number
  onComplete?: (result: AudioRecorderResult) => void
  onCancel?: () => void
  onError?: (err: Error) => void
}

export function useAudioRecorder(options: AudioRecorderOptions = {}) {
  const minDuration = options.minDuration ?? 1
  const cancelZoneThreshold = options.cancelZoneThreshold ?? 0.3

  const isRecording = ref(false)
  const isInCancelZone = ref(false)
  const recordingText = ref('0:00')

  let mediaRecorder: MediaRecorder | null = null
  let audioChunks: Blob[] = []
  let recordingTimer: ReturnType<typeof setInterval> | null = null
  let recordingSeconds = 0
  let shouldSendAudio = false

  function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return m + ':' + s.toString().padStart(2, '0')
  }

  function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => {
        const result = reader.result as string
        resolve(result.split(',')[1] || '')
      }
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })
  }

  async function startRecording(_e: PointerEvent): Promise<void> {
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

      mediaRecorder.onstop = async () => {
        mediaRecorder!.stream.getTracks().forEach((t: MediaStreamTrack) => t.stop())
        clearInterval(recordingTimer!)

        if (!shouldSendAudio || isInCancelZone.value || audioChunks.length === 0 || recordingSeconds < minDuration) {
          audioChunks = []
          isRecording.value = false
          isInCancelZone.value = false
          options.onCancel?.()
          return
        }

        const audioBlob = new Blob(audioChunks, { type: mediaRecorder!.mimeType || 'audio/webm' })
        const mt = mediaRecorder!.mimeType || ''
        const audioFormat = mt.includes('ogg') ? 'ogg' : mt.includes('webm') ? 'webm' : mt.includes('mp4') ? 'mp4' : 'wav'

        if (audioBlob.size === 0) {
          audioChunks = []
          isRecording.value = false
          isInCancelZone.value = false
          options.onCancel?.()
          return
        }

        recordingText.value = '处理中...'

        try {
          const base64 = await blobToBase64(audioBlob)
          if (!base64) throw new Error('音频编码失败')
          isRecording.value = false
          isInCancelZone.value = false
          options.onComplete?.({ base64, format: audioFormat, duration: recordingSeconds, blob: audioBlob })
        } catch (err) {
          console.error('音频处理失败:', err)
          isRecording.value = false
          isInCancelZone.value = false
          options.onError?.(err as Error)
        }
      }

      mediaRecorder.start(1000)
      recordingTimer = setInterval(() => {
        recordingSeconds++
        recordingText.value = formatDuration(recordingSeconds)
      }, 1000)

      document.addEventListener('pointermove', onPointerMove)
      document.addEventListener('pointerup', onPointerUp)
      document.addEventListener('pointercancel', onPointerUp)
    } catch (err) {
      console.error('麦克风访问失败:', err)
      isRecording.value = false
      options.onError?.(err as Error)
    }
  }

  function onPointerMove(e: PointerEvent) {
    if (!isRecording.value) return
    isInCancelZone.value = e.clientY < window.innerHeight * cancelZoneThreshold
  }

  function onPointerUp(_e: PointerEvent) {
    if (!isRecording.value) return
    document.removeEventListener('pointermove', onPointerMove)
    document.removeEventListener('pointerup', onPointerUp)
    document.removeEventListener('pointercancel', onPointerUp)

    if (mediaRecorder?.state !== 'recording') {
      isRecording.value = false
      isInCancelZone.value = false
      return
    }

    shouldSendAudio = !isInCancelZone.value
    mediaRecorder.stop()
  }

  return {
    isRecording: readonly(isRecording),
    isInCancelZone: readonly(isInCancelZone),
    recordingText: readonly(recordingText),
    startRecording,
    formatDuration,
  }
}
