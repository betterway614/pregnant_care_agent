<template>
  <div class="agent-avatar" :class="[`agent-avatar--${agent}`, { 'agent-avatar--thinking': thinking }]">
    <div class="agent-avatar__circle">
      <span v-if="!thinking" class="agent-avatar__icon">{{ icon }}</span>
      <div v-else class="agent-avatar__thinking-dots">
        <span /><span /><span />
      </div>
    </div>
    <span v-if="showName" class="agent-avatar__name">{{ name }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  agent?: 'xiaan' | 'xiaohu' | 'zhiyi'
  thinking?: boolean
  showName?: boolean
  size?: number
}>(), {
  agent: 'xiaan',
  thinking: false,
  showName: false,
  size: 34,
})

const AGENT_CONFIG = {
  xiaan: { name: '小安', icon: '💗' },
  xiaohu: { name: '小护', icon: '🌸' },
  zhiyi: { name: '智医', icon: '🩺' },
} as const

const name = computed(() => AGENT_CONFIG[props.agent].name)
const icon = computed(() => AGENT_CONFIG[props.agent].icon)
</script>

<style scoped>
.agent-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.agent-avatar__circle {
  width: v-bind('size + "px"');
  height: v-bind('size + "px"');
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

/* 小安 - 粉色渐变 */
.agent-avatar--xiaan .agent-avatar__circle {
  background: linear-gradient(135deg, #fce4ec, #f8bbd0);
  box-shadow: 0 2px 8px rgba(236, 64, 122, 0.2);
}

/* 小护 - 薰衣草渐变 */
.agent-avatar--xiaohu .agent-avatar__circle {
  background: linear-gradient(135deg, #e8eaf6, #c5cae9);
  box-shadow: 0 2px 8px rgba(92, 107, 192, 0.2);
}

/* 智医 - 青色渐变 */
.agent-avatar--zhiyi .agent-avatar__circle {
  background: linear-gradient(135deg, #e0f2f1, #b2dfdb);
  box-shadow: 0 2px 8px rgba(0, 150, 136, 0.2);
}

.agent-avatar__icon {
  font-size: calc(v-bind('size + "px"') * 0.5);
  line-height: 1;
}

.agent-avatar__name {
  font-size: 11px;
  color: #666;
  font-weight: 500;
}

/* Thinking 动画 */
.agent-avatar--thinking .agent-avatar__circle {
  animation: pulse 1.5s ease-in-out infinite;
}

.agent-avatar__thinking-dots {
  display: flex;
  gap: 4px;
}

.agent-avatar__thinking-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #999;
  animation: dot-bounce 1.4s ease-in-out infinite;
}

.agent-avatar__thinking-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.agent-avatar__thinking-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
