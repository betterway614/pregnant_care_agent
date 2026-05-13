<template>
  <div class="patient-theme patient-layout">
    <!-- 主内容区 -->
    <main class="patient-layout__content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- 底部导航栏 - 5个标签 -->
    <nav v-if="!hideTabBar" class="patient-tab-bar">
      <div
        v-for="tab in tabs"
        :key="tab.path"
        class="patient-tab-item"
        :class="{ active: isActive(tab.path) }"
        @click="navigate(tab.path)"
      >
        <el-icon class="patient-tab-icon" :size="tab.size || 22">
          <component :is="tab.icon" />
        </el-icon>
        <span class="patient-tab-label">{{ tab.label }}</span>
      </div>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const hideTabBar = computed(() => route.meta.hideTabBar === true)

const tabs = [
  { path: '/pregnant/home', label: '首页', icon: 'HomeFilled', size: 22 },
  { path: '/pregnant/chat', label: '小安', icon: 'ChatDotSquare', size: 22 },
  { path: '/pregnant/schedule', label: '日程', icon: 'Calendar', size: 22 },
  { path: '/pregnant/tools', label: '健康', icon: 'TrendCharts', size: 22 },
  { path: '/pregnant/profile', label: '我的', icon: 'User', size: 22 },
]

function isActive(path: string) {
  return route.path === path
}

function navigate(path: string) {
  router.push(path)
}

onMounted(() => {
  appStore.setRole('pregnant')
})
</script>

<style scoped>
.patient-layout {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  height: 100vh;
  overflow: hidden;
}

.patient-layout__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
