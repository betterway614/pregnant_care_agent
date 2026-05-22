<template>
  <div class="signature-pad">
    <div class="signature-pad__label">{{ label }}</div>
    <div class="signature-pad__canvas-wrap" ref="canvasWrap">
      <canvas
        ref="canvasEl"
        class="signature-pad__canvas"
        @mousedown="startDraw"
        @mousemove="draw"
        @mouseup="endDraw"
        @mouseleave="endDraw"
        @touchstart.prevent="startDrawTouch"
        @touchmove.prevent="drawTouch"
        @touchend.prevent="endDraw"
      />
      <div v-if="!hasDrawn" class="signature-pad__placeholder">在此处手写签名</div>
    </div>
    <div class="signature-pad__actions">
      <el-button size="small" @click="clear" :disabled="!hasDrawn">清除重签</el-button>
      <slot name="actions" :data-url="dataUrl" :has-drawn="hasDrawn" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

const props = defineProps<{
  label?: string
  width?: number
  height?: number
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
const canvasWrap = ref<HTMLDivElement | null>(null)
const ctx = ref<CanvasRenderingContext2D | null>(null)
const drawing = ref(false)
const hasDrawn = ref(false)
const dataUrl = ref('')

onMounted(() => {
  if (!canvasEl.value) return
  const w = props.width || 400
  const h = props.height || 150
  canvasEl.value.width = w
  canvasEl.value.height = h
  ctx.value = canvasEl.value.getContext('2d')
  if (ctx.value) {
    ctx.value.strokeStyle = '#333'
    ctx.value.lineWidth = 2
    ctx.value.lineCap = 'round'
    ctx.value.lineJoin = 'round'
  }
})

function getPos(e: MouseEvent) {
  const rect = canvasEl.value!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function startDraw(e: MouseEvent) {
  drawing.value = true
  const pos = getPos(e)
  ctx.value?.beginPath()
  ctx.value?.moveTo(pos.x, pos.y)
}

function draw(e: MouseEvent) {
  if (!drawing.value) return
  const pos = getPos(e)
  ctx.value?.lineTo(pos.x, pos.y)
  ctx.value?.stroke()
  hasDrawn.value = true
}

function endDraw() {
  drawing.value = false
  if (canvasEl.value && hasDrawn.value) {
    dataUrl.value = canvasEl.value.toDataURL('image/png')
  }
}

function getTouchPos(e: TouchEvent) {
  const rect = canvasEl.value!.getBoundingClientRect()
  const t = e.touches[0]
  return { x: t.clientX - rect.left, y: t.clientY - rect.top }
}

function startDrawTouch(e: TouchEvent) {
  drawing.value = true
  const pos = getTouchPos(e)
  ctx.value?.beginPath()
  ctx.value?.moveTo(pos.x, pos.y)
}

function drawTouch(e: TouchEvent) {
  if (!drawing.value) return
  const pos = getTouchPos(e)
  ctx.value?.lineTo(pos.x, pos.y)
  ctx.value?.stroke()
  hasDrawn.value = true
}

function clear() {
  if (!canvasEl.value || !ctx.value) return
  ctx.value.clearRect(0, 0, canvasEl.value.width, canvasEl.value.height)
  hasDrawn.value = false
  dataUrl.value = ''
}

defineExpose({ dataUrl, hasDrawn, clear })
</script>

<style scoped>
.signature-pad {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.signature-pad__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.signature-pad__canvas-wrap {
  position: relative;
  border: 1.5px dashed #ccc;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.signature-pad__canvas {
  display: block;
  cursor: crosshair;
  touch-action: none;
}
.signature-pad__placeholder {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 14px;
  color: #ccc;
  pointer-events: none;
}
.signature-pad__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
