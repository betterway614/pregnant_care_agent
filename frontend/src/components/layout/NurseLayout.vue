<template>
  <div class="layout">
    <Sidebar />
    <div class="layout__main" :class="{ collapsed: appStore.sidebarCollapsed }">
      <HeaderBar />
      <main class="layout__content">
        <router-view />
      </main>
    </div>
    <NurseAIFab />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import Sidebar from './Sidebar.vue'
import HeaderBar from './HeaderBar.vue'
import NurseAIFab from '@/views/nurse/components/NurseAIFab.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

onMounted(() => {
  appStore.setRole('nurse')
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
}

.layout__main.collapsed {
  margin-left: 64px;
}

.layout__content {
  flex: 1;
  background: var(--bg-page);
  min-height: calc(100vh - 60px);
}
</style>
