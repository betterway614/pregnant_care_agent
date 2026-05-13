# 孕妇端工具页面布局重设计 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PregnantTools.vue（1400行）拆分为工具网格导航页 + 4 个独立子页面，解决手机端滚动过长、找不到重点功能的问题。

**Architecture:** /pregnant/tools 改为嵌套路由，外层 PregnantTools.vue 仅保留 `<router-view>`。新建 ToolGrid.vue 作为网格导航页，4 个子页面各自独立。子页面通过 `meta.hideTabBar` 隐藏底部 tab bar。

**Tech Stack:** Vue3 / Element Plus / vue-echarts / TypeScript / Vue Router

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| `frontend/src/views/pregnant/tools/ToolGrid.vue` | 工具网格导航页（2×2 卡片 + 今日摘要） |
| `frontend/src/views/pregnant/tools/FetalMovement.vue` | 胎动计数器 + 历史记录 |
| `frontend/src/views/pregnant/tools/HealthRecord.vue` | 快速录入（体重/血压/血糖/情绪） |
| `frontend/src/views/pregnant/tools/HealthTrend.vue` | 健康趋势图表 |
| `frontend/src/views/pregnant/tools/MentalHealth.vue` | 心理筛查（EPDS） |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `frontend/src/components/layout/PregnantLayout.vue` | 子页面隐藏底部 tab bar |
| `frontend/src/router/index.ts` | tools 改为嵌套路由 |
| `frontend/src/views/pregnant/PregnantTools.vue` | 替换为 `<router-view>` 容器 |

---

### Task 1: PregnantLayout 支持 hideTabBar

**Files:**
- Modify: `frontend/src/components/layout/PregnantLayout.vue`

- [ ] **Step 1: 在 script setup 中添加 hideTabBar 计算属性**

在 `const route = useRoute()` 之后添加：

```typescript
const hideTabBar = computed(() => route.meta.hideTabBar === true)
```

确保 `computed` 已从 vue 导入。

- [ ] **Step 2: 在模板中用 v-if 控制 tab bar 显示**

将 `<nav class="patient-tab-bar">` 改为 `<nav v-if="!hideTabBar" class="patient-tab-bar">`。

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | grep -i "PregnantLayout" || echo "No errors"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/PregnantLayout.vue
git commit -m "feat: PregnantLayout support hideTabBar meta for sub-pages"
```

---

### Task 2: 路由配置改为嵌套路由

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 创建 tools 子页面目录**

```bash
mkdir -p frontend/src/views/pregnant/tools
```

- [ ] **Step 2: 修改 router/index.ts 中的 tools 路由**

将原来的：
```typescript
{ path: 'tools', name: 'PregnantTools', component: () => import('@/views/pregnant/PregnantTools.vue'), meta: { title: '工具' } },
```

替换为：
```typescript
{
  path: 'tools',
  component: () => import('@/views/pregnant/PregnantTools.vue'),
  children: [
    { path: '', name: 'ToolGrid', component: () => import('@/views/pregnant/tools/ToolGrid.vue'), meta: { title: '健康工具' } },
    { path: 'fetal-movement', name: 'FetalMovement', component: () => import('@/views/pregnant/tools/FetalMovement.vue'), meta: { title: '胎动计数', hideTabBar: true } },
    { path: 'health-record', name: 'HealthRecord', component: () => import('@/views/pregnant/tools/HealthRecord.vue'), meta: { title: '快速录入', hideTabBar: true } },
    { path: 'health-trend', name: 'HealthTrend', component: () => import('@/views/pregnant/tools/HealthTrend.vue'), meta: { title: '健康趋势', hideTabBar: true } },
    { path: 'mental-health', name: 'MentalHealth', component: () => import('@/views/pregnant/tools/MentalHealth.vue'), meta: { title: '心理筛查', hideTabBar: true } },
  ],
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/router/index.ts frontend/src/views/pregnant/tools/
git commit -m "feat: convert /pregnant/tools to nested routes"
```

---

### Task 3: PregnantTools.vue 改为 router-view 容器

**Files:**
- Modify: `frontend/src/views/pregnant/PregnantTools.vue`

- [ ] **Step 1: 替换整个文件内容**

将 PregnantTools.vue 的全部 template/script/style 替换为：

```vue
<template>
  <router-view />
</template>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/PregnantTools.vue
git commit -m "refactor: PregnantTools.vue becomes router-view container"
```

---

### Task 4: ToolGrid 工具网格导航页

**Files:**
- Create: `frontend/src/views/pregnant/tools/ToolGrid.vue`

- [ ] **Step 1: 实现 ToolGrid.vue**

```vue
<template>
  <div class="page-container">
    <!-- 渐变头部 -->
    <div class="patient-header-card" style="min-height: 80px; padding: 20px">
      <div class="patient-header-card__name">健康工具</div>
      <div class="patient-header-card__week">选择工具开始记录</div>
    </div>

    <!-- 工具网格 -->
    <div class="tool-grid">
      <div
        v-for="tool in tools"
        :key="tool.name"
        class="tool-card"
        :style="{ background: tool.bg }"
        @click="$router.push(tool.route)"
      >
        <div class="tool-card__icon">{{ tool.icon }}</div>
        <div class="tool-card__name">{{ tool.label }}</div>
        <div class="tool-card__desc">{{ tool.desc }}</div>
      </div>
    </div>

    <!-- 今日健康摘要 -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #42A5F5"></span>
        今日健康摘要
      </div>
      <div v-if="summaryLoading" class="empty-tip">加载中...</div>
      <div v-else class="summary-grid">
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.weight_kg || '--' }}</div>
          <div class="summary-item__label">体重 kg</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.bp || '--' }}</div>
          <div class="summary-item__label">血压 mmHg</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__value">{{ healthSummary.fetal_movement || '--' }}</div>
          <div class="summary-item__label">胎动/时</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { pregnantApi } from '@/api/endpoints'

const tools = [
  { name: 'fetal-movement', icon: '👶', label: '胎动计数', desc: '记录宝宝每一次踢动', bg: 'linear-gradient(135deg, #fce4ec, #f8bbd0)', route: '/pregnant/tools/fetal-movement' },
  { name: 'health-record', icon: '📝', label: '快速录入', desc: '体重/血压/血糖', bg: 'linear-gradient(135deg, #e8f5e9, #c8e6c9)', route: '/pregnant/tools/health-record' },
  { name: 'health-trend', icon: '📊', label: '健康趋势', desc: '数据曲线一目了然', bg: 'linear-gradient(135deg, #e3f2fd, #bbdefb)', route: '/pregnant/tools/health-trend' },
  { name: 'mental-health', icon: '🧠', label: '心理筛查', desc: 'EPDS 情绪评估', bg: 'linear-gradient(135deg, #f3e5f5, #e1bee7)', route: '/pregnant/tools/mental-health' },
]

const healthSummary = ref<any>({})
const summaryLoading = ref(false)

async function loadSummary() {
  const pid = localStorage.getItem('currentPregnantId')
  if (!pid) return
  summaryLoading.value = true
  try {
    const res = await pregnantApi.getHome(pid)
    healthSummary.value = res.data?.health_summary || {}
  } catch { /* ignore */ } finally {
    summaryLoading.value = false
  }
}

onMounted(() => { loadSummary() })
</script>

<style scoped>
.page-container {
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  height: 100%;
  box-sizing: border-box;
  padding-bottom: 24px;
}

.tool-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px;
}

.tool-card {
  border-radius: 16px;
  padding: 20px 16px;
  text-align: center;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.tool-card:active {
  transform: scale(0.96);
}

.tool-card__icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.tool-card__name {
  font-size: 15px;
  font-weight: 700;
  color: #333;
}

.tool-card__desc {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.summary-grid {
  display: flex;
  justify-content: space-around;
  text-align: center;
}

.summary-item__value {
  font-size: 20px;
  font-weight: 700;
  color: #333;
}

.summary-item__label {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.empty-tip {
  text-align: center;
  padding: 16px 0;
  font-size: 13px;
  color: #999;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/tools/ToolGrid.vue
git commit -m "feat: implement ToolGrid navigation page"
```

---

### Task 5: FetalMovement 胎动计数子页面

**Files:**
- Create: `frontend/src/views/pregnant/tools/FetalMovement.vue`

- [ ] **Step 1: 从 PregnantTools.vue 提取胎动计数器代码**

从原 PregnantTools.vue 中提取以下部分到新的 FetalMovement.vue：
- 模板：胎动记录卡片（计数显示 +1按钮 + 操作按钮）+ 历史记录卡片
- 脚本：`count`, `sessionId`, `kickTimestamps`, `lastKickTime`, `sessionHistory`, `recordKick`, `saveProgress`, `saveSession`, `resetCounter`, `resetState`, `formatTimeShort`, `formatDateShort`, `loadHistory`, `deleteSession`, `beijingISO`
- 样式：`.timer-section`, `.count-display`, `.kick-btn`, `.ctrl-btn`, `.fm-row` 等

新增顶部返回导航栏：
```html
<div class="sub-page-header">
  <el-page-header @back="$router.back()">
    <template #content>胎动计数</template>
  </el-page-header>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/tools/FetalMovement.vue
git commit -m "feat: extract FetalMovement sub-page from PregnantTools"
```

---

### Task 6: HealthRecord 快速录入子页面

**Files:**
- Create: `frontend/src/views/pregnant/tools/HealthRecord.vue`

- [ ] **Step 1: 从 PregnantTools.vue 提取快速录入代码**

从原 PregnantTools.vue 中提取以下部分：
- 模板：快速录入表单（体重/血压/胎动/情绪 + 保存按钮）
- 脚本：`form`, `moods`, `saving`, `hasData`, `saveAll`, `loadSummary`, `pregnantId`
- 样式：`.health-form`, `.health-field`, `.mood-btn`, `.save-btn` 等

新增顶部返回导航栏（同 Task 5）。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/tools/HealthRecord.vue
git commit -m "feat: extract HealthRecord sub-page from PregnantTools"
```

---

### Task 7: HealthTrend 健康趋势子页面

**Files:**
- Create: `frontend/src/views/pregnant/tools/HealthTrend.vue`

- [ ] **Step 1: 从 PregnantTools.vue 提取健康趋势代码**

从原 PregnantTools.vue 中提取以下部分：
- 模板：指标选择器 + 横轴切换 + HealthTrendChart + 数据点详情卡片
- 脚本：`selectedMetrics`, `trendAxisMode`, `trendSeries`, `trendLoading`, `pointDetail`, `metricOptions`, `loadTrendData`, `handlePointClick`, `handleRangeChange`
- 样式：`.trend-metric-selector`, `.trend-axis-toggle`, `.point-detail-card` 等

新增顶部返回导航栏。此页面进入时直接加载数据（不再需要 IntersectionObserver 懒加载）。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/tools/HealthTrend.vue
git commit -m "feat: extract HealthTrend sub-page from PregnantTools"
```

---

### Task 8: MentalHealth 心理筛查子页面

**Files:**
- Create: `frontend/src/views/pregnant/tools/MentalHealth.vue`

- [ ] **Step 1: 从 PregnantTools.vue 提取心理筛查代码**

从原 PregnantTools.vue 中提取以下部分：
- 模板：EPDS 介绍 + 开始按钮 + 问卷 + 结果展示
- 脚本：`showEpds`, `epdsQuestions`, `epdsCurrentQ`, `epdsAnswers`, `epdsResult`, `startEpds`, `selectEpdsOption`, `submitEpds`, `resetEpds`
- 样式：`.epds-form`, `.epds-question`, `.epds-option`, `.epds-result` 等

新增顶部返回导航栏。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/pregnant/tools/MentalHealth.vue
git commit -m "feat: extract MentalHealth sub-page from PregnantTools"
```

---

### Task 9: 最终验证

- [ ] **Step 1: TypeScript 编译验证**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | grep -E "(ToolGrid|FetalMovement|HealthRecord|HealthTrend|MentalHealth|PregnantTools|PregnantLayout)" | head -10
```

Expected: 无错误

- [ ] **Step 2: 功能验证清单**

- [ ] 访问 `/pregnant/tools` → 显示工具网格 + 今日摘要
- [ ] 点击「胎动计数」→ 跳转 `/pregnant/tools/fetal-movement`，底部 tab 隐藏
- [ ] 点击「快速录入」→ 跳转 `/pregnant/tools/health-record`，底部 tab 隐藏
- [ ] 点击「健康趋势」→ 跳转 `/pregnant/tools/health-trend`，图表正常加载
- [ ] 点击「心理筛查」→ 跳转 `/pregnant/tools/mental-health`，EPDS 问卷正常
- [ ] 子页面点击返回 → 回到工具网格，底部 tab 恢复
