<template>
  <div class="audit-trail">
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" size="default">
        <el-form-item label="用户ID">
          <el-input v-model="filters.user_id" placeholder="输入用户ID" clearable style="width: 160px;" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="filters.agent_role" placeholder="全部" clearable style="width: 120px;" @change="onRoleChange">
            <el-option label="孕妇端" value="pregnant" />
            <el-option label="护士端" value="nurse" />
            <el-option label="医生端" value="doctor" />
          </el-select>
        </el-form-item>
        <el-form-item label="Agent 变体">
          <el-select v-model="filters.agent_variant" placeholder="全部" clearable style="width: 160px;">
            <template v-if="filters.agent_role">
              <el-option v-for="v in roleVariants" :key="v.value" :label="v.label" :value="v.value" />
            </template>
            <template v-else>
              <el-option-group v-for="group in allVariantGroups" :key="group.role" :label="group.label">
                <el-option v-for="v in group.variants" :key="v.value" :label="v.label" :value="v.value" />
              </el-option-group>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search" style="background-color: #3b82f6; border-color: #3b82f6;">查询</el-button>
          <el-button @click="reset" style="border-color: #d1d5db; color: #374151;">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px;">
      <el-table :data="sessions" stripe size="small" v-loading="loading" @row-click="showDetail">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="agent_role" label="角色" width="80">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.agent_role)" size="small">{{ roleLabel(row.agent_role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="session_id" label="会话ID" width="180" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="intent_classification" label="意图" width="120" />
        <el-table-column prop="agent_variant" label="路由" width="90">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="model_id" label="模型" width="140" show-overflow-tooltip />
        <el-table-column prop="total_tokens" label="Token 数" width="80" />
        <el-table-column prop="total_latency_ms" label="延迟" width="80">
          <template #default="{ row }">{{ row.total_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="guardrail_triggered" label="护栏" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.guardrail_triggered" type="danger" size="small">触发</el-tag>
            <span v-else style="color: #bbb;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default>
            <el-button type="primary" link size="small">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; text-align: right;">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="fetchData"
        />
      </div>
    </el-card>

    <el-drawer v-model="drawerVisible" title="会话审计详情" size="600px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="会话ID">{{ detail.session_id }}</el-descriptions-item>
          <el-descriptions-item label="记录数">{{ detail.run_count }}</el-descriptions-item>
        </el-descriptions>

        <el-timeline style="margin-top: 24px;">
          <el-timeline-item
            v-for="run in detail.runs"
            :key="run.id"
            :timestamp="run.created_at"
            placement="top"
            :type="run.guardrail_triggered ? 'danger' : 'primary'"
          >
            <el-card shadow="never" size="small">
              <p><b>路由:</b> {{ run.routed_agent }} | <b>意图:</b> {{ run.intent_classification || '-' }}</p>
              <p><b>Token:</b> 输入={{ run.input_tokens }} 输出={{ run.output_tokens }} 总计={{ run.total_tokens }}</p>
              <p><b>延迟:</b> {{ run.total_latency_ms }}ms | <b>模型:</b> {{ run.model_id }}</p>
              <div v-if="run.tool_call_count || run.tool_calls?.length" class="tool-call-section">
                <div class="tool-call-summary" @click.stop="toggleToolCalls(run)">
                  <b>工具调用 ({{ run.tool_call_count || run.tool_calls?.length }})</b>
                  <span v-if="run.tool_error_count" style="color: #ff4d4f; margin-left: 8px;">
                    错误={{ run.tool_error_count }}
                  </span>
                  <span class="tool-call-names">{{ (run.tool_calls || []).map((t: any) => t.name).join('  →  ') }}</span>
                  <el-button type="primary" link size="small" style="margin-left: auto;">
                    {{ expandedRuns.has(run.id) ? '收起 ▲' : '详情 ▼' }}
                  </el-button>
                </div>

                <transition name="el-fade-in">
                  <div v-if="expandedRuns.has(run.id)" class="tool-call-details" @click.stop>
                    <div v-if="loadingToolCalls.has(run.id)" style="text-align: center; padding: 12px;">
                      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
                    </div>
                    <template v-else-if="toolCallData.get(run.id)?.length">
                      <div
                        v-for="tc in toolCallData.get(run.id)"
                        :key="tc.call_order"
                        class="tool-call-card"
                        :class="{ 'is-error': !tc.success }"
                      >
                        <div class="tc-header">
                          <span class="tc-order">#{{ tc.call_order + 1 }}</span>
                          <span class="tc-name">{{ tc.tool_name }}</span>
                          <el-tag :type="tc.success ? 'success' : 'danger'" size="small" style="margin-left: auto;">
                            {{ tc.success ? '成功' : '失败' }}
                          </el-tag>
                          <span v-if="tc.latency_ms != null" class="tc-latency">{{ tc.latency_ms }}ms</span>
                        </div>
                        <div v-if="tc.tool_args && Object.keys(tc.tool_args).length" class="tc-block">
                          <div class="tc-label">调用参数</div>
                          <pre class="tc-pre">{{ JSON.stringify(tc.tool_args, null, 2) }}</pre>
                        </div>
                        <div v-if="tc.result_preview" class="tc-block">
                          <div class="tc-label">返回结果</div>
                          <pre class="tc-pre">{{ tc.result_preview }}</pre>
                        </div>
                        <div v-if="tc.error_message" class="tc-block tc-error">
                          <div class="tc-label">错误信息</div>
                          <pre class="tc-pre">{{ tc.error_message }}</pre>
                        </div>
                      </div>
                    </template>
                    <div v-else style="color: #bbb; padding: 8px; font-size: 12px;">无工具调用详情数据</div>
                  </div>
                </transition>
              </div>
              <p v-if="run.response_preview" style="color: #8c8c8c;">
                <b>回复预览:</b> {{ run.response_preview }}
              </p>
              <p v-if="run.guardrail_triggered" style="color: #ff4d4f;">
                <el-icon><WarningFilled /></el-icon> 安全护栏已触发
              </p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, inject } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { adminApi } from '@/api/admin'
import type { AdminSessionItem, AdminSessionDetail, AdminSessionRun, ToolCallDetailItem } from '@/types'

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

// ── 角色-变体映射 ──
interface VariantOption { label: string; value: string }

const ROLE_VARIANTS: Record<string, VariantOption[]> = {
  pregnant: [
    { label: '对话', value: 'chat' },
    { label: '记录', value: 'record' },
    { label: '问答', value: 'qa' },
    { label: '紧急', value: 'emergency' },
    { label: '复杂分析', value: 'complex' },
  ],
  nurse: [
    { label: '分析', value: 'analyze' },
    { label: '随访', value: 'followup' },
    { label: '上报', value: 'report' },
    { label: '对话', value: 'chat' },
    { label: '复杂分析', value: 'complex' },
  ],
  doctor: [
    { label: '分析', value: 'analyze' },
    { label: '医嘱', value: 'order' },
    { label: '处置', value: 'issue' },
    { label: '对话', value: 'chat' },
    { label: '复杂分析', value: 'complex' },
  ],
}

const ROLE_LABELS: Record<string, string> = { pregnant: '孕妇', nurse: '护士', doctor: '医生' }
const ROLE_TAG_TYPES: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
  pregnant: '', nurse: 'success', doctor: 'warning',
}

const allVariantGroups = computed(() => [
  { role: 'pregnant', label: '孕妇端', variants: ROLE_VARIANTS.pregnant },
  { role: 'nurse', label: '护士端', variants: ROLE_VARIANTS.nurse },
  { role: 'doctor', label: '医生端', variants: ROLE_VARIANTS.doctor },
])

const roleVariants = computed(() => ROLE_VARIANTS[filters.agent_role] ?? [])

function roleLabel(role: string) { return ROLE_LABELS[role] ?? role }
function roleTagType(role: string) { return ROLE_TAG_TYPES[role] ?? 'info' }

// ── 状态 ──
const loading = ref(false)
const sessions = ref<AdminSessionItem[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const filters = reactive({ user_id: '', agent_role: '', agent_variant: '' })

const drawerVisible = ref(false)
const detail = ref<AdminSessionDetail | null>(null)

// ── 工具调用详情展开状态 ──
const expandedRuns = ref<Set<number>>(new Set())
const loadingToolCalls = ref<Set<number>>(new Set())
const toolCallData = ref<Map<number, ToolCallDetailItem[]>>(new Map())

async function toggleToolCalls(run: AdminSessionRun) {
  if (expandedRuns.value.has(run.id)) {
    expandedRuns.value.delete(run.id)
    return
  }
  expandedRuns.value.add(run.id)
  if (toolCallData.value.has(run.id)) return  // 已缓存
  loadingToolCalls.value.add(run.id)
  try {
    const res = await adminApi.getToolCallsBySession(detail.value!.session_id)
    const runData = res.data.runs.find(r => r.audit_log_id === run.id)
    toolCallData.value.set(run.id, runData?.tool_calls ?? [])
  } catch {
    toolCallData.value.set(run.id, [])
  } finally {
    loadingToolCalls.value.delete(run.id)
  }
}

function onRoleChange() {
  filters.agent_variant = ''
}

async function fetchData() {
  loading.value = true
  try {
    const res = await adminApi.getSessions({
      page: pagination.page,
      page_size: pagination.page_size,
      user_id: filters.user_id || undefined,
      agent_role: filters.agent_role || undefined,
      agent_variant: filters.agent_variant || undefined,
      date_from: dateRange.from.value,
      date_to: dateRange.to.value,
    })
    sessions.value = res.data.data
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function search() { pagination.page = 1; fetchData() }
function reset() { filters.user_id = ''; filters.agent_role = ''; filters.agent_variant = ''; pagination.page = 1; fetchData() }

async function showDetail(row: AdminSessionItem) {
  // 重置工具调用展开状态
  expandedRuns.value = new Set()
  loadingToolCalls.value = new Set()
  toolCallData.value = new Map()
  try {
    const res = await adminApi.getSessionDetail(row.session_id)
    detail.value = res.data
    drawerVisible.value = true
  } catch { /* ignore */ }
}

fetchData()
</script>

<style scoped>
.filter-card :deep(.el-card__body) { padding: 16px 20px 0; }

/* ── 工具调用面板 ── */
.tool-call-section { margin: 8px 0 4px; border: 1px solid #f0f0f0; border-radius: 6px; overflow: hidden; }

.tool-call-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fafafa;
  cursor: pointer;
  font-size: 13px;
  user-select: none;
  transition: background 0.15s;
}
.tool-call-summary:hover { background: #f0f5ff; }
.tool-call-names { color: #8c8c8c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }

.tool-call-details { padding: 0 12px 10px; display: flex; flex-direction: column; gap: 8px; }

.tool-call-card {
  margin-top: 8px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
  font-size: 12px;
}
.tool-call-card.is-error { border-color: #ffccc7; background: #fff2f0; }

.tc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.tc-order { color: #bbb; font-size: 11px; min-width: 22px; }
.tc-name { font-weight: 600; color: #262626; word-break: break-all; }
.tc-latency { color: #8c8c8c; font-size: 11px; white-space: nowrap; }

.tc-block { margin-top: 6px; }
.tc-label { font-size: 11px; color: #8c8c8c; margin-bottom: 3px; }
.tc-pre {
  margin: 0;
  padding: 6px 8px;
  background: #f6f8fa;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.5;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: #434343;
}
.tc-error .tc-pre { background: #fff1f0; color: #cf1322; }
</style>
