<template>
  <div class="followup-timeline">
    <div v-if="!records.length" class="timeline-empty">
      <el-empty description="暂无随访记录" :image-size="60" />
    </div>
    <div v-else class="timeline-list">
      <div
        v-for="record in records"
        :key="record.id"
        class="timeline-item"
        :class="{ 'timeline-item--selected': record.id === selectedId }"
        @click="$emit('select', record)"
      >
        <div class="timeline-item__dot" :class="dotClass(record.status)" />
        <div class="timeline-item__content">
          <div class="timeline-item__header">
            <span class="timeline-item__date">{{ formatDate(record.follow_up_date) }}</span>
            <el-tag :type="statusType(record.status)" size="small">
              {{ statusLabel(record.status) }}
            </el-tag>
          </div>
          <div v-if="record.gestational_week" class="timeline-item__week">
            孕{{ record.gestational_week }}周
          </div>
          <div v-if="record.summary" class="timeline-item__summary">
            {{ record.summary }}
          </div>
          <div v-if="record.chief_complaint" class="timeline-item__complaint">
            主诉：{{ record.chief_complaint }}
          </div>
          <!-- 展开详情 — SOAP格式化展示 -->
          <div v-if="record.id === selectedId" class="timeline-item__detail">
            <!-- 分类标签 -->
            <div class="detail-classification">
              <el-tag
                :type="classificationType(record.classification)"
                size="small"
              >
                {{ classificationLabel(record.classification) }}
              </el-tag>
              <span v-if="record.next_followup_date" class="detail-next-date">
                下次随访：{{ record.next_followup_date }}
              </span>
            </div>

            <!-- S: 主观数据 -->
            <div v-if="Object.keys(record.self_reported_data || {}).length" class="detail-section">
              <div class="detail-section__title">
                <span class="detail-section__badge detail-section__badge--s">S</span> 主观数据
              </div>
              <div class="detail-section__body">
                <span v-for="(val, key) in record.self_reported_data" :key="key" class="detail-tag">
                  {{ fieldLabel(String(key)) }}: {{ val }}
                </span>
              </div>
            </div>

            <!-- O: 客观检查 -->
            <div v-if="hasExam(record.obstetric_exam) || hasExam(record.lab_results)" class="detail-section">
              <div class="detail-section__title">
                <span class="detail-section__badge detail-section__badge--o">O</span> 客观检查
              </div>
              <div class="exam-grid" v-if="hasExam(record.obstetric_exam)">
                <div class="exam-grid__item" v-for="(val, key) in record.obstetric_exam" :key="key">
                  <span class="exam-grid__label">{{ examLabel(String(key)) }}</span>
                  <span class="exam-grid__value" :class="examHighlightClass(String(key), val)">{{ val }}</span>
                </div>
              </div>
              <div class="exam-grid" v-if="hasExam(record.lab_results)" style="margin-top: 6px;">
                <div class="exam-grid__item" v-for="(val, key) in record.lab_results" :key="key">
                  <span class="exam-grid__label">{{ labLabel(String(key)) }}</span>
                  <span class="exam-grid__value" :class="labHighlightClass(String(key), val)">{{ val }}</span>
                </div>
              </div>
            </div>

            <!-- A: 评估 -->
            <div v-if="record.summary" class="detail-section">
              <div class="detail-section__title">
                <span class="detail-section__badge detail-section__badge--a">A</span> 评估
              </div>
              <div class="detail-section__summary">{{ record.summary }}</div>
            </div>

            <!-- P: 计划 -->
            <div v-if="record.guidance_tags?.length || record.referral" class="detail-section">
              <div class="detail-section__title">
                <span class="detail-section__badge detail-section__badge--p">P</span> 计划
              </div>
              <div class="guidance-tags">
                <div v-for="(g, i) in (record.guidance_tags || [])" :key="i" class="guidance-tag">
                  <el-tag size="small" effect="plain">{{ g.tag }}</el-tag>
                  <span class="guidance-tag__content">{{ g.content }}</span>
                </div>
              </div>
              <div v-if="record.referral?.has_referral" class="referral-card">
                <span class="referral-card__label">转诊</span>
                <span>{{ record.referral.reason }} → {{ record.referral.institution }} {{ record.referral.department }}</span>
              </div>
            </div>

            <!-- 审核追溯 -->
            <div v-if="record.reviewed_by" class="detail-section detail-section--audit">
              <div class="detail-section__title">审核信息</div>
              <div class="audit-info">
                <span>审核人：{{ record.reviewed_by }}</span>
                <span v-if="record.reviewed_at">时间：{{ formatDate(record.reviewed_at) }}</span>
                <span v-if="record.review_comment">意见：{{ record.review_comment }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FollowUpHistoryRecord } from '@/types'
import { fieldLabel, examLabel, labLabel } from '@/utils/labelMaps'

defineProps<{
  records: FollowUpHistoryRecord[]
  selectedId?: string | null
}>()

defineEmits<{
  select: [record: FollowUpHistoryRecord]
}>()

function formatDate(iso: string | null): string {
  if (!iso) return '--'
  const m = iso.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : iso.slice(0, 10)
}

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

function dotClass(status: string): string {
  if (status === 'archived' || status === 'confirmed') return 'dot--success'
  if (status === 'in_progress') return 'dot--warning'
  if (status === 'draft') return 'dot--default'
  return 'dot--default'
}

function classificationType(cls: string): string {
  const map: Record<string, string> = { critical: 'danger', abnormal: 'warning', normal: 'success' }
  return map[cls] || 'info'
}

function classificationLabel(cls: string): string {
  const map: Record<string, string> = { critical: '高危', abnormal: '异常', normal: '正常' }
  return map[cls] || cls
}

function hasExam(obj: Record<string, any> | undefined): boolean {
  return !!obj && Object.keys(obj).length > 0
}

function examHighlightClass(key: string, val: any): string {
  if (key === 'fetal_heart_rate_bpm') {
    const v = Number(val)
    if (v < 110 || v > 170) return 'value--abnormal'
  }
  if (key === 'blood_pressure' && typeof val === 'string' && val.includes('/')) {
    const [s, d] = val.split('/').map(Number)
    if (s >= 140 || d >= 90) return 'value--abnormal'
  }
  return ''
}

function labHighlightClass(key: string, val: any): string {
  if (key === 'hemoglobin_g_L' && Number(val) < 100) return 'value--abnormal'
  if (key === 'urine_protein' && val !== '阴性') return 'value--abnormal'
  if (key === 'blood_sugar_fasting' && Number(val) > 5.3) return 'value--abnormal'
  if (key === 'blood_sugar_2h' && Number(val) > 6.7) return 'value--abnormal'
  return ''
}
</script>

<style scoped>
.followup-timeline {
  height: 100%;
  overflow-y: auto;
}

.timeline-list {
  position: relative;
  padding-left: 20px;
}

.timeline-list::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #e4e7ed;
}

.timeline-item {
  position: relative;
  padding: 12px 0;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: 6px;
  padding-left: 12px;
  margin-bottom: 4px;
}

.timeline-item:hover {
  background: #f5f7fa;
}

.timeline-item--selected {
  background: #ecf5ff;
}

.timeline-item__dot {
  position: absolute;
  left: -17px;
  top: 18px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #e4e7ed;
  background: #fff;
  z-index: 1;
}

.dot--success {
  border-color: #67c23a;
  background: #67c23a;
}

.dot--warning {
  border-color: #e6a23c;
  background: #e6a23c;
}

.dot--default {
  border-color: #909399;
  background: #fff;
}

.timeline-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-item__date {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.timeline-item__week {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.timeline-item__summary {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
  line-height: 1.5;
}

.timeline-item__complaint {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.timeline-item__detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}

.detail-section {
  margin-bottom: 8px;
}

.detail-section__title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}

.detail-section__body {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-tag {
  font-size: 11px;
  background: #f0f2f5;
  padding: 2px 8px;
  border-radius: 4px;
  color: #606266;
}

.detail-section__list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #606266;
}

.detail-section__list li {
  margin: 2px 0;
}

.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

/* 分类标签 */
.detail-classification {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.detail-next-date {
  font-size: 12px;
  color: #909399;
}

/* S/O/A/P badge */
.detail-section__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  margin-right: 4px;
}
.detail-section__badge--s { background: #409EFF; }
.detail-section__badge--o { background: #67C23A; }
.detail-section__badge--a { background: #E6A23C; }
.detail-section__badge--p { background: #909399; }

/* 客观检查网格 */
.exam-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 6px;
}
.exam-grid__item {
  background: #f5f7fa;
  padding: 6px 8px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.exam-grid__label {
  font-size: 11px;
  color: #909399;
}
.exam-grid__value {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.value--abnormal {
  color: #F56C6C;
}

/* 评估摘要 */
.detail-section__summary {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

/* 指导标签 */
.guidance-tags {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.guidance-tag {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.guidance-tag__content {
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

/* 转诊卡片 */
.referral-card {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 6px;
  font-size: 12px;
  color: #E6A23C;
}
.referral-card__label {
  font-weight: 700;
  margin-right: 6px;
}

/* 审核信息 */
.detail-section--audit {
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 6px;
}
.audit-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: #909399;
}
</style>
