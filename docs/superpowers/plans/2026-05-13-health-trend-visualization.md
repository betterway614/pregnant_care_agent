# 孕妇健康数据时间曲线可视化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三端（孕妇/护士/医生）健康数据时间曲线可视化，支持日期/孕周双模式横轴，护士/医生端含随访归档时间线联动。

**Architecture:** 后端新增 `/health-trends` 和 `/follow-up-history` 两个 API，复用现有 `TrendEngine` 和 `HealthDataPoint` 模型。前端创建共享 `HealthTrendChart` ECharts 组件 + `FollowUpTimeline` 时间线组件，三端各自组装页面。分 3 期实现：第 1 期核心图表 + 孕妇端，第 2 期护士端详情页，第 3 期医生端详情页。

**Tech Stack:** Python/FastAPI/SQLAlchemy (后端), Vue3/ElementPlus/ECharts/vue-echarts/TypeScript (前端)

---

## 文件结构总览

### 后端

| 文件 | 职责 |
|------|------|
| `backend/app/routers/health_trends.py` | 新建 - 健康趋势 + 随访历史 API 路由 |
| `backend/app/schemas/schemas.py` | 修改 - 新增趋势数据响应 Schema |
| `backend/app/main.py` | 修改 - 注册新路由 |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/types/index.ts` | 修改 - 新增 HealthTrendSeries 等类型 |
| `frontend/src/api/endpoints.ts` | 修改 - 新增健康趋势 + 随访历史 API |
| `frontend/src/components/charts/HealthTrendChart.vue` | 新建 - 共享图表组件 |
| `frontend/src/components/followup/FollowUpTimeline.vue` | 新建 - 随访时间线组件 |
| `frontend/src/views/pregnant/PregnantTools.vue` | 修改 - 新增「健康趋势」卡片 |
| `frontend/src/views/nurse/PregnantDetail.vue` | 新建 - 护士端孕妇详情页 |
| `frontend/src/views/doctor/PregnantDetail.vue` | 新建 - 医生端孕妇详情页 |
| `frontend/src/router/index.ts` | 修改 - 新增详情页路由 |
| `frontend/src/views/nurse/FollowUpList.vue` | 修改 - 添加跳转入口 |
| `frontend/src/views/doctor/DoctorDashboard.vue` | 修改 - 添加跳转入口 |

---

## 第 1 期：数据曲线核心 + 孕妇端

### Task 1: 后端 Pydantic Schema 定义

**Files:**
- Modify: `backend/app/schemas/schemas.py`

- [ ] **Step 1: 在 schemas.py 末尾新增健康趋势相关 Schema**

在 `backend/app/schemas/schemas.py` 文件末尾追加以下内容：

```python
# === Health Trend ===
class TrendDataPoint(BaseModel):
    date: str                          # ISO日期 "2026-04-01"
    gest_week: int                     # 孕周（整数，如 20）
    value: float                       # 数据值


class TrendSeries(BaseModel):
    metric: str                        # 指标代码，如 "systolic"
    name: str                          # 指标中文名，如 "收缩压"
    unit: str                          # 单位，如 "mmHg"
    normal_range: dict = {}            # {"min": 90, "max": 140}
    data: list[TrendDataPoint] = []    # 时序数据点
    trend: str = "insufficient_data"   # rising/falling/stable/insufficient_data
    latest_value: float | None = None
    is_normal: bool | None = None


class HealthTrendResponse(BaseModel):
    pregnant_id: str
    gestational_week: str = ""         # "24+3"
    axis_mode: str = "date"            # date / gestational_week
    series: list[TrendSeries] = []
```

- [ ] **Step 2: 在 schemas.py 末尾新增随访历史响应 Schema**

在上面的代码之后继续追加：

```python
# === Follow-Up History ===
class FollowUpHistoryRecord(BaseModel):
    id: str
    follow_up_date: str | None = None
    gestational_week: str | None = None
    status: str = "draft"
    summary: str | None = None
    chief_complaint: str | None = None
    self_reported_data: dict = {}
    health_education: list[str] = []


class FollowUpHistoryResponse(BaseModel):
    pregnant_id: str
    records: list[FollowUpHistoryRecord] = []
```

- [ ] **Step 3: 验证 Schema 语法**

```bash
cd backend && python -c "from app.schemas.schemas import HealthTrendResponse, FollowUpHistoryResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: add HealthTrendResponse and FollowUpHistoryResponse schemas"
```

---

### Task 2: 后端健康趋势 API

**Files:**
- Create: `backend/app/routers/health_trends.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 health_trends.py 路由文件**

```python
"""健康趋势 + 随访历史 API"""
from datetime import datetime, date, timedelta
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, FollowUpRecord
from ..core.trend_engine import TrendEngine
from ..schemas.schemas import (
    HealthTrendResponse, TrendSeries, TrendDataPoint,
    FollowUpHistoryResponse, FollowUpHistoryRecord,
)

router = APIRouter(prefix="/api/v1/pregnant", tags=["健康趋势"])

# 指标元数据: metric_code -> (中文名, 单位, normal_range)
METRIC_META = {
    "weight": ("体重", "kg", {"min": 40, "max": 120}),
    "systolic": ("收缩压", "mmHg", {"min": 90, "max": 140}),
    "diastolic": ("舒张压", "mmHg", {"min": 60, "max": 90}),
    "blood_sugar_fasting": ("空腹血糖", "mmol/L", {"min": 3.5, "max": 5.1}),
    "blood_sugar_postprandial": ("餐后血糖", "mmol/L", {"min": 3.5, "max": 8.5}),
    "fetal_movement": ("胎动", "次/小时", {"min": 3, "max": 10}),
    "heart_rate": ("心率", "bpm", {"min": 60, "max": 100}),
    "sleep_hours": ("睡眠", "小时", {"min": 6, "max": 10}),
    "steps": ("步数", "步", {"min": 2000, "max": 15000}),
    "emotion_score": ("情绪", "分", {"min": 1, "max": 3}),
}


@router.get("/{pregnant_id}/health-trends", response_model=HealthTrendResponse)
def get_health_trends(
    pregnant_id: str,
    metrics: str = Query(..., description="指标列表，逗号分隔"),
    start_date: str | None = Query(None, description="起始日期 ISO"),
    end_date: str | None = Query(None, description="结束日期 ISO"),
    axis_mode: str = Query("date", description="date 或 gestational_week"),
    granularity: str = Query("daily", description="daily 或 weekly"),
):
    """获取健康数据时间趋势"""
    db: Session = SessionLocal()
    try:
        # 验证孕妇存在
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        # 计算当前孕周
        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7

        # 解析日期范围
        today = date.today()
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
            end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
        except ValueError:
            raise HTTPException(400, "日期格式错误，请使用 YYYY-MM-DD")

        # 解析指标列表
        metric_codes = [m.strip() for m in metrics.split(",") if m.strip()]
        valid_codes = [m for m in metric_codes if m in METRIC_META]
        if not valid_codes:
            raise HTTPException(400, f"无有效指标，可选: {', '.join(METRIC_META.keys())}")

        # LMP 日期（用于计算数据点对应孕周）
        lmp = pregnant.lmp_date

        series_list = []
        trend_engine = TrendEngine()

        for metric_code in valid_codes:
            name, unit, normal_range = METRIC_META[metric_code]

            # 查询数据点
            points = (
                db.query(HealthDataPoint)
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == metric_code,
                    func.date(HealthDataPoint.recorded_at) >= start,
                    func.date(HealthDataPoint.recorded_at) <= end,
                )
                .order_by(HealthDataPoint.recorded_at.asc())
                .all()
            )

            # 构建时序数据
            data = []
            for p in points:
                rec_date = p.recorded_at.date() if p.recorded_at else start
                gw = 0
                if lmp:
                    gw = (rec_date - lmp).days // 7
                data.append(TrendDataPoint(
                    date=rec_date.isoformat(),
                    gest_week=gw,
                    value=p.value,
                ))

            # 趋势分析
            trend_result = None
            if len(data) >= 2:
                records_for_trend = [
                    {"metric": metric_code, "value": d.value, "unit": unit, "recorded_at": d.date}
                    for d in data
                ]
                trend_engine = TrendEngine()
                results = trend_engine.analyze(records_for_trend, gest_week)
                if results:
                    trend_result = results[0]

            series_list.append(TrendSeries(
                metric=metric_code,
                name=name,
                unit=unit,
                normal_range=normal_range,
                data=data,
                trend=trend_result.trend if trend_result else "insufficient_data",
                latest_value=data[-1].value if data else None,
                is_normal=trend_result.is_normal if trend_result else None,
            ))

        return HealthTrendResponse(
            pregnant_id=pregnant_id,
            gestational_week=f"{gest_week}+{gest_day}",
            axis_mode=axis_mode,
            series=series_list,
        )
    finally:
        db.close()


@router.get("/{pregnant_id}/follow-up-history", response_model=FollowUpHistoryResponse)
def get_follow_up_history(
    pregnant_id: str,
    status: str | None = Query(None, description="筛选状态"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取随访历史记录"""
    db: Session = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        query = db.query(FollowUpRecord).filter(FollowUpRecord.pregnant_id == pregnant_id)
        if status:
            query = query.filter(FollowUpRecord.status == status)

        records = query.order_by(FollowUpRecord.follow_up_date.desc()).limit(limit).all()

        result = []
        for r in records:
            result.append(FollowUpHistoryRecord(
                id=str(r.id),
                follow_up_date=r.follow_up_date.isoformat() if r.follow_up_date else None,
                gestational_week=r.gestational_week,
                status=r.status,
                summary=r.summary,
                chief_complaint=r.chief_complaint,
                self_reported_data=r.self_reported_data or {},
                health_education=r.health_education or [],
            ))

        return FollowUpHistoryResponse(
            pregnant_id=pregnant_id,
            records=result,
        )
    finally:
        db.close()
```

- [ ] **Step 2: 注册路由到 main.py**

在 `backend/app/main.py` 的 import 部分添加：

```python
from .routers import health_trends
```

在 `app.include_router(mental_health.router)` 之后添加：

```python
app.include_router(health_trends.router)
```

- [ ] **Step 3: 验证路由注册成功**

```bash
cd backend && python -c "from app.main import app; routes = [r.path for r in app.routes]; assert '/api/v1/pregnant/{pregnant_id}/health-trends' in routes; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/health_trends.py backend/app/main.py
git commit -m "feat: implement /health-trends and /follow-up-history APIs"
```

---

### Task 3: 前端类型定义 + API 端点

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/endpoints.ts`

- [ ] **Step 1: 在 types/index.ts 末尾新增健康趋势类型**

在 `frontend/src/types/index.ts` 末尾追加：

```typescript
// 健康趋势数据
export interface TrendDataPoint {
  date: string
  gest_week: number
  value: number
}

export interface TrendSeries {
  metric: string
  name: string
  unit: string
  normal_range: { min: number; max: number }
  data: TrendDataPoint[]
  trend: 'rising' | 'falling' | 'stable' | 'insufficient_data'
  latest_value: number | null
  is_normal: boolean | null
}

export interface HealthTrendResponse {
  pregnant_id: string
  gestational_week: string
  axis_mode: string
  series: TrendSeries[]
}

// 随访历史
export interface FollowUpHistoryRecord {
  id: string
  follow_up_date: string | null
  gestational_week: string | null
  status: string
  summary: string | null
  chief_complaint: string | null
  self_reported_data: Record<string, any>
  health_education: string[]
}

export interface FollowUpHistoryResponse {
  pregnant_id: string
  records: FollowUpHistoryRecord[]
}
```

- [ ] **Step 2: 在 endpoints.ts 中新增健康趋势 API**

在 `frontend/src/api/endpoints.ts` 的 `pregnantApi` 对象中，在 `submitHealthData` 方法之后添加：

```typescript
  getHealthTrends: (pregnantId: string, params: {
    metrics: string
    start_date?: string
    end_date?: string
    axis_mode?: 'date' | 'gestational_week'
    granularity?: 'daily' | 'weekly'
  }) => client.get<HealthTrendResponse>(
    `/pregnant/${pregnantId}/health-trends`,
    { params }
  ),
  getFollowUpHistory: (pregnantId: string, params?: {
    status?: string
    limit?: number
  }) => client.get<FollowUpHistoryResponse>(
    `/pregnant/${pregnantId}/follow-up-history`,
    { params }
  ),
```

同时在文件顶部的 import 中添加新类型：

```typescript
import type {
  Pregnant, FollowUpRecord, Alert, ScheduleNode,
  FgrAssessment, FgrTrendPoint, MedicalOrder,
  DashboardStats, ChatRequest, ChatResponse,
  HomeResponse, RecommendResponse,
  HealthTrendResponse, FollowUpHistoryResponse,
} from '@/types'
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

Expected: 无类型错误（或只有已有不相关错误）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/endpoints.ts
git commit -m "feat: add health trend types and API endpoints"
```

---

### Task 4: HealthTrendChart 共享图表组件

**Files:**
- Create: `frontend/src/components/charts/HealthTrendChart.vue`

- [ ] **Step 1: 创建 charts 目录**

```bash
mkdir -p frontend/src/components/charts
```

- [ ] **Step 2: 实现 HealthTrendChart.vue**

```vue
<template>
  <div class="health-trend-chart" :style="{ height: height + 'px' }">
    <div v-if="!series.length" class="chart-empty">
      <el-empty description="暂无数据" :image-size="80" />
    </div>
    <v-chart
      v-else
      ref="chartRef"
      :option="chartOption"
      :autoresize="true"
      @click="handleClick"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { TrendSeries, TrendDataPoint } from '@/types'

const props = withDefaults(defineProps<{
  series: TrendSeries[]
  axisMode?: 'date' | 'gest_week'
  showNormalRange?: boolean
  interactive?: boolean
  height?: number
}>(), {
  axisMode: 'date',
  showNormalRange: true,
  interactive: true,
  height: 400,
})

const emit = defineEmits<{
  'point-click': [data: { metric: string; date: string; value: number }]
  'range-change': [range: { startDate: string; endDate: string }]
}>()

const chartRef = ref()

// 指标颜色映射
const METRIC_COLORS: Record<string, string> = {
  weight: '#8B5CF6',
  systolic: '#EF4444',
  diastolic: '#F97316',
  blood_sugar_fasting: '#EC4899',
  blood_sugar_postprandial: '#F472B6',
  fetal_movement: '#06B6D4',
  heart_rate: '#10B981',
  sleep_hours: '#6366F1',
  steps: '#F59E0B',
  emotion_score: '#8B5CF6',
}

// 需要双线组合的指标对
const BP_METRICS = ['systolic', 'diastolic']
const SUGAR_METRICS = ['blood_sugar_fasting', 'blood_sugar_postprandial']

function getAxisData(s: TrendSeries): string[] {
  return s.data.map(d => props.axisMode === 'gest_week' ? `孕${d.gest_week}周` : d.date)
}

const chartOption = computed(() => {
  const sList = props.series
  if (!sList.length) return {}

  // 判断是否为血压或血糖组合
  const metricCodes = sList.map(s => s.metric)
  const isBP = BP_METRICS.every(m => metricCodes.includes(m))
  const isSugar = SUGAR_METRICS.every(m => metricCodes.includes(m))
  const isCombo = isBP || isSugar

  if (isCombo) {
    return buildComboOption(sList, isBP)
  }

  // 单指标或多指标独立图表（grid 叠加）
  return buildSingleOption(sList)
})

function buildComboOption(sList: TrendSeries[], isBP: boolean) {
  const primary = sList.find(s => s.metric === (isBP ? 'systolic' : 'blood_sugar_fasting'))!
  const secondary = sList.find(s => s.metric === (isBP ? 'diastolic' : 'blood_sugar_postprandial'))!
  const xAxisData = getAxisData(primary)
  const markAreaData = buildMarkArea(primary, isBP)

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: [primary.name, secondary.name], bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      name: primary.unit,
      min: (val: any) => Math.floor(val.min * 0.9),
      max: (val: any) => Math.ceil(val.max * 1.1),
    },
    series: [
      buildLineSeries(primary, markAreaData),
      buildLineSeries(secondary),
    ],
  }
}

function buildSingleOption(sList: TrendSeries[]) {
  // 单指标
  if (sList.length === 1) {
    const s = sList[0]
    const xAxisData = getAxisData(s)
    const markAreaData = buildMarkArea(s, false)
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
      },
      yAxis: {
        type: 'value',
        name: s.unit,
        min: (val: any) => Math.floor(val.min * 0.9),
        max: (val: any) => Math.ceil(val.max * 1.1),
      },
      series: [buildLineSeries(s, markAreaData)],
    }
  }

  // 多指标：使用多 Y 轴
  const first = sList[0]
  const xAxisData = getAxisData(first)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: sList.map(s => s.name), bottom: 0 },
    grid: { left: 50, right: 50, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLabel: { rotate: xAxisData.length > 10 ? 30 : 0 },
    },
    yAxis: sList.map((s, i) => ({
      type: 'value',
      name: s.unit,
      position: i % 2 === 0 ? 'left' : 'right',
    })),
    series: sList.map((s, i) => ({
      ...buildLineSeries(s),
      yAxisIndex: i,
    })),
  }
}

function buildLineSeries(s: TrendSeries, markArea?: any[]) {
  return {
    name: s.name,
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    data: s.data.map(d => d.value),
    itemStyle: { color: METRIC_COLORS[s.metric] || '#409EFF' },
    lineStyle: { width: 2 },
    areaStyle: { opacity: 0.05 },
    markArea: markArea && markArea.length ? { data: markArea } : undefined,
    markLine: s.normal_range.min != null ? {
      silent: true,
      data: [
        { yAxis: s.normal_range.max, lineStyle: { color: '#E6A23C', type: 'dashed' } },
        ...(s.metric !== 'blood_sugar_postprandial' ? [{ yAxis: s.normal_range.min, lineStyle: { color: '#E6A23C', type: 'dashed' } }] : []),
      ],
    } : undefined,
  }
}

function buildMarkArea(s: TrendSeries, isBP: boolean): any[] {
  if (!props.showNormalRange) return []
  if (!s.normal_range || s.normal_range.min == null) return []

  // 血压特殊：只标异常区域
  if (isBP) {
    if (s.metric === 'systolic') {
      return [[
        { yAxis: 140, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } },
        { yAxis: 200 },
      ]]
    }
    return [[
      { yAxis: 90, itemStyle: { color: 'rgba(239, 68, 68, 0.08)' } },
      { yAxis: 150 },
    ]]
  }

  // 通用：正常范围区域
  return [[
    { yAxis: s.normal_range.min, itemStyle: { color: 'rgba(16, 185, 129, 0.06)' } },
    { yAxis: s.normal_range.max },
  ]]
}

function handleClick(params: any) {
  if (!props.interactive || !params.data) return
  const seriesIdx = params.seriesIndex || 0
  const dataIdx = params.dataIndex
  const s = props.series[seriesIdx]
  if (s && s.data[dataIdx]) {
    emit('point-click', {
      metric: s.metric,
      date: s.data[dataIdx].date,
      value: s.data[dataIdx].value,
    })
  }
}

/** 外部调用：跳转到指定日期范围 */
function zoomToRange(startDate: string, endDate: string) {
  emit('range-change', { startDate, endDate })
}

defineExpose({ zoomToRange })
</script>

<style scoped>
.health-trend-chart {
  width: 100%;
  min-height: 200px;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
```

- [ ] **Step 3: 验证组件无语法错误**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | grep -i "HealthTrendChart" || echo "No errors in HealthTrendChart"
```

Expected: `No errors in HealthTrendChart`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/charts/HealthTrendChart.vue
git commit -m "feat: implement HealthTrendChart shared chart component"
```

---

### Task 5: 孕妇端集成健康趋势

**Files:**
- Modify: `frontend/src/views/pregnant/PregnantTools.vue`

- [ ] **Step 1: 在 PregnantTools.vue 模板中添加「健康趋势」卡片**

在 `<!-- ==================== 历史记录 ==================== -->` 的胎动计数历史卡片之后、`<!-- ==================== 心理健康筛查 ==================== -->` 之前，插入新的卡片：

```html
    <!-- ==================== 健康趋势 ==================== -->
    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #42A5F5"></span>
        健康趋势
      </div>

      <!-- 指标选择器 -->
      <div class="trend-metric-selector">
        <el-checkbox-group v-model="selectedMetrics" @change="loadTrendData">
          <el-checkbox v-for="m in metricOptions" :key="m.value" :label="m.value" :value="m.value">
            {{ m.label }}
          </el-checkbox>
        </el-checkbox-group>
      </div>

      <!-- 横轴模式切换 -->
      <div class="trend-axis-toggle">
        <el-radio-group v-model="trendAxisMode" size="small" @change="loadTrendData">
          <el-radio-button value="date">按日期</el-radio-button>
          <el-radio-button value="gestational_week">按孕周</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 图表 -->
      <HealthTrendChart
        :series="trendSeries"
        :axis-mode="trendAxisMode === 'gestational_week' ? 'gest_week' : 'date'"
        :show-normal-range="true"
        :interactive="false"
        :height="300"
      />
    </div>
```

- [ ] **Step 2: 在 script setup 中添加健康趋势逻辑**

在 `import` 部分添加：

```typescript
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import type { TrendSeries } from '@/types'
```

在 `onMounted` 之前添加以下响应式数据和方法：

```typescript
/* ==================== 健康趋势 ==================== */
const selectedMetrics = ref<string[]>(['weight', 'systolic', 'diastolic'])
const trendAxisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const trendLoading = ref(false)

const metricOptions = [
  { value: 'weight', label: '体重' },
  { value: 'systolic', label: '收缩压' },
  { value: 'diastolic', label: '舒张压' },
  { value: 'blood_sugar_fasting', label: '空腹血糖' },
  { value: 'blood_sugar_postprandial', label: '餐后血糖' },
  { value: 'fetal_movement', label: '胎动' },
  { value: 'heart_rate', label: '心率' },
  { value: 'sleep_hours', label: '睡眠' },
  { value: 'steps', label: '步数' },
]

async function loadTrendData() {
  if (!pregnantId.value || !selectedMetrics.value.length) {
    trendSeries.value = []
    return
  }
  trendLoading.value = true
  try {
    const res = await pregnantApi.getHealthTrends(pregnantId.value, {
      metrics: selectedMetrics.value.join(','),
      axis_mode: trendAxisMode.value,
    })
    trendSeries.value = res.data.series || []
  } catch {
    trendSeries.value = []
  } finally {
    trendLoading.value = false
  }
}
```

在 `onMounted` 中添加调用：

```typescript
onMounted(() => {
  loadSummary()
  loadHistory()
  loadTrendData()
})
```

- [ ] **Step 3: 添加 CSS 样式**

在 `<style scoped>` 部分末尾追加：

```css
/* 健康趋势 */
.trend-metric-selector {
  margin-bottom: 12px;
}

.trend-metric-selector .el-checkbox {
  margin-right: 12px;
  margin-bottom: 4px;
}

.trend-axis-toggle {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}
```

- [ ] **Step 4: 验证编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/pregnant/PregnantTools.vue
git commit -m "feat: integrate health trend chart into PregnantTools page"
```

---

## 第 2 期：护士端详情页

### Task 6: FollowUpTimeline 组件

**Files:**
- Create: `frontend/src/components/followup/FollowUpTimeline.vue`

- [ ] **Step 1: 创建 followup 组件目录**

```bash
mkdir -p frontend/src/components/followup
```

- [ ] **Step 2: 实现 FollowUpTimeline.vue**

```vue
<template>
  <div class="followup-timeline">
    <div v-if="!records.length" class="timeline-empty">
      <el-empty description="暂无随访记录" :image-size="60" />
    </div>
    <div v-else class="timeline-list">
      <div
        v-for="record in records"
        :key="record.id"
        class="timeline-item"
        :class="{ 'timeline-item--selected': record.id === selectedId }"
        @click="$emit('select', record)"
      >
        <div class="timeline-item__dot" :class="dotClass(record.status)" />
        <div class="timeline-item__content">
          <div class="timeline-item__header">
            <span class="timeline-item__date">{{ formatDate(record.follow_up_date) }}</span>
            <el-tag :type="statusType(record.status)" size="small">
              {{ statusLabel(record.status) }}
            </el-tag>
          </div>
          <div v-if="record.gestational_week" class="timeline-item__week">
            孕{{ record.gestational_week }}周
          </div>
          <div v-if="record.summary" class="timeline-item__summary">
            {{ record.summary }}
          </div>
          <div v-if="record.chief_complaint" class="timeline-item__complaint">
            主诉：{{ record.chief_complaint }}
          </div>
          <!-- 展开详情 -->
          <div v-if="record.id === selectedId" class="timeline-item__detail">
            <div v-if="Object.keys(record.self_reported_data || {}).length" class="detail-section">
              <div class="detail-section__title">自报数据</div>
              <div class="detail-section__body">
                <span v-for="(val, key) in record.self_reported_data" :key="key" class="detail-tag">
                  {{ key }}: {{ val }}
                </span>
              </div>
            </div>
            <div v-if="record.health_education?.length" class="detail-section">
              <div class="detail-section__title">健康教育</div>
              <ul class="detail-section__list">
                <li v-for="(item, i) in record.health_education" :key="i">{{ item }}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FollowUpHistoryRecord } from '@/types'

defineProps<{
  records: FollowUpHistoryRecord[]
  selectedId?: string | null
}>()

defineEmits<{
  select: [record: FollowUpHistoryRecord]
}>()

function formatDate(iso: string | null): string {
  if (!iso) return '--'
  const m = iso.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : iso.slice(0, 10)
}

function statusType(status: string): string {
  const map: Record<string, string> = {
    archived: 'success',
    confirmed: 'success',
    completed: 'primary',
    in_progress: 'warning',
    draft: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    archived: '已归档',
    confirmed: '已确认',
    completed: '已完成',
    in_progress: '进行中',
    draft: '草稿',
  }
  return map[status] || status
}

function dotClass(status: string): string {
  if (status === 'archived' || status === 'confirmed') return 'dot--success'
  if (status === 'in_progress') return 'dot--warning'
  return 'dot--default'
}
</script>

<style scoped>
.followup-timeline {
  height: 100%;
  overflow-y: auto;
}

.timeline-list {
  position: relative;
  padding-left: 20px;
}

.timeline-list::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #e4e7ed;
}

.timeline-item {
  position: relative;
  padding: 12px 0;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: 6px;
  padding-left: 12px;
  margin-bottom: 4px;
}

.timeline-item:hover {
  background: #f5f7fa;
}

.timeline-item--selected {
  background: #ecf5ff;
}

.timeline-item__dot {
  position: absolute;
  left: -17px;
  top: 18px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #e4e7ed;
  background: #fff;
  z-index: 1;
}

.dot--success {
  border-color: #67c23a;
  background: #67c23a;
}

.dot--warning {
  border-color: #e6a23c;
  background: #e6a23c;
}

.dot--default {
  border-color: #909399;
  background: #fff;
}

.timeline-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-item__date {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.timeline-item__week {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.timeline-item__summary {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
  line-height: 1.5;
}

.timeline-item__complaint {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.timeline-item__detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}

.detail-section {
  margin-bottom: 8px;
}

.detail-section__title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}

.detail-section__body {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-tag {
  font-size: 11px;
  background: #f0f2f5;
  padding: 2px 8px;
  border-radius: 4px;
  color: #606266;
}

.detail-section__list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #606266;
}

.detail-section__list li {
  margin: 2px 0;
}

.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}
</style>
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | grep -i "FollowUpTimeline" || echo "No errors"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/followup/FollowUpTimeline.vue
git commit -m "feat: implement FollowUpTimeline component"
```

---

### Task 7: 护士端 PregnantDetail 页面

**Files:**
- Create: `frontend/src/views/nurse/PregnantDetail.vue`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 实现护士端 PregnantDetail.vue**

```vue
<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button text @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <h1 class="page-title">{{ pregnantInfo?.display_name || '孕妇详情' }}</h1>
      <span v-if="pregnantInfo?.gestational_age_days" class="header-subtitle">
        孕{{ Math.floor(pregnantInfo.gestational_age_days / 7) }}周
      </span>
    </div>

    <!-- 主内容区：左时间线 + 右曲线 -->
    <el-row :gutter="16" class="detail-body">
      <!-- 左侧：随访时间线 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">随访记录</span>
            <el-tag size="small">{{ followUpRecords.length }} 条</el-tag>
          </div>
          <div class="content-card__body">
            <FollowUpTimeline
              :records="followUpRecords"
              :selected-id="selectedFollowUpId"
              @select="handleFollowUpSelect"
            />
          </div>
        </div>
      </el-col>

      <!-- 右侧：健康数据曲线 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">健康趋势</span>
            <div class="chart-controls">
              <el-checkbox-group v-model="selectedMetrics" @change="loadTrendData" size="small">
                <el-checkbox value="weight">体重</el-checkbox>
                <el-checkbox value="systolic">收缩压</el-checkbox>
                <el-checkbox value="diastolic">舒张压</el-checkbox>
                <el-checkbox value="blood_sugar_fasting">空腹血糖</el-checkbox>
                <el-checkbox value="fetal_movement">胎动</el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-model="axisMode" size="small" @change="loadTrendData" style="margin-left: 12px">
                <el-radio-button value="date">日期</el-radio-button>
                <el-radio-button value="gestational_week">孕周</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="content-card__body">
            <HealthTrendChart
              ref="chartRef"
              :series="trendSeries"
              :axis-mode="axisMode === 'gestational_week' ? 'gest_week' : 'date'"
              :show-normal-range="true"
              :interactive="true"
              :height="450"
              @point-click="handlePointClick"
            />
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { pregnantApi, dashboardApi } from '@/api/endpoints'
import FollowUpTimeline from '@/components/followup/FollowUpTimeline.vue'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import type { TrendSeries, FollowUpHistoryRecord, Pregnant } from '@/types'

const route = useRoute()
const pregnantId = computed(() => route.params.pregnantId as string)

const pregnantInfo = ref<Pregnant | null>(null)
const followUpRecords = ref<FollowUpHistoryRecord[]>([])
const selectedFollowUpId = ref<string | null>(null)
const selectedMetrics = ref(['systolic', 'diastolic', 'weight'])
const axisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const chartRef = ref()

async function loadPregnantInfo() {
  try {
    const res = await pregnantApi.get(pregnantId.value)
    pregnantInfo.value = res.data
  } catch { /* ignore */ }
}

async function loadFollowUpHistory() {
  try {
    const res = await pregnantApi.getFollowUpHistory(pregnantId.value, { limit: 50 })
    followUpRecords.value = res.data.records || []
  } catch { /* ignore */ }
}

async function loadTrendData() {
  if (!pregnantId.value || !selectedMetrics.value.length) {
    trendSeries.value = []
    return
  }
  try {
    const res = await pregnantApi.getHealthTrends(pregnantId.value, {
      metrics: selectedMetrics.value.join(','),
      axis_mode: axisMode.value,
    })
    trendSeries.value = res.data.series || []
  } catch {
    trendSeries.value = []
  }
}

function handleFollowUpSelect(record: FollowUpHistoryRecord) {
  selectedFollowUpId.value = record.id
  // 联动：跳转曲线到该随访日期前后 14 天
  if (record.follow_up_date && chartRef.value) {
    const followDate = new Date(record.follow_up_date)
    const start = new Date(followDate)
    start.setDate(start.getDate() - 7)
    const end = new Date(followDate)
    end.setDate(end.getDate() + 7)
    chartRef.value.zoomToRange(
      start.toISOString().slice(0, 10),
      end.toISOString().slice(0, 10),
    )
  }
}

function handlePointClick(data: { metric: string; date: string; value: number }) {
  console.log('Point clicked:', data)
}

onMounted(() => {
  loadPregnantInfo()
  loadFollowUpHistory()
  loadTrendData()
})
</script>

<style scoped>
.detail-body {
  margin-top: 16px;
}

.header-subtitle {
  font-size: 14px;
  color: #909399;
  margin-left: 8px;
}

.chart-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
</style>
```

- [ ] **Step 2: 在 router/index.ts 中添加护士端详情页路由**

在 `children` 数组中的 `{ path: 'alerts'...` 之后添加：

```typescript
      { path: 'pregnant/:pregnantId', name: 'NursePregnantDetail', component: () => import('@/views/nurse/PregnantDetail.vue'), meta: { title: '孕妇详情' } },
```

- [ ] **Step 3: 验证路由配置**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/nurse/PregnantDetail.vue frontend/src/router/index.ts
git commit -m "feat: implement nurse PregnantDetail page with timeline + chart linkage"
```

---

### Task 8: 护士端跳转入口

**Files:**
- Modify: `frontend/src/views/nurse/FollowUpList.vue`

- [ ] **Step 1: 在 FollowUpList.vue 的 viewDetail 方法中添加跳转**

找到 `viewDetail` 方法（或 `@row-click="viewDetail"`），修改为跳转到孕妇详情页。在 `<script setup>` 中添加：

```typescript
function viewDetail(row: any) {
  if (row.pregnant_id) {
    router.push({ name: 'NursePregnantDetail', params: { pregnantId: row.pregnant_id } })
  }
}
```

确保 `useRouter` 已导入：

```typescript
import { useRouter } from 'vue-router'
const router = useRouter()
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/nurse/FollowUpList.vue
git commit -m "feat: add jump-to-detail from FollowUpList"
```

---

## 第 3 期：医生端详情页

### Task 9: 医生端 PregnantDetail 页面

**Files:**
- Create: `frontend/src/views/doctor/PregnantDetail.vue`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 实现医生端 PregnantDetail.vue**

与护士端基本一致，增加异常标注功能。基于护士端版本复制，主要区别在 `HealthTrendChart` 的 `showNormalRange` 始终为 `true`，并在顶部增加风险标签展示。

```vue
<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button text @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <h1 class="page-title">{{ pregnantInfo?.display_name || '孕妇详情' }}</h1>
      <span v-if="pregnantInfo?.gestational_age_days" class="header-subtitle">
        孕{{ Math.floor(pregnantInfo.gestational_age_days / 7) }}周
      </span>
      <div v-if="pregnantInfo?.risk_tags?.length" class="risk-tags">
        <el-tag v-for="tag in pregnantInfo.risk_tags" :key="tag" type="danger" size="small">
          {{ tag }}
        </el-tag>
      </div>
    </div>

    <!-- 主内容区 -->
    <el-row :gutter="16" class="detail-body">
      <!-- 左侧：随访时间线 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">随访记录</span>
            <el-tag size="small">{{ followUpRecords.length }} 条</el-tag>
          </div>
          <div class="content-card__body">
            <FollowUpTimeline
              :records="followUpRecords"
              :selected-id="selectedFollowUpId"
              @select="handleFollowUpSelect"
            />
          </div>
        </div>
      </el-col>

      <!-- 右侧：健康数据曲线 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">健康趋势</span>
            <div class="chart-controls">
              <el-checkbox-group v-model="selectedMetrics" @change="loadTrendData" size="small">
                <el-checkbox value="weight">体重</el-checkbox>
                <el-checkbox value="systolic">收缩压</el-checkbox>
                <el-checkbox value="diastolic">舒张压</el-checkbox>
                <el-checkbox value="blood_sugar_fasting">空腹血糖</el-checkbox>
                <el-checkbox value="blood_sugar_postprandial">餐后血糖</el-checkbox>
                <el-checkbox value="fetal_movement">胎动</el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-model="axisMode" size="small" @change="loadTrendData" style="margin-left: 12px">
                <el-radio-button value="date">日期</el-radio-button>
                <el-radio-button value="gestational_week">孕周</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="content-card__body">
            <HealthTrendChart
              ref="chartRef"
              :series="trendSeries"
              :axis-mode="axisMode === 'gestational_week' ? 'gest_week' : 'date'"
              :show-normal-range="true"
              :interactive="true"
              :height="450"
              @point-click="handlePointClick"
            />
          </div>
        </div>

        <!-- 异常数据摘要卡片 -->
        <div v-if="abnormalMetrics.length" class="content-card" style="margin-top: 16px">
          <div class="content-card__header">
            <span class="content-card__title" style="color: #f56c6c">异常数据提示</span>
          </div>
          <div class="content-card__body">
            <div v-for="item in abnormalMetrics" :key="item.metric" class="abnormal-item">
              <el-icon color="#f56c6c"><WarningFilled /></el-icon>
              <span>{{ item.name }}: {{ item.latest_value }}{{ item.unit }}</span>
              <el-tag type="danger" size="small">超出正常范围</el-tag>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, WarningFilled } from '@element-plus/icons-vue'
import { pregnantApi } from '@/api/endpoints'
import FollowUpTimeline from '@/components/followup/FollowUpTimeline.vue'
import HealthTrendChart from '@/components/charts/HealthTrendChart.vue'
import type { TrendSeries, FollowUpHistoryRecord, Pregnant } from '@/types'

const route = useRoute()
const router = useRouter()
const pregnantId = computed(() => route.params.pregnantId as string)

const pregnantInfo = ref<Pregnant | null>(null)
const followUpRecords = ref<FollowUpHistoryRecord[]>([])
const selectedFollowUpId = ref<string | null>(null)
const selectedMetrics = ref(['systolic', 'diastolic', 'weight', 'blood_sugar_fasting'])
const axisMode = ref<'date' | 'gestational_week'>('date')
const trendSeries = ref<TrendSeries[]>([])
const chartRef = ref()

// 异常数据检测
const abnormalMetrics = computed(() => {
  return trendSeries.value.filter(s => s.is_normal === false)
})

async function loadPregnantInfo() {
  try {
    const res = await pregnantApi.get(pregnantId.value)
    pregnantInfo.value = res.data
  } catch { /* ignore */ }
}

async function loadFollowUpHistory() {
  try {
    const res = await pregnantApi.getFollowUpHistory(pregnantId.value, { limit: 50 })
    followUpRecords.value = res.data.records || []
  } catch { /* ignore */ }
}

async function loadTrendData() {
  if (!pregnantId.value || !selectedMetrics.value.length) {
    trendSeries.value = []
    return
  }
  try {
    const res = await pregnantApi.getHealthTrends(pregnantId.value, {
      metrics: selectedMetrics.value.join(','),
      axis_mode: axisMode.value,
    })
    trendSeries.value = res.data.series || []
  } catch {
    trendSeries.value = []
  }
}

function handleFollowUpSelect(record: FollowUpHistoryRecord) {
  selectedFollowUpId.value = record.id
  if (record.follow_up_date && chartRef.value) {
    const followDate = new Date(record.follow_up_date)
    const start = new Date(followDate)
    start.setDate(start.getDate() - 7)
    const end = new Date(followDate)
    end.setDate(end.getDate() + 7)
    chartRef.value.zoomToRange(
      start.toISOString().slice(0, 10),
      end.toISOString().slice(0, 10),
    )
  }
}

function handlePointClick(data: { metric: string; date: string; value: number }) {
  console.log('Point clicked:', data)
}

onMounted(() => {
  loadPregnantInfo()
  loadFollowUpHistory()
  loadTrendData()
})
</script>

<style scoped>
.detail-body {
  margin-top: 16px;
}

.header-subtitle {
  font-size: 14px;
  color: #909399;
  margin-left: 8px;
}

.risk-tags {
  display: inline-flex;
  gap: 4px;
  margin-left: 12px;
}

.chart-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.abnormal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 14px;
}

.abnormal-item:not(:last-child) {
  border-bottom: 1px solid #ebeef5;
}
</style>
```

- [ ] **Step 2: 在 router/index.ts 中添加医生端详情页路由**

在 `children` 数组中的 `{ path: 'orders'...` 之后添加：

```typescript
      { path: 'pregnant/:pregnantId', name: 'DoctorPregnantDetail', component: () => import('@/views/doctor/PregnantDetail.vue'), meta: { title: '孕妇详情' } },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/doctor/PregnantDetail.vue frontend/src/router/index.ts
git commit -m "feat: implement doctor PregnantDetail page with abnormal data highlights"
```

---

### Task 10: 医生端跳转入口

**Files:**
- Modify: `frontend/src/views/doctor/DoctorDashboard.vue`

- [ ] **Step 1: 在 DoctorDashboard.vue 的表格行点击事件中添加跳转**

在 `@row-click="handleAlertClick"` 方法中，修改为同时支持跳转到孕妇详情：

```typescript
function handleAlertClick(row: any) {
  if (row.pregnant_id) {
    router.push({ name: 'DoctorPregnantDetail', params: { pregnantId: row.pregnant_id } })
  }
}
```

确保 `useRouter` 已导入。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/doctor/DoctorDashboard.vue
git commit -m "feat: add jump-to-detail from DoctorDashboard"
```

---

## 最终验证

- [ ] **Step 1: 后端 API 集成测试**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 无新增测试失败

- [ ] **Step 2: 前端编译验证**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```

Expected: 无新增类型错误

- [ ] **Step 3: 功能验证清单**

- [ ] 孕妇端：访问 `/pregnant/tools`，「健康趋势」卡片正常显示，切换指标和横轴模式
- [ ] 护士端：从随访列表点击某行，跳转到 `/nurse/pregnant/:id`，时间线+曲线联动
- [ ] 医生端：从工作台点击某行，跳转到 `/doctor/pregnant/:id`，异常数据标注正确
