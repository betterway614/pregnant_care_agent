<template>
  <div class="page-container">
    <div class="sub-page-header">
      <el-page-header @back="$router.back()">
        <template #content>{{ pageTitle }}</template>
      </el-page-header>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner" />
      <span class="loading-text">加载中...</span>
    </div>

    <!-- 无待处理随访 -->
    <div v-else-if="!pending.has_pending && !completed" class="empty-state">
      <div class="empty-icon-wrap">
        <span class="empty-icon-text">✓</span>
      </div>
      <p class="empty-title">暂无待完成的随访</p>
      <p class="empty-desc">所有随访已完成，感谢配合</p>
      <button class="btn btn--outline" @click="$router.back()">返回</button>
    </div>

    <!-- 随访表单 -->
    <template v-else-if="!completed">
      <!-- 顶部信息卡 -->
      <div class="info-banner">
        <div class="info-banner__left">
          <div class="info-banner__name">{{ pending.patient_name }}</div>
          <div class="info-banner__meta">{{ pending.template_name }}</div>
        </div>
        <div class="info-banner__right">
          <div class="progress-ring">
            <svg viewBox="0 0 36 36" class="progress-ring__svg">
              <path
                class="progress-ring__bg"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                class="progress-ring__fill"
                :stroke-dasharray="`${progressPercent}, 100`"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <span class="progress-ring__text">{{ filledCount }}/{{ totalCount }}</span>
          </div>
        </div>
      </div>

      <!-- 表单列表 -->
      <div class="form-list">
        <div
          v-for="(q, idx) in pending.questions"
          :key="q.key"
          class="form-card"
          :class="{ 'form-card--done': q.answered || isFieldFilled(q) }"
        >
          <div class="form-card__header">
            <span class="form-card__index">{{ idx + 1 }}</span>
            <span class="form-card__question">{{ q.question }}</span>
            <span v-if="q.answered || isFieldFilled(q)" class="form-card__check">✓</span>
          </div>

          <!-- 血压双输入框 -->
          <div v-if="q.format === 'sbp/dbp'" class="form-card__body">
            <div class="bp-input-group">
              <input
                v-model.number="formData[q.key].sbp"
                type="number"
                inputmode="numeric"
                min="0"
                max="300"
                placeholder="收缩压"
                class="field-input field-input--half"
                :disabled="q.answered"
              />
              <span class="bp-separator">/</span>
              <input
                v-model.number="formData[q.key].dbp"
                type="number"
                inputmode="numeric"
                min="0"
                max="200"
                placeholder="舒张压"
                class="field-input field-input--half"
                :disabled="q.answered"
              />
              <span class="field-unit">mmHg</span>
            </div>
          </div>

          <!-- 数字输入框 -->
          <div v-else-if="q.type === 'number'" class="form-card__body">
            <div class="number-input-wrap">
              <input
                v-model.number="formData[q.key].value"
                type="number"
                inputmode="decimal"
                step="0.1"
                min="0"
                :placeholder="getPlaceholder(q.key)"
                class="field-input"
                :disabled="q.answered"
              />
              <span v-if="q.unit" class="field-unit">{{ q.unit }}</span>
              <span v-if="q.target" class="field-target">{{ q.target }}</span>
            </div>
          </div>

          <!-- 文本输入框 -->
          <div v-else class="form-card__body">
            <textarea
              v-model="formData[q.key].value"
              :rows="isLongText(q.key) ? 3 : 2"
              :placeholder="getPlaceholder(q.key)"
              class="field-textarea"
              :class="{ 'field-textarea--long': isLongText(q.key) }"
              :disabled="q.answered"
            />
          </div>
        </div>
      </div>

      <!-- 底部提交栏 -->
      <div class="submit-bar">
        <button
          class="btn btn--primary btn--block"
          :disabled="submitting || !hasFilledFields"
          @click="handleSubmit"
        >
          <span v-if="submitting" class="btn-spinner" />
          {{ submitting ? '提交中...' : '提交随访' }}
        </button>
      </div>
    </template>

    <!-- 完成后：汇总卡片 -->
    <template v-else>
      <div class="completion-view">
        <!-- 完成头部 -->
        <div class="completion-hero">
          <div class="completion-check">
            <span class="completion-check-icon">✓</span>
          </div>
          <h2 class="completion-title">随访完成</h2>
          <p class="completion-subtitle">感谢 {{ pending.patient_name }} 的配合</p>
        </div>

        <!-- LLM 温馨总结 -->
        <div v-if="summary" class="summary-card">
          <div class="summary-card__header">
            <span class="summary-card__avatar">🤖</span>
            <span class="summary-card__name">小安的总结</span>
          </div>
          <div class="summary-card__body">{{ summary }}</div>
        </div>

        <!-- 异常指标警告 -->
        <div v-if="analysisReport?.abnormal_indicators?.length" class="alert-card">
          <div class="alert-card__header">
            <span class="alert-card__icon">⚠</span>
            <span class="alert-card__title">需关注指标</span>
          </div>
          <ul class="alert-card__list">
            <li v-for="(item, i) in analysisReport.abnormal_indicators" :key="i">{{ item }}</li>
          </ul>
        </div>

        <!-- 趋势分析 -->
        <div v-if="analysisReport?.trend_analysis" class="info-card">
          <div class="info-card__header">📊 趋势分析</div>
          <div class="info-card__body">{{ analysisReport.trend_analysis }}</div>
        </div>

        <!-- 个性化建议 -->
        <div v-if="analysisReport?.personalized_advice" class="advice-card">
          <div class="advice-card__header">💡 个性化建议</div>
          <div class="advice-card__body">{{ analysisReport.personalized_advice }}</div>
        </div>

        <!-- 健康教育 -->
        <div v-if="healthEducation.length" class="education-card">
          <div class="education-card__title">健康提示</div>
          <ul class="education-card__list">
            <li v-for="(item, i) in healthEducation" :key="i">{{ item }}</li>
          </ul>
        </div>

        <button class="btn btn--outline btn--block" @click="$router.push('/pregnant/home')">
          返回首页
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { followUpApi } from '@/api/endpoints'
import { ElMessage } from 'element-plus'

interface FollowUpQuestion {
  key: string
  question: string
  type: 'text' | 'number'
  unit?: string
  target?: string
  format?: string
  answered?: boolean
  answer?: any
}

interface PendingData {
  record_id: string
  patient_name: string
  template_id: string
  template_name: string
  questions: FollowUpQuestion[]
  answered_count: number
  total_count: number
  has_pending: boolean
  health_education: string[]
}

const route = useRoute()
const loading = ref(true)
const submitting = ref(false)
const completed = ref(false)
const summary = ref('')
const healthEducation = ref<string[]>([])
const analysisReport = ref<{
  warm_summary: string
  abnormal_indicators: string[]
  trend_analysis: string
  personalized_advice: string
  nurse_action_suggestion: string
} | null>(null)

const pending = ref<PendingData>({
  record_id: '',
  patient_name: '',
  template_id: '',
  template_name: '',
  questions: [],
  answered_count: 0,
  total_count: 0,
  has_pending: false,
  health_education: [],
})

const formData = reactive<Record<string, any>>({})

const pageTitle = computed(() =>
  completed.value ? '随访完成' : pending.value.template_name || '随访'
)

const gestWeek = computed(() => '?')

// 已回答数（后端标记）
const answeredCount = computed(() =>
  pending.value.questions.filter((q) => q.answered).length
)

// 总问题数
const totalCount = computed(() => pending.value.questions.length)

// 已填写数（后端已回答 + 前端新填写）
const filledCount = computed(() => {
  let count = answeredCount.value
  for (const q of pending.value.questions) {
    if (q.answered) continue
    if (isFieldFilled(q)) count++
  }
  return count
})

// 进度百分比
const progressPercent = computed(() =>
  totalCount.value > 0 ? Math.round((filledCount.value / totalCount.value) * 100) : 0
)

// 是否有新填写的字段（可提交）
const hasFilledFields = computed(() => {
  return pending.value.questions.some((q) => {
    if (q.answered) return false
    return isFieldFilled(q)
  })
})

function isFieldFilled(q: FollowUpQuestion): boolean {
  const v = formData[q.key]
  if (!v) return false
  if (q.format === 'sbp/dbp') return v.sbp != null && v.sbp !== '' && v.dbp != null && v.dbp !== ''
  return v.value != null && v.value !== ''
}

function isLongText(key: string): boolean {
  return ['feeling', 'diet', 'nutrition', 'stress', 'coping'].includes(key)
}

function getPlaceholder(key: string): string {
  const map: Record<string, string> = {
    feeling: '请描述最近的身体感受...',
    weight: '请输入体重',
    bp: '收缩压',
    fetal_movement: '每小时胎动次数',
    diet: '请描述饮食和睡眠情况...',
    blood_sugar_fasting: '空腹血糖值',
    blood_sugar_postprandial: '餐后血糖值',
    exercise: '运动情况...',
    medication: '用药情况...',
    edema: '水肿情况...',
    mood: '最近心情如何...',
    sleep: '睡眠情况...',
  }
  return map[key] || '请输入...'
}

function initFormData(questions: FollowUpQuestion[]) {
  for (const q of questions) {
    if (q.format === 'sbp/dbp') {
      if (q.answered && typeof q.answer === 'string' && q.answer.includes('/')) {
        const [s, d] = q.answer.split('/')
        formData[q.key] = { sbp: Number(s), dbp: Number(d) }
      } else {
        formData[q.key] = { sbp: null, dbp: null }
      }
    } else {
      formData[q.key] = { value: q.answered ? q.answer : null }
    }
  }
}

async function loadPending() {
  const pregnantId = localStorage.getItem('currentPregnantId') || ''
  if (!pregnantId) {
    loading.value = false
    return
  }
  try {
    const res = await followUpApi.getPending(pregnantId)
    pending.value = res.data as PendingData
    healthEducation.value = (res.data as any).health_education || []
    initFormData(pending.value.questions)
  } catch {
    ElMessage.error('加载随访数据失败')
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  if (!hasFilledFields.value) return
  submitting.value = true

  const answers: Record<string, any> = {}
  for (const q of pending.value.questions) {
    if (q.answered) continue
    const v = formData[q.key]
    if (!v) continue
    if (q.format === 'sbp/dbp') {
      if (v.sbp != null && v.dbp != null) answers[q.key] = `${v.sbp}/${v.dbp}`
    } else if (v.value != null && v.value !== '') {
      answers[q.key] = v.value
    }
  }

  if (Object.keys(answers).length === 0) {
    ElMessage.warning('请至少填写一项')
    submitting.value = false
    return
  }

  try {
    const res = await followUpApi.respond(pending.value.record_id, answers, totalCount.value)
    const data = res.data as any
    if (data.status === 'completed') {
      completed.value = true
      summary.value = data.summary || ''
      if (data.analysis_report) {
        analysisReport.value = data.analysis_report
      }
      healthEducation.value = pending.value.health_education || []
      ElMessage.success('随访已完成，护士会尽快审核')
    } else {
      ElMessage.success('已保存')
      loading.value = true
      await loadPending()
    }
  } catch {
    ElMessage.error('提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

onMounted(loadPending)
</script>

<style scoped>
/* ===== 基础布局 ===== */
.page-container {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  height: 100%;
  box-sizing: border-box;
  padding-bottom: 80px;
}
.sub-page-header {
  margin: 12px 16px;
  padding: 12px 16px;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(255,255,255,0.5);
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  position: sticky;
  top: 12px;
  z-index: 10;
}

/* ===== 加载状态 ===== */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 0;
}
.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(244, 143, 177, 0.2);
  border-top-color: var(--pt-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { font-size: 13px; color: var(--pt-text-muted); }

/* ===== 空状态 ===== */
.empty-state {
  text-align: center;
  padding: 80px 24px 40px;
}
.empty-icon-wrap {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #E8F5E9, #C8E6C9);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}
.empty-icon-text { font-size: 28px; color: #4CAF50; font-weight: 700; }
.empty-title { font-size: 17px; font-weight: 700; color: var(--pt-text); margin: 0 0 6px; }
.empty-desc { font-size: 13px; color: var(--pt-text-muted); margin: 0 0 24px; }

/* ===== 顶部信息横幅 ===== */
.info-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  margin: 12px 12px 0;
  background: linear-gradient(135deg, #FCE4EC, #FFF);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(244, 143, 177, 0.1);
}
.info-banner__name {
  font-size: 17px;
  font-weight: 700;
  color: var(--pt-text);
}
.info-banner__meta {
  font-size: 12px;
  color: var(--pt-text-secondary);
  margin-top: 2px;
}

/* 环形进度条 */
.progress-ring {
  position: relative;
  width: 52px;
  height: 52px;
}
.progress-ring__svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.progress-ring__bg {
  fill: none;
  stroke: rgba(244, 143, 177, 0.15);
  stroke-width: 3;
}
.progress-ring__fill {
  fill: none;
  stroke: var(--pt-primary);
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.5s ease;
}
.progress-ring__text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--pt-primary-dark);
}

/* ===== 表单卡片列表 ===== */
.form-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.form-card {
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  border: 1.5px solid transparent;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.form-card:focus-within {
  border-color: var(--pt-primary);
  box-shadow: 0 2px 12px rgba(244, 143, 177, 0.12);
}
.form-card--done {
  border-color: rgba(76, 175, 80, 0.3);
  background: #FAFDF9;
}

.form-card__header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}
.form-card__index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--pt-primary-light);
  color: var(--pt-primary-dark);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.form-card--done .form-card__index {
  background: #E8F5E9;
  color: #4CAF50;
}
.form-card__question {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--pt-text);
  line-height: 1.4;
}
.form-card__check {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #4CAF50;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ===== 输入控件 ===== */
.form-card__body { margin-top: 2px; }

.field-input {
  width: 100%;
  height: 46px;
  border: 1.5px solid #E8E4E0;
  border-radius: 10px;
  padding: 0 14px;
  font-size: 15px;
  font-family: 'Figtree', sans-serif;
  font-weight: 600;
  color: var(--pt-text);
  background: #FAFAF8;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
  box-sizing: border-box;
  -moz-appearance: textfield;
}
.field-input::-webkit-outer-spin-button,
.field-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.field-input:focus { border-color: var(--pt-primary); background: #fff; }
.field-input::placeholder { color: #C0B8B0; font-weight: 400; }
.field-input:disabled { background: #F5F3F0; color: #A09890; border-color: #E8E4E0; }
.field-input--half { flex: 1; min-width: 0; }

.field-textarea {
  width: 100%;
  min-height: 46px;
  border: 1.5px solid #E8E4E0;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  color: var(--pt-text);
  background: #FAFAF8;
  outline: none;
  resize: vertical;
  transition: border-color 0.2s, background 0.2s;
  box-sizing: border-box;
  line-height: 1.5;
}
.field-textarea:focus { border-color: var(--pt-primary); background: #fff; }
.field-textarea::placeholder { color: #C0B8B0; }
.field-textarea:disabled { background: #F5F3F0; color: #A09890; }
.field-textarea--long { min-height: 80px; }

.field-unit {
  font-size: 12px;
  color: var(--pt-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: 6px;
}
.field-target {
  font-size: 11px;
  color: var(--pt-primary-dark);
  background: var(--pt-primary-light);
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  margin-left: 6px;
}

/* 血压输入组 */
.bp-input-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.bp-separator {
  font-size: 18px;
  font-weight: 700;
  color: var(--pt-text-muted);
  flex-shrink: 0;
}

/* 数字输入包装 */
.number-input-wrap {
  display: flex;
  align-items: center;
  gap: 0;
}
.number-input-wrap .field-input { flex: 1; min-width: 0; }

/* ===== 底部提交栏 ===== */
.submit-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(0,0,0,0.06);
  z-index: 20;
}

/* ===== 通用按钮 ===== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 48px;
  border: none;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  font-family: 'Figtree', sans-serif;
  cursor: pointer;
  transition: all 0.2s;
  -webkit-tap-highlight-color: transparent;
}
.btn:active:not(:disabled) { transform: scale(0.98); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn--block { width: 100%; }
.btn--primary {
  background: linear-gradient(135deg, var(--pt-primary), var(--pt-primary-dark));
  color: #fff;
  box-shadow: 0 4px 14px rgba(244, 143, 177, 0.3);
}
.btn--outline {
  background: #fff;
  border: 1.5px solid #E8E4E0;
  color: var(--pt-text);
}
.btn--outline:active { background: var(--pt-primary-light); }

.btn-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ===== 完成页面 ===== */
.completion-view {
  padding: 16px;
  max-width: 480px;
  margin: 0 auto;
}
.completion-hero {
  text-align: center;
  padding: 32px 0 24px;
}
.completion-check {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4CAF50, #66BB6A);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  box-shadow: 0 4px 20px rgba(76, 175, 80, 0.3);
}
.completion-check-icon { font-size: 28px; color: #fff; font-weight: 700; }
.completion-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--pt-text);
  margin: 0 0 4px;
}
.completion-subtitle {
  font-size: 13px;
  color: var(--pt-text-muted);
  margin: 0;
}

.summary-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.summary-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.summary-card__avatar { font-size: 20px; }
.summary-card__name { font-size: 13px; font-weight: 600; color: var(--pt-text-secondary); }
.summary-card__body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--pt-text);
}

.education-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.education-card__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--pt-text);
  margin-bottom: 10px;
}
.education-card__list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--pt-text-secondary);
}
.education-card__list li { margin-bottom: 2px; }

/* ===== 结构化分析卡片 ===== */
.alert-card {
  background: #FFF8E1;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1.5px solid #FFB74D;
  box-shadow: 0 1px 4px rgba(255, 152, 0, 0.08);
}
.alert-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.alert-card__icon { font-size: 18px; }
.alert-card__title { font-size: 14px; font-weight: 700; color: #E65100; }
.alert-card__list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
  color: #BF360C;
}
.alert-card__list li { margin-bottom: 2px; }

.info-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  border-left: 3px solid #42A5F5;
}
.info-card__header {
  font-size: 14px;
  font-weight: 700;
  color: var(--pt-text);
  margin-bottom: 8px;
}
.info-card__body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--pt-text-secondary);
}

.advice-card {
  background: #E8F5E9;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1.5px solid #A5D6A7;
}
.advice-card__header {
  font-size: 14px;
  font-weight: 700;
  color: #2E7D32;
  margin-bottom: 8px;
}
.advice-card__body {
  font-size: 13px;
  line-height: 1.7;
  color: #1B5E20;
}

/* ===== 移动端适配 ===== */
@media (max-width: 430px) {
  .info-banner { margin: 8px; padding: 12px 14px; }
  .form-list { padding: 8px; gap: 8px; }
  .form-card { padding: 12px 14px; }
  .submit-bar { padding: 10px 12px; }
}
</style>
