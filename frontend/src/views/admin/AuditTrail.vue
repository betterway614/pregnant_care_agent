<template>
  <div class="audit-trail">
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" size="default">
        <el-form-item label="用户ID">
          <el-input v-model="filters.user_id" placeholder="输入用户ID" clearable style="width: 160px;" />
        </el-form-item>
        <el-form-item label="Agent 变体">
          <el-select v-model="filters.agent_variant" placeholder="全部" clearable style="width: 140px;">
            <el-option label="chat" value="chat" />
            <el-option label="record" value="record" />
            <el-option label="qa" value="qa" />
            <el-option label="emergency" value="emergency" />
            <el-option label="complex" value="complex" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px;">
      <el-table :data="sessions" stripe size="small" v-loading="loading" @row-click="showDetail">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="session_id" label="会话ID" width="180" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="intent_classification" label="意图" width="120" />
        <el-table-column prop="agent_variant" label="路由" width="90">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Token" width="80" />
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
              <p v-if="run.tool_calls?.length">
                <b>工具调用:</b> {{ run.tool_calls.map(t => t.name).join('  →  ') }}
              </p>
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
import { ref, reactive, inject } from 'vue'
import { adminApi } from '@/api/admin'
import type { AdminSessionItem, AdminSessionDetail } from '@/types'

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const loading = ref(false)
const sessions = ref<AdminSessionItem[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const filters = reactive({ user_id: '', agent_variant: '' })

const drawerVisible = ref(false)
const detail = ref<AdminSessionDetail | null>(null)

async function fetchData() {
  loading.value = true
  try {
    const res = await adminApi.getSessions({
      page: pagination.page,
      page_size: pagination.page_size,
      user_id: filters.user_id || undefined,
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
function reset() { filters.user_id = ''; filters.agent_variant = ''; pagination.page = 1; fetchData() }

async function showDetail(row: AdminSessionItem) {
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
</style>
