<template>
  <div class="agent-avatar" :class="[`agent-avatar--${agent}`, { 'agent-avatar--thinking': thinking }]">
    <div class="agent-avatar__circle">
      <div v-if="!thinking" class="agent-avatar__icon-svg">
        <!-- 小安: 温暖心形 -->
        <svg v-if="agent === 'xiaan'" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"></path>
        </svg>
        <!-- 小护: 医疗盾牌 -->
        <svg v-else-if="agent === 'xiaohu'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
          <path d="M8 11h8"></path>
          <path d="M12 7v8"></path>
        </svg>
        <!-- 智医: 听诊器 -->
        <svg v-else-if="agent === 'zhiyi'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"></path>
          <path d="M8 15v1a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6v-4"></path>
          <circle cx="20" cy="10" r="2"></circle>
        </svg>
      </div>
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
  xiaan: { name: '小安' },
  xiaohu: { name: '小护' },
  zhiyi: { name: '智医' },
} as const

const name = computed(() => AGENT_CONFIG[props.agent].name)
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

.agent-avatar__icon-svg {
  display: flex;
  align-items: center;
  justify-content: center;
  width: calc(v-bind('size + "px"') * 0.55);
  height: calc(v-bind('size + "px"') * 0.55);
}

.agent-avatar__icon-svg svg {
  width: 100%;
  height: 100%;
}

.agent-avatar--xiaan .agent-avatar__icon-svg svg {
  color: #EC407A;
}

.agent-avatar--xiaohu .agent-avatar__icon-svg svg {
  color: #5C6BC0;
}

.agent-avatar--zhiyi .agent-avatar__icon-svg svg {
  color: #009688;
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
