# 轻量化后台管理系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Agent 审计日志轻量化 Web 管理后台（仪表盘 / Token分析 / 对话审计 / 路由监控 4 页 + AdminLayout + API 层）

**Architecture:** 独立 AdminLayout（内联侧边栏 + 顶栏 + 内容区），4 页面通过 Vue Router 嵌套路由切换，后端补充 2 个查询端点。全部复用 Element Plus + vue-echarts，零新依赖。

**Tech Stack:** Vue 3.5 + TypeScript + Element Plus 2.9 + vue-echarts 7.0 + FastAPI + SQLAlchemy

---

### Task 1: 后端 — 补充 2 个审计查询 API 端点

**Files:**
- Modify: `backend/app/routers/admin.py`

- [ ] **Step 1: 添加会话分页列表端点**

在 `get_session_audit` 函数之后追加：

```python
@router.get("/audit/sessions")
def list_audit_sessions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: str | None = Query(None, description="用户ID筛选"),
    agent_variant: str | None = Query(None, description="Agent变体筛选"),
    date_from: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """分页查询审计会话列表"""
    db = SessionLocal()
    try:
        query = db.query(AgentAuditLog)

        if user_id:
            query = query.filter(AgentAuditLog.user_id == user_id)
        if agent_variant:
            query = query.filter(AgentAuditLog.agent_variant == agent_variant)
        if date_from:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(AgentAuditLog.created_at >= dt_from)
        if date_to:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AgentAuditLog.created_at < dt_to)

        total = query.count()
        rows = (
            query.order_by(AgentAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": [
                {
                    "id": log.id,
                    "session_id": log.session_id,
                    "user_id": log.user_id,
                    "agent_role": log.agent_role,
                    "agent_variant": log.agent_variant,
                    "intent_classification": log.intent_classification,
                    "routed_agent": log.routed_agent,
                    "input_tokens": log.input_tokens,
                    "output_tokens": log.output_tokens,
                    "total_tokens": log.total_tokens,
                    "total_latency_ms": log.total_latency_ms,
                    "guardrail_triggered": log.guardrail_triggered,
                    "response_preview": log.response_preview,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in rows
            ],
        }
    finally:
        db.close()
```

- [ ] **Step 2: 添加仪表盘概览端点**

```python
@router.get("/audit/dashboard")
def get_audit_dashboard(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """仪表盘概览：汇总卡片 + 日趋势 + 变体分布 + 最近记录"""
    db = SessionLocal()
    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

        # 汇总统计
        summary_row = (
            db.query(
                func.count(AgentAuditLog.id).label("total_calls"),
                func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
                func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
                func.count(func.distinct(AgentAuditLog.session_id)).label("active_sessions"),
            )
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .first()
        )

        # 日趋势
        daily_trend = (
            db.query(
                func.date(AgentAuditLog.created_at).label("date"),
                func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
                func.count(AgentAuditLog.id).label("call_count"),
            )
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .group_by(func.date(AgentAuditLog.created_at))
            .order_by(func.date(AgentAuditLog.created_at))
            .all()
        )

        # 变体分布
        variant_dist = (
            db.query(
                AgentAuditLog.agent_variant,
                func.count(AgentAuditLog.id).label("count"),
                func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            )
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .group_by(AgentAuditLog.agent_variant)
            .all()
        )

        # 最近记录
        recent_logs = (
            db.query(AgentAuditLog)
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .order_by(AgentAuditLog.created_at.desc())
            .limit(10)
            .all()
        )

        return {
            "summary": {
                "total_calls": summary_row.total_calls or 0,
                "total_tokens": summary_row.total_tokens or 0,
                "avg_latency_ms": round(summary_row.avg_latency_ms or 0, 1),
                "active_sessions": summary_row.active_sessions or 0,
            },
            "daily_trend": [
                {
                    "date": str(row.date),
                    "total_tokens": row.total_tokens or 0,
                    "call_count": row.call_count,
                }
                for row in daily_trend
            ],
            "variant_distribution": [
                {
                    "agent_variant": row.agent_variant,
                    "count": row.count,
                    "total_tokens": row.total_tokens or 0,
                }
                for row in variant_dist
            ],
            "recent_logs": [
                {
                    "id": log.id,
                    "session_id": log.session_id,
                    "user_id": log.user_id,
                    "agent_variant": log.agent_variant,
                    "intent_classification": log.intent_classification,
                    "total_tokens": log.total_tokens,
                    "total_latency_ms": log.total_latency_ms,
                    "guardrail_triggered": log.guardrail_triggered,
                    "response_preview": (log.response_preview or "")[:100],
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in recent_logs
            ],
        }
    finally:
        db.close()
```

- [ ] **Step 3: 验证端点**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/routers/admin.py
git commit -m "feat: add audit session list and dashboard summary API endpoints"
```

---

### Task 2: 前端 — 补充 Admin 类型定义

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 在文件末尾追加 Admin 相关类型**

```typescript
// ==================== Admin 审计日志类型 ====================

/** 仪表盘概览 */
export interface AdminDashboardSummary {
  total_calls: number
  total_tokens: number
  avg_latency_ms: number
  active_sessions: number
}

export interface AdminDailyTrend {
  date: string
  total_tokens: number
  call_count: number
}

export interface AdminVariantDist {
  agent_variant: string
  count: number
  total_tokens: number
}

export interface AdminRecentLog {
  id: number
  session_id: string
  user_id: string
  agent_variant: string
  intent_classification: string | null
  total_tokens: number
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminDashboardResponse {
  summary: AdminDashboardSummary
  daily_trend: AdminDailyTrend[]
  variant_distribution: AdminVariantDist[]
  recent_logs: AdminRecentLog[]
}

/** Token 日级别 */
export interface AdminTokenDaily {
  date: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  call_count: number
  avg_latency_ms: number
}

/** Token 按 Agent */
export interface AdminTokenByAgent {
  agent_role: string
  agent_variant: string
  total_tokens: number
  call_count: number
  avg_input_tokens: number
  avg_output_tokens: number
  avg_latency_ms: number
}

/** 会话列表项 */
export interface AdminSessionItem {
  id: number
  session_id: string
  user_id: string
  agent_role: string
  agent_variant: string
  intent_classification: string | null
  routed_agent: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminSessionListResponse {
  total: number
  page: number
  page_size: number
  data: AdminSessionItem[]
}

/** 会话审计详情 */
export interface AdminSessionRun {
  id: number
  agent_role: string
  agent_variant: string
  intent_classification: string | null
  routed_agent: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  tool_calls: Array<{ name: string; success: boolean; result_preview: string }> | null
  model_id: string
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminSessionDetail {
  session_id: string
  run_count: number
  runs: AdminSessionRun[]
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add admin audit log TypeScript types"
```

---

### Task 3: 前端 — 创建 Admin API 封装

**Files:**
- Create: `frontend/src/api/admin.ts`

- [ ] **Step 1: 创建 admin.ts**

```typescript
/* Admin 审计日志 API */
import client from './client'
import type {
  AdminDashboardResponse,
  AdminTokenDaily,
  AdminTokenByAgent,
  AdminSessionListResponse,
  AdminSessionDetail,
} from '@/types'

export const adminApi = {
  /** 仪表盘概览 */
  getDashboard: (dateFrom: string, dateTo: string) =>
    client.get<AdminDashboardResponse>('/admin/audit/dashboard', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  /** Token 日级别汇总 */
  getTokenDaily: (dateFrom: string, dateTo: string) =>
    client.get<{ data: AdminTokenDaily[] }>('/admin/audit/token/daily', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  /** Token 按 Agent 汇总 */
  getTokenByAgent: (dateFrom: string, dateTo: string) =>
    client.get<{ data: AdminTokenByAgent[] }>('/admin/audit/token/by-agent', {
      params: { date_from: dateFrom, date_to: dateTo },
    }),

  /** 审计会话列表 */
  getSessions: (params: {
    page: number
    page_size: number
    user_id?: string
    agent_variant?: string
    date_from?: string
    date_to?: string
  }) => client.get<AdminSessionListResponse>('/admin/audit/sessions', { params }),

  /** 单次会话审计详情 */
  getSessionDetail: (sessionId: string) =>
    client.get<AdminSessionDetail>(`/admin/audit/sessions/${sessionId}`),
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/api/admin.ts
git commit -m "feat: add admin audit API layer"
```

---

### Task 4: 前端 — 更新路由支持 admin 角色

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 扩展 RouteMeta 的 role 类型**

将第 10 行的 role 类型声明改为：

```typescript
role?: 'nurse' | 'doctor' | 'pregnant' | 'admin'
```

- [ ] **Step 2: 在 routes 数组中添加 admin 路由组**

在 pregnant 路由组之后（第 80 行 `];` 之前）追加：

```typescript
  // 管理员端
  {
    path: '/admin',
    component: () => import('@/components/layout/AdminLayout.vue'),
    redirect: '/admin/dashboard',
    meta: { requiresAuth: true, role: 'admin' },
    children: [
      { path: 'dashboard', name: 'AdminDashboard', component: () => import('@/views/admin/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'token-analysis', name: 'AdminTokenAnalysis', component: () => import('@/views/admin/TokenAnalysis.vue'), meta: { title: 'Token 消耗分析' } },
      { path: 'audit-trail', name: 'AdminAuditTrail', component: () => import('@/views/admin/AuditTrail.vue'), meta: { title: '对话审计追溯' } },
      { path: 'route-monitor', name: 'AdminRouteMonitor', component: () => import('@/views/admin/RouteMonitor.vue'), meta: { title: '路由监控' } },
    ],
  },
```

- [ ] **Step 3: 在导航守卫中添加 admin 仪表盘路由映射**

在第 128 行的 `dashboardMap` 中添加 admin 条目：

```typescript
const dashboardMap: Record<string, string> = {
  nurse: '/nurse/dashboard',
  doctor: '/doctor/dashboard',
  pregnant: '/pregnant/home',
  admin: '/admin/dashboard',
}
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/router/index.ts
git commit -m "feat: add admin routes with role-based guard support"
```

---

### Task 5: 前端 — 创建 AdminLayout 布局

**Files:**
- Create: `frontend/src/components/layout/AdminLayout.vue`

- [ ] **Step 1: 创建 AdminLayout.vue**

```vue
<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="admin-sidebar">
      <div class="admin-sidebar__logo">
        <el-icon :size="24"><Setting /></el-icon>
        <span class="admin-sidebar__logo-text">管理后台</span>
      </div>

      <el-menu
        :default-active="route.path"
        :router="true"
        class="admin-sidebar__menu"
        background-color="#1d1e2c"
        text-color="#a0a4b8"
        active-text-color="#fff"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><DataBoard /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/admin/token-analysis">
          <el-icon><Coin /></el-icon>
          <template #title>Token 消耗分析</template>
        </el-menu-item>
        <el-menu-item index="/admin/audit-trail">
          <el-icon><Search /></el-icon>
          <template #title>对话审计追溯</template>
        </el-menu-item>
        <el-menu-item index="/admin/route-monitor">
          <el-icon><Connection /></el-icon>
          <template #title>路由监控</template>
        </el-menu-item>
      </el-menu>

      <div class="admin-sidebar__footer">
        <a href="/login" class="back-link" @click.prevent="backToMain">
          <el-icon><Back /></el-icon>
          <span>返回主站</span>
        </a>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="admin-main">
      <header class="admin-header">
        <h2 class="admin-header__title">{{ route.meta?.title || '管理后台' }}</h2>
        <div class="admin-header__actions">
          <el-date-picker
            v-if="showDatePicker"
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :shortcuts="dateShortcuts"
            size="default"
            @change="onDateChange"
          />
        </div>
      </header>
      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import dayjs from 'dayjs'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

appStore.setRole('admin')

const dateRange = ref<[Date, Date]>([
  dayjs().subtract(7, 'day').toDate(),
  new Date(),
])

const dateShortcuts = [
  { text: '最近7天', value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 7); return [s, e] } },
  { text: '最近30天', value: () => { const e = new Date(); const s = new Date(); s.setDate(s.getDate() - 30); return [s, e] } },
  { text: '本月', value: () => { const e = new Date(); const s = new Date(); s.setDate(1); return [s, e] } },
]

// 只在需要日期筛选的页面显示日期选择器
const showDatePicker = computed(() =>
  ['AdminDashboard', 'AdminTokenAnalysis', 'AdminRouteMonitor'].includes(route.name as string)
)

const formatDate = (d: Date) => dayjs(d).format('YYYY-MM-DD')

provide('dateRange', {
  from: computed(() => formatDate(dateRange.value[0])),
  to: computed(() => formatDate(dateRange.value[1])),
})

function onDateChange() {
  // 日期变更时触发页面刷新（各页面 watch dateRange 自行处理）
}

function backToMain() {
  localStorage.removeItem('isLoggedIn')
  localStorage.removeItem('currentRole')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
  background: #f0f2f5;
}

.admin-sidebar {
  width: 220px;
  background: #1d1e2c;
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  z-index: 100;
}

.admin-sidebar__logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.admin-sidebar__logo-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.admin-sidebar__menu {
  flex: 1;
  border-right: none !important;
  padding: 8px;
}

.admin-sidebar__menu .el-menu-item {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 44px;
  line-height: 44px;
}

.admin-sidebar__menu .el-menu-item.is-active {
  background: rgba(255, 255, 255, 0.1) !important;
}

.admin-sidebar__footer {
  padding: 12px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.back-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #a0a4b8;
  text-decoration: none;
  font-size: 13px;
  transition: color 0.2s;
}

.back-link:hover {
  color: #fff;
}

.admin-main {
  margin-left: 220px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.admin-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  position: sticky;
  top: 0;
  z-index: 99;
}

.admin-header__title {
  font-size: 16px;
  font-weight: 600;
  color: #1d1e2c;
  margin: 0;
}

.admin-content {
  flex: 1;
  padding: 24px;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/layout/AdminLayout.vue
git commit -m "feat: add AdminLayout with dark sidebar and date range picker"
```

---

### Task 6: 前端 — 创建 Dashboard 仪表盘页面

**Files:**
- Create: `frontend/src/views/admin/Dashboard.vue`

- [ ] **Step 1: 创建 Dashboard.vue**

```vue
<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #e6f7ff;"><el-icon :size="24" color="#1890ff"><PhoneFilled /></el-icon></div>
            <div class="stat-card__info">
              <div class="stat-card__label">总调用次数</div>
              <div class="stat-card__value">{{ summary.total_calls.toLocaleString() }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #fff7e6;"><el-icon :size="24" color="#fa8c16"><Coin /></el-icon></div>
            <div class="stat-card__info">
              <div class="stat-card__label">Token 总消耗</div>
              <div class="stat-card__value">{{ formatTokens(summary.total_tokens) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #f6ffed;"><el-icon :size="24" color="#52c41a"><Timer /></el-icon></div>
            <div class="stat-card__info">
              <div class="stat-card__label">平均延迟</div>
              <div class="stat-card__value">{{ summary.avg_latency_ms }}ms</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-card__icon" style="background: #f0f5ff;"><el-icon :size="24" color="#722ed1"><ChatDotRound /></el-icon></div>
            <div class="stat-card__info">
              <div class="stat-card__label">活跃会话数</div>
              <div class="stat-card__value">{{ summary.active_sessions }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>近 7 天 Token 消耗趋势</template>
          <VChart :option="trendChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>Agent 变体调用分布</template>
          <VChart :option="pieChartOption" autoresize style="height: 320px;" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近记录 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>最近调用记录</template>
      <el-table :data="recentLogs" stripe size="small" @row-click="goToSession">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="agent_variant" label="变体" width="90">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="intent_classification" label="意图" width="120" />
        <el-table-column prop="total_tokens" label="Token" width="90" />
        <el-table-column prop="total_latency_ms" label="延迟" width="90">
          <template #default="{ row }">{{ row.total_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="guardrail_triggered" label="护栏" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.guardrail_triggered" type="danger" size="small">触发</el-tag>
            <span v-else style="color: #bbb;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="response_preview" label="回复预览" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminDashboardResponse, AdminRecentLog } from '@/types'

use([CanvasRenderer, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const router = useRouter()

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const summary = ref({ total_calls: 0, total_tokens: 0, avg_latency_ms: 0, active_sessions: 0 })
const dailyTrend = ref<Array<{ date: string; total_tokens: number; call_count: number }>>([])
const variantDist = ref<Array<{ agent_variant: string; count: number; total_tokens: number }>>([])
const recentLogs = ref<AdminRecentLog[]>([])

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

const trendChartOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, data: dailyTrend.value.map(d => d.date.slice(5)) },
  yAxis: { type: 'value' as const },
  series: [{
    name: 'Token 消耗', type: 'line', data: dailyTrend.value.map(d => d.total_tokens),
    smooth: true, areaStyle: { opacity: 0.15 },
    itemStyle: { color: '#1890ff' },
  }],
}))

const pieChartOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  series: [{
    type: 'pie', radius: ['45%', '75%'], center: ['50%', '50%'],
    data: variantDist.value.map(v => ({ name: v.agent_variant, value: v.count })),
    emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } },
  }],
}))

function goToSession(row: AdminRecentLog) {
  router.push({ name: 'AdminAuditTrail', query: { session_id: row.session_id } })
}

async function fetchData() {
  try {
    const res = await adminApi.getDashboard(dateRange.from.value, dateRange.to.value)
    summary.value = res.data.summary
    dailyTrend.value = res.data.daily_trend
    variantDist.value = res.data.variant_distribution
    recentLogs.value = res.data.recent_logs
  } catch { /* ignore */ }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>

<style scoped>
.stat-cards :deep(.el-card__body) { padding: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-card__icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-card__label { font-size: 13px; color: #8c8c8c; margin-bottom: 4px; }
.stat-card__value { font-size: 24px; font-weight: 700; color: #1d1e2c; }
:deep(.el-table__row) { cursor: pointer; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/admin/Dashboard.vue
git commit -m "feat: add admin dashboard with stats cards, charts and recent logs"
```

---

### Task 7: 前端 — 创建 TokenAnalysis 页面

**Files:**
- Create: `frontend/src/views/admin/TokenAnalysis.vue`

- [ ] **Step 1: 创建 TokenAnalysis.vue**

```vue
<template>
  <div class="token-analysis">
    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>按日 Token 消耗汇总</template>
          <el-table :data="dailyData" stripe size="small" v-loading="loading">
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="call_count" label="调用次数" width="100" />
            <el-table-column prop="input_tokens" label="输入Token" width="120">
              <template #default="{ row }">{{ row.input_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="output_tokens" label="输出Token" width="120">
              <template #default="{ row }">{{ row.output_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="total_tokens" label="总Token" width="120">
              <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="avg_latency_ms" label="平均延迟" width="100">
              <template #default="{ row }">{{ row.avg_latency_ms }}ms</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>按 Agent 变体 Token 消耗对比</template>
          <el-table :data="agentData" stripe size="small" v-loading="loading" style="margin-bottom: 16px;">
            <el-table-column prop="agent_role" label="角色" width="100" />
            <el-table-column prop="agent_variant" label="变体" width="100">
              <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="100" />
            <el-table-column prop="total_tokens" label="总Token" width="120">
              <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="avg_input_tokens" label="平均输入" width="100" />
            <el-table-column prop="avg_output_tokens" label="平均输出" width="100" />
            <el-table-column prop="avg_latency_ms" label="平均延迟" width="100">
              <template #default="{ row }">{{ row.avg_latency_ms }}ms</template>
            </el-table-column>
          </el-table>
          <VChart :option="barChartOption" autoresize style="height: 300px;" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminTokenDaily, AdminTokenByAgent } from '@/types'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent])

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const loading = ref(false)
const dailyData = ref<AdminTokenDaily[]>([])
const agentData = ref<AdminTokenByAgent[]>([])

const barChartOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, data: agentData.value.map(d => d.agent_variant) },
  yAxis: { type: 'value' as const },
  series: [{
    name: '总Token', type: 'bar', data: agentData.value.map(d => d.total_tokens),
    itemStyle: { borderRadius: [4, 4, 0, 0], color: '#1890ff' },
  }],
}))

async function fetchData() {
  loading.value = true
  try {
    const [dailyRes, agentRes] = await Promise.all([
      adminApi.getTokenDaily(dateRange.from.value, dateRange.to.value),
      adminApi.getTokenByAgent(dateRange.from.value, dateRange.to.value),
    ])
    dailyData.value = dailyRes.data.data
    agentData.value = agentRes.data.data
  } finally {
    loading.value = false
  }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/admin/TokenAnalysis.vue
git commit -m "feat: add admin token analysis page with daily and agent breakdown"
```

---

### Task 8: 前端 — 创建 AuditTrail 页面

**Files:**
- Create: `frontend/src/views/admin/AuditTrail.vue`

- [ ] **Step 1: 创建 AuditTrail.vue**

```vue
<template>
  <div class="audit-trail">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" size="default">
        <el-form-item label="用户ID">
          <el-input v-model="filters.user_id" placeholder="输入用户ID" clearable style="width: 160px;" />
        </el-form-item>
        <el-form-item label="Agent变体">
          <el-select v-model="filters.agent_variant" placeholder="全部" clearable style="width: 140px;">
            <el-option label="chat" value="chat" />
            <el-option label="record" value="record" />
            <el-option label="qa" value="qa" />
            <el-option label="emergency" value="emergency" />
            <el-option label="complex" value="complex" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <el-table :data="sessions" stripe size="small" v-loading="loading" @row-click="showDetail">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="session_id" label="会话ID" width="180" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="intent_classification" label="意图" width="120" />
        <el-table-column prop="agent_variant" label="路由" width="90">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Token" width="80" />
        <el-table-column prop="total_latency_ms" label="延迟" width="80">
          <template #default="{ row }">{{ row.total_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="guardrail_triggered" label="护栏" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.guardrail_triggered" type="danger" size="small">触发</el-tag>
            <span v-else style="color: #bbb;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default>
            <el-button type="primary" link size="small">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; text-align: right;">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="fetchData"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="会话审计详情" size="600px">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="会话ID">{{ detail.session_id }}</el-descriptions-item>
          <el-descriptions-item label="记录数">{{ detail.run_count }}</el-descriptions-item>
        </el-descriptions>

        <el-timeline style="margin-top: 24px;">
          <el-timeline-item
            v-for="(run, idx) in detail.runs"
            :key="run.id"
            :timestamp="run.created_at"
            placement="top"
            :type="run.guardrail_triggered ? 'danger' : 'primary'"
          >
            <el-card shadow="never" size="small">
              <p><b>路由:</b> {{ run.routed_agent }} | <b>意图:</b> {{ run.intent_classification || '-' }}</p>
              <p><b>Token:</b> in={{ run.input_tokens }} out={{ run.output_tokens }} total={{ run.total_tokens }}</p>
              <p><b>延迟:</b> {{ run.total_latency_ms }}ms | <b>模型:</b> {{ run.model_id }}</p>
              <p v-if="run.tool_calls?.length"><b>工具调用:</b> {{ run.tool_calls.map(t => t.name).join(' → ') }}</p>
              <p v-if="run.response_preview" style="color: #8c8c8c;"><b>回复预览:</b> {{ run.response_preview }}</p>
              <p v-if="run.guardrail_triggered" style="color: #ff4d4f;"><b>安全护栏已触发</b></p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, inject } from 'vue'
import { adminApi } from '@/api/admin'
import type { AdminSessionItem, AdminSessionDetail } from '@/types'

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const loading = ref(false)
const sessions = ref<AdminSessionItem[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const filters = reactive({ user_id: '', agent_variant: '' })

const drawerVisible = ref(false)
const detail = ref<AdminSessionDetail | null>(null)

async function fetchData() {
  loading.value = true
  try {
    const res = await adminApi.getSessions({
      page: pagination.page,
      page_size: pagination.page_size,
      user_id: filters.user_id || undefined,
      agent_variant: filters.agent_variant || undefined,
      date_from: dateRange.from.value,
      date_to: dateRange.to.value,
    })
    sessions.value = res.data.data
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function search() { pagination.page = 1; fetchData() }
function reset() { filters.user_id = ''; filters.agent_variant = ''; pagination.page = 1; fetchData() }

async function showDetail(row: AdminSessionItem) {
  try {
    const res = await adminApi.getSessionDetail(row.session_id)
    detail.value = res.data
    drawerVisible.value = true
  } catch { /* ignore */ }
}

fetchData()
</script>

<style scoped>
.filter-card :deep(.el-card__body) { padding: 16px 20px 0; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/admin/AuditTrail.vue
git commit -m "feat: add admin audit trail page with session search and detail drawer"
```

---

### Task 9: 前端 — 创建 RouteMonitor 页面

**Files:**
- Create: `frontend/src/views/admin/RouteMonitor.vue`

- [ ] **Step 1: 创建 RouteMonitor.vue**

```vue
<template>
  <div class="route-monitor">
    <!-- 变体统计卡片 -->
    <el-row :gutter="16">
      <el-col v-for="v in variantCards" :key="v.name" :span="4">
        <el-card shadow="never" class="variant-card">
          <div class="variant-card__name">{{ v.name }}</div>
          <div class="variant-card__count">{{ v.count }}</div>
          <div class="variant-card__tokens">{{ v.tokens }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>变体调用分布</template>
          <VChart :option="pieOption" autoresize style="height: 300px;" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>平均 Token 消耗对比</template>
          <VChart :option="barOption" autoresize style="height: 300px;" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 详细表格 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>变体详细数据</template>
      <el-table :data="agentData" stripe size="small" v-loading="loading">
        <el-table-column prop="agent_role" label="角色" width="100" />
        <el-table-column prop="agent_variant" label="变体" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.agent_variant }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="call_count" label="调用次数" width="100" />
        <el-table-column prop="total_tokens" label="总Token" width="120">
          <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="avg_input_tokens" label="平均输入Token" width="120" />
        <el-table-column prop="avg_output_tokens" label="平均输出Token" width="120" />
        <el-table-column prop="avg_latency_ms" label="平均延迟" width="100">
          <template #default="{ row }">{{ row.avg_latency_ms }}ms</template>
        </el-table-column>
        <el-table-column label="占比" width="100">
          <template #default="{ row }">
            <el-progress :percentage="getPercent(row.call_count)" :stroke-width="8" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { adminApi } from '@/api/admin'
import type { AdminTokenByAgent } from '@/types'

use([CanvasRenderer, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

const dateRange = inject<{ from: { value: string }; to: { value: string } }>('dateRange')!

const loading = ref(false)
const agentData = ref<AdminTokenByAgent[]>([])

const totalCalls = computed(() => agentData.value.reduce((s, d) => s + d.call_count, 0) || 1)

function getPercent(count: number) { return Math.round((count / totalCalls.value) * 100) }

const variantCards = computed(() => {
  const variants = ['chat', 'record', 'qa', 'emergency', 'complex']
  return variants.map(name => {
    const found = agentData.value.find(d => d.agent_variant === name)
    return {
      name,
      count: found?.call_count ?? 0,
      tokens: found ? (found.total_tokens >= 1000 ? (found.total_tokens / 1000).toFixed(1) + 'K' : String(found.total_tokens)) : '0',
    }
  })
})

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  series: [{
    type: 'pie', radius: ['40%', '70%'],
    data: agentData.value.map(d => ({ name: d.agent_variant, value: d.call_count })),
  }],
}))

const barOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, data: agentData.value.map(d => d.agent_variant) },
  yAxis: { type: 'value' as const },
  legend: { data: ['平均输入', '平均输出'] },
  series: [
    { name: '平均输入', type: 'bar' as const, data: agentData.value.map(d => d.avg_input_tokens), itemStyle: { color: '#1890ff' } },
    { name: '平均输出', type: 'bar' as const, data: agentData.value.map(d => d.avg_output_tokens), itemStyle: { color: '#52c41a' } },
  ],
}))

async function fetchData() {
  loading.value = true
  try {
    const res = await adminApi.getTokenByAgent(dateRange.from.value, dateRange.to.value)
    agentData.value = res.data.data
  } finally { loading.value = false }
}

fetchData()
watch(() => [dateRange.from.value, dateRange.to.value], fetchData)
</script>

<style scoped>
.variant-card { text-align: center; }
.variant-card :deep(.el-card__body) { padding: 16px; }
.variant-card__name { font-size: 12px; color: #8c8c8c; text-transform: uppercase; margin-bottom: 6px; }
.variant-card__count { font-size: 28px; font-weight: 700; color: #1d1e2c; }
.variant-card__tokens { font-size: 12px; color: #8c8c8c; margin-top: 4px; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/admin/RouteMonitor.vue
git commit -m "feat: add admin route monitor page with variant distribution and token comparison"
```

---

### Task 10: 更新 Login 页面支持 admin 登录

**Files:**
- Modify: `frontend/src/views/Login.vue`

- [ ] **Step 1: 在 Login.vue 添加 admin 登录逻辑**

找到 `handleLogin` 函数中的角色判断逻辑，添加 admin 支持。在密码验证通过后，增加 admin 判断：

```typescript
// 在现有 nurse/doctor 判断之后添加 admin 判断
if (form.hospital_id === 'admin' && form.password === 'admin123') {
  appStore.login('admin')
  router.push('/admin/dashboard')
  return
}
```

同时更新页面上的 Demo 账号提示区域（`login-hint`），添加 admin 账号信息：

```html
<p>管理员：admin / admin123</p>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/Login.vue
git commit -m "feat: add admin login support (admin/admin123)"
```

---

### Task 11: UI/UX 优化

**Skill:** 使用 `ui-ux-pro-max` skill 对管理后台界面进行视觉优化

- [ ] **Step 1: 调用 ui-ux-pro-max skill**

对以下方面进行优化：
- 统计卡片的配色方案和图标选择（与医疗主题协调）
- ECharts 图表配色（与深色侧边栏协调）
- 侧边栏深色主题打磨（间距、hover 效果、选中态）
- 表格、抽屉、时间线的排版和间距
- 整体视觉一致性

- [ ] **Step 2: 提交优化后的变更**

```bash
git add frontend/src/components/layout/AdminLayout.vue frontend/src/views/admin/
git commit -m "style: apply ui-ux-pro-max optimization to admin panel"
```

---

### Task 12: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd backend && python run.py
```

检查日志确认 admin 端点可用。

- [ ] **Step 2: 测试后端 API**

```bash
curl "http://localhost:9999/api/v1/admin/audit/sessions?page=1&page_size=5&date_from=2026-05-01&date_to=2026-05-23"
curl "http://localhost:9999/api/v1/admin/audit/dashboard?date_from=2026-05-01&date_to=2026-05-23"
```

预期返回 JSON 数据。

- [ ] **Step 3: 启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **Step 4: 浏览器验证**

1. 访问 `http://localhost:5173/login`，用 `admin / admin123` 登录
2. 验证跳转到 `/admin/dashboard`
3. 检查 4 个统计卡片、折线图、饼图、最近记录表格
4. 切换到 Token 分析页，检查日期筛选和表格数据
5. 切换到对话审计页，测试筛选和详情抽屉
6. 切换到路由监控页，检查变体卡片和图表
7. 点击"返回主站"验证回到登录页

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore: end-to-end verification of admin panel"
```

---

### 完成自检清单

- [ ] admin 登录可正常跳转管理后台
- [ ] 4 个页面导航正常切换
- [ ] 全局日期范围选择器在 3 个页面间共享，变更时触发数据刷新
- [ ] 仪表盘统计卡片、图表、最近记录正常渲染
- [ ] Token 分析表格和柱状图数据正确
- [ ] 对话审计筛选、分页、详情抽屉正常
- [ ] 路由监控卡片、图表、进度条正常
- [ ] "返回主站"可回到登录页
- [ ] 零新依赖（仅使用 Element Plus + vue-echarts 已有组件）
