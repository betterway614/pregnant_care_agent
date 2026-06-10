<template>
  <!-- Mobile overlay backdrop -->
  <div
    v-if="isMobile && !appStore.sidebarCollapsed"
    class="sidebar-overlay"
    @click="appStore.sidebarCollapsed = true"
  />

  <div
    class="sidebar"
    :class="{
      collapsed: appStore.sidebarCollapsed,
      'sidebar--mobile': isMobile,
      'sidebar--open': isMobile && !appStore.sidebarCollapsed
    }"
  >
    <div class="sidebar__logo">
      <div class="sidebar__logo-icon">
        <el-icon :size="28"><FirstAidKit /></el-icon>
      </div>
      <span v-show="!appStore.sidebarCollapsed" class="sidebar__logo-text">AI-Care</span>
    </div>

    <el-menu
      :default-active="route.path"
      :collapse="appStore.sidebarCollapsed"
      :router="true"
      class="sidebar__menu"
      background-color="transparent"
      text-color="var(--text-secondary)"
      active-text-color="var(--primary)"
    >
      <el-menu-item
        v-for="item in menuItems"
        :key="item.path"
        :index="item.path"
        @click="handleMenuClick"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <template #title>
          <span>{{ item.title }}</span>
        </template>
      </el-menu-item>
    </el-menu>

    <div class="sidebar__footer">
      <div class="sidebar__logout" @click="handleLogout">
        <el-icon><SwitchButton /></el-icon>
        <span v-show="!appStore.sidebarCollapsed">退出登录</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const { isMobile } = useResponsive()

function handleMenuClick() {
  if (isMobile.value) {
    appStore.sidebarCollapsed = true
  }
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定退出登录？', '退出确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  // 清除登录状态
  localStorage.removeItem('isLoggedIn')
  localStorage.removeItem('currentRole')
  localStorage.removeItem('token')
  localStorage.removeItem('nurse_id')
  router.push('/login')
}

const menuItems = computed(() => {
  const role = appStore.currentRole
  if (role === 'nurse') {
    return [
      { path: '/nurse/dashboard', title: '工作台', icon: 'DataBoard' },
      { path: '/nurse/patients', title: '孕妇管理', icon: 'User' },
      { path: '/nurse/followup', title: '随访管理', icon: 'Document' },
      { path: '/nurse/schedule', title: '排期管理', icon: 'Calendar' },
      { path: '/nurse/alerts', title: '预警管理', icon: 'WarningFilled' },
    ]
  }
  if (role === 'doctor') {
    return [
      { path: '/doctor/dashboard', title: '工作台', icon: 'DataBoard' },
      { path: '/doctor/patients', title: '孕妇管理', icon: 'User' },
      { path: '/doctor/fgr-board', title: 'FGR看板', icon: 'Monitor' },
      { path: '/doctor/review', title: '审核工作台', icon: 'Edit' },
      { path: '/doctor/orders', title: '医嘱管理', icon: 'DocumentCopy' },
    ]
  }
  return []
})

</script>

<style scoped>
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
  backdrop-filter: blur(2px);
}

.sidebar {
  width: 220px;
  height: 100vh;
  background: #fff;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.3s, transform 0.3s;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar--mobile {
  width: 260px;
  transform: translateX(-100%);
}

.sidebar--mobile.collapsed {
  width: 260px;
  transform: translateX(-100%);
}

.sidebar--mobile.sidebar--open {
  transform: translateX(0);
}

.sidebar__logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  border-bottom: 1px solid var(--border);
}

.sidebar__logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.sidebar__logo-text {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  white-space: nowrap;
}

.sidebar__menu {
  flex: 1;
  border-right: none !important;
  padding: 8px;
}

.sidebar__menu .el-menu-item {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 44px;
  line-height: 44px;
}

.sidebar__menu .el-menu-item.is-active {
  background: var(--primary-bg) !important;
  font-weight: 600;
}

.sidebar__footer {
  padding: 12px;
  border-top: 1px solid var(--border);
}

.sidebar__logout {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 13px;
  transition: var(--transition);
}

.sidebar__logout:hover {
  background: #FEF2F2;
  color: #DC2626;
}

/* Tablet: collapsed sidebar */
@media (max-width: 1024px) {
  .sidebar:not(.sidebar--mobile) {
    width: 64px;
  }
  .sidebar:not(.sidebar--mobile) .sidebar__logo-text {
    display: none;
  }
}
</style>
