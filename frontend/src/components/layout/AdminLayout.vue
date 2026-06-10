<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <div class="admin-sidebar__logo">
        <el-icon :size="24"><Setting /></el-icon>
        <span class="admin-sidebar__logo-text">管理后台</span>
      </div>

      <el-menu
        :default-active="route.path"
        :router="true"
        class="admin-sidebar__menu"
        background-color="#0f172a"
        text-color="#94a3b8"
        active-text-color="#3b82f6"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><DataBoard /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/admin/token-analysis">
          <el-icon><Coin /></el-icon>
          <template #title>Token 消耗分析</template>
        </el-menu-item>
        <el-menu-item index="/admin/audit-trail">
          <el-icon><Search /></el-icon>
          <template #title>对话审计追溯</template>
        </el-menu-item>
        <el-menu-item index="/admin/route-monitor">
          <el-icon><Connection /></el-icon>
          <template #title>路由监控</template>
        </el-menu-item>
        <el-menu-item index="/admin/knowledge">
          <el-icon><Collection /></el-icon>
          <template #title>知识库管理</template>
        </el-menu-item>
        <el-menu-item index="/admin/api-config">
          <el-icon><Promotion /></el-icon>
          <template #title>API 配置</template>
        </el-menu-item>
        <el-menu-item index="/admin/resource-monitor">
          <el-icon><Monitor /></el-icon>
          <template #title>资源监控</template>
        </el-menu-item>
        <el-menu-item index="/admin/resource-config">
          <el-icon><Tools /></el-icon>
          <template #title>资源配置</template>
        </el-menu-item>
        <el-menu-item index="/admin/operation-report">
          <el-icon><Document /></el-icon>
          <template #title>运营报告</template>
        </el-menu-item>
      </el-menu>

      <div class="admin-sidebar__footer">
        <a href="/login" class="back-link" @click.prevent="backToMain">
          <el-icon><Back /></el-icon>
          <span>返回主站</span>
        </a>
      </div>
    </aside>

    <div class="admin-main">
      <header class="admin-header">
        <h2 class="admin-header__title">{{ route.meta?.title || '管理后台' }}</h2>
        <div class="admin-header__actions">
          <el-date-picker
            v-if="showDatePicker"
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :shortcuts="dateShortcuts"
            size="default"
          />
        </div>
      </header>
      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import dayjs from 'dayjs'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

appStore.setRole('admin')

const dateRange = ref<[Date, Date]>([
  dayjs().subtract(7, 'day').toDate(),
  new Date(),
])

const dateShortcuts = [
  {
    text: '最近7天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 7)
      return [start, end]
    },
  },
  {
    text: '最近30天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 30)
      return [start, end]
    },
  },
  {
    text: '本月',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(1)
      return [start, end]
    },
  },
]

const showDatePicker = computed(() =>
  ['AdminDashboard', 'AdminTokenAnalysis', 'AdminRouteMonitor', 'AdminResourceMonitor', 'AdminOperationReport'].includes(route.name as string)
)

const formatDate = (d: Date) => dayjs(d).format('YYYY-MM-DD')

provide('dateRange', {
  from: computed(() => formatDate(dateRange.value[0])),
  to: computed(() => formatDate(dateRange.value[1])),
})

function backToMain() {
  localStorage.removeItem('isLoggedIn')
  localStorage.removeItem('currentRole')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
  background: #f1f5f9;
}

.admin-sidebar {
  width: 220px;
  background: #0f172a;
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  z-index: 100;
}

.admin-sidebar__logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.admin-sidebar__logo-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.admin-sidebar__menu {
  flex: 1;
  border-right: none !important;
  padding: 8px;
}

.admin-sidebar__menu .el-menu-item {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 44px;
  line-height: 44px;
  transition: all 0.2s;
}

.admin-sidebar__menu .el-menu-item:hover {
  background: rgba(59, 130, 246, 0.1) !important;
}

.admin-sidebar__menu .el-menu-item.is-active {
  background: rgba(59, 130, 246, 0.15) !important;
  color: #3b82f6 !important;
}

.admin-sidebar__footer {
  padding: 12px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.back-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 13px;
  transition: color 0.2s;
}

.back-link:hover {
  color: #3b82f6;
}

.admin-main {
  margin-left: 220px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.admin-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  position: sticky;
  top: 0;
  z-index: 99;
}

.admin-header__title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.admin-content {
  flex: 1;
  padding: 24px;
}
</style>
