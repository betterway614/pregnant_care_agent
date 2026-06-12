<template>
  <div class="order-detail-page">
    <!-- 返回按钮 -->
    <div class="nav-bar">
      <el-button text @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <template v-else-if="order">
      <!-- 使用与医生端一致的医嘱文档样式 -->
      <OrderDocumentPrint
        :patient-name="patientName"
        :gest-week="gestWeek"
        :content="order.content"
        :order-type="order.order_type"
        :source="order.source"
        :signature-image="signatureImage"
        :signed-at="order.signed_at"
      />

      <!-- 已阅读确认区 -->
      <div class="acknowledge-bar">
        <div v-if="!order.acknowledged_at" class="acknowledge-action">
          <el-button type="primary" size="large" @click="handleAcknowledge" :loading="acknowledging">
            我已阅读
          </el-button>
        </div>
        <div v-else class="acknowledged-info">
          <el-icon color="#34D399"><CircleCheck /></el-icon>
          <span>已于 {{ formatTime(order.acknowledged_at) }} 确认阅读</span>
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      <el-icon :size="40" color="#94A3B8"><Document /></el-icon>
      <p>医嘱不存在</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loading, CircleCheck, Document, ArrowLeft } from '@element-plus/icons-vue'
import { orderApi, pregnantApi } from '@/api/endpoints'
import OrderDocumentPrint from '@/components/orders/OrderDocumentPrint.vue'

const route = useRoute()
const order = ref<any>(null)
const loading = ref(true)
const acknowledging = ref(false)
const gestDays = ref(0)

const patientName = computed(() => order.value?.patient_name || '未知')
const gestWeek = computed(() => {
  if (gestDays.value <= 0) return '未知'
  return `${Math.floor(gestDays.value / 7)}+${gestDays.value % 7}`
})
const signatureImage = computed(() => order.value?.signature_data?.image || null)

onMounted(async () => {
  const orderId = route.params.orderId as string
  if (!orderId) {
    loading.value = false
    return
  }

  try {
    const pid = localStorage.getItem('currentPregnantId') || ''
    if (pid) {
      const [ordersRes, homeRes] = await Promise.all([
        orderApi.getPregnantOrders(pid),
        pregnantApi.getHome(pid).catch(() => null)
      ])
      const orders = ordersRes.data || []
      order.value = orders.find((o: any) => o.id === orderId) || null
      if (homeRes) {
        gestDays.value = homeRes.data?.gestational_day || 0
      }
    }
  } catch (err) {
    console.error('加载医嘱失败:', err)
  } finally {
    loading.value = false
  }
})

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
.order-detail-page {
  min-height: 100vh;
  min-height: 100dvh;
  background: #f5f5f5;
  padding-bottom: calc(32px + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.nav-bar {
  padding: 8px 16px;
  padding-top: calc(8px + env(safe-area-inset-top));
  background: #fff;
  border-bottom: 1px solid #eee;
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 12px;
  color: #94A3B8;
}

.acknowledge-bar {
  margin: 20px 16px;
  text-align: center;
}

.acknowledge-action {
  display: flex;
  justify-content: center;
}

.acknowledged-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  color: #34D399;
  background: #fff;
  padding: 16px;
  border-radius: 12px;
}

/* ========== 移动端响应式优化 ========== */
@media (max-width: 768px) {
  .order-detail-page {
    background: #fff;
  }

  .nav-bar {
    padding: 10px 12px;
    padding-top: calc(10px + env(safe-area-inset-top));
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  }

  .loading-state,
  .empty-state {
    min-height: 50vh;
    gap: 16px;
  }

  .loading-state p,
  .empty-state p {
    font-size: 15px;
    color: #94A3B8;
  }

  .acknowledge-bar {
    margin: 0;
    padding: 16px;
    padding-bottom: calc(16px + env(safe-area-inset-bottom));
    background: #fff;
    border-top: 1px solid #f0f0f0;
    /* 固定在底部，确保不被键盘或滚动影响 */
    position: sticky;
    bottom: 0;
    z-index: 5;
  }

  .acknowledge-action {
    width: 100%;
  }

  .acknowledge-action :deep(.el-button) {
    width: 100%;
    height: 48px;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    /* 确保足够的触控面积 */
    min-height: 48px;
  }

  .acknowledged-info {
    padding: 14px 16px;
    border-radius: 12px;
    font-size: 13px;
    gap: 6px;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
  }
}
</style>
