<template>
  <div class="page-container">
    <div class="sub-page-header">
      <el-page-header @back="$router.back()">
        <template #content>快速录入</template>
      </el-page-header>
    </div>

    <div class="patient-info-card">
      <div class="patient-info-card__title"><span class="dot"></span>快速录入</div>
      <div class="health-form">
        <div class="health-field">
          <span class="health-field__label">体重</span>
          <div class="health-field__input">
            <input v-model.number="form.weight" type="number" step="0.1" min="0" max="200" placeholder="65.5" class="health-input" />
            <span class="health-field__unit">kg</span>
          </div>
        </div>
        <div class="health-field">
          <span class="health-field__label">血压</span>
          <div class="health-field__input bp-row">
            <input v-model.number="form.systolic" type="number" min="0" max="300" placeholder="120" class="health-input health-input--half" />
            <span class="bp-sep">/</span>
            <input v-model.number="form.diastolic" type="number" min="0" max="200" placeholder="80" class="health-input health-input--half" />
            <span class="health-field__unit">mmHg</span>
          </div>
        </div>
        <div class="health-field">
          <span class="health-field__label">胎动（最近1小时）</span>
          <div class="health-field__input">
            <input v-model.number="form.fetalMovement" type="number" step="1" min="0" max="50" placeholder="每小时次数" class="health-input" />
            <span class="health-field__unit">次/小时</span>
          </div>
        </div>
        <div class="health-field">
          <span class="health-field__label">情绪</span>
          <div class="mood-row">
            <button v-for="m in moods" :key="m.value" class="mood-btn" :class="{ active: form.mood === m.value }" @click="form.mood = m.value" type="button">
              <span class="mood-emoji">{{ m.emoji }}</span>
              <span class="mood-text">{{ m.label }}</span>
            </button>
          </div>
        </div>
        <button class="save-btn" :disabled="saving || !hasData" @click="saveAll">
          {{ saving ? '保存中...' : '保存全部' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { pregnantApi } from '@/api/endpoints'
import { ElMessage } from 'element-plus'

const form = reactive({
  weight: null as number | null,
  systolic: null as number | null,
  diastolic: null as number | null,
  fetalMovement: null as number | null,
  mood: '' as string,
})

const moods = [
  { emoji: '😊', label: '好', value: 'good' },
  { emoji: '😐', label: '一般', value: 'neutral' },
  { emoji: '😟', label: '差', value: 'bad' },
]

const saving = ref(false)
const pregnantId = computed(() => localStorage.getItem('currentPregnantId') || '')

const hasData = computed(() =>
  form.weight != null || form.systolic != null || form.diastolic != null ||
  form.fetalMovement != null || form.mood
)

async function saveAll() {
  if (!hasData.value) return
  saving.value = true
  try {
    const payload: Record<string, any> = {}
    if (form.weight != null) payload.weight = form.weight
    if (form.systolic != null) payload.systolic = form.systolic
    if (form.diastolic != null) payload.diastolic = form.diastolic
    if (form.fetalMovement != null) payload.fetal_movement = form.fetalMovement
    if (form.mood) payload.mood = form.mood

    const res = await pregnantApi.submitHealthData(pregnantId.value, payload)
    if (res.data.success) {
      ElMessage.success(res.data.message || '保存成功')
      form.weight = null; form.systolic = null; form.diastolic = null
      form.fetalMovement = null; form.mood = ''
    } else { ElMessage.error('保存失败') }
  } catch { ElMessage.error('保存失败') } finally { saving.value = false }
}
</script>

<style scoped>
.page-container { overflow-y: auto; -webkit-overflow-scrolling: touch; height: 100%; box-sizing: border-box; padding-bottom: 24px; }
.sub-page-header { margin: 12px 16px; padding: 12px 16px; border-radius: 16px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04); border: 1px solid rgba(255, 255, 255, 0.5); background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); position: sticky; top: 12px; z-index: 10; }
.health-form { display: flex; flex-direction: column; gap: 16px; }
.health-field { display: flex; flex-direction: column; gap: 6px; }
.health-field__label { font-size: 13px; font-weight: 600; color: var(--pt-text-secondary); }
.health-field__input { display: flex; align-items: center; gap: 8px; }
.health-input { flex: 1; height: 44px; border: 2px solid var(--pt-border); border-radius: 12px; padding: 0 14px; font-size: 16px; font-family: 'Figtree', sans-serif; font-weight: 600; color: var(--pt-text); background: #FAFAFA; outline: none; transition: border-color 0.2s; width: 100%; min-width: 0; -moz-appearance: textfield; box-sizing: border-box; }
.health-input::-webkit-outer-spin-button, .health-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.health-input:focus { border-color: var(--pt-primary); background: #fff; }
.health-input::placeholder { color: var(--pt-text-muted); font-weight: 400; }
.health-input--half { flex: 1; min-width: 0; }
.health-field__unit { font-size: 13px; color: var(--pt-text-muted); white-space: nowrap; flex-shrink: 0; }
.bp-row { display: flex; align-items: center; gap: 4px; }
.bp-sep { font-size: 18px; font-weight: 700; color: var(--pt-text-muted); flex-shrink: 0; }
.mood-row { display: flex; gap: 8px; }
.mood-btn { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 8px; border: 2px solid var(--pt-border); border-radius: 14px; background: #FAFAFA; cursor: pointer; transition: all 0.2s; font-size: 12px; color: var(--pt-text-secondary); font-family: inherit; }
.mood-btn.active { border-color: var(--pt-primary); background: var(--pt-primary-light); }
.mood-btn:active { transform: scale(0.96); }
.mood-emoji { font-size: 28px; line-height: 1; }
.mood-text { font-weight: 500; }
.save-btn { width: 100%; height: 48px; border: none; border-radius: 14px; background: linear-gradient(135deg, var(--pt-primary), var(--pt-primary-dark)); color: #fff; font-size: 16px; font-weight: 700; font-family: 'Figtree', sans-serif; cursor: pointer; transition: all 0.2s; margin-top: 4px; }
.save-btn:active { transform: scale(0.98); }
.save-btn:disabled { background: #E0D8E8; color: #B0A8BC; cursor: not-allowed; }
</style>
