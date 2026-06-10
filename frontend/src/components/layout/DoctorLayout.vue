<template>
  <div class="layout">
    <Sidebar />
    <div
      class="layout__main"
      :class="{
        'layout__main--sidebar-collapsed': effectiveSidebarCollapsed,
        'layout__main--mobile': isMobile
      }"
    >
      <HeaderBar />
      <main class="layout__content">
        <router-view />
      </main>
    </div>
    <!-- Dr.智 AI 悬浮球 -->
    <DoctorAIFab />
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import Sidebar from './Sidebar.vue'
import HeaderBar from './HeaderBar.vue'
import DoctorAIFab from '@/views/doctor/components/DoctorAIFab.vue'
import { useAppStore } from '@/stores/app'
import { useResponsive } from '@/composables/useResponsive'

const appStore = useAppStore()
const { isMobile, isTablet } = useResponsive()

const effectiveSidebarCollapsed = computed(() => {
  if (isMobile.value) return true
  if (isTablet.value) return true
  return appStore.sidebarCollapsed
})

onMounted(() => {
  appStore.setRole('doctor')
  // Auto-collapse on tablet
  if (isTablet.value) {
    appStore.sidebarCollapsed = true
  }
})
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.layout__main {
  margin-left: 220px;
  flex: 1;
  display: flex;
  flex-direction: column;
  transition: margin-left 0.3s;
  min-width: 0;
}

.layout__main--sidebar-collapsed {
  margin-left: 64px;
}

.layout__main--mobile {
  margin-left: 0;
}

.layout__content {
  flex: 1;
  background: var(--bg-page);
  min-height: calc(100vh - 60px);
  padding: 0;
}

@media (max-width: 1024px) {
  .layout__main {
    margin-left: 64px;
  }
}

@media (max-width: 768px) {
  .layout__main {
    margin-left: 0;
  }
}
</style>
