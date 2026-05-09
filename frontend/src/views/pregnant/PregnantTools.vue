<template>
  <div class="page-container">
    <!-- 渐变头部 -->
    <div class="patient-header-card" style="min-height: 80px; padding: 20px">
      <div class="patient-header-card__name">健康工具</div>
      <div class="patient-header-card__week">记录胎动，关注宝宝每一步成长</div>
    </div>

    <!-- ==================== 胎动记录 ==================== -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #EC407A"></span>
        胎动记录
        <span v-if="count > 0 && sessionId" class="status-badge status-badge--live">记录中</span>
      </div>

      <!-- 计数显示 -->
      <div class="timer-section">
        <div class="count-display">
          <span class="count-number">{{ count }}</span>
          <span class="count-unit">次</span>
        </div>
        <div class="kick-last-time" v-if="lastKickTime">上次记录 {{ lastKickTime }}</div>
      </div>

      <!-- +1 按钮 -->
      <div class="kick-btn-wrap">
        <button
          class="kick-btn kick-btn--active"
          @click="recordKick"
        >
          <span class="kick-btn__icon">👶</span>
          <span class="kick-btn__text">+1 胎动</span>
        </button>
        <p class="kick-hint">{{ count > 0 ? '每次感觉到胎动，点击一次 👆' : '宝宝踢一下，就点一次 👶' }}</p>
      </div>

      <!-- 操作按钮 -->
      <div class="timer-controls" v-if="count > 0">
        <button class="ctrl-btn ctrl-btn--save" @click="saveSession">
          ✔ 完成记录
        </button>
        <button class="ctrl-btn ctrl-btn--cancel" @click="resetCounter">
          ↺ 重置
        </button>
      </div>
    </div>

    <!-- ==================== 快速录入 ==================== -->
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

    <!-- ==================== 历史记录 ==================== -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #CE93D8"></span>
        胎动计数历史
      </div>
      <div v-if="historyLoading" class="empty-tip">加载中...</div>
      <div v-else-if="sessionHistory.length === 0" class="empty-tip">暂无胎动计数记录，开始第一次计数吧~ 👶</div>
      <div v-else class="records-list">
        <div
          v-for="s in sessionHistory"
          :key="s.id"
          class="record-row fm-row"
        >
          <div class="fm-row__header">
            <div class="fm-row__info">
              <span class="fm-row__date">{{ formatDateShort(s.start_time) }}</span>
              <span class="fm-row__count-label">{{ s.total_count }}次</span>
            </div>
            <button class="fm-row__del" @click="deleteSession(s.id)" title="删除">✕</button>
          </div>
          <div class="fm-row__kicks" v-if="s.kick_times && s.kick_times.length">
            <span
              v-for="(kt, ki) in s.kick_times"
              :key="ki"
              class="kick-dot"
            >
              👶 {{ formatTimeShort(kt) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { chatApi, pregnantApi, fetalMovementApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'

/* ==================== 胎动计数器状态 ==================== */

const count = ref(0)
const sessionId = ref<string | null>(null)
const kickTimestamps = ref<string[]>([])
const lastKickTime = ref('')
const historyLoading = ref(false)
const sessionHistory = ref<Array<{
  id: string; start_time: string; kick_times: string[];
  duration_minutes?: number; total_count: number;
}>>([])

let fmSaving = false

/** 返回东八区 ISO 时间字符串 */
function beijingISO(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  const beijingOffset = 8 * 3600000
  return new Date(now.getTime() + offset + beijingOffset).toISOString()
}

/* ==================== 胎动记录方法 ==================== */

async function recordKick() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) { ElMessage.warning('请先登录'); return }

  const kickTime = beijingISO()

  // 第一次点击 → 自动创建会话
  if (!sessionId.value) {
    try {
      const res = await fetalMovementApi.createSession(pid)
      sessionId.value = res.data.id
      kickTimestamps.value = [kickTime]
      count.value = 1
      lastKickTime.value = formatTimeShort(kickTime)

      await saveProgress()
    } catch {
      ElMessage.error('启动胎动记录失败')
      return
    }
  } else {
    // 后续点击：记录时刻 + 计数
    kickTimestamps.value.push(kickTime)
    count.value++
    lastKickTime.value = formatTimeShort(kickTime)
    // 每 5 次自动保存
    if (count.value % 5 === 0) {
      await saveProgress()
    }
  }

  if (navigator.vibrate) navigator.vibrate(20)
}

async function saveProgress() {
  if (!sessionId.value) return
  try {
    await fetalMovementApi.updateSession(sessionId.value, {
      total_count: count.value,
      kick_times: kickTimestamps.value,
    })
  } catch { /* ignore */ }
}

async function saveSession() {
  if (!sessionId.value || count.value === 0 || fmSaving) return
  fmSaving = true

  try {
    await fetalMovementApi.updateSession(sessionId.value, {
      total_count: count.value,
      kick_times: kickTimestamps.value,
    })
    const fromTime = formatTimeShort(kickTimestamps.value[0])
    ElMessage.success(`${count.value} 次胎动已记录（${fromTime} 开始）`)
    resetState()
    await loadHistory()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    fmSaving = false
  }
}

function resetCounter() {
  if (sessionId.value) {
    fetalMovementApi.deleteSession(sessionId.value).catch(() => {})
  }
  resetState()
  ElMessage.info('已重置')
}

function resetState() {
  count.value = 0
  sessionId.value = null
  kickTimestamps.value = []
  lastKickTime.value = ''
}

function formatTimeShort(iso: string): string {
  // ISO 已是东八区时间，直接从字符串提取
  const m = iso.match(/T(\d{2}):(\d{2}):(\d{2})/)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : iso
}

function formatDateShort(iso: string): string {
  const m = iso.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  return m ? `${m[2]}/${m[3]} ${m[4]}:${m[5]}` : iso
}

async function loadHistory() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) return
  historyLoading.value = true
  try {
    const res = await fetalMovementApi.listSessions(pid, 30)
    sessionHistory.value = res.data || []
  } catch {
    // ignore
  } finally {
    historyLoading.value = false
  }
}

async function deleteSession(id: string) {
  try {
    await ElMessageBox.confirm('确定删除这条胎动记录吗？', '确认')
    await fetalMovementApi.deleteSession(id)
    sessionHistory.value = sessionHistory.value.filter(s => s.id !== id)
    ElMessage.success('已删除')
  } catch {
    // cancelled
  }
}

/* ==================== 原健康数据录入 ==================== */

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
const healthSummary = ref<any>({})

const pregnantId = computed(() => localStorage.getItem('currentPregnantId') || '')

const hasData = computed(() =>
  form.weight != null || form.systolic != null || form.diastolic != null ||
  form.fetalMovement != null || form.mood
)

const recentRecords = computed(() => {
  const rows: any[] = []
  const s = healthSummary.value
  if (!s) return rows
  const today = new Date()
  const ds = `${today.getMonth() + 1}/${today.getDate()}`
  if (s.latest_weight) rows.push({ date: ds, label: '体重', value: s.latest_weight, unit: 'kg' })
  if (s.latest_blood_pressure) rows.push({ date: ds, label: '血压', value: s.latest_blood_pressure, unit: 'mmHg' })
  if (s.latest_fetal_movement) rows.push({ date: ds, label: '胎动', value: s.latest_fetal_movement, unit: '次/小时' })
  return rows
})

async function saveAll() {
  if (!hasData.value) return
  saving.value = true
  const msgs: string[] = []
  if (form.weight != null) msgs.push(`体重：${form.weight}kg`)
  if (form.systolic != null && form.diastolic != null) msgs.push(`血压：${form.systolic}/${form.diastolic}mmHg`)
  else if (form.systolic != null) msgs.push(`收缩压：${form.systolic}mmHg`)
  else if (form.diastolic != null) msgs.push(`舒张压：${form.diastolic}mmHg`)
  if (form.fetalMovement != null) msgs.push(`胎动：${form.fetalMovement}次`)
  if (form.mood) {
    const moodLabels: Record<string, string> = { good: '开心', neutral: '一般', bad: '低落' }
    msgs.push(`情绪：${moodLabels[form.mood]}`)
  }
  try {
    for (const msg of msgs) {
      await chatApi.send({ pregnant_id: pregnantId.value, message: msg, session_id: 's1' })
    }
    ElMessage.success('保存成功')
    form.weight = null; form.systolic = null; form.diastolic = null
    form.fetalMovement = null; form.mood = ''
    await loadSummary()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function loadSummary() {
  if (!pregnantId.value) return
  try {
    const res = await pregnantApi.getHome(pregnantId.value)
    healthSummary.value = res.data?.health_summary || {}
  } catch { /* ignore */ }
}

onMounted(() => {
  loadSummary()
  loadHistory()
})
</script>

<style scoped>
/* 页面滚动容器 */
.page-container {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  height: 100%;
  box-sizing: border-box;
  padding-bottom: 24px;
}

/* 胎动记录区域 */
.timer-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0 8px;
}

.kick-last-time {
  font-size: 12px;
  color: var(--pt-text-muted);
  margin-top: 6px;
}

.count-display {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.count-number {
  font-size: 64px;
  font-weight: 800;
  font-family: 'Figtree', 'SF Mono', monospace;
  color: var(--pt-primary-dark);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.count-unit {
  font-size: 20px;
  font-weight: 600;
  color: var(--pt-text-muted);
}

/* +1 按钮 */
.kick-btn-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 16px 0;
}

.kick-btn {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 3px solid rgba(244, 143, 177, 0.3);
  background: linear-gradient(135deg, #fce4ec, #f8bbd0);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.kick-btn:active:not(:disabled) {
  transform: scale(0.92);
}

.kick-btn--active {
  border-color: var(--pt-primary);
  box-shadow: 0 0 0 6px rgba(244, 143, 177, 0.15), 0 8px 30px rgba(244, 143, 177, 0.3);
  animation: kickPulse 2s ease-in-out infinite;
}

.kick-btn--active:active {
  transform: scale(0.88);
  box-shadow: 0 0 0 10px rgba(244, 143, 177, 0.25), 0 8px 30px rgba(244, 143, 177, 0.4);
}

@keyframes kickPulse {
  0%, 100% { box-shadow: 0 0 0 6px rgba(244, 143, 177, 0.15), 0 8px 30px rgba(244, 143, 177, 0.2); }
  50% { box-shadow: 0 0 0 12px rgba(244, 143, 177, 0.08), 0 8px 30px rgba(244, 143, 177, 0.3); }
}

.kick-btn__icon {
  font-size: 32px;
  line-height: 1;
}

.kick-btn__text {
  font-size: 16px;
  font-weight: 700;
  color: var(--pt-primary-dark);
}

.kick-hint {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--pt-text-muted);
  text-align: center;
}

/* 控制按钮 */
.timer-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 8px 0 4px;
}

.ctrl-btn {
  padding: 10px 22px;
  border-radius: 24px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ctrl-btn:active {
  transform: scale(0.96);
}

.ctrl-btn--save {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1px solid rgba(46, 125, 50, 0.2);
}

.ctrl-btn--cancel {
  background: transparent;
  color: var(--pt-text-muted);
  border: 1px solid rgba(0, 0, 0, 0.1);
}

/* 状态标 */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 8px;
}

.status-badge--live {
  background: #ffebee;
  color: #c62828;
  animation: dotBlink 1.5s ease-in-out infinite;
}

@keyframes dotBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* 胎动历史行 */
.fm-row {
  padding: 10px 0;
}

.fm-row__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.fm-row__info {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.fm-row__date {
  font-size: 13px;
  font-weight: 600;
  color: var(--pt-text);
}

.fm-row__count-label {
  font-size: 12px;
  color: var(--pt-text-muted);
}

.fm-row__kicks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--pt-border);
}

.kick-dot {
  font-size: 12px;
  color: var(--pt-text-secondary);
  white-space: nowrap;
}

.fm-row__del {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--pt-text-muted);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  flex-shrink: 0;
}

.record-row:hover .fm-row__del {
  opacity: 1;
}

.fm-row__del:hover {
  background: #ffebee;
  color: #c62828;
}

/* ==================== 原有样式（保持兼容） ==================== */

.health-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.health-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.health-field__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--pt-text-secondary);
}

.health-field__input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.health-input {
  flex: 1;
  height: 44px;
  border: 2px solid var(--pt-border);
  border-radius: 12px;
  padding: 0 14px;
  font-size: 16px;
  font-family: 'Figtree', sans-serif;
  font-weight: 600;
  color: var(--pt-text);
  background: #FAFAFA;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
  min-width: 0;
  -moz-appearance: textfield;
  box-sizing: border-box;
}

.health-input::-webkit-outer-spin-button,
.health-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.health-input:focus {
  border-color: var(--pt-primary);
  background: #fff;
}

.health-input::placeholder {
  color: var(--pt-text-muted);
  font-weight: 400;
}

.health-input--half {
  flex: 1;
  min-width: 0;
}

.health-field__unit {
  font-size: 13px;
  color: var(--pt-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.bp-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.bp-sep {
  font-size: 18px;
  font-weight: 700;
  color: var(--pt-text-muted);
  flex-shrink: 0;
}

.mood-row {
  display: flex;
  gap: 8px;
}

.mood-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  border: 2px solid var(--pt-border);
  border-radius: 14px;
  background: #FAFAFA;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 12px;
  color: var(--pt-text-secondary);
  font-family: inherit;
}

.mood-btn.active {
  border-color: var(--pt-primary);
  background: var(--pt-primary-light);
}

.mood-btn:active {
  transform: scale(0.96);
}

.mood-emoji {
  font-size: 28px;
  line-height: 1;
}

.mood-text {
  font-weight: 500;
}

.save-btn {
  width: 100%;
  height: 48px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--pt-primary), var(--pt-primary-dark));
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  font-family: 'Figtree', sans-serif;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 4px;
}

.save-btn:active {
  transform: scale(0.98);
}

.save-btn:disabled {
  background: #E0D8E8;
  color: #B0A8BC;
  cursor: not-allowed;
}

.records-list {
  display: flex;
  flex-direction: column;
}

.record-row {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--pt-border);
  gap: 12px;
}

.record-row:last-child {
  border-bottom: none;
}

.record-date {
  font-size: 12px;
  color: var(--pt-text-muted);
  width: 36px;
  flex-shrink: 0;
}

.record-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--pt-text);
  flex: 1;
}

.record-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--pt-text);
  font-family: 'Figtree', sans-serif;
}

.record-value small {
  font-weight: 400;
  color: var(--pt-text-muted);
  font-size: 12px;
}

.empty-tip {
  text-align: center;
  padding: 24px 0;
  font-size: 13px;
  color: var(--pt-text-muted);
}

/* ========== 触摸反馈 ========== */
.kick-btn {
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.15s ease, box-shadow 0.2s ease;
}

.kick-btn:active:not(:disabled) {
  transform: scale(0.88);
}

.save-btn {
  -webkit-tap-highlight-color: transparent;
}

.save-btn:active {
  transform: scale(0.96);
}

.ctrl-btn {
  -webkit-tap-highlight-color: transparent;
}

.fm-row {
  -webkit-tap-highlight-color: transparent;
}

/* ========== ≤430px 标准移动端 ========== */
@media (max-width: 430px) {
  .page-container {
    padding: 12px 14px 24px;
  }

  .patient-header-card {
    min-height: 70px !important;
    padding: 16px !important;
  }

  .patient-header-card__name {
    font-size: 18px;
  }

  .patient-header-card__week {
    font-size: 12px;
  }

  /* 胎动计数区域 */
  .timer-section {
    padding: 12px 0 6px;
  }

  .count-number {
    font-size: 52px;
  }

  .count-unit {
    font-size: 16px;
  }

  .kick-last-time {
    font-size: 11px;
  }

  .kick-btn {
    width: 100px;
    height: 100px;
  }

  .kick-btn__icon {
    font-size: 28px;
  }

  .kick-btn__text {
    font-size: 14px;
  }

  .kick-hint {
    font-size: 12px;
    margin-top: 8px;
  }

  .timer-controls {
    flex-wrap: wrap;
    justify-content: center;
  }

  .ctrl-btn {
    padding: 8px 16px;
    font-size: 13px;
  }

  /* 快捷记录表单 */
  .health-form {
    gap: 12px;
  }

  .health-field__label {
    font-size: 12px;
  }

  .health-input {
    height: 40px;
    font-size: 15px;
    border-radius: 10px;
    padding: 0 12px;
  }

  .mood-btn {
    padding: 10px 6px;
  }

  .mood-emoji {
    font-size: 24px;
  }

  .mood-text {
    font-size: 11px;
  }

  .save-btn {
    height: 44px;
    font-size: 15px;
    border-radius: 12px;
  }

  /* 历史记录 */
  .fm-row {
    padding: 8px 0;
  }

  .fm-row__date {
    font-size: 12px;
  }

  .fm-row__count-label {
    font-size: 11px;
  }

  .kick-dot {
    font-size: 11px;
  }

  .empty-tip {
    padding: 18px 0;
    font-size: 12px;
  }
}

/* ========== ≤374px 小屏手机 ========== */
@media (max-width: 374px) {
  .page-container {
    padding: 10px 10px 20px;
  }

  .patient-header-card {
    min-height: 60px !important;
    padding: 14px !important;
  }

  .patient-header-card__name {
    font-size: 16px;
  }

  .count-number {
    font-size: 44px;
  }

  .count-unit {
    font-size: 14px;
  }

  .kick-btn {
    width: 88px;
    height: 88px;
  }

  .kick-btn__icon {
    font-size: 24px;
  }

  .kick-btn__text {
    font-size: 13px;
  }

  .health-input {
    height: 38px;
    font-size: 14px;
  }

  .health-field__label {
    font-size: 11px;
  }

  .mood-emoji {
    font-size: 22px;
  }

  .mood-text {
    font-size: 10px;
  }
}

/* ========== 触摸设备删除按钮可见 ========== */
@media (hover: none) and (pointer: coarse) {
  .fm-row__del {
    opacity: 0.5 !important;
  }

  .record-row:hover .fm-row__del {
    opacity: 0.5 !important;
  }

  .fm-row__del:active {
    opacity: 1 !important;
    background: #ffebee;
    color: #c62828;
  }
}
</style>
