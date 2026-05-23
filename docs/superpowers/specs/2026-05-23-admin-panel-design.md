# 轻量化后台管理系统设计

**日期**：2026-05-23  
**状态**：已确认  
**依赖**：[Token 优化与审计日志系统](2026-05-23-token-optimization-audit-log-design.md)

---

## 1. 目标

为 Agent 审计日志（`agent_audit_logs` 表）构建一个轻量化的 Web 管理后台，覆盖三个维度：

1. **成本审核**：每日/每变体的 token 消耗量和趋势
2. **对话溯源**：单次会话的完整审计链（用户消息 → 意图 → 路由 → 工具调用 → 响应）
3. **运行监控**：各 Agent 变体的调用量、延迟、路由分布

**原则**：零新依赖，全部复用 Element Plus + vue-echarts 已有组件。

---

## 2. 访问控制

- 独立管理员登录：复用现有 `Login.vue`，admin 角色登录后跳转 `/admin/dashboard`
- admin 角色在 `UserRole` 类型中已定义，在 Pinia store 中已配置角色名和图标
- 后端 admin API 端点暂不强制鉴权（后续可加中间件）

---

## 3. 架构

### 3.1 路由结构

```
/admin (AdminLayout) → 重定向到 /admin/dashboard
  ├─ /admin/dashboard      Dashboard.vue      仪表盘首页
  ├─ /admin/token-analysis TokenAnalysis.vue   Token消耗分析
  ├─ /admin/audit-trail    AuditTrail.vue      对话审计追溯
  └─ /admin/route-monitor  RouteMonitor.vue    路由监控
```

### 3.2 布局

复用 `NurseLayout.vue` / `DoctorLayout.vue` 的 Sidebar 布局模式：

```
┌─────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌───────────────────────────────────┐ │
│ │  侧边栏   │ │  HeaderBar（页面标题 + 日期范围）  │ │
│ │  dark     │ ├───────────────────────────────────┤ │
│ │  theme    │ │                                   │ │
│ │           │ │  <router-view /> 页面内容区        │ │
│ │ 📊 仪表盘 │ │                                   │ │
│ │ 💰 Token  │ │                                   │ │
│ │   分析    │ │                                   │ │
│ │ 🔍 对话   │ │                                   │ │
│ │   审计    │ │                                   │ │
│ │ 🔀 路由   │ │                                   │ │
│ │   监控    │ │                                   │ │
│ │           │ │                                   │ │
│ │ 返回主站   │ │                                   │ │
│ └──────────┘ └───────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

- 侧边栏：深色 `el-menu`，4 个导航项 + 底部"返回主站"链接
- 顶栏：页面标题 + 全局日期范围选择器（Dashboard / TokenAnalysis / RouteMonitor 共享）
- 内容区：`el-main` + `el-scrollbar`，各页面独立滚动
- 无 AI FAB 浮动按钮

### 3.3 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 框架 | Vue 3.5 + TypeScript | 与主项目一致 |
| UI | Element Plus 2.9 | 已有 |
| 图表 | vue-echarts 7.0 + echarts 5.5 | 已有 |
| 状态 | Pinia 2.3 | 已有 |
| HTTP | axios 1.7 | 已有 |
| 日期 | dayjs 1.11 | 已有 |
| 后端 | FastAPI + SQLAlchemy | 已有 |

---

## 4. 页面设计

### 4.1 仪表盘首页 (Dashboard.vue)

**数据源**：`GET /api/v1/admin/audit/dashboard?date_from=&date_to=`

**顶部 4 卡片**（`el-row` + `el-card` + `el-statistic`）：
- 总调用次数
- Token 总消耗
- 平均延迟(ms)
- 活跃会话数

**左侧**：近 7 天 Token 消耗趋势（折线图，vue-echarts）  
**右侧**：Agent 变体调用分布（饼图，vue-echarts）  
**底部**：最近调用记录（`el-table`，最后 10 条，点击行跳转到审计详情）

### 4.2 Token 消耗分析 (TokenAnalysis.vue)

**数据源**：`GET /api/v1/admin/audit/token/daily` + `GET /api/v1/admin/audit/token/by-agent`

**筛选栏**：Agent 变体多选下拉（复用顶栏全局日期）

**上半部分-按日汇总**（`el-table`，分页）：

| 日期 | 输入Token | 输出Token | 总Token | 调用次数 | 平均延迟 |
|------|----------|----------|---------|---------|---------|

**下半部分-按变体汇总**（`el-table`，分页）：

| Agent角色 | Agent变体 | 总Token | 调用次数 | 平均输入 | 平均输出 | 平均延迟 |
|----------|----------|---------|---------|---------|---------|---------|

### 4.3 对话审计追溯 (AuditTrail.vue)

**数据源**：`GET /api/v1/admin/audit/sessions?page=&page_size=&user_id=&agent_variant=&date_from=&date_to=`  
**详情**：`GET /api/v1/admin/audit/sessions/{session_id}`

**筛选栏**：用户 ID 搜索 + Agent 变体下拉 + 日期范围

**列表页**（`el-table`，分页）：

| 时间 | 会话ID | 用户ID | 意图 | 路由Agent | Token | 延迟 | 护栏 | 操作 |
|------|--------|--------|------|----------|-------|------|------|------|

**详情抽屉**（`el-drawer`，点击"详情"触发）：
- 响应预览（`response_preview`）
- NLU 意图分类
- Agent 路由决策
- 工具调用链时间线（`tool_calls_json` 展开）
- Token 消耗明细（input / output / total）
- 模型 ID 与延迟
- 安全护栏状态

会话内多条记录高亮关联，同一 session_id 的调用链可展开查看。

### 4.4 路由监控 (RouteMonitor.vue)

**数据源**：`GET /api/v1/admin/audit/token/by-agent`

**顶部统计卡片**：各变体调用量（chat / record / qa / emergency / complex）  
**左侧**：变体调用分布饼图（可点击图例筛选）  
**右侧**：各变体平均 Token 消耗对比柱状图  
**底部**：按变体分组的详细表格（调用次数、平均 Token、平均延迟、占比%）

---

## 5. API 端点

### 5.1 已有端点

```
GET /api/v1/admin/audit/token/daily?date_from=&date_to=
GET /api/v1/admin/audit/token/by-agent?date_from=&date_to=
GET /api/v1/admin/audit/sessions/{session_id}
```

### 5.2 新增端点

**会话列表（分页查询）**

```
GET /api/v1/admin/audit/sessions?page=1&page_size=20&user_id=&agent_variant=&date_from=&date_to=

Response:
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "id": 1,
      "session_id": "xxx",
      "user_id": "P001",
      "agent_variant": "chat",
      "intent_classification": "emotion",
      "routed_agent": "小安-chat",
      "total_tokens": 850,
      "total_latency_ms": 1234,
      "guardrail_triggered": false,
      "response_preview": "我理解你现在的感受...",
      "created_at": "2026-05-23T10:30:00"
    }
  ]
}
```

**仪表盘概览**

```
GET /api/v1/admin/audit/dashboard?date_from=&date_to=

Response:
{
  "summary": {
    "total_calls": 1250,
    "total_tokens": 1250000,
    "avg_latency_ms": 1234.5,
    "active_sessions": 89
  },
  "daily_trend": [
    {"date": "2026-05-17", "total_tokens": 180000, "call_count": 175},
    ...
  ],
  "variant_distribution": [
    {"agent_variant": "chat", "count": 450, "total_tokens": 350000},
    {"agent_variant": "record", "count": 320, "total_tokens": 420000},
    ...
  ],
  "recent_logs": [...]  // 最近 10 条
}
```

---

## 6. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/components/layout/AdminLayout.vue` | 新建 | 管理后台布局 |
| `frontend/src/views/admin/Dashboard.vue` | 新建 | 仪表盘首页 |
| `frontend/src/views/admin/TokenAnalysis.vue` | 新建 | Token 消耗分析 |
| `frontend/src/views/admin/AuditTrail.vue` | 新建 | 对话审计追溯 |
| `frontend/src/views/admin/RouteMonitor.vue` | 新建 | 路由监控 |
| `frontend/src/api/admin.ts` | 新建 | 管理后台 API 封装 |
| `frontend/src/router/index.ts` | 修改 | 新增 admin 路由组 |
| `frontend/src/types/index.ts` | 修改 | 补充 admin 类型定义 |
| `frontend/src/stores/app.ts` | 修改 | 补充 admin 角色路由逻辑 |
| `backend/app/routers/admin.py` | 修改 | 补充 2 个查询端点 |

**总计**：6 新文件 + 4 修改，零新依赖。

---

## 7. 界面优化

设计确认后，使用 `ui-ux-pro-max` skill 对界面进行视觉优化，包括：
- 统计卡片的配色和图标选择
- 图表配色方案（与医疗主题协调）
- 侧边栏深色主题定制
- 表格和抽屉的间距与排版
- 暗色模式兼容

---

## 8. 不做的事项

- 不做独立的后台鉴权系统（复用现有登录机制）
- 不做实时推送 / WebSocket
- 不做导出 PDF/Excel 功能
- 不做短信/邮件告警通知
- Phase 2 的护士/医生审计 Dashboard 不在本次范围
