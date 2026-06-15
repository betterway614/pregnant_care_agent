<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">排期管理</h1>
      <el-button :icon="Refresh" @click="fetchSchedule" :loading="loading" :disabled="!selectedPregnantId">
        刷新
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

    <!-- 操作栏 -->
    <div class="search-bar">
      <el-select
        v-model="selectedPregnantId"
        placeholder="选择孕妇查看排期"
        filterable
        style="width: 240px"
        @change="onPregnantChange"
        :loading="pregnantLoading"
      >
        <el-option
          v-for="p in pregnant"
          :key="p.pregnant_id"
          :label="p.display_name"
          :value="p.pregnant_id"
        />
      </el-select>
      <el-button
        type="primary"
        :icon="Plus"
        :disabled="!selectedPregnantId"
        :loading="generating"
        @click="generateSchedule"
      >
        生成排期
      </el-button>
      <el-button
        type="success"
        :disabled="!selectedPregnantId || !nodes.length"
        :loading="publishing"
        @click="publishSchedule"
      >
        发布排期
      </el-button>
      <el-tag v-if="selectedPregnantId && nodes.length" type="info" effect="plain" size="small" class="publish-tag">
        {{ isSchedulePublished ? '已发布' : '未发布' }}
      </el-tag>
    </div>

    <!-- 排期内容 -->
    <div v-loading="loading">
      <!-- 未选择孕妇 -->
      <el-empty v-if="!selectedPregnantId" description="请先选择孕妇查看或管理排期" />

      <!-- 无排期节点 -->
      <el-empty v-else-if="!nodes.length" description='暂无排期数据，点击"生成排期"创建'>
        <template #image>
          <el-icon :size="60" color="var(--text-light)"><Calendar /></el-icon>
        </template>
      </el-empty>

      <!-- 时间轴 -->
      <div v-else class="content-card">
        <div class="content-card__header">
          <span class="content-card__title">
            排期时间轴 - {{ currentPregnantName }}
          </span>
          <span class="text-light">{{ nodes.length }} 个节点</span>
        </div>
        <div class="content-card__body">
          <el-timeline>
            <el-timeline-item
              v-for="node in sortedNodes"
              :key="node.id"
              :timestamp="`孕${node.gest_week}周${node.gest_week_start ? ` (${node.gest_week_start}-${node.gest_week_end}周)` : ''} · ${formatDate(node.scheduled_date)}`"
              placement="top"
              :type="getTimelineType(node)"
              :hollow="!node.is_published"
            >
              <el-card shadow="hover" class="node-card">
                <div class="node-card__header">
                  <div class="node-card__title-row">
                    <span class="node-card__week">孕 {{ node.gest_week }} 周</span>
                    <el-tag v-if="node.visit_number" size="small" type="primary">
                      第{{ node.visit_number }}次
                    </el-tag>
                    <el-tag size="small" :type="getNodeTypeTag(node.node_type)">
                      {{ getNodeTypeLabel(node) }}
                    </el-tag>
                    <el-tag v-if="node.category" size="small" :type="getCategoryTag(node.category)">
                      {{ getCategoryLabel(node.category) }}
                    </el-tag>
                    <el-tag v-if="node.status === 'completed'" size="small" type="success">已完成</el-tag>
                    <el-tag v-if="node.is_published" size="small" type="info">已发布</el-tag>
                  </div>
                </div>

                <p class="node-card__item">{{ node.item }}</p>

                <!-- 必查项目 -->
                <div v-if="node.mandatory_items?.length" class="node-card__items">
                  <span class="node-card__items-label">必查：</span>
                  <el-tag
                    v-for="(mi, i) in node.mandatory_items"
                    :key="'m'+i"
                    size="small"
                    type="danger"
                    effect="plain"
                    class="node-card__item-tag"
                  >{{ mi }}</el-tag>
                </div>

                <!-- 备查项目 -->
                <div v-if="node.optional_items?.length" class="node-card__items">
                  <span class="node-card__items-label">备查：</span>
                  <el-tag
                    v-for="(oi, i) in node.optional_items"
                    :key="'o'+i"
                    size="small"
                    type="warning"
                    effect="plain"
                    class="node-card__item-tag"
                  >{{ oi }}</el-tag>
                </div>

                <!-- 注意事项 -->
                <div v-if="node.notes" class="node-card__notes">
                  <el-icon><InfoFilled /></el-icon>
                  <span>{{ node.notes }}</span>
                </div>

                <div class="node-card__footer">
                  <div class="node-card__frequency" v-if="node.frequency && node.frequency !== 'once'">
                    <span class="text-light">频率：</span>
                    <el-tag size="small" type="info">{{ getFrequencyLabel(node.frequency) }}</el-tag>
                  </div>
                  <div class="node-card__date">
                    <span class="node-card__date-label">日期：</span>
                    <el-date-picker
                      v-model="node.scheduled_date"
                      type="date"
                      size="small"
                      value-format="YYYY-MM-DD"
                      placeholder="选择日期"
                      style="width: 150px"
                      @change="(val: string) => updateNodeDate(node, val)"
                    />
                  </div>
                  <div class="node-card__status">
                    <span class="text-light">状态：</span>
                    <el-tag :type="node.status === 'completed' ? 'success' : 'warning'" size="small">
                      {{ node.status === 'completed' ? '已完成' : '待执行' }}
                    </el-tag>
                  </div>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Refresh, Calendar, InfoFilled } from '@element-plus/icons-vue'
import { scheduleApi, dashboardApi } from '@/api/endpoints'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Pregnant, ScheduleNode } from '@/types'

const route = useRoute()
const loading = ref(false)
const error = ref('')
const pregnant = ref<Pregnant[]>([])
const pregnantLoading = ref(false)
const selectedPregnantId = ref('')
const nodes = ref<ScheduleNode[]>([])
const generating = ref(false)
const publishing = ref(false)

/** 当前孕妇名称 */
const currentPregnantName = computed(() => {
  const p = pregnant.value.find((p) => p.pregnant_id === selectedPregnantId.value)
  return p?.display_name || selectedPregnantId.value
})

/** 按孕周排序的节点 */
const sortedNodes = computed(() => {
  return [...nodes.value].sort((a, b) => a.gest_week - b.gest_week)
})

/** 排期是否已发布（所有节点 is_published 都为 1） */
const isSchedulePublished = computed(() => {
  return nodes.value.length > 0 && nodes.value.every((n) => n.is_published)
})

/** 获取时间轴类型 */
function getTimelineType(node: ScheduleNode): string {
  if (node.status === 'completed') return 'primary'
  if (!node.is_published) return 'info'
  return 'primary'
}

/** 获取节点类型标签样式 */
function getNodeTypeTag(type: string): string {
  const map: Record<string, string> = {
    检查: 'primary',
    超声: 'success',
    随访: 'warning',
    评估: 'info',
    检验: '',
  }
  return map[type] || 'info'
}

/** 获取节点类型中文标签 */
function getNodeTypeLabel(node: ScheduleNode): string {
  const map: Record<string, string> = {
    routine: '常规产检',
    fgr_high_risk: 'FGR高风险',
    gdm_monitor: 'GDM监测',
    bp_monitor: '血压监测',
    ultrasound: '超声检查',
    checkup: '产检',
    lab: '检验',
    custom: '自定义',
  }
  return map[node.node_type] || node.node_type
}

/** 获取分类标签样式 */
function getCategoryTag(category: string): string {
  const map: Record<string, string> = {
    checkup: 'primary',
    ultrasound: 'success',
    lab: 'warning',
  }
  return map[category] || 'info'
}

/** 获取分类中文标签 */
function getCategoryLabel(category: string): string {
  const map: Record<string, string> = {
    checkup: '产检',
    ultrasound: '超声',
    lab: '检验',
  }
  return map[category] || category
}

/** 获取频率中文标签 */
function getFrequencyLabel(frequency: string): string {
  const map: Record<string, string> = {
    once: '单次',
    weekly: '每周',
    biweekly: '每两周',
    every_4_weeks: '每四周',
  }
  return map[frequency] || frequency
}

/** 日期格式化 */
function formatDate(d?: string): string {
  if (!d) return '--'
  const date = new Date(d)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/** 加载孕妇列表 */
async function fetchPregnant() {
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

/** 加载排期 */
async function fetchSchedule() {
  if (!selectedPregnantId.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await scheduleApi.get(selectedPregnantId.value)
    nodes.value = res.data || []
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '加载排期失败'
    error.value = msg
    console.error('加载排期失败:', err)
  } finally {
    loading.value = false
  }
}

/** 孕妇切换 */
function onPregnantChange() {
  nodes.value = []
  error.value = ''
  if (selectedPregnantId.value) {
    fetchSchedule()
  }
}

/** 生成排期 */
async function generateSchedule() {
  if (!selectedPregnantId.value) return
  try {
    await ElMessageBox.confirm(
      `将为孕妇「${currentPregnantName.value}」生成完整孕期排期，是否继续？`,
      '确认生成排期',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'info' }
    )
  } catch {
    return
  }

  generating.value = true
  try {
    await scheduleApi.generate(selectedPregnantId.value)
    ElMessage.success('排期生成成功')
    await fetchSchedule()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '生成排期失败'
    ElMessage.error(msg)
    console.error('生成排期失败:', err)
  } finally {
    generating.value = false
  }
}

/** 发布排期 */
async function publishSchedule() {
  if (!selectedPregnantId.value) return
  try {
    await ElMessageBox.confirm(
      `确认发布「${currentPregnantName.value}」的全部排期节点？发布后不可撤回。`,
      '确认发布排期',
      { confirmButtonText: '发布', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  publishing.value = true
  try {
    await scheduleApi.publish(selectedPregnantId.value)
    ElMessage.success('排期发布成功')
    await fetchSchedule()
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '发布排期失败'
    ElMessage.error(msg)
    console.error('发布排期失败:', err)
  } finally {
    publishing.value = false
  }
}

/** 更新节点日期 */
async function updateNodeDate(node: ScheduleNode, newDate: string) {
  if (!newDate || newDate === node.scheduled_date) return
  try {
    await scheduleApi.updateNode(node.id, { scheduled_date: newDate })
    ElMessage.success('日期更新成功')
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || '日期更新失败'
    ElMessage.error(msg)
    console.error('更新节点日期失败:', err)
    // 重新加载以恢复正确日期
    await fetchSchedule()
  }
}

onMounted(async () => {
  await fetchPregnant()
  // 从路由 query 读取预选孕妇（从孕妇详情页跳转时传入）
  const queryPregnantId = route.query.pregnant_id as string
  if (queryPregnantId && pregnant.value.some(p => p.pregnant_id === queryPregnantId)) {
    selectedPregnantId.value = queryPregnantId
    fetchSchedule()
  }
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.publish-tag {
  margin-left: 8px;
}

/* 时间轴卡片 - 玻璃拟态 */
.node-card {
  border-radius: var(--radius);
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--glass-border);
  transition: all var(--transition);
}

.node-card:hover {
  box-shadow: var(--shadow);
  border-color: rgba(255, 255, 255, 0.55);
}

.node-card__header {
  margin-bottom: 10px;
}

.node-card__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.node-card__week {
  font-size: 15px;
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.node-card__item {
  font-size: 14px;
  color: var(--text-primary);
  margin: 10px 0;
  line-height: 1.6;
}

/* 必查/备查项目标签区 */
.node-card__items {
  margin: 8px 0;
  display: flex;
  align-items: flex-start;
  gap: 4px;
  flex-wrap: wrap;
}
.node-card__items-label {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  line-height: 22px;
  margin-right: 4px;
}
.node-card__item-tag {
  margin-bottom: 2px;
}

/* 注意事项 */
.node-card__notes {
  margin: 8px 0;
  padding: 8px 12px;
  background: rgba(230, 162, 60, 0.08);
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: flex-start;
  gap: 6px;
  line-height: 1.5;
}

.node-card__frequency {
  display: flex;
  align-items: center;
  gap: 4px;
}

.node-card__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.node-card__date {
  display: flex;
  align-items: center;
  gap: 4px;
}

.node-card__date-label {
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
}

.node-card__status {
  display: flex;
  align-items: center;
  gap: 4px;
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
