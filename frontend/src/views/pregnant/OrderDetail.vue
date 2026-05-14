<template>
  <div class="order-detail">
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <template v-else-if="order">
      <div class="order-header">
        <h3>医嘱详情</h3>
        <el-tag :type="getStatusType(order.status)">{{ getStatusText(order.status) }}</el-tag>
      </div>

      <div class="order-content">
        <div class="content-label">医嘱内容</div>
        <div class="content-text">{{ order.content }}</div>
      </div>

      <div class="order-meta">
        <div class="meta-item">
          <span class="meta-label">开具时间</span>
          <span class="meta-value">{{ formatTime(order.created_at) }}</span>
        </div>
        <div class="meta-item" v-if="order.signed_at">
          <span class="meta-label">签署时间</span>
          <span class="meta-value">{{ formatTime(order.signed_at) }}</span>
        </div>
      </div>

      <div class="order-actions" v-if="!order.acknowledged_at">
        <el-button type="primary" @click="handleAcknowledge" :loading="acknowledging">
          我已阅读
        </el-button>
      </div>

      <div class="acknowledged-info" v-else>
        <el-icon><CircleCheck /></el-icon>
        <span>已于 {{ formatTime(order.acknowledged_at) }} 确认阅读</span>
      </div>
    </template>

    <div v-else class="empty-state">
      <el-icon :size="40" color="#94A3B8"><Document /></el-icon>
      <p>医嘱不存在</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loading, CircleCheck, Document } from '@element-plus/icons-vue'
import { orderApi } from '@/api/endpoints'

const route = useRoute()
const order = ref<any>(null)
const loading = ref(true)
const acknowledging = ref(false)

onMounted(async () => {
  const orderId = route.params.orderId as string
  if (!orderId) {
    loading.value = false
    return
  }

  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const res = await orderApi.getPregnantOrders(pid)
      const orders = res.data || []
      order.value = orders.find((o: any) => o.id === orderId) || null
    }
  } catch (err) {
    console.error('加载医嘱失败:', err)
  } finally {
    loading.value = false
  }
})

function getStatusType(status: string): string {
  const map: Record<string, string> = {
    draft: 'info',
    signed: 'success',
    executed: 'primary',
  }
  return map[status] || 'info'
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    signed: '已签署',
    executed: '已执行',
  }
  return map[status] || status
}

function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function handleAcknowledge() {
  if (!order.value) return
  acknowledging.value = true
  try {
    await orderApi.acknowledge(order.value.id)
    order.value.acknowledged_at = new Date().toISOString()
  } catch (err) {
    console.error('确认阅读失败:', err)
  } finally {
    acknowledging.value = false
  }
}
</script>

<style scoped>
.order-detail {
  padding: 16px;
  min-height: 100vh;
  background: var(--el-bg-color);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 12px;
  color: var(--el-text-color-secondary);
}

.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.order-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.order-content {
  margin-bottom: 16px;
}

.content-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.content-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 8px;
}

.order-meta {
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.meta-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.meta-value {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.order-actions {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.acknowledged-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--el-color-success);
  font-size: 14px;
  margin-top: 24px;
}
</style>
