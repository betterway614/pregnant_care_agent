<template>
  <header class="header-bar">
    <div class="header-bar__left">
      <el-button text @click="appStore.toggleSidebar">
        <el-icon :size="20"><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
      </el-button>
      <span class="header-bar__title">{{ currentTitle }}</span>
    </div>

    <div class="header-bar__right">
      <!-- 硬件监控指示器 -->
      <el-tooltip content="硬件状态" placement="bottom">
        <div class="header-bar__hw" @click="showMonitor = true">
          <el-icon><Cpu /></el-icon>
          <span class="hw-dot" :class="hwStatus"></span>
        </div>
      </el-tooltip>

      <!-- 通知 -->
      <el-badge :value="pendingCount" :hidden="pendingCount === 0" class="header-bar__notif">
        <el-button text @click="refreshStats">
          <el-icon :size="20"><Bell /></el-icon>
        </el-button>
      </el-badge>

      <!-- 角色信息 -->
      <div class="header-bar__user">
        <el-avatar :size="32" class="user-avatar">
          <el-icon><UserFilled /></el-icon>
        </el-avatar>
        <span class="user-name">{{ appStore.roleName }}</span>
      </div>
    </div>
  </header>

  <!-- 硬件监控弹窗 -->
  <el-dialog v-model="showMonitor" title="AMD 硬件资源监控" width="520px">
    <div v-if="hw" class="hw-monitor">
      <div class="hw-grid">
        <div class="hw-item">
          <div class="hw-label">GPU 利用率</div>
          <el-progress :percentage="hw.gpu_utilization" :color="utilColors" />
        </div>
        <div class="hw-item">
          <div class="hw-label">NPU 利用率</div>
          <el-progress :percentage="hw.npu_utilization" :color="utilColors" />
        </div>
        <div class="hw-item">
          <div class="hw-label">CPU 利用率</div>
          <el-progress :percentage="hw.cpu_utilization" :color="utilColors" />
        </div>
        <div class="hw-item">
          <div class="hw-label">推理延迟</div>
          <div class="hw-value">{{ hw.inference_latency_ms }}ms</div>
        </div>
      </div>
      <div class="hw-info">
        <div class="hw-info-row"><span>GPU</span><span>{{ hw.gpu_info?.model }} / {{ hw.gpu_info?.temperature }}°C</span></div>
        <div class="hw-info-row"><span>NPU</span><span>{{ hw.npu_info?.model }} ({{ hw.npu_info?.ops }})</span></div>
        <div class="hw-info-row"><span>UMA</span><span>{{ hw.uma_info?.used_gb }}GB / {{ hw.uma_info?.total_gb }}GB</span></div>
        <div class="hw-info-row"><span>功耗</span><span>{{ hw.power_watts }}W</span></div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()
const showMonitor = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const currentTitle = computed(() => (route.meta?.title as string) || '工作台')

const pendingCount = computed(() => appStore.stats.pending_alerts + appStore.stats.pending_reviews)

const hw = computed(() => appStore.hardwareMonitor)

const hwStatus = computed(() => {
  if (!hw.value) return 'offline'
  const gpu = hw.value.gpu_utilization
  if (gpu >= 80) return 'high'
  if (gpu >= 50) return 'normal'
  return 'low'
})

const utilColors = [
  { color: '#4CAF50', percentage: 50 },
  { color: '#FF9800', percentage: 80 },
  { color: '#F44336', percentage: 100 },
]

async function refreshStats() {
  await appStore.fetchStats()
  await appStore.fetchHardwareMonitor()
}

onMounted(() => {
  appStore.fetchHardwareMonitor()
  timer = setInterval(() => appStore.fetchHardwareMonitor(), 10000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.header-bar {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 99;
}

.header-bar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-bar__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-bar__right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-bar__hw {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: var(--transition);
}

.header-bar__hw:hover {
  background: var(--primary-bg);
}

.hw-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.hw-dot.high { background: #F44336; }
.hw-dot.normal { background: #FF9800; }
.hw-dot.low { background: #4CAF50; }
.hw-dot.offline { background: #ccc; }

.header-bar__user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  background: linear-gradient(135deg, var(--primary-light), var(--accent-light));
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 监控弹窗 */
.hw-monitor {
  padding: 8px 0;
}

.hw-grid {
  display: grid;
  gap: 16px;
  margin-bottom: 20px;
}

.hw-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hw-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.hw-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
}

.hw-info {
  background: #f8fafb;
  border-radius: 8px;
  padding: 12px 16px;
}

.hw-info-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 13px;
}

.hw-info-row + .hw-info-row {
  border-top: 1px solid var(--border);
}

.hw-info-row span:first-child {
  color: var(--text-secondary);
}

.hw-info-row span:last-child {
  font-weight: 500;
}

.header-bar__notif :deep(.el-badge__content) {
  background: var(--danger);
}
</style>
