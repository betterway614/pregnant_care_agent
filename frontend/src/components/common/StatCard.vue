<template>
  <div class="stat-card" :style="cardStyle">
    <div class="stat-card__icon" :style="iconStyle">
      <el-icon :size="22"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-card__value" :style="{ color: color }">{{ value }}</div>
    <div class="stat-card__label">{{ label }}</div>
    <div v-if="subLabel" class="stat-card__sublabel">{{ subLabel }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  icon: string
  value: string | number
  label: string
  subLabel?: string
  color?: string
  bgColor?: string
}>()

const color = computed(() => props.color || 'var(--primary)')
const bgColor = computed(() => props.bgColor || 'var(--primary-bg)')

const cardStyle = computed(() => ({
  borderLeft: `3px solid ${color.value}`,
}))

const iconStyle = computed(() => ({
  background: bgColor.value,
  color: color.value,
}))
</script>

<style scoped>
.stat-card {
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
  transition: var(--transition);
  border: 1px solid var(--border);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}

.stat-card__icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.stat-card__value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 4px;
}

.stat-card__label {
  font-size: 13px;
  color: var(--text-light);
}

.stat-card__sublabel {
  font-size: 12px;
  color: var(--text-light);
  margin-top: 4px;
}
</style>
