<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">FGR专项看板</h1>
      <el-button type="primary" :icon="Refresh" @click="loadData" :loading="loading">
        刷新数据
      </el-button>
    </div>

    <!-- 分布统计卡片 -->
    <el-row :gutter="16" class="stat-grid-row">
      <el-col :xs="12" :sm="12" :md="6" v-for="card in distributionCards" :key="card.label">
        <StatCard
          :icon="card.icon"
          :value="card.value"
          :label="card.label"
          :color="card.color"
          :bg-color="card.bgColor"
          :sub-label="card.subLabel"
        />
      </el-col>
    </el-row>

    <!-- 搜索/筛选栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索孕妇姓名..."
        clearable
        :prefix-icon="Search"
        style="width: 240px"
        @input="handleSearch"
      />
      <el-select v-model="filterRisk" placeholder="风险等级筛选" clearable style="width: 150px" @change="handleFilter">
        <el-option label="全部" value="" />
        <el-option label="高风险" value="high" />
        <el-option label="中风险" value="medium" />
        <el-option label="低风险" value="low" />
      </el-select>
      <el-select v-model="filterGestWeek" placeholder="孕周范围" clearable style="width: 150px" @change="handleFilter">
        <el-option label="全部" value="" />
        <el-option label="早孕期 (~14周)" value="early" />
        <el-option label="中孕期 (15-28周)" value="mid" />
        <el-option label="晚孕期 (29周~)" value="late" />
      </el-select>
      <el-select v-model="filterImage" placeholder="图片状态" clearable style="width: 130px" @change="handleFilter">
        <el-option label="全部" value="" />
        <el-option label="已绑定图片" value="has" />
        <el-option label="暂无图片" value="none" />
      </el-select>
    </div>

    <!-- FGR孕妇列表 -->
    <div class="content-card" style="margin-bottom: 16px">
      <div class="content-card__header">
        <span class="content-card__title">FGR孕妇列表</span>
        <span class="text-light">共 {{ filteredPregnant.length }} 人</span>
      </div>
      <div class="content-card__body" v-loading="loading">
        <el-table :data="filteredPregnant" stripe style="width: 100%" @row-click="handleRowClick">
          <el-table-column prop="display_name" label="孕妇姓名" min-width="100" />
          <el-table-column label="孕周" width="80" align="center">
            <template #default="{ row }">
              <span class="gest-week">{{ calcGestationalWeek(row.gestational_age_days) }}周</span>
            </template>
          </el-table-column>
          <el-table-column label="超声图像" width="90" align="center">
            <template #default="{ row }">
              <el-tooltip :content="hasImage(row.pregnant_id) ? '点击查看超声图' : '暂无绑定图像'" placement="top">
                <el-button
                  text
                  :type="hasImage(row.pregnant_id) ? 'primary' : 'info'"
                  size="small"
                  :icon="PictureFilled"
                  @click.stop="previewImage(row)"
                >
                  {{ hasImage(row.pregnant_id) ? '查看' : '上传' }}
                </el-button>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="最近FGR等级" width="130">
            <template #default="{ row }">
              <RiskBadge :level="getLatestFgrLevel(row)" />
            </template>
          </el-table-column>
          <el-table-column label="置信区间" width="160" align="center">
            <template #default="{ row }">
              <span class="confidence-range">{{ formatConfidence(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                size="small"
                :loading="assessingIds.has(row.pregnant_id)"
                @click.stop="handleAnalyze(row)"
              >
                分析
              </el-button>
              <el-button text type="primary" size="small" @click.stop="openTrendDrawer(row)">
                趋势
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!filteredPregnant.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><Search /></el-icon>
          <p>{{ searchQuery ? '未找到匹配孕妇' : '暂无FGR孕妇数据' }}</p>
        </div>
      </div>
    </div>

    <!-- 置信区间范围说明 -->
    <div class="content-card">
      <div class="content-card__header">
        <span class="content-card__title">风险等级置信区间范围</span>
        <el-tooltip content="置信区间反映模型预测的可靠性范围" placement="top">
          <el-icon color="var(--text-light)"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="content-card__body">
        <el-row :gutter="16">
          <el-col :span="8" v-for="range in confidenceRanges" :key="range.label">
            <div class="confidence-card" :style="{ borderLeftColor: range.color }">
              <div class="confidence-card__header">
                <RiskBadge :level="range.level" />
                <span class="confidence-card__range">{{ range.lower }} ~ {{ range.upper }}</span>
              </div>
              <p class="confidence-card__desc">{{ range.desc }}</p>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>

    <!-- 超声图像预览弹窗 -->
    <el-dialog v-model="imagePreviewVisible" title="超声图像" width="600px" destroy-on-close>
      <div v-if="imagePreviewId && hasImage(imagePreviewId)" style="text-align: center">
        <el-image
          :src="imagePreviewSrc"
          style="max-width: 100%; max-height: 500px; border-radius: 8px"
          fit="contain"
        />
        <p style="margin-top: 12px; color: var(--text-secondary); font-size: 13px">
          {{ imagePreviewName }} · 孕{{ calcGestationalWeek(imagePreviewGestDays) }}周
        </p>
      </div>
      <div v-else style="text-align: center; padding: 40px">
        <el-icon :size="48" color="var(--text-light)"><PictureFilled /></el-icon>
        <p style="margin-top: 12px; color: var(--text-secondary)">该患者暂无绑定超声图像</p>
        <el-button type="primary" style="margin-top: 12px" @click="imagePreviewVisible = false; openUploadDialog(imagePreviewPregnant!)">
          上传超声图像
        </el-button>
      </div>
    </el-dialog>

    <!-- 上传超声图像弹窗 -->
    <el-dialog v-model="uploadDialogVisible" title="上传超声图像" width="500px" destroy-on-close @closed="resetUploadForm">
      <div v-if="uploadPregnant">
        <el-descriptions :column="2" border style="margin-bottom: 20px">
          <el-descriptions-item label="孕妇">{{ uploadPregnant.display_name }}</el-descriptions-item>
          <el-descriptions-item label="孕周">{{ calcGestationalWeek(uploadPregnant.gestational_age_days) }}周</el-descriptions-item>
        </el-descriptions>

        <el-form label-position="top">
          <el-form-item label="超声图像 (NT期B超, PNG/JPEG)">
            <el-upload
              ref="imageUploadRef"
              :auto-upload="false"
              :limit="1"
              accept="image/png,image/jpeg"
              :on-change="(f: any) => uploadImageFile = f.raw"
              :on-remove="() => uploadImageFile = null"
              drag
            >
              <el-icon :size="32"><UploadFilled /></el-icon>
              <div>拖拽或点击上传超声原图</div>
            </el-upload>
          </el-form-item>
        </el-form>
        <div v-if="uploading" class="upload-progress">
          <el-icon class="is-loading" :size="20"><Loading /></el-icon>
          <span>正在进行图像分割分析...</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!uploadImageFile"
          @click="handleUploadSubmit"
        >
          上传并分析
        </el-button>
      </template>
    </el-dialog>

    <!-- 分析结果弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="FGR 分析结果" width="560px" destroy-on-close>
      <div v-if="lastResult" class="result-body">
        <div class="result-main">
          <span class="result-label">风险评估：</span>
          <RiskBadge :level="lastResult.risk_level" />
          <span class="result-prob">
            FGR 概率 <strong>{{ ((lastResult.fgr_probability ?? 0) * 100).toFixed(1) }}%</strong>
          </span>
        </div>
        <div class="result-row">
          <span>预测标签：<el-tag size="small">{{ lastResult.predicted_label ?? '--' }}</el-tag></span>
          <span>置信度：<el-tag size="small" :type="confidenceTagType(lastResult.model_confidence)">{{ lastResult.model_confidence ?? '--' }}</el-tag></span>
        </div>
        <div class="result-row">
          <span>置信区间：{{ formatCI(lastResult.confidence_interval) }}</span>
          <span>耗时：{{ lastResult.processing_time }}ms</span>
        </div>
        <el-divider />
        <p class="result-explain">{{ lastResult.explanation }}</p>
        <el-collapse v-if="lastResult.fold_details?.length" style="margin-top: 12px">
          <el-collapse-item title="5折预测明细">
            <el-table :data="lastResult.fold_details" size="small" stripe>
              <el-table-column prop="fold" label="折" width="50" />
              <el-table-column label="ResNet" width="80">
                <template #default="{ row }">{{ (row.p_resnet * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column label="SVM" width="80">
                <template #default="{ row }">{{ (row.p_svm * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column label="融合权重" width="80">
                <template #default="{ row }">{{ row.fusion_weight }}</template>
              </el-table-column>
              <el-table-column label="融合概率">
                <template #default="{ row }">{{ (row.p_fused * 100).toFixed(1) }}%</template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button type="primary" @click="resultDialogVisible = false">确定</el-button>
      </template>
    </el-dialog>

    <!-- 趋势图抽屉 -->
    <el-drawer
      v-model="trendDrawerVisible"
      :title="`${trendPregnant?.display_name || ''} - FGR风险趋势`"
      size="500px"
      destroy-on-close
    >
      <div v-loading="trendLoading" style="min-height: 300px">
        <template v-if="trendData.length">
          <div class="trend-summary">
            <div class="trend-summary__item">
              <span class="trend-summary__label">当前风险</span>
              <RiskBadge :level="trendCurrentLevel" />
            </div>
            <div class="trend-summary__item">
              <span class="trend-summary__label">数据点数</span>
              <strong>{{ trendData.length }}</strong>
            </div>
            <div class="trend-summary__item">
              <span class="trend-summary__label">趋势方向</span>
              <el-tag :type="trendDirection === 'up' ? 'danger' : trendDirection === 'down' ? 'success' : 'info'" size="small">
                {{ trendDirection === 'up' ? '上升' : trendDirection === 'down' ? '下降' : '平稳' }}
              </el-tag>
            </div>
          </div>

          <div class="bar-chart">
            <div class="bar-chart__y-axis">
              <span>1.0</span><span>0.8</span><span>0.6</span><span>0.4</span><span>0.2</span><span>0.0</span>
            </div>
            <div class="bar-chart__canvas">
              <div class="bar-chart__grid">
                <div v-for="i in 5" :key="i" class="bar-chart__grid-line" :style="{ bottom: `${i * 20}%` }" />
              </div>
              <div
                v-for="(point, idx) in trendData"
                :key="idx"
                class="bar-chart__bar-group"
                :style="{ left: `${(idx / (trendData.length - 1 || 1)) * 100}%` }"
              >
                <div class="bar-chart__bar" :style="{ height: `${point.risk_score * 100}%`, background: getBarColor(point.risk_score) }">
                  <el-tooltip :content="`${point.gestational_weeks}周: ${(point.risk_score * 100).toFixed(0)}分`" placement="top">
                    <div class="bar-chart__dot" :style="{ background: getBarColor(point.risk_score) }" />
                  </el-tooltip>
                </div>
                <span class="bar-chart__label" v-if="trendData.length <= 15 || idx % Math.ceil(trendData.length / 10) === 0">{{ point.gestational_weeks }}w</span>
              </div>
            </div>
          </div>

          <el-divider />
          <h4 style="margin-bottom: 12px; font-size: 14px">历史评估记录</h4>
          <el-table :data="trendData" stripe size="small" max-height="240">
            <el-table-column label="孕周" width="70" align="center">
              <template #default="{ row }">{{ row.gestational_weeks }}周</template>
            </el-table-column>
            <el-table-column label="风险评分" width="90" align="center">
              <template #default="{ row }">{{ (row.risk_score * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="置信区间" width="120" align="center">
              <template #default="{ row }">{{ (row.confidence_lower * 100).toFixed(1) }}% ~ {{ (row.confidence_upper * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="评估时间" width="90" align="center">
              <template #default="{ row }">{{ formatTime(row.assessed_at) }}</template>
            </el-table-column>
          </el-table>
        </template>
        <div v-if="!trendData.length && !trendLoading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><TrendCharts /></el-icon>
          <p>暂无趋势数据</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { Search, Refresh, InfoFilled, TrendCharts, PictureFilled, UploadFilled, Loading } from '@element-plus/icons-vue'
import { dashboardApi, fgrApi, alertApi } from '@/api/endpoints'
import type { Pregnant, FgrAssessment, FgrTrendPoint, PatientImageInfo, Alert } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const searchQuery = ref('')
const filterRisk = ref('')
const filterGestWeek = ref('')
const filterImage = ref('')
const pregnant = ref<Pregnant[]>([])
const alertList = ref<Alert[]>([])
const trendDrawerVisible = ref(false)
const trendPregnant = ref<Pregnant | null>(null)
const trendData = ref<FgrTrendPoint[]>([])
const trendLoading = ref(false)

// 图片相关状态
const patientImageMap = reactive<Record<string, PatientImageInfo>>({})
const imagePreviewVisible = ref(false)
const imagePreviewId = ref('')
const imagePreviewName = ref('')
const imagePreviewGestDays = ref(0)
const imagePreviewPregnant = ref<Pregnant | null>(null)
const imagePreviewSrc = ref('')

// 上传相关状态
const uploadDialogVisible = ref(false)
const uploadPregnant = ref<Pregnant | null>(null)
const uploadImageFile = ref<File | null>(null)
const uploading = ref(false)

// 分析相关状态
const assessingIds = reactive(new Set<string>())
const resultDialogVisible = ref(false)
const lastResult = ref<FgrAssessment | null>(null)

/** 是否有绑定图片 */
function hasImage(pid: string): boolean {
  return patientImageMap[pid]?.has_image ?? false
}

/** 预览超声图像（异步加载 blob URL） */
async function previewImage(row: Pregnant) {
  imagePreviewPregnant.value = row
  imagePreviewId.value = row.pregnant_id
  imagePreviewName.value = row.display_name
  imagePreviewGestDays.value = row.gestational_age_days ?? 0
  imagePreviewSrc.value = ''
  imagePreviewVisible.value = true

  const blobUrl = await fgrApi.loadImageBlobUrl(row.pregnant_id)
  if (blobUrl) {
    imagePreviewSrc.value = blobUrl
  }
}

/** 打��上传弹窗 */
function openUploadDialog(row: Pregnant) {
  uploadPregnant.value = row
  uploadDialogVisible.value = true
}

/** 重置上传表单 */
function resetUploadForm() {
  uploadImageFile.value = null
}

/** 提交上传并分析 */
async function handleUploadSubmit() {
  if (!uploadImageFile.value || !uploadPregnant.value) return

  uploading.value = true
  const pid = uploadPregnant.value.pregnant_id
  const weeks = uploadPregnant.value.gestational_age_days
    ? Math.floor(uploadPregnant.value.gestational_age_days / 7)
    : 28

  try {
    const fd = new FormData()
    fd.append('gestational_weeks', String(weeks))
    fd.append('image_type', 'AC')
    fd.append('image', uploadImageFile.value)

    const res = await fgrApi.upload(pid, fd)
    lastResult.value = res.data
    resultDialogVisible.value = true
    uploadDialogVisible.value = false

    // 刷新图片状态（异步加载 blob URL，不阻塞主流程）
    patientImageMap[pid] = { pregnant_id: pid, has_image: true, image_url: '', display_name: uploadPregnant.value?.display_name ?? '' }
    fgrApi.loadImageBlobUrl(pid).then(url => { if (url) patientImageMap[pid].image_url = url })
    ElMessage.success('上传成功，分析完成')
    loadData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

/** 触发分析 */
async function handleAnalyze(row: Pregnant) {
  // 无绑定图片：引导上传
  if (!hasImage(row.pregnant_id)) {
    openUploadDialog(row)
    return
  }

  assessingIds.add(row.pregnant_id)
  const weeks = row.gestational_age_days
    ? Math.floor(row.gestational_age_days / 7)
    : 28

  try {
    const res = await fgrApi.assess(row.pregnant_id, { gestational_weeks: weeks })
    lastResult.value = res.data
    resultDialogVisible.value = true
    ElMessage.success('分析完成')
    loadData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '分析失败')
  } finally {
    assessingIds.delete(row.pregnant_id)
  }
}

/** 格式化置信区间显示 */
function formatCI(ci: Record<string, number> | null | undefined): string {
  if (!ci) return '--'
  const lb = ci.lower_bound ?? ci.lowerBound ?? 0
  const ub = ci.upper_bound ?? ci.upperBound ?? 0
  return `${(lb * 100).toFixed(1)}% ~ ${(ub * 100).toFixed(1)}%`
}

/** 置信度标签类型 */
function confidenceTagType(level: string | null | undefined): string {
  if (level === 'High') return 'success'
  if (level === 'Medium') return 'warning'
  if (level === 'Low') return 'info'
  return 'info'
}

/** 风险等级对应颜色 */
const riskColors: Record<string, string> = {
  high: '#D32F2F',
  medium: '#E65100',
  low: '#2E7D32',
}

/** FGR 看板展示所有孕妇（支持上传图片 + 分析） */
const fgrPatients = computed(() => pregnant.value)

/** 已评估的孕妇（有 FGR 预警记录） */
const assessedPatients = computed(() =>
  pregnant.value.filter((p) => hasAlertForPatient(p))
)

const distributionCards = computed(() => {
  const total = pregnant.value.length
  const withImage = pregnant.value.filter((p) => hasImage(p.pregnant_id)).length
  const assessed = assessedPatients.value
  const highCount = assessed.filter((p) => getLatestFgrLevel(p) === 'high').length
  const mediumCount = assessed.filter((p) => getLatestFgrLevel(p) === 'medium').length
  const lowCount = assessed.filter((p) => getLatestFgrLevel(p) === 'low').length

  return [
    { icon: 'User', value: total, label: '全部孕妇', color: 'var(--primary)', bgColor: 'var(--primary-bg)', subLabel: `${withImage} 已绑定影像 · ${assessed.length} 已评估` },
    { icon: 'WarningFilled', value: highCount, label: '高风险', color: '#D32F2F', bgColor: '#FFEBEE', subLabel: `占比 ${assessed.length ? ((highCount / assessed.length) * 100).toFixed(0) : 0}%` },
    { icon: 'WarningFilled', value: mediumCount, label: '中风险', color: '#E65100', bgColor: '#FFF3E0', subLabel: `占比 ${assessed.length ? ((mediumCount / assessed.length) * 100).toFixed(0) : 0}%` },
    { icon: 'CircleCheck', value: lowCount, label: '低风险', color: '#2E7D32', bgColor: '#E8F5E9', subLabel: `占比 ${assessed.length ? ((lowCount / assessed.length) * 100).toFixed(0) : 0}%` },
  ]
})

/** 是否有 FGR 预警 */
function hasAlertForPatient(p: Pregnant): boolean {
  return alertList.value.some(
    (a) => a.pregnant_id === p.pregnant_id && a.trigger_source?.toLowerCase().includes('fgr')
  )
}

function getLatestFgrLevel(pregnant: Pregnant): string {
  if (!hasAlertForPatient(pregnant)) return 'unassessed'
  const fgrAlerts = alertList.value
    .filter((a) => a.pregnant_id === pregnant.pregnant_id && a.trigger_source?.toLowerCase().includes('fgr'))
  if (!fgrAlerts.length) return 'unassessed'
  const latest = fgrAlerts.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())[0]
  return mapLevelToFgr(latest.level)
}

function mapLevelToFgr(level: string): string {
  const map: Record<string, string> = { RED: 'high', ORANGE: 'medium', YELLOW: 'low', GREEN: 'low', high: 'high', medium: 'medium', low: 'low', unassessed: 'unassessed' }
  return map[level] || 'low'
}

function formatConfidence(pregnant: Pregnant): string {
  const fgrAlerts = alertList.value
    .filter((a) => a.pregnant_id === pregnant.pregnant_id && a.trigger_source?.toLowerCase().includes('fgr'))
  if (!fgrAlerts.length) return '--'
  const latest = fgrAlerts.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())[0]
  const details = latest.details
  if (details?.confidence_interval) {
    const ci = details.confidence_interval
    return `${((ci.lowerBound ?? ci.lower_bound ?? 0) * 100).toFixed(1)}% ~ ${((ci.upperBound ?? ci.upper_bound ?? 0) * 100).toFixed(1)}%`
  }
  return '--'
}

function calcGestationalWeek(days?: number): number {
  if (!days) return 0
  return Math.floor(days / 7)
}

function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function getGestStage(days?: number): string {
  if (!days) return ''
  const weeks = Math.floor(days / 7)
  if (weeks <= 14) return 'early'
  if (weeks <= 28) return 'mid'
  return 'late'
}

const filteredPregnant = computed(() => {
  let list = fgrPatients.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter((p) => p.display_name?.toLowerCase().includes(q))
  }
  if (filterRisk.value) {
    list = list.filter((p) => getLatestFgrLevel(p) === filterRisk.value)
  }
  if (filterGestWeek.value) {
    list = list.filter((p) => getGestStage(p.gestational_age_days) === filterGestWeek.value)
  }
  if (filterImage.value === 'has') {
    list = list.filter((p) => hasImage(p.pregnant_id))
  } else if (filterImage.value === 'none') {
    list = list.filter((p) => !hasImage(p.pregnant_id))
  }
  return list
})

function handleSearch() {}
function handleFilter() {}

async function openTrendDrawer(pregnant: Pregnant) {
  trendPregnant.value = pregnant
  trendDrawerVisible.value = true
  trendLoading.value = true
  trendData.value = []
  try {
    const res = await fgrApi.trend(pregnant.pregnant_id)
    trendData.value = (res.data || []).sort((a, b) => a.gestational_weeks - b.gestational_weeks)
  } catch (err) {
    console.error('加载FGR趋势失败:', err)
  } finally {
    trendLoading.value = false
  }
}

const trendCurrentLevel = computed(() => {
  if (!trendData.value.length) return 'low'
  const latest = trendData.value[trendData.value.length - 1]
  if (latest.risk_score >= 0.7) return 'high'
  if (latest.risk_score >= 0.4) return 'medium'
  return 'low'
})

const trendDirection = computed(() => {
  if (trendData.value.length < 2) return 'stable'
  const diff = trendData.value[trendData.value.length - 1].risk_score - trendData.value[0].risk_score
  if (diff > 0.1) return 'up'
  if (diff < -0.1) return 'down'
  return 'stable'
})

function getBarColor(score: number): string {
  if (score >= 0.7) return '#D32F2F'
  if (score >= 0.4) return '#E65100'
  return '#4CAF50'
}

const confidenceRanges = [
  { level: 'high', label: '高风险', color: '#D32F2F', lower: '70%', upper: '100%', desc: 'FGR可能性较高，建议加强监测频率，考虑进一步影像学检查。' },
  { level: 'medium', label: '中风险', color: '#E65100', lower: '40%', upper: '70%', desc: '需要关注，建议2周内复查超声，综合评估胎儿生长指标。' },
  { level: 'low', label: '低风险', color: '#2E7D32', lower: '0%', upper: '40%', desc: '目前风险较低，按常规产检流程进行管理即可。' },
]

/** 点击行：打开图片预览或上传 */
function handleRowClick(row: Pregnant) {
  previewImage(row)
}

/** 批量加载所有孕妇的图片绑定状态 */
async function loadPatientImages() {
  const ids = pregnant.value.map((p) => p.pregnant_id)
  if (!ids.length) return

  try {
    const res = await fgrApi.patientImagesAll(ids.join(','))
    const items = res.data?.data || []
    for (const item of items) {
      if (item.has_image) {
        patientImageMap[item.pregnant_id] = item
      }
    }
  } catch (err) {
    console.error('加载患者图片绑定状态失败:', err)
  }
}

/** 加载数据 */
async function loadData() {
  loading.value = true
  try {
    const [pregnantRes, alertsRes] = await Promise.all([
      dashboardApi.pregnant(),
      alertApi.list({ status: 'pending,escalated,confirmed' }),
    ])
    pregnant.value = pregnantRes.data?.data || []
    alertList.value = alertsRes.data || []
    await loadPatientImages()
  } catch (err) {
    console.error('加载FGR看板数据失败:', err)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.stat-grid-row { margin-bottom: 28px; }

.gest-week { font-weight: 700; color: var(--text-primary); }
.confidence-range { font-size: 13px; color: var(--text-secondary); font-family: 'SF Mono', 'Fira Code', monospace; }

/* 置信区间卡片 - 玻璃拟态 */
.confidence-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--primary);
  border-radius: var(--radius);
  padding: 18px;
  transition: var(--transition);
}
.confidence-card:hover { box-shadow: var(--shadow); border-color: rgba(255, 255, 255, 0.55); }
.confidence-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.confidence-card__range { font-size: 16px; font-weight: 700; color: var(--text-primary); font-family: 'SF Mono', 'Fira Code', monospace; }
.confidence-card__desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin: 0; }

/* 分析结果 */
.result-main { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
.result-label { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.result-prob { font-size: 18px; color: var(--text-primary); font-weight: 600; }
.result-row { display: flex; gap: 24px; margin-bottom: 10px; color: var(--text-secondary); font-size: 13px; }
.result-explain { color: var(--text-secondary); font-size: 13px; line-height: 1.8; }

/* 趋势 */
.trend-summary {
  display: flex; gap: 24px; margin-bottom: 24px;
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 18px;
  border: 1px solid var(--border);
}
.trend-summary__item { display: flex; flex-direction: column; gap: 6px; }
.trend-summary__label { font-size: 12px; color: var(--text-muted); font-weight: 500; }

.bar-chart { display: flex; height: 240px; margin-bottom: 16px; padding: 16px 0; position: relative; }
.bar-chart__y-axis { display: flex; flex-direction: column; justify-content: space-between; padding-right: 8px; font-size: 11px; color: var(--text-muted); width: 32px; flex-shrink: 0; }
.bar-chart__canvas { flex: 1; position: relative; border-left: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.bar-chart__grid { position: absolute; inset: 0; }
.bar-chart__grid-line { position: absolute; left: 0; right: 0; height: 1px; background: var(--border); opacity: 0.4; }
.bar-chart__bar-group { position: absolute; bottom: 0; display: flex; flex-direction: column; align-items: center; transform: translateX(-50%); }
.bar-chart__bar { width: 10px; border-radius: 5px 5px 0 0; min-height: 4px; transition: height 0.5s cubic-bezier(0.4, 0, 0.2, 1); cursor: pointer; position: relative; }
.bar-chart__dot { width: 12px; height: 12px; border-radius: 50%; position: absolute; top: -6px; left: -1px; cursor: pointer; transition: transform 0.2s; box-shadow: 0 2px 6px rgba(0,0,0,0.15); }
.bar-chart__dot:hover { transform: scale(1.4); }
.bar-chart__label { font-size: 10px; color: var(--text-muted); margin-top: 6px; white-space: nowrap; }

.text-light { font-size: 12px; color: var(--text-muted); }
.upload-progress { display: flex; align-items: center; gap: 8px; padding: 12px; color: var(--primary); font-size: 13px; }
.empty-state p { color: var(--text-muted); font-size: 14px; font-weight: 500; }
</style>
