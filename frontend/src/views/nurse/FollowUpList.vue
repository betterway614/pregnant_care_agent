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
        <el-option label="待开始" value="draft" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已完成" value="completed" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-select v-model="filterPregnantId" placeholder="按孕妇筛选" clearable filterable style="width: 180px" @change="handleFilterChange">
        <el-option v-for="p in pregnant" :key="p.pregnant_id" :label="p.display_name" :value="p.pregnant_id" />
      </el-select>
      <el-button :icon="Refresh" @click="fetchRecords" :loading="loading" circle />
    </div>

    <!-- AI 推荐面板 -->
    <el-collapse v-model="recommendPanelOpen" class="recommend-collapse">
      <el-collapse-item name="recommend">
        <template #title>
          <div class="recommend-header">
            <span>AI 随访推荐</span>
            <el-tag v-if="recommendations.length" size="small" type="info" style="margin-left: 8px">{{ recommendations.length }} 条</el-tag>
          </div>
        </template>
        <div v-if="recommendLoading" class="recommend-loading">
          <el-skeleton :rows="3" animated />
        </div>
        <div v-else-if="!recommendations.length" class="recommend-empty">
          暂无推荐，所有孕妇随访状态良好
        </div>
        <div v-else>
          <!-- 批量操作栏 -->
          <div class="recommend-batch-bar">
            <el-checkbox
              v-model="selectAllRecommendations"
              :indeterminate="isIndeterminate"
              @change="handleSelectAll"
            >
              全选
            </el-checkbox>
            <el-button
              type="primary"
              size="small"
              :disabled="selectedRecommendations.length === 0"
              :loading="batchTriggering"
              @click="doBatchTrigger"
            >
              批量触发 ({{ selectedRecommendations.length }})
            </el-button>
          </div>
          <div class="recommend-list">
            <div v-for="(rec, i) in recommendations" :key="i" class="recommend-item">
              <el-checkbox v-model="rec._selected" class="recommend-item__checkbox" />
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
          <el-table-column prop="chief_complaint" label="主诉" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.chief_complaint || '无' }}
            </template>
          </el-table-column>
          <el-table-column label="分类" width="80" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.classification === 'critical' ? 'danger' : row.classification === 'abnormal' ? 'warning' : 'success'"
                size="small"
              >
                {{ row.classification === 'critical' ? '高危' : row.classification === 'abnormal' ? '异常' : '正常' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right" align="left" header-align="left">
            <template #default="{ row }">
              <div class="table-row-actions">
                <el-button type="primary" class="brand-gradient-btn" size="small" @click.stop="goPregnantDetail(row)">
                  孕妇详情
                </el-button>
                <el-button
                  v-if="row.status === 'completed'"
                  type="primary"
                  class="brand-gradient-btn"
                  size="small"
                  @click.stop="openReviewDrawer(row)"
                >
                  确认审核
                </el-button>
                <el-button
                  v-else-if="row.status === 'in_progress'"
                  type="warning"
                  size="small"
                  @click.stop="openReviewDrawer(row)"
                >
                  进行中
                </el-button>
                <el-button
                  v-else-if="row.status === 'draft'"
                  type="primary"
                  class="brand-gradient-btn"
                  size="small"
                  @click.stop="openReviewDrawer(row)"
                >
                  查看/编辑
                </el-button>
                <el-button
                  v-else
                  type="info"
                  size="small"
                  @click.stop="openReviewDrawer(row)"
                >
                  查看详情
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

    <!-- 随访审核/编辑抽屉 -->
    <el-drawer
      v-model="showReviewDrawer"
      :title="drawerTitle"
      size="620px"
      destroy-on-close
    >
      <template v-if="reviewRecord">
        <!-- 记录头：患者信息 + 分类标签 + 状态 -->
        <div class="record-header">
          <div class="record-header__row">
            <div class="record-header__name">{{ reviewRecord.patient_name }}</div>
            <el-tag
              :type="reviewRecord.classification === 'critical' ? 'danger' : reviewRecord.classification === 'abnormal' ? 'warning' : 'success'"
              size="small"
            >
              {{ reviewRecord.classification === 'critical' ? '高危' : reviewRecord.classification === 'abnormal' ? '异常' : '正常' }}
            </el-tag>
            <el-tag :type="statusType(reviewRecord.status)" size="small">
              {{ statusLabel(reviewRecord.status) }}
            </el-tag>
          </div>
          <div class="record-header__meta">
            孕{{ reviewRecord.gestational_week || '--' }}周 &nbsp;|&nbsp;
            {{ formatDate(reviewRecord.follow_up_date) }} &nbsp;|&nbsp;
            {{ reviewRecord.chief_complaint || '无主诉' }}
          </div>
        </div>

        <!-- S: 主观数据 -->
        <div class="record-section">
          <div class="record-section__head">
            <span class="record-badge record-badge--s">S</span>
            <span class="record-section__title">主观数据</span>
          </div>
          <div class="record-section__body">
            <template v-if="Object.keys(visibleSelfReportedData).length">
              <div v-for="(val, key) in visibleSelfReportedData" :key="key" class="record-kv">
                <span class="record-kv__key">{{ fieldLabel(String(key)) }}</span>
                <span class="record-kv__val">{{ formatDisplayValue(val) }}</span>
              </div>
            </template>
            <span v-else class="record-muted">暂无自报数据</span>
          </div>
        </div>

        <!-- O: 客观检查 -->
        <div class="record-section">
          <div class="record-section__head">
            <span class="record-badge record-badge--o">O</span>
            <span class="record-section__title">客观检查</span>
          </div>
          <div class="record-section__body">
            <!-- 产科检查 -->
            <div v-if="hasExam(reviewRecord.obstetric_exam)" class="record-exam-row">
              <div v-for="(val, key) in reviewRecord.obstetric_exam" :key="key" class="record-exam-cell">
                <div class="record-exam-cell__label">{{ examLabel(String(key)) }}</div>
                <div class="record-exam-cell__value" :class="examHighlightClass(String(key), val)">{{ val }}</div>
              </div>
            </div>
            <!-- 化验结果 -->
            <div v-if="hasExam(reviewRecord.lab_results)" class="record-exam-row" style="margin-top: 6px;">
              <div v-for="(val, key) in reviewRecord.lab_results" :key="key" class="record-exam-cell">
                <div class="record-exam-cell__label">{{ labLabel(String(key)) }}</div>
                <div class="record-exam-cell__value" :class="labHighlightClass(String(key), val)">{{ val }}</div>
              </div>
            </div>
            <span v-if="!hasExam(reviewRecord.obstetric_exam) && !hasExam(reviewRecord.lab_results)" class="record-muted">暂无检查数据</span>
          </div>
        </div>

        <!-- A: 评估 -->
        <div class="record-section">
          <div class="record-section__head">
            <span class="record-badge record-badge--a">A</span>
            <span class="record-section__title">评估</span>
          </div>
          <div class="record-section__body">
            <p class="record-summary">{{ reviewRecord.summary || '暂无评估' }}</p>
            <!-- AI 快照分析（已完成的记录显示历史快照） -->
            <div v-if="reviewRecord.ai_snapshot && Object.keys(reviewRecord.ai_snapshot).length" class="record-ai-snapshot">
              <div class="record-ai-snapshot__title">AI 分析快照</div>
              <div v-if="reviewRecord.ai_snapshot.summary || reviewRecord.ai_snapshot.warm_summary" class="record-ai-snapshot__text">
                {{ reviewRecord.ai_snapshot.summary || reviewRecord.ai_snapshot.warm_summary }}
              </div>
              <div v-if="(reviewRecord.ai_snapshot.abnormal_flags || reviewRecord.ai_snapshot.abnormal_indicators)?.length" class="record-ai-snapshot__abnormal">
                <el-tag
                  v-for="(item, i) in (reviewRecord.ai_snapshot.abnormal_flags || reviewRecord.ai_snapshot.abnormal_indicators)"
                  :key="i"
                  type="danger"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px;"
                >{{ item }}</el-tag>
              </div>
              <div v-if="reviewRecord.ai_snapshot.detail_analysis" class="record-ai-snapshot__text" style="margin-top: 6px">
                {{ reviewRecord.ai_snapshot.detail_analysis }}
              </div>
            </div>
          </div>
        </div>

        <!-- P: 计划 -->
        <div class="record-section">
          <div class="record-section__head">
            <span class="record-badge record-badge--p">P</span>
            <span class="record-section__title">计划</span>
          </div>
          <div class="record-section__body">
            <!-- 指导标签 -->
            <div v-if="reviewRecord.guidance_tags?.length" class="record-guidance-list">
              <div v-for="(g, i) in reviewRecord.guidance_tags" :key="i" class="record-guidance-item">
                <el-tag size="small" effect="plain">{{ g.tag }}</el-tag>
                <span>{{ g.content }}</span>
              </div>
            </div>
            <!-- 下次随访 -->
            <div v-if="reviewRecord.next_followup_date" class="record-next-date">
              下次随访日期：{{ formatDate(reviewRecord.next_followup_date) }}
            </div>
            <!-- 转诊 -->
            <div v-if="reviewRecord.referral?.has_referral" class="record-referral">
              转诊：{{ reviewRecord.referral.reason }} → {{ reviewRecord.referral.institution }} {{ reviewRecord.referral.department }}
            </div>
            <span v-if="!reviewRecord.guidance_tags?.length && !reviewRecord.referral && !reviewRecord.next_followup_date" class="record-muted">暂无计划</span>
          </div>
        </div>

        <!-- 审核追溯（已审核的记录显示） -->
        <div v-if="reviewRecord.reviewed_by" class="record-section record-section--audit">
          <div class="record-section__head">
            <span class="record-section__title">审核信息</span>
          </div>
          <div class="record-section__body record-audit-info">
            <span>审核人：{{ reviewRecord.reviewed_by }}</span>
            <span v-if="reviewRecord.reviewed_at">时间：{{ formatDate(reviewRecord.reviewed_at) }}</span>
            <span v-if="reviewRecord.review_comment">意见：{{ reviewRecord.review_comment }}</span>
            <div v-if="reviewRecord.signature_data?.image" class="record-signature">
              <span>护士签名：</span>
              <img :src="reviewRecord.signature_data.image" class="record-signature__img" />
              <span v-if="reviewRecord.signature_data.signed_at" class="record-signature__time">
                {{ formatDate(reviewRecord.signature_data.signed_at) }}
              </span>
            </div>
          </div>
        </div>

        <!-- AI 审核辅助（待审核时加载） -->
        <div class="record-section" v-if="isReviewable">
          <div class="record-section__head">
            <span class="record-section__title">AI 审核辅助</span>
          </div>
          <div class="record-section__body">
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
                style="margin-bottom: 8px"
              />
              <div v-if="aiReviewResult.abnormal_flags?.length">
                <el-tag
                  v-for="(flag, i) in aiReviewResult.abnormal_flags"
                  :key="i"
                  type="danger"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px;"
                >{{ flag }}</el-tag>
              </div>
              <p v-if="aiReviewResult.detail_analysis" class="record-summary" style="margin-top: 8px;">
                {{ aiReviewResult.detail_analysis }}
              </p>
            </template>
            <span v-else class="record-muted">暂无 AI 分析结果</span>
          </div>
        </div>

        <!-- draft 状态：等待孕妇填写，不可确认归档 -->
        <div class="record-actions" v-if="reviewRecord.status === 'draft'">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="该随访尚未被孕妇填写，无法确认归档。"
            style="flex: 1"
          />
        </div>

        <!-- in_progress 状态：等待孕妇填写完成 -->
        <div class="record-actions" v-else-if="isInProgress">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="孕妇正在填写中，请等待完成后再进行审核。"
            style="flex: 1"
          />
        </div>

        <!-- completed 状态：审核通过 + 上报医生 -->
        <div class="record-actions" v-else-if="isReviewable">
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

        <!-- confirmed 状态：前往归档确认页 -->
        <div class="record-actions" v-else-if="reviewRecord.status === 'confirmed'">
          <el-button
            type="primary"
            @click="goPrintPage"
            style="flex: 1"
          >
            归档确认
          </el-button>
        </div>

        <!-- archived 状态：打印/导出（归档后方可发布） -->
        <div class="record-actions" v-else-if="reviewRecord.status === 'archived'">
          <el-button type="primary" @click="goPrintPage" style="flex: 1">
            预览打印版
          </el-button>
          <el-button type="success" @click="goPrintPage" style="flex: 1">
            导出 PDF
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
import { followUpApi, dashboardApi, nurseAiApi, collaborationApi, nurseBriefingApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FollowUpRecord, Pregnant } from '@/types'
import { fieldLabel, examLabel, labLabel } from '@/utils/labelMaps'

/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 30000
/** 推荐列表刷新倍率：每 N 次记录轮询刷新一次推荐 */
const RECOMMEND_POLL_MULTIPLIER = 3
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTick = 0

/** 开始轮询 */
function startPolling() {
  if (pollTimer) return
  pollTick = 0
  pollTimer = setInterval(() => {
    pollTick++
    fetchRecords()
    // 每 N 次记录轮询同步刷新一次推荐列表
    if (pollTick % RECOMMEND_POLL_MULTIPLIER === 0) {
      fetchRecommendations()
    }
  }, POLL_INTERVAL)
}

/** 停止轮询 */
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/** 页面可见性变化：隐藏时暂停轮询，显示时恢复并立即刷新 */
function handleVisibilityChange() {
  if (document.hidden) {
    stopPolling()
  } else {
    fetchRecords()
    fetchRecommendations()
    startPolling()
  }
}

const router = useRouter()
const loading = ref(false)
const error = ref('')
const records = ref<FollowUpRecord[]>([])
const filterStatus = ref('')
const filterPregnantId = ref('')
const todayOnly = ref(false)
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
/** 编辑功能 */
const editMode = ref(false)
const saveEditLoading = ref(false)
const editForm = ref({ chief_complaint: '', summary: '' })
const editFormAnswers = ref<Array<{ key: string; value: string }>>([])

const drawerTitle = computed(() => {
  if (!reviewRecord.value) return '随访详情'
  const s = reviewRecord.value.status
  if (s === 'draft') return '随访草稿'
  if (s === 'in_progress' || s === 'completed') return '随访审核'
  return '随访记录详情'
})

const isEditable = computed(() => {
  const s = reviewRecord.value?.status
  return s === 'draft' || s === 'in_progress'
})

const isReviewable = computed(() => {
  const s = reviewRecord.value?.status
  return s === 'completed'
})

const isInProgress = computed(() => {
  const s = reviewRecord.value?.status
  return s === 'in_progress'
})

const isArchived = computed(() => {
  const s = reviewRecord.value?.status
  return s === 'confirmed' || s === 'archived'
})

function goPrintPage() {
  if (!reviewRecord.value) return
  router.push({ name: 'FollowUpPrint', params: { id: reviewRecord.value.id } })
}

/** AI 推荐面板 */
const recommendPanelOpen = ref<string[]>(['recommend'])
const recommendLoading = ref(false)
const recommendations = ref<any[]>([])
const batchTriggering = ref(false)
const selectAllRecommendations = ref(false)

const selectedRecommendations = computed(() =>
  recommendations.value.filter((r: any) => r._selected)
)

const isIndeterminate = computed(() => {
  const sel = selectedRecommendations.value.length
  return sel > 0 && sel < recommendations.value.length
})

function handleSelectAll(val: boolean) {
  recommendations.value.forEach((r: any) => { r._selected = val })
}

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
    cancelled: 'info',
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
    draft: '待开始',
    cancelled: '已取消',
  }
  return map[status] || status
}

/** 日期格式化（从ISO字符串直接提取，避免浏览器时区干扰） */
function formatDate(d?: string): string {
  if (!d) return '--'
  // 直接从字符串提取日期部分，避免 new Date() 的时区偏差
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : d.slice(0, 10)
}

function hasExam(obj: Record<string, any> | undefined): boolean {
  return !!obj && Object.keys(obj).length > 0
}

/** 系统内部字段，不应展示给护士 */
const INTERNAL_FIELDS = new Set(['template_id', 'auto_generated'])

/** 过滤掉内部字段后的主观数据 */
const visibleSelfReportedData = computed(() => {
  const data = reviewRecord.value?.self_reported_data
  if (!data) return {}
  return Object.fromEntries(
    Object.entries(data).filter(([key]) => !INTERNAL_FIELDS.has(key))
  )
})

/** 格式化显示值：布尔→中文，对象/数组→友好文本 */
function formatDisplayValue(val: any): string {
  if (val === null || val === undefined || val === '') return '--'
  if (typeof val === 'boolean') return val ? '是' : '否'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function examHighlightClass(key: string, val: any): string {
  if (key === 'fetal_heart_rate_bpm') {
    const v = Number(val)
    if (v < 110 || v > 170) return 'value-abnormal'
  }
  if (key === 'blood_pressure' && typeof val === 'string' && val.includes('/')) {
    const [s, d] = val.split('/').map(Number)
    if (s >= 140 || d >= 90) return 'value-abnormal'
  }
  return ''
}

function labHighlightClass(key: string, val: any): string {
  if (key === 'hemoglobin_g_L' && Number(val) < 100) return 'value-abnormal'
  if (key === 'urine_protein' && val !== '阴性') return 'value-abnormal'
  if (key === 'blood_sugar_fasting' && Number(val) > 5.3) return 'value-abnormal'
  if (key === 'blood_sugar_2h' && Number(val) > 6.7) return 'value-abnormal'
  return ''
}

/** 加载随访记录 */
async function fetchRecords() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, any> = {}
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPregnantId.value) params.pregnant_id = filterPregnantId.value
    if (todayOnly.value) params.today_only = true
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
    pregnant.value = res.data?.data || []
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

/** 打开审核/编辑抽屉 */
async function openReviewDrawer(row: FollowUpRecord) {
  reviewRecord.value = row
  showReviewDrawer.value = true
  editMode.value = false
  editForm.value = {
    chief_complaint: row.chief_complaint || '',
    summary: row.summary || '',
  }
  // 将 self_reported_data 转为可编辑数组
  const data = row.self_reported_data || {}
  editFormAnswers.value = Object.entries(data).map(([key, value]) => ({ key, value: String(value) }))

  // 已完成/进行中的记录加载 AI 审核
  if (row.status === 'completed' || row.status === 'in_progress') {
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
    aiReviewResult.value = null
  }
}

/** 保存编辑 */
async function saveEdit() {
  if (!reviewRecord.value) return
  saveEditLoading.value = true
  try {
    // 将编辑的答案数组转回对象
    const selfReportedData: Record<string, string> = {}
    editFormAnswers.value.forEach(e => {
      if (e.key.trim()) selfReportedData[e.key.trim()] = e.value
    })

    await followUpApi.update(reviewRecord.value.id, {
      chief_complaint: editForm.value.chief_complaint,
      summary: editForm.value.summary,
      self_reported_data: selfReportedData,
    })

    ElMessage.success('保存成功')
    editMode.value = false
    await fetchRecords()
    // 刷新抽屉中的记录
    const updated = records.value.find(r => r.id === reviewRecord.value?.id)
    if (updated) reviewRecord.value = updated
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '保存失败'
    ElMessage.error(msg)
  } finally {
    saveEditLoading.value = false
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

/** 保存护士签名 */
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
    recommendations.value = (res.data?.recommendations || []).map((r: any) => ({ ...r, _triggering: false, _selected: false }))
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
  const idx = recommendations.value.indexOf(rec)
  try {
    await followUpApi.trigger(rec.pregnant_id, rec.template_id)
    ElMessage.success(`已触发对 ${rec.patient_name} 的随访`)
    // 乐观移除：立即从推荐列表中移除，避免等待后端重取
    if (idx !== -1) {
      recommendations.value.splice(idx, 1)
    }
    await fetchRecords()
    // 后台异步同步推荐列表（不阻塞 UI）
    fetchRecommendations()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '触发失败'
    ElMessage.error(msg)
    rec._triggering = false
  }
}

/** 批量触发选中的推荐随访（使用后端批量端点，避免串行逐个调用） */
async function doBatchTrigger() {
  const selected = selectedRecommendations.value
  if (!selected.length) return

  await ElMessageBox.confirm(
    `确定批量触发 ${selected.length} 条随访推荐？`,
    '批量触发确认',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  )

  batchTriggering.value = true
  // 记录选中项的 pregnant_id 集合，用于乐观移除
  const triggeredIds = new Set(selected.map(r => r.pregnant_id))
  try {
    const pregnantIds = selected.map(r => r.pregnant_id)
    const res = await nurseBriefingApi.batchTriggerFollowups(pregnantIds, '')
    const data = res.data
    const triggered = data?.triggered ?? 0
    const skipped = data?.skipped ?? 0
    const errors = data?.errors ?? []

    if (triggered > 0) {
      ElMessage.success(
        `成功触发 ${triggered} 条随访` +
        (skipped > 0 ? `，${skipped} 条已跳过（存在活跃随访）` : '') +
        (errors.length > 0 ? `，${errors.length} 条失败` : '')
      )
    } else if (skipped > 0) {
      ElMessage.warning(`${skipped} 条已跳过（存在活跃随访）`)
    } else {
      ElMessage.error('批量触发失败')
    }

    // 乐观移除：立即从推荐列表中移除已触发的条目（含 skipped 的，因为已有活跃随访）
    recommendations.value = recommendations.value.filter(
      (r: any) => !triggeredIds.has(r.pregnant_id)
    )
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '批量触发失败')
  } finally {
    batchTriggering.value = false
    selectAllRecommendations.value = false
  }

  await fetchRecords()
  // 后台异步同步推荐列表
  fetchRecommendations()
}

onMounted(() => {
  // 从路由查询参数读取默认筛选条件（从工作台统计卡片跳转时传入）
  const query = router.currentRoute.value.query
  const queryStatus = query.status as string
  const queryTodayOnly = query.today_only as string
  if (queryStatus) {
    filterStatus.value = queryStatus
  }
  if (queryTodayOnly === 'true') {
    todayOnly.value = true
  }
  fetchRecords()
  fetchPatients()
  fetchRecommendations()
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
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
.recommend-header {
  display: flex;
  align-items: center;
}
.recommend-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  margin-bottom: 10px;
  background: var(--bg-page);
  border-radius: 8px;
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
.recommend-item__checkbox {
  flex-shrink: 0;
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

/* ===== 随访记录单样式 ===== */
.mb-3 { margin-bottom: 12px; }

.record-header {
  padding: 12px 16px;
  background: linear-gradient(135deg, #f0f9ff, #fff);
  border: 1px solid #d4e6f9;
  border-radius: 10px;
  margin-bottom: 16px;
}
.record-header__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.record-header__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.record-header__meta {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* SOAP 各节 */
.record-section {
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.record-section__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-page);
  border-bottom: 1px solid var(--border);
}
.record-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.record-section__body {
  padding: 12px 14px;
}
.record-muted {
  font-size: 13px;
  color: var(--text-muted);
}

/* S/O/A/P badge */
.record-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.record-badge--s { background: #409EFF; }
.record-badge--o { background: #67C23A; }
.record-badge--a { background: #E6A23C; }
.record-badge--p { background: #909399; }

/* S: 主观数据 key-value */
.record-kv {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border);
}
.record-kv:last-child { border-bottom: none; }
.record-kv__key {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 64px;
  flex-shrink: 0;
}
.record-kv__val {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

/* O: 客观检查网格 */
.record-exam-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.record-exam-cell {
  text-align: center;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 8px;
}
.record-exam-cell__label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 2px;
}
.record-exam-cell__value {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.value-abnormal { color: #F56C6C; }

/* A: 评估 */
.record-summary {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  margin: 0;
}
.record-ai-snapshot {
  margin-top: 10px;
  padding: 10px 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 8px;
}
.record-ai-snapshot__title {
  font-size: 12px;
  font-weight: 600;
  color: #E6A23C;
  margin-bottom: 6px;
}
.record-ai-snapshot__text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

/* P: 指导标签 */
.record-guidance-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.record-guidance-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.record-guidance-item span {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.record-next-date {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.record-referral {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 6px;
  font-size: 12px;
  color: #F56C6C;
}

/* 审核信息 */
.record-section--audit {
  background: #f5f7fa;
  border-color: #e4e7ed;
}
.record-audit-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.record-signature {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  font-size: 13px;
  color: var(--text-secondary);
}
.record-signature__img {
  max-width: 140px;
  max-height: 45px;
  border-bottom: 1px solid #333;
}
.record-signature__time {
  font-size: 12px;
  color: var(--text-muted);
}

/* AI 加载+操作按钮 */
.review-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--text-muted);
  font-size: 13px;
}
.record-actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  margin-top: 12px;
  border-top: 1px solid var(--border);
}

</style>
