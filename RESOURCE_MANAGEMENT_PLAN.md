# 资源管理系统实现计划

## 概述
将动态资源管理系统集成到 pregnant_care_agent 项目中，包括后端 API、规则引擎、前端监控面板。

## 任务列表

### P1: 核心后端 + 规则引擎

#### Task 1: 资源监控器 (resource_monitor.py)
- **状态**: ✅ 已完成
- **文件**: `backend/app/core/resource_monitor.py`
- **功能**: 实时监控 VRAM/GPU/CPU/NPU

#### Task 2: 规则引擎 (resource_rules.py)
- **状态**: ✅ 已完成
- **文件**: `backend/app/core/resource_rules.py`
- **功能**: 基于规则的动态资源分配决策

#### Task 3: 资源服务 (resource_service.py)
- **状态**: 待实现
- **文件**: `backend/app/services/resource_service.py`
- **功能**: 业务逻辑层，整合监控器和规则引擎

#### Task 4: 资源 API 路由 (resource.py)
- **状态**: 待实现
- **文件**: `backend/app/routers/resource.py`
- **功能**: RESTful API 端点

### P1: Admin 前端

#### Task 5: 资源 API 客户端 (resource.ts)
- **状态**: 待实现
- **文件**: `frontend/src/api/resource.ts`
- **功能**: 前端 API 调用封装

#### Task 6: 资源监控页面 (ResourceMonitor.vue)
- **状态**: 待实现
- **文件**: `frontend/src/views/admin/ResourceMonitor.vue`
- **功能**: 实时资源监控仪表盘

#### Task 7: 资源配置页面 (ResourceConfig.vue)
- **状态**: 待实现
- **文件**: `frontend/src/views/admin/ResourceConfig.vue`
- **功能**: 策略配置和服务管理

### P2: 历史数据分析

#### Task 8: 资源指标模型 (ResourceMetric)
- **状态**: 待实现
- **文件**: `backend/app/models/models.py` (新增)
- **功能**: 存储资源使用历史

#### Task 9: 历史查询 API
- **状态**: 待实现
- **文件**: `backend/app/routers/resource.py` (扩展)
- **功能**: 历史数据查询和趋势分析

### P3: LLM 智能分析

#### Task 10: 资源分析器 (resource_analyzer.py)
- **状态**: 待实现
- **文件**: `backend/app/core/resource_analyzer.py`
- **功能**: 使用 LLM 分析使用模式，生成优化建议

### 集成任务

#### Task 11: 注册路由到 main.py
- **状态**: 待实现
- **文件**: `backend/app/main.py`
- **功能**: 注册 resource router

#### Task 12: 添加前端路由
- **状态**: 待实现
- **文件**: `frontend/src/router/index.ts`
- **功能**: 添加 ResourceMonitor 和 ResourceConfig 路由

## 依赖关系

```
Task 1, 2 (已完成)
    ↓
Task 3 (依赖 1, 2)
    ↓
Task 4 (依赖 3)
    ↓
Task 5 (依赖 4)
    ↓
Task 6, 7 (依赖 5, 可并行)
    ↓
Task 8, 9 (可与 6, 7 并行)
    ↓
Task 10 (依赖 3, 8)
    ↓
Task 11, 12 (最后集成)
```
