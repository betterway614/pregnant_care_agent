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
          <!-- 展开详情 -->
          <div v-if="record.id === selectedId" class="timeline-item__detail">
            <div v-if="Object.keys(record.self_reported_data || {}).length" class="detail-section">
              <div class="detail-section__title">自报数据</div>
              <div class="detail-section__body">
                <span v-for="(val, key) in record.self_reported_data" :key="key" class="detail-tag">
                  {{ key }}: {{ val }}
                </span>
              </div>
            </div>
            <div v-if="record.health_education?.length" class="detail-section">
              <div class="detail-section__title">健康教育</div>
              <ul class="detail-section__list">
                <li v-for="(item, i) in record.health_education" :key="i">{{ item }}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FollowUpHistoryRecord } from '@/types'

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
  }
  return map[status] || 'info'
}

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

function dotClass(status: string): string {
  if (status === 'archived' || status === 'confirmed') return 'dot--success'
  if (status === 'in_progress') return 'dot--warning'
  return 'dot--default'
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
</style>
