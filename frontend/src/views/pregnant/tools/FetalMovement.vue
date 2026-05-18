<template>
  <div class="page-container">
    <!-- 返回导航 -->
    <div class="sub-page-header">
      <el-page-header @back="$router.back()">
        <template #content>胎动计数</template>
      </el-page-header>
    </div>

    <!-- 胎动记录 -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #EC407A"></span>
        胎动记录
        <span v-if="count > 0 && sessionId" class="status-badge status-badge--live">记录中</span>
      </div>

      <div class="timer-section">
        <div class="count-display">
          <span class="count-number">{{ count }}</span>
          <span class="count-unit">次</span>
        </div>
        <div class="kick-last-time" v-if="lastKickTime">上次记录 {{ lastKickTime }}</div>
      </div>

      <div class="kick-btn-wrap">
        <button class="kick-btn kick-btn--active" @click="recordKick">
          <span class="kick-btn__icon">👶</span>
          <span class="kick-btn__text">+1 胎动</span>
        </button>
        <p class="kick-hint">{{ count > 0 ? '每次感觉到胎动，点击一次 👆' : '宝宝踢一下，就点一次 👶' }}</p>
      </div>

      <div class="timer-controls" v-if="count > 0">
        <button class="ctrl-btn ctrl-btn--save" @click="saveSession">✔ 完成记录</button>
        <button class="ctrl-btn ctrl-btn--cancel" @click="resetCounter">↺ 重置</button>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #CE93D8"></span>
        胎动计数历史
      </div>
      <div v-if="historyLoading" class="empty-tip">加载中...</div>
      <div v-else-if="sessionHistory.length === 0" class="empty-tip">暂无胎动计数记录，开始第一次计数吧~ 👶</div>
      <div v-else class="records-list">
        <div v-for="s in sessionHistory" :key="s.id" class="record-row fm-row">
          <div class="fm-row__header">
            <div class="fm-row__info">
              <span class="fm-row__date">{{ formatDateShort(s.start_time) }}</span>
              <span class="fm-row__count-label">{{ s.total_count }}次</span>
            </div>
            <button class="fm-row__del" @click="deleteSession(s.id)" title="删除">✕</button>
          </div>
          <div class="fm-row__kicks" v-if="s.kick_times && s.kick_times.length">
            <span v-for="(kt, ki) in s.kick_times" :key="ki" class="kick-dot">
              👶 {{ formatTimeShort(kt) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetalMovementApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'

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

function beijingISO(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  const beijingOffset = 8 * 3600000
  return new Date(now.getTime() + offset + beijingOffset).toISOString()
}

async function recordKick() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) { ElMessage.warning('请先登录'); return }
  const kickTime = beijingISO()

  if (!sessionId.value) {
    try {
      const res = await fetalMovementApi.createSession(pid)
      sessionId.value = res.data.id
      kickTimestamps.value = [kickTime]
      count.value = 1
      lastKickTime.value = formatTimeShort(kickTime)
      await saveProgress()
    } catch { ElMessage.error('启动胎动记录失败'); return }
  } else {
    kickTimestamps.value.push(kickTime)
    count.value++
    lastKickTime.value = formatTimeShort(kickTime)
    if (count.value % 5 === 0) await saveProgress()
  }
  if (navigator.vibrate) navigator.vibrate(20)
}

async function saveProgress() {
  if (!sessionId.value) return
  try {
    await fetalMovementApi.updateSession(sessionId.value, { total_count: count.value, kick_times: kickTimestamps.value })
  } catch { /* ignore */ }
}

async function saveSession() {
  if (!sessionId.value || count.value === 0 || fmSaving) return
  fmSaving = true
  try {
    await fetalMovementApi.updateSession(sessionId.value, { total_count: count.value, kick_times: kickTimestamps.value })
    const fromTime = formatTimeShort(kickTimestamps.value[0])
    ElMessage.success(`${count.value} 次胎动已记录（${fromTime} 开始）`)
    resetState()
    await loadHistory()
  } catch { ElMessage.error('保存失败') } finally { fmSaving = false }
}

function resetCounter() {
  if (sessionId.value) fetalMovementApi.deleteSession(sessionId.value).catch(() => {})
  resetState()
  ElMessage.info('已重置')
}

function resetState() {
  count.value = 0; sessionId.value = null; kickTimestamps.value = []; lastKickTime.value = ''
}

function formatTimeShort(iso: string): string {
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
  try { sessionHistory.value = (await fetalMovementApi.listSessions(pid, 30)).data || [] } catch {} finally { historyLoading.value = false }
}

async function deleteSession(id: string) {
  try {
    await ElMessageBox.confirm('确定删除这条胎动记录吗？', '确认')
    await fetalMovementApi.deleteSession(id)
    sessionHistory.value = sessionHistory.value.filter(s => s.id !== id)
    ElMessage.success('已删除')
  } catch { /* cancelled */ }
}

onMounted(() => { loadHistory() })
</script>

<style scoped>
.page-container { overflow-y: auto; -webkit-overflow-scrolling: touch; height: 100%; box-sizing: border-box; padding-bottom: 24px; }
.sub-page-header { margin: 12px 16px; padding: 12px 16px; border-radius: 16px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04); border: 1px solid rgba(255, 255, 255, 0.5); background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); position: sticky; top: 12px; z-index: 10; }
.timer-section { display: flex; flex-direction: column; align-items: center; padding: 16px 0 8px; }
.count-display { display: flex; align-items: baseline; gap: 4px; }
.count-number { font-size: 64px; font-weight: 800; font-family: 'Figtree', 'SF Mono', monospace; color: var(--pt-primary-dark); line-height: 1; }
.count-unit { font-size: 20px; font-weight: 600; color: var(--pt-text-muted); }
.kick-last-time { font-size: 12px; color: var(--pt-text-muted); margin-top: 6px; }
.kick-btn-wrap { display: flex; flex-direction: column; align-items: center; margin: 16px 0; }
.kick-btn { width: 120px; height: 120px; border-radius: 50%; border: 3px solid rgba(244, 143, 177, 0.3); background: linear-gradient(135deg, #fce4ec, #f8bbd0); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; cursor: pointer; transition: all 0.2s ease; }
.kick-btn:active:not(:disabled) { transform: scale(0.92); }
.kick-btn--active { border-color: var(--pt-primary); box-shadow: 0 0 0 6px rgba(244, 143, 177, 0.15), 0 8px 30px rgba(244, 143, 177, 0.3); }
.kick-btn__icon { font-size: 32px; line-height: 1; }
.kick-btn__text { font-size: 16px; font-weight: 700; color: var(--pt-primary-dark); }
.kick-hint { margin: 10px 0 0; font-size: 13px; color: var(--pt-text-muted); text-align: center; }
.timer-controls { display: flex; align-items: center; justify-content: center; gap: 8px; margin: 8px 0 4px; }
.ctrl-btn { padding: 10px 22px; border-radius: 24px; border: none; font-size: 14px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all 0.2s ease; }
.ctrl-btn:active { transform: scale(0.96); }
.ctrl-btn--save { background: #e8f5e9; color: #2e7d32; border: 1px solid rgba(46, 125, 50, 0.2); }
.ctrl-btn--cancel { background: transparent; color: var(--pt-text-muted); border: 1px solid rgba(0, 0, 0, 0.1); }
.status-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 8px; }
.status-badge--live { background: #ffebee; color: #c62828; animation: dotBlink 1.5s ease-in-out infinite; }
@keyframes dotBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.records-list { display: flex; flex-direction: column; }
.record-row { display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--pt-border); gap: 12px; }
.record-row:last-child { border-bottom: none; }
.fm-row__header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.fm-row__info { display: flex; align-items: baseline; gap: 10px; }
.fm-row__date { font-size: 13px; font-weight: 600; color: var(--pt-text); }
.fm-row__count-label { font-size: 12px; color: var(--pt-text-muted); }
.fm-row__kicks { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--pt-border); }
.kick-dot { font-size: 12px; color: var(--pt-text-secondary); white-space: nowrap; }
.fm-row__del { width: 24px; height: 24px; border: none; border-radius: 50%; background: transparent; color: var(--pt-text-muted); font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transition: all 0.2s; flex-shrink: 0; }
.record-row:hover .fm-row__del { opacity: 1; }
.fm-row__del:hover { background: #ffebee; color: #c62828; }
.empty-tip { text-align: center; padding: 24px 0; font-size: 13px; color: var(--pt-text-muted); }
</style>
