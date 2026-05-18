<template>
  <header class="header-bar">
    <div class="header-bar__left">
      <el-button text @click="appStore.toggleSidebar">
        <el-icon :size="20"><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
      </el-button>
      <span class="header-bar__title">{{ currentTitle }}</span>
    </div>

    <div class="header-bar__right">
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

</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()
const currentTitle = computed(() => (route.meta?.title as string) || '工作台')
const pendingCount = computed(() => (appStore as any).pendingCount || 0)

async function refreshStats() {
  await appStore.fetchStats()
}
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

.header-bar__user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  background: var(--avatar-gradient);
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.header-bar__notif :deep(.el-badge__content) {
  background: var(--danger);
}
</style>
