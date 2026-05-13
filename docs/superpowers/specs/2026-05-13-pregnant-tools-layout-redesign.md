# 孕妇端工具页面布局重设计

**日期**: 2026-05-13
**状态**: 已确认
**范围**: 将 PregnantTools.vue 从单一长页面拆分为工具网格 + 独立子页面

---

## 1. 问题

当前 `/pregnant/tools` 页面（PregnantTools.vue，约 1400 行）包含 5 个大模块：
1. 胎动计数器（约 300 行）
2. 快速录入表单（约 100 行）
3. 胎动历史列表（约 80 行）
4. 健康趋势图表（约 80 行 + ECharts）
5. 心理健康筛查 EPDS（约 200 行）

问题：
- 手机端需滚动 5-6 屏才能看完，找不到重点功能
- 各模块之间没有层次关系
- ECharts 加载影响整体页面性能
- 不符合移动端「一页一功能」的交互原则

---

## 2. 方案：拆分为工具网格 + 独立子页面

### 2.1 路由结构

```
/pregnant/tools              → 工具网格导航页（新）
/pregnant/tools/fetal-movement → 胎动计数器
/pregnant/tools/health-record  → 快速录入（体重/血压/血糖/情绪）
/pregnant/tools/health-trend   → 健康趋势图表
/pregnant/tools/mental-health  → 心理筛查（EPDS）
```

### 2.2 工具网格页设计

页面结构：
1. 渐变头部：「健康工具」标题 + 副标题
2. 2×2 工具网格：每个工具卡片含图标 + 名称 + 简短描述
3. 今日健康摘要卡片：体重 / 血压 / 胎动 快速概览（数据来自 PregnantHome 的 health_summary）

工具卡片列表：
| 工具 | 图标 | 颜色 | 描述 |
|------|------|------|------|
| 胎动计数 | 👶 | 粉色渐变 | 记录宝宝每一次踢动 |
| 快速录入 | 📝 | 绿色渐变 | 体重/血压/血糖 |
| 健康趋势 | 📊 | 蓝色渐变 | 数据曲线一目了然 |
| 心理筛查 | 🧠 | 紫色渐变 | EPDS 情绪评估 |

### 2.3 子页面设计

每个子页面统一结构：
1. 顶部导航栏：返回箭头 + 页面标题（使用 el-page-header）
2. 功能主体：从原 PregnantTools.vue 对应模块提取
3. 无底部导航（子页面不显示底部 tab bar）

### 2.4 胎动计数子页面特殊处理

胎动计数器需要同时展示「计数器」和「历史记录」：
- 主体：计数器（+1 按钮、计数显示、操作按钮）
- 底部：最近 5 条历史记录（折叠展示，点击展开全部）

---

## 3. 文件变更

### 新增文件
| 文件 | 说明 |
|------|------|
| `frontend/src/views/pregnant/tools/ToolGrid.vue` | 工具网格导航页 |
| `frontend/src/views/pregnant/tools/FetalMovement.vue` | 胎动计数器 |
| `frontend/src/views/pregnant/tools/HealthRecord.vue` | 快速录入 |
| `frontend/src/views/pregnant/tools/HealthTrend.vue` | 健康趋势图表 |
| `frontend/src/views/pregnant/tools/MentalHealth.vue` | 心理筛查 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `frontend/src/router/index.ts` | 新增子路由配置 |
| `frontend/src/views/pregnant/PregnantTools.vue` | 改为 `<router-view>` 出口容器 |
| `frontend/src/components/layout/PregnantLayout.vue` | 子页面隐藏底部 tab bar |

### 删除内容
- `PregnantTools.vue` 中的所有业务代码（已拆分到子页面）

---

## 4. 路由配置

```typescript
// router/index.ts 中的 tools 子路由
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
}
```

---

## 5. 底部 Tab Bar 隐藏逻辑

子页面（`hideTabBar: true`）需要隐藏底部导航栏。修改 `PregnantLayout.vue`：

```typescript
const hideTabBar = computed(() => route.meta.hideTabBar === true)
```

模板中：
```html
<nav v-if="!hideTabBar" class="patient-tab-bar">
  ...
</nav>
```
