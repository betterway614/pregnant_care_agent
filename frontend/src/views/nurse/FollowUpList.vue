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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh, Document } from '@element-plus/icons-vue'
import { followUpApi, dashboardApi } from '@/api/endpoints'
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

/** 确认归档 */
async function confirmRecord(row: FollowUpRecord) {
  try {
    await followUpApi.confirm(row.id, 'confirmed')
    ElMessage.success('归档成功')
    await fetchRecords()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '归档失败'
    ElMessage.error(msg)
    console.error('归档失败:', err)
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

onMounted(() => {
  fetchRecords()
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

.search-bar {
  margin-bottom: 20px;
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
  color: var(--text-light);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  gap: 12px;
}

.empty-state p {
  color: var(--text-light);
  font-size: 14px;
}
</style>
