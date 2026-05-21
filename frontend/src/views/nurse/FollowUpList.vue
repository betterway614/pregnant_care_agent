<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">随访管理</h1>
      <el-button type="primary" :icon="Plus" @click="showTriggerDialog = true">
        触发随访
      </el-button>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      closable
      class="mb-4"
      @close="error = ''"
    />

    <!-- 筛选栏 -->
    <div class="search-bar">
      <el-select v-model="filterStatus" placeholder="随访状态筛选" clearable style="width: 160px" @change="handleFilterChange">
        <el-option label="全部状态" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已完成" value="completed" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-button :icon="Refresh" @click="fetchRecords" :loading="loading" circle />
    </div>

    <!-- AI 推荐面板 -->
    <el-collapse v-model="recommendPanelOpen" class="recommend-collapse">
      <el-collapse-item title="🤖 AI 随访推荐" name="recommend">
        <div v-if="recommendLoading" class="recommend-loading">
          <el-skeleton :rows="3" animated />
        </div>
        <div v-else-if="!recommendations.length" class="recommend-empty">
          暂无推荐，所有孕妇随访状态良好
        </div>
        <div v-else class="recommend-list">
          <div v-for="(rec, i) in recommendations" :key="i" class="recommend-item">
            <div class="recommend-item__left">
              <div class="recommend-item__name">
                {{ rec.patient_name }}
                <span class="recommend-item__week">孕{{ rec.gestational_week }}周</span>
              </div>
              <div class="recommend-item__reason">{{ rec.reason }}</div>
            </div>
            <div class="recommend-item__right">
              <el-tag
                :type="rec.priority === 'high' ? 'danger' : rec.priority === 'medium' ? 'warning' : 'success'"
                size="small"
              >
                {{ rec.priority === 'high' ? '紧急' : rec.priority === 'medium' ? '重要' : '常规' }}
              </el-tag>
              <el-button
                type="primary"
                size="small"
                :loading="rec._triggering"
                @click="doQuickTrigger(rec)"
              >
                一键触发
              </el-button>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 随访记录列表 -->
    <div class="content-card">
      <div class="content-card__header">
        <span class="content-card__title">随访记录</span>
        <span class="text-light">共 {{ total }} 条</span>
      </div>
      <div class="content-card__body" v-loading="loading">
        <el-table :data="paginatedRecords" stripe style="width: 100%" size="small">
          <el-table-column label="随访日期" width="110" align="center">
            <template #default="{ row }">
              {{ formatDate(row.follow_up_date) }}
            </template>
          </el-table-column>
          <el-table-column prop="patient_name" label="孕妇姓名" min-width="90" />
          <el-table-column label="孕周" width="70" align="center">
            <template #default="{ row }">
              {{ row.gestational_week || '--' }}
            </template>
          </el-table-column>
          <el-table-column prop="chief_complaint" label="主诉" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.chief_complaint || '无' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right" align="left" header-align="left">
            <template #default="{ row }">
              <div class="table-row-actions">
                <el-button type="primary" class="brand-gradient-btn" size="small" @click.stop="goPregnantDetail(row)">
                  孕妇详情
                </el-button>
                <el-button
                  v-if="row.status === 'completed' || row.status === 'in_progress'"
                  type="primary"
                  class="brand-gradient-btn"
                  size="small"
                  @click.stop="confirmRecord(row)"
                >
                  确认审核
                </el-button>
                <el-button
                  v-else-if="row.status === 'draft'"
                  type="primary"
                  class="brand-gradient-btn"
                  size="small"
                  @click.stop="confirmRecord(row)"
                >
                  确认归档
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空状态 -->
        <div v-if="!paginatedRecords.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><Document /></el-icon>
          <p>{{ filterStatus ? '暂无匹配的随访记录' : '暂无随访记录，点击上方"触发随访"创建' }}</p>
        </div>

        <!-- 分页 -->
        <div v-if="total > pageSize" class="pagination-wrapper">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            background
            small
          />
        </div>
      </div>
    </div>

    <!-- 触发随访对话框 -->
    <el-dialog v-model="showTriggerDialog" title="触发随访" width="480px" destroy-on-close>
      <el-form :model="triggerForm" label-width="80px">
        <el-form-item label="选择孕妇" required>
          <el-select
            v-model="triggerForm.pregnantId"
            placeholder="请选择孕妇（支持搜索）"
            filterable
            style="width: 100%"
            :loading="pregnantLoading"
          >
            <el-option
              v-for="p in pregnant"
              :key="p.pregnant_id"
              :label="`${p.display_name}${p.nickname ? '（' + p.nickname + '）' : ''}${p.gestational_age_days ? ' 孕' + Math.floor(p.gestational_age_days / 7) + '周' : ''}`"
              :value="p.pregnant_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="随访模板">
          <el-select v-model="triggerForm.templateId" placeholder="选择模板（可选）" clearable style="width: 100%">
            <el-option label="常规随访" value="常规随访" />
            <el-option label="高危随访" value="高危随访" />
            <el-option label="产后随访" value="产后随访" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTriggerDialog = false">取消</el-button>
        <el-button type="primary" :loading="triggering" :disabled="!triggerForm.pregnantId" @click="doTrigger">
          确认触发
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 审核辅助抽屉 -->
    <el-drawer
      v-model="showReviewDrawer"
      title="随访审核"
      size="480px"
      destroy-on-close
    >
      <template v-if="reviewRecord">
        <!-- 基本信息 -->
        <div class="review-section">
          <h4 class="review-section__title">基本信息</h4>
          <div class="review-info-grid">
            <div class="review-info-item">
              <span class="review-info-label">孕妇</span>
              <span class="review-info-value">{{ reviewRecord.patient_name }}</span>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">孕周</span>
              <span class="review-info-value">{{ reviewRecord.gestational_week || '--' }}</span>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">日期</span>
              <span class="review-info-value">{{ formatDate(reviewRecord.follow_up_date) }}</span>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">主诉</span>
              <span class="review-info-value">{{ reviewRecord.chief_complaint || '无' }}</span>
            </div>
          </div>
        </div>

        <!-- 随访答案 -->
        <div class="review-section" v-if="reviewRecord.self_reported_data && Object.keys(reviewRecord.self_reported_data).length">
          <h4 class="review-section__title">随访回答</h4>
          <div class="review-answer-list">
            <div v-for="(value, key) in reviewRecord.self_reported_data" :key="key" class="review-answer-item">
              <span class="review-answer-key">{{ key }}</span>
              <span class="review-answer-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <!-- AI 审核辅助 -->
        <div class="review-section">
          <h4 class="review-section__title">🤖 AI 审核辅助</h4>
          <div v-if="aiReviewLoading" class="review-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>AI 正在分析随访数据...</span>
          </div>
          <template v-else-if="aiReviewResult">
            <el-alert
              :title="aiReviewResult.recommendation"
              :description="aiReviewResult.summary"
              :type="aiReviewResult.action_needed ? 'error' : 'success'"
              show-icon
              :closable="false"
              class="mb-3"
            />
            <div v-if="aiReviewResult.abnormal_flags?.length" class="review-abnormal">
              <p class="review-abnormal__title">异常指标：</p>
              <el-tag
                v-for="(flag, i) in aiReviewResult.abnormal_flags"
                :key="i"
                type="danger"
                size="small"
                class="review-abnormal__tag"
              >{{ flag }}</el-tag>
            </div>
            <div v-if="aiReviewResult.detail_analysis" class="review-detail">
              <p class="review-detail__title">详细分析：</p>
              <p class="review-detail__body">{{ aiReviewResult.detail_analysis }}</p>
            </div>
          </template>
          <div v-else class="review-empty">暂无 AI 分析结果</div>
        </div>

        <!-- 操作按钮 -->
        <div class="review-actions">
          <el-button
            type="primary"
            :loading="confirmLoading"
            @click="doConfirmFromDrawer('confirmed')"
            style="flex: 1"
          >
            确认通过
          </el-button>
          <el-button
            v-if="aiReviewResult?.action_needed"
            type="danger"
            @click="escalateToDoctor"
            style="flex: 1"
          >
            上报医生
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh, Document, Loading } from '@element-plus/icons-vue'
import { followUpApi, dashboardApi, nurseAiApi, collaborationApi } from '@/api/endpoints'
import { ElMessage } from 'element-plus'
import type { FollowUpRecord, Pregnant } from '@/types'

/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 30000
let pollTimer: ReturnType<typeof setInterval> | null = null

/** 开始轮询 */
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    fetchRecords()
  }, POLL_INTERVAL)
}

/** 停止轮询 */
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const router = useRouter()
const loading = ref(false)
const error = ref('')
const records = ref<FollowUpRecord[]>([])
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

/** 触发随访 */
const showTriggerDialog = ref(false)
const triggering = ref(false)
const pregnant = ref<Pregnant[]>([])
const pregnantLoading = ref(false)
const triggerForm = ref({
  pregnantId: '',
  templateId: '',
})

/** AI 审核辅助抽屉 */
const showReviewDrawer = ref(false)
const reviewRecord = ref<FollowUpRecord | null>(null)
const aiReviewLoading = ref(false)
const aiReviewResult = ref<any>(null)
const confirmLoading = ref(false)

/** AI 推荐面板 */
const recommendPanelOpen = ref<string[]>(['recommend'])
const recommendLoading = ref(false)
const recommendations = ref<any[]>([])

/** 打开对话框时加载孕妇列表 */
watch(showTriggerDialog, (val) => {
  if (val) fetchPatients()
})

/** 过滤后的记录总数 */
const total = computed(() => records.value.length)

/** 分页后的记录 */
const paginatedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return records.value.slice(start, start + pageSize.value)
})

/** 筛选变化时重置分页并重新加载 */
function handleFilterChange() {
  currentPage.value = 1
  fetchRecords()
}

/** 状态标签类型 */
function statusType(status: string): string {
  const map: Record<string, string> = {
    archived: 'success',
    confirmed: 'success',
    completed: 'primary',
    in_progress: 'warning',
    draft: 'info',
  }
  return map[status] || 'info'
}

/** 状态标签文本 */
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    archived: '已归档',
    confirmed: '已确认',
    completed: '已完成',
    in_progress: '进行中',
    draft: '草稿',
  }
  return map[status] || status
}

/** 日期格式化 */
function formatDate(d?: string): string {
  if (!d) return '--'
  const date = new Date(d)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/** 加载随访记录 */
async function fetchRecords() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (filterStatus.value) params.status = filterStatus.value
    const res = await followUpApi.list(params)
    records.value = res.data || []
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '加载随访记录失败'
    error.value = msg
    console.error('加载随访记录失败:', err)
  } finally {
    loading.value = false
  }
}

/** 加载孕妇列表（用于触发随访） */
async function fetchPatients() {
  if (pregnant.value.length) return
  pregnantLoading.value = true
  try {
    const res = await dashboardApi.pregnant()
    pregnant.value = res.data || []
  } catch (err) {
    console.error('加载孕妇列表失败:', err)
  } finally {
    pregnantLoading.value = false
  }
}

/** 跳转到孕妇详情页 */
function goPregnantDetail(row: FollowUpRecord) {
  if (row.pregnant_id) {
    router.push({ name: 'NursePregnantDetail', params: { pregnantId: row.pregnant_id } })
  }
}

/** 确认审核 / 打开AI审核抽屉 */
async function confirmRecord(row: FollowUpRecord) {
  if (row.status === 'completed' || row.status === 'in_progress') {
    // 打开 AI 审核抽屉
    reviewRecord.value = row
    showReviewDrawer.value = true
    aiReviewResult.value = null
    aiReviewLoading.value = true
    try {
      const res = await followUpApi.aiReview(row.id)
      aiReviewResult.value = res.data
    } catch (err) {
      console.error('AI 审核加载失败:', err)
      aiReviewResult.value = null
    } finally {
      aiReviewLoading.value = false
    }
  } else {
    // 草稿状态直接归档
    try {
      await followUpApi.confirm(row.id, 'confirmed')
      ElMessage.success('归档成功')
      await fetchRecords()
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || '归档失败'
      ElMessage.error(msg)
    }
  }
}

/** 从抽屉中确认通过 */
async function doConfirmFromDrawer(status: string) {
  if (!reviewRecord.value) return
  confirmLoading.value = true
  try {
    const nurseId = localStorage.getItem('currentUserId') || 'nurse_default'
    await followUpApi.confirm(reviewRecord.value.id, status, {
      reviewer_id: nurseId,
      review_comment: aiReviewResult.value?.recommendation || '',
      ai_snapshot: aiReviewResult.value || {},
    })
    ElMessage.success('审核通过')
    showReviewDrawer.value = false
    await fetchRecords()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '审核失败'
    ElMessage.error(msg)
  } finally {
    confirmLoading.value = false
  }
}

/** 上报医生 */
async function escalateToDoctor() {
  if (!reviewRecord.value) return
  try {
    const pregnantId = reviewRecord.value.pregnant_id
    await collaborationApi.reportIssue({
      pregnant_id: pregnantId,
      issue_type: 'risk_alert',
      priority: 'high',
      title: `随访审核异常 - ${reviewRecord.value.patient_name}`,
      description: `AI审核发现异常：${aiReviewResult.value?.abnormal_flags?.join('；') || '需进一步沟通'}\n\n建议：${aiReviewResult.value?.recommendation || ''}`,
    })
    ElMessage.success('已上报给医生')
    await doConfirmFromDrawer('confirmed')
  } catch {
    ElMessage.error('上报失败，请重试')
  }
}

/** 触发随访 */
async function doTrigger() {
  if (!triggerForm.value.pregnantId) {
    ElMessage.warning('请选择孕妇')
    return
  }
  triggering.value = true
  try {
    await followUpApi.trigger(triggerForm.value.pregnantId, triggerForm.value.templateId || undefined)
    ElMessage.success('随访已触发')
    showTriggerDialog.value = false
    triggerForm.value = { pregnantId: '', templateId: '' }
    await fetchRecords()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '触发随访失败'
    ElMessage.error(msg)
    console.error('触发随访失败:', err)
  } finally {
    triggering.value = false
  }
}

/** 加载 AI 推荐 */
async function fetchRecommendations() {
  recommendLoading.value = true
  try {
    const res = await nurseAiApi.getFollowupRecommendations()
    recommendations.value = (res.data?.recommendations || []).map((r: any) => ({ ...r, _triggering: false }))
  } catch (err) {
    console.error('加载AI推荐失败:', err)
    recommendations.value = []
  } finally {
    recommendLoading.value = false
  }
}

/** 一键触发推荐的随访 */
async function doQuickTrigger(rec: any) {
  rec._triggering = true
  try {
    await followUpApi.trigger(rec.pregnant_id, rec.template_id)
    ElMessage.success(`已触发对 ${rec.patient_name} 的随访`)
    await fetchRecords()
    await fetchRecommendations()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '触发失败'
    ElMessage.error(msg)
  } finally {
    rec._triggering = false
  }
}

onMounted(() => {
  fetchRecords()
  fetchRecommendations()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

/* ===== AI 推荐面板 ===== */
.recommend-collapse {
  margin-bottom: 16px;
}
.recommend-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.recommend-loading {
  padding: 8px;
}
.recommend-empty {
  text-align: center;
  padding: 16px;
  color: var(--text-muted);
  font-size: 13px;
}
.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.recommend-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-page);
  border-radius: 10px;
  border: 1px solid var(--border);
}
.recommend-item__left {
  flex: 1;
  min-width: 0;
}
.recommend-item__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.recommend-item__week {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 6px;
}
.recommend-item__reason {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recommend-item__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}

.empty-state p {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}

/* ===== AI 审核抽屉 ===== */
.mb-3 {
  margin-bottom: 12px;
}
.review-section {
  margin-bottom: 20px;
}
.review-section__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px;
}
.review-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.review-info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.review-info-label {
  font-size: 12px;
  color: var(--text-muted);
}
.review-info-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}
.review-answer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.review-answer-item {
  display: flex;
  gap: 12px;
  padding: 8px 12px;
  background: var(--bg-page);
  border-radius: 8px;
}
.review-answer-key {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 80px;
  flex-shrink: 0;
}
.review-answer-value {
  font-size: 13px;
  color: var(--text-primary);
}
.review-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: var(--text-muted);
  font-size: 13px;
}
.review-abnormal {
  margin-bottom: 12px;
}
.review-abnormal__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-danger);
  margin: 0 0 8px;
}
.review-abnormal__tag {
  margin: 0 8px 8px 0;
}
.review-detail {
  background: var(--bg-page);
  border-radius: 8px;
  padding: 12px;
}
.review-detail__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 6px;
}
.review-detail__body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  margin: 0;
}
.review-empty {
  text-align: center;
  padding: 24px;
  color: var(--text-muted);
  font-size: 13px;
}
.review-actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  margin-top: auto;
}
</style>
