<template>
  <div class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
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
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <template #title>
          <span>{{ item.title }}</span>
        </template>
      </el-menu-item>
    </el-menu>

    <div class="sidebar__footer">
      <div class="sidebar__role-switch" @click="showRoleDialog = true">
        <el-icon><Refresh /></el-icon>
        <span v-show="!appStore.sidebarCollapsed">切换角色</span>
      </div>
    </div>
  </div>

  <el-dialog v-model="showRoleDialog" title="切换角色" width="400px">
    <el-radio-group v-model="selectedRole" class="role-select">
      <el-radio-button value="nurse">护士端 - 小护</el-radio-button>
      <el-radio-button value="doctor">医生端 - Dr.智</el-radio-button>
      <el-radio-button value="pregnant">孕妇端 - 小安</el-radio-button>
    </el-radio-group>
    <template #footer>
      <el-button @click="showRoleDialog = false">取消</el-button>
      <el-button type="primary" @click="switchRole">确认切换</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const showRoleDialog = ref(false)
const selectedRole = ref<UserRole>('nurse')

const menuItems = computed(() => {
  const role = appStore.currentRole
  if (role === 'nurse') {
    return [
      { path: '/nurse/dashboard', title: '工作台', icon: 'DataBoard' },
      { path: '/nurse/followup', title: '随访管理', icon: 'Document' },
      { path: '/nurse/schedule', title: '排期管理', icon: 'Calendar' },
      { path: '/nurse/alerts', title: '预警管理', icon: 'WarningFilled' },
    ]
  }
  if (role === 'doctor') {
    return [
      { path: '/doctor/dashboard', title: '工作台', icon: 'DataBoard' },
      { path: '/doctor/fgr-board', title: 'FGR看板', icon: 'Monitor' },
      { path: '/doctor/review', title: '审核工作台', icon: 'Edit' },
      { path: '/doctor/orders', title: '医嘱管理', icon: 'DocumentCopy' },
    ]
  }
  return []
})

function switchRole() {
  appStore.setRole(selectedRole.value)
  showRoleDialog.value = false
  const paths: Record<UserRole, string> = {
    nurse: '/nurse/dashboard',
    doctor: '/doctor/dashboard',
    pregnant: '/pregnant/chat',
    admin: '/nurse/dashboard',
  }
  router.push(paths[selectedRole.value])
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  height: 100vh;
  background: #fff;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
}

.sidebar.collapsed {
  width: 64px;
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

.sidebar__role-switch {
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

.sidebar__role-switch:hover {
  background: var(--primary-bg);
  color: var(--primary);
}

.role-select {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-select .el-radio-button {
  width: 100%;
}

.role-select .el-radio-button__inner {
  width: 100%;
  justify-content: flex-start;
  padding: 12px 16px;
}
</style>
