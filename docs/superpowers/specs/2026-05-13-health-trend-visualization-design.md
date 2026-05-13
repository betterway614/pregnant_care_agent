# 孕妇健康数据时间曲线可视化 设计文档

**日期**: 2026-05-13
**状态**: 已确认
**范围**: 孕妇端、护士端、医生端的数据时间曲线表 + 随访归档展示

---

## 1. 需求概述

### 1.1 孕妇端
- 孕妇查看自己健康数据的时间曲线表
- 支持指标：体重、血压（收缩压/舒张压）、血糖（空腹/餐后）、胎动、心率、睡眠、步数、情绪
- 横轴支持日期/孕周双模式切换
- 简化视图，无复杂交互

### 1.2 护士端
- 在孕妇详情页中嵌入数据曲线和随访归档
- 左侧：随访时间线列表（按时间倒序）
- 右侧：健康数据时间曲线图
- 联动交互：点击随访记录 → 曲线跳转到对应时间范围

### 1.3 医生端
- 与护士端类似的详情页布局
- 增加异常标注功能（血压超标区域标红、血糖超标标注等）
- 未来扩展：与同孕周平均值对比分析

---

## 2. 技术架构

### 2.1 方案选型：共享图表引擎 + 各端页面独立组装

抽取通用 `HealthTrendChart` ECharts 组件，三个端各自在自己的页面中组装，共享图表核心逻辑。

**理由**：
- 图表核心逻辑复用，维护成本低
- 各端页面结构独立，互不影响
- 符合现有代码风格（各端 views 已分离）
- 前端已有 ECharts + vue-echarts 依赖

### 2.2 现有基础复用

| 已有模块 | 复用方式 |
|----------|----------|
| `HealthDataPoint` 模型 | 直接查询，无需新建表 |
| `DailyHealthSummary` 模型 | 用于快速概览 |
| `TrendEngine` | 复用正常范围定义和趋势判断逻辑 |
| `HealthDataService.METRIC_MAP` | 复用指标代码和单位映射 |
| `FollowUpRecord` 模型 | 查询随访历史 |

---

## 3. 后端 API 设计

### 3.1 健康趋势数据 API

**端点**: `GET /api/v1/pregnant/{pregnant_id}/health-trends`

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| metrics | string | 是 | 指标列表，逗号分隔（如 `weight,systolic,diastolic`） |
| start_date | string | 否 | 起始日期（ISO格式），默认最近30天 |
| end_date | string | 否 | 结束日期（ISO格式），默认今天 |
| axis_mode | string | 否 | `gestational_week` 或 `date`，默认 `date` |
| granularity | string | 否 | `daily` 或 `weekly`，默认 `daily` |

**响应结构**:
```json
{
  "pregnant_id": "hash_id",
  "gestational_week": "24+3",
  "axis_mode": "date",
  "series": [
    {
      "metric": "systolic",
      "name": "收缩压",
      "unit": "mmHg",
      "normal_range": {"min": 90, "max": 140},
      "data": [
        {"date": "2026-04-01", "gest_week": 20, "value": 118},
        {"date": "2026-04-08", "gest_week": 21, "value": 122}
      ],
      "trend": "rising",
      "latest_value": 122,
      "is_normal": true
    }
  ]
}
```

**设计要点**:
- 一次请求返回所有请求指标的时序数据
- 响应同时包含 `date` 和 `gest_week`，前端切换模式时无需重新请求
- 复用 `TrendEngine.NORMAL_RANGES` 提供正常范围
- 复用 `TrendEngine` 的趋势判断逻辑

### 3.2 随访历史 API

**端点**: `GET /api/v1/pregnant/{pregnant_id}/follow-up-history`

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 筛选状态：`archived`/`confirmed`/`draft`，默认全部 |
| limit | int | 否 | 返回条数，默认50 |

**响应结构**:
```json
{
  "pregnant_id": "hash_id",
  "records": [
    {
      "id": "uuid",
      "follow_up_date": "2026-04-15T10:30:00",
      "gestational_week": "22",
      "status": "archived",
      "summary": "血压偏高，建议加强监测",
      "chief_complaint": "偶有头晕",
      "self_reported_data": {"weight": 68, "bp": "135/88"},
      "health_education": ["控制盐摄入", "每日监测血压"]
    }
  ]
}
```

---

## 4. 前端组件设计

### 4.1 共享组件

#### `HealthTrendChart.vue` — 核心图表组件

**Props**:
| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| series | SeriesData[] | - | 数据序列 |
| axisMode | `'date'` \| `'gest_week'` | `'date'` | 横轴模式 |
| showNormalRange | boolean | `true` | 是否显示正常范围区域 |
| interactive | boolean | `true` | 是否支持点击交互 |
| height | number | `400` | 图表高度(px) |

**Events**:
| Event | 参数 | 说明 |
|-------|------|------|
| point-click | `{ metric, date, value }` | 点击数据点 |
| range-change | `{ startDate, endDate }` | 缩放范围变化 |

**ECharts 配置策略**:

| 指标类型 | 图表类型 | 特殊处理 |
|----------|----------|----------|
| 血压 | 双Y轴线图 | 收缩压+舒张压双线，红色区域标注≥140/90 |
| 体重 | 单线图 | 推荐增长区间半透明绿色区域 |
| 血糖 | 双线图 | 空腹+餐后双线，阈值线标注（空腹<5.1, 餐后<8.5） |
| 胎动 | 单线图 | 正常范围区域（3-10次/小时） |
| 心率/睡眠/步数/情绪 | 单线图 | 正常范围区域 |

#### `FollowUpTimeline.vue` — 随访时间线组件

**Props**:
| Prop | 类型 | 说明 |
|------|------|------|
| records | FollowUpRecord[] | 随访记录列表 |
| selectedId | string \| null | 当前选中的记录ID |

**Events**:
| Event | 参数 | 说明 |
|-------|------|------|
| select | FollowUpRecord | 选中记录 |

**UI**: 垂直时间线，每条记录显示日期、孕周、状态标签、摘要。点击展开详情。

### 4.2 三端页面组装

#### 孕妇端：`PregnantTools.vue` 新增「健康趋势」卡片

- 在现有「快速录入」卡片下方，新增「健康趋势」卡片区域
- 使用 el-tabs 实现 tab 切换：「胎动记录」/「快速录入」/「健康趋势」
- 「健康趋势」tab 包含：
  - 顶部：指标选择器（checkbox 组，默认勾选体重+血压）
  - 中部：日期/孕周模式切换按钮组
  - 底部：`HealthTrendChart`（简化模式，interactive=false）
- 无随访时间线（孕妇不需要看归档）

#### 护士端：新增 `PregnantDetail.vue`

- 从 `FollowUpList.vue` 或 `NurseDashboard.vue` 的孕妇列表点击跳转
- 左侧面板：`FollowUpTimeline`（随访时间线）
- 右侧面板：`HealthTrendChart`（数据曲线）
- 联动：点击随访记录 → 曲线跳转到该日期范围

#### 医生端：新增 `PregnantDetail.vue`

- 从 `DoctorDashboard.vue` 的孕妇列表点击跳转
- 布局同护士端：左时间线 + 右曲线
- 增加异常标注：血压/血糖超标区域自动标红
- 未来扩展：与同孕周平均值对比

### 4.3 联动交互流程

```
护士/医生端 PregnantDetail 页面:

左侧 FollowUpTimeline          右侧 HealthTrendChart
┌─────────────────┐           ┌─────────────────────┐
│ 2026-04-15      │           │                     │
│ 孕22周 [已归档]  │──点击──→ │ 曲线跳转到4月范围    │
│ 血压偏高...      │           │ 高亮4/15数据点      │
│                  │           │                     │
│ 2026-03-20      │           │                     │
│ 孕18周 [已归档]  │           │                     │
└─────────────────┘           └─────────────────────┘
```

---

## 5. 数据指标与正常范围

基于现有 `TrendEngine.NORMAL_RANGES`，扩展如下：

| 指标 | metric_code | 单位 | 正常范围 | 孕期特殊说明 |
|------|-------------|------|----------|--------------|
| 体重 | weight | kg | 40-120 | 按孕周动态调整推荐增长 |
| 收缩压 | systolic | mmHg | 90-140 | ≥140 为异常 |
| 舒张压 | diastolic | mmHg | 60-90 | ≥90 为异常 |
| 空腹血糖 | blood_sugar_fasting | mmol/L | 3.5-5.1 | GDM诊断阈值5.1 |
| 餐后血糖 | blood_sugar_postprandial | mmol/L | 3.5-8.5 | GDM诊断阈值8.5 |
| 胎动 | fetal_movement | 次/小时 | 3-10 | <3 需要关注 |
| 心率 | heart_rate | bpm | 60-100 | 孕期可略高 |
| 睡眠 | sleep_hours | 小时 | 6-10 | - |
| 步数 | steps | 步 | 2000-15000 | - |
| 情绪 | emotion_score | 分 | 1-3 | 1=bad, 2=neutral, 3=good |

---

## 6. 实现分期

### 第1期：数据曲线核心（优先级最高）

**后端**:
- 实现 `GET /health-trends` API
- 复用 `TrendEngine` 做趋势分析
- 从 `HealthDataPoint` 查询时序数据

**前端**:
- 实现 `HealthTrendChart.vue` 通用图表组件
- 在 `PregnantTools.vue` 中集成「健康趋势」tab
- 支持日期/孕周双模式切换
- 支持指标选择和多指标同屏展示

**验收标准**:
- 孕妇端可查看自己的体重、血压、血糖、胎动等指标的时间曲线
- 支持日期/孕周横轴切换
- 血压双线图、血糖双线图正确渲染
- 正常范围区域正确显示

### 第2期：护士端详情页

**后端**:
- 实现 `GET /follow-up-history` API

**前端**:
- 实现 `FollowUpTimeline.vue` 时间线组件
- 新增护士端 `PregnantDetail.vue` 页面
- 实现时间线与曲线的联动交互
- 从护士列表页/随访列表页添加跳转入口

**验收标准**:
- 护士可从列表点击进入孕妇详情页
- 左侧显示随访时间线，右侧显示数据曲线
- 点击随访记录，曲线自动跳转到对应时间范围

### 第3期：医生端详情页

**前端**:
- 新增医生端 `PregnantDetail.vue` 页面
- 增加异常标注功能（超标区域标红）
- 从医生工作台添加跳转入口

**验收标准**:
- 医生可从工作台点击进入孕妇详情页
- 血压/血糖超标区域自动标红标注
- 布局和交互与护士端一致

---

## 7. 文件变更清单

### 新增文件
| 文件路径 | 说明 |
|----------|------|
| `backend/app/routers/health_trends.py` | 健康趋势 API 路由 |
| `frontend/src/components/charts/HealthTrendChart.vue` | 通用图表组件 |
| `frontend/src/components/followup/FollowUpTimeline.vue` | 随访时间线组件 |
| `frontend/src/views/nurse/PregnantDetail.vue` | 护士端孕妇详情页 |
| `frontend/src/views/doctor/PregnantDetail.vue` | 医生端孕妇详情页 |

### 修改文件
| 文件路径 | 修改内容 |
|----------|----------|
| `backend/app/main.py` | 注册 health_trends 路由 |
| `backend/app/schemas/schemas.py` | 新增趋势数据响应 Schema |
| `frontend/src/api/endpoints.ts` | 新增 API 端点 |
| `frontend/src/api/client.ts` | 新增 API 调用函数 |
| `frontend/src/views/pregnant/PregnantTools.vue` | 新增「健康趋势」tab |
| `frontend/src/views/nurse/FollowUpList.vue` | 添加跳转到详情页的入口 |
| `frontend/src/views/doctor/DoctorDashboard.vue` | 添加跳转到详情页的入口 |
| `frontend/src/router/index.ts` | 新增详情页路由 |
