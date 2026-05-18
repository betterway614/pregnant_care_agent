# 预警实时推送给医生端 - 设计文档

## 1. 概述

### 1.1 背景

当前系统的预警管理采用**被动式**模式：护士创建预警后只保存到数据库，医生需要手动刷新页面才能看到新预警。这种模式存在以下问题：

- **响应延迟**：医生无法及时获知新预警
- **操作繁琐**：需要频繁手动刷新页面
- **用户体验差**：缺乏实时性和主动性

### 1.2 目标

实现预警的**实时推送**功能，当护士确认创建预警后，立即将预警信息推送到医生端的异常审核工作台，提升系统的实时性和用户体验。

### 1.3 范围

- ✅ 护士创建预警时实时推送给医生端
- ✅ 医生端实时接收并显示新预警
- ✅ 支持断线重连机制
- ✅ 新预警高亮显示和通知提示
- ❌ 不涉及预警审核流程的修改
- ❌ 不涉及多医生账号的权限控制

---

## 2. 需求

### 2.1 功能需求

| 需求ID | 需求描述 | 优先级 |
|--------|---------|--------|
| FR-001 | 护士创建预警时，后端实时推送给医生端 | P0 |
| FR-002 | 医生端实时接收预警并更新UI | P0 |
| FR-003 | 新预警在列表中高亮显示 | P1 |
| FR-004 | 收到新预警时弹出通知提示 | P1 |
| FR-005 | 支持WebSocket断线自动重连 | P1 |
| FR-006 | 显示WebSocket连接状态 | P2 |

### 2.2 非功能需求

| 需求ID | 需求描述 | 指标 |
|--------|---------|------|
| NFR-001 | 推送延迟 | < 1秒 |
| NFR-002 | 连接稳定性 | 支持自动重连，最大重试5次 |
| NFR-003 | 并发支持 | 支持多个医生端同时连接 |
| NFR-004 | 资源占用 | 单连接内存占用 < 1MB |

### 2.3 用户故事

**作为**一名医生  
**我希望**在护士创建预警后立即收到通知  
**以便**能够及时处理高危孕妇的预警情况

---

## 3. 架构设计

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层                                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐                    ┌─────────────┐         │
│  │   护士端    │                    │   医生端    │         │
│  │  (Vue 3)    │                    │  (Vue 3)    │         │
│  └──────┬──────┘                    └──────▲──────┘         │
│         │                                  │                 │
└─────────┼──────────────────────────────────┼─────────────────┘
          │                                  │
          │ HTTP API                         │ WebSocket
          ▼                                  │
┌─────────────────────────────────────────────────────────────┐
│                        后端层                                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │  Alert API  │────▶│  WebSocket  │────▶│   SQLite    │   │
│  │  (FastAPI)  │     │   Manager   │     │  Database   │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 组件说明

| 组件 | 职责 | 技术栈 |
|------|------|--------|
| Alert API | 处理预警创建、查询、审核 | FastAPI |
| WebSocket Manager | 管理医生端WebSocket连接，广播预警 | Python asyncio |
| 前端 WebSocket Client | 接收实时预警，管理连接状态 | TypeScript |
| 医生工作台 | 显示预警列表，处理新预警通知 | Vue 3 + Element Plus |

### 3.3 数据流

```
1. 护士创建预警
   ↓
2. POST /api/v1/alerts
   ↓
3. 保存到 SQLite 数据库
   ↓
4. WebSocket Manager 广播预警
   ↓
5. 所有连接的医生端接收推送
   ↓
6. 前端更新 UI（通知 + 列表刷新）
```

---

## 4. 详细设计

### 4.1 后端实现

#### 4.1.1 WebSocket 连接管理器

**文件位置**: `backend/app/core/websocket_manager.py`

**类设计**:

```python
class WebSocketManager:
    """管理医生端的 WebSocket 连接"""
    
    # 属性
    active_connections: Dict[str, WebSocket]  # 存储活跃连接
    
    # 方法
    async def connect(websocket: WebSocket, doctor_id: str)
    def disconnect(doctor_id: str)
    async def send_alert_to_doctor(doctor_id: str, alert_data: dict) -> bool
    async def broadcast_alert(alert_data: dict)
    def get_active_connections_count() -> int
```

**关键实现细节**:

1. **连接存储**: 使用字典存储 `{doctor_id: websocket}` 映射
2. **断线处理**: 发送失败时自动清理断开的连接
3. **广播机制**: 遍历所有活跃连接发送预警
4. **错误处理**: 捕获异常并记录日志

#### 4.1.2 WebSocket 端点

**文件位置**: `backend/app/routers/websocket.py`

**端点设计**:

```
WebSocket /ws/alerts/{doctor_id}
```

**连接流程**:

1. 医生端建立WebSocket连接
2. 服务器接受连接并注册到WebSocket Manager
3. 保持连接活跃，接收客户端心跳消息
4. 连接断开时自动清理

**消息格式**:

```json
// 服务器 -> 客户端
{
  "type": "NEW_ALERT",
  "data": {
    "id": "alert-uuid",
    "pregnant_id": "pregnant-id",
    "patient_name": "孕妇姓名",
    "level": "RED|ORANGE|YELLOW",
    "message": "预警消息",
    "trigger_source": "触发来源",
    "status": "PENDING",
    "created_at": "2026-05-14T10:30:00Z",
    "gestational_age_days": 200
  }
}

// 客户端 -> 服务器（心跳）
"ping"

// 服务器 -> 客户端（心跳响应）
"pong"
```

#### 4.1.3 修改预警创建逻辑

**文件位置**: `backend/app/routers/alerts.py`

**修改点**:

1. 新增 `POST /api/v1/alerts` 端点
2. 创建预警后调用 `ws_manager.broadcast_alert()`
3. 返回完整的预警信息

**接口设计**:

```
POST /api/v1/alerts
Content-Type: application/json

{
  "pregnant_id": "孕妇ID",
  "level": "RED|ORANGE|YELLOW",
  "message": "预警消息",
  "trigger_source": "MANUAL|RULE_ENGINE|FGR_ALGORITHM",
  "rule_id": "规则ID（可选）",
  "details": {} // 触发详情（可选）
}

Response:
{
  "id": "预警ID",
  "pregnant_id": "孕妇ID",
  "patient_name": "孕妇姓名",
  "level": "预警级别",
  "message": "预警消息",
  "status": "PENDING",
  "created_at": "创建时间",
  "gestational_age_days": 200
}
```

#### 4.1.4 修改护士AI分析逻辑

**文件位置**: `backend/app/routers/nurse_ai.py`

**修改点**:

1. 在 `nurse_analyze` 函数中，当检测到高风险时创建预警
2. 调用 WebSocket Manager 推送预警
3. 保持现有AI分析逻辑不变

### 4.2 前端实现

#### 4.2.1 WebSocket 客户端管理器

**文件位置**: `frontend/src/utils/websocket.ts`

**类设计**:

```typescript
class WebSocketClient {
  // 属性
  private ws: WebSocket | null
  private doctorId: string
  private reconnectAttempts: number
  private maxReconnectAttempts: number
  private reconnectInterval: number
  private alertCallbacks: AlertCallback[]
  private heartbeatInterval: NodeJS.Timeout | null
  
  // 方法
  connect(): void
  disconnect(): void
  onAlert(callback: AlertCallback): void
  offAlert(callback: AlertCallback): void
  getConnectionState(): string
}
```

**关键实现细节**:

1. **单例模式**: 全局只创建一个WebSocket客户端实例
2. **自动重连**: 断线后自动尝试重连，最多5次
3. **心跳机制**: 每30秒发送心跳保持连接
4. **回调机制**: 支持注册多个预警回调函数
5. **状态管理**: 提供连接状态查询方法

#### 4.2.2 医生工作台修改

**文件位置**: `frontend/src/views/doctor/DoctorDashboard.vue`

**新增功能**:

1. **WebSocket连接状态指示器**
   - 显示"实时连接"（绿色）或"连接断开"（红色）
   - 位置：页面标题栏右侧

2. **新预警通知横幅**
   - 当收到新预警时，在页面顶部显示横幅
   - 显示患者姓名和预警摘要
   - 提供"立即处理"按钮跳转到审核页面

3. **新预警高亮显示**
   - 新预警在列表中高亮显示（动画效果）
   - 高亮持续2秒后消失

4. **通知提示**
   - 收到新预警时弹出Element Plus通知
   - 显示患者姓名和预警摘要
   - 5秒后自动关闭

**UI组件修改**:

```vue
<!-- 页面标题栏 -->
<div class="page-header">
  <h1 class="page-title">医生工作台</h1>
  <div class="page-header__actions">
    <el-tag :type="wsConnected ? 'success' : 'danger'" size="small">
      {{ wsConnected ? '实时连接' : '连接断开' }}
    </el-tag>
    <el-button @click="loadAllData">刷新数据</el-button>
  </div>
</div>

<!-- 新预警通知横幅 -->
<el-alert
  v-if="newAlert"
  :title="`新预警: ${newAlert.patient_name}`"
  :description="newAlert.message"
  :type="getAlertType(newAlert.level)"
  show-icon
>
  <el-button @click="goToReview(newAlert)">立即处理</el-button>
</el-alert>
```

#### 4.2.3 异常审核工作台修改

**文件位置**: `frontend/src/views/doctor/ReviewWorkbench.vue`

**新增功能**:

1. **WebSocket连接状态指示器**
   - 同医生工作台

2. **新预警通知横幅**
   - 当有待处理的新预警时显示
   - 显示新预警数量
   - 提供"查看新预警"按钮

3. **新预警标记**
   - 新预警在列表项左侧显示橙色边框
   - 列表项右上角显示"新"标记
   - 背景色变为浅橙色

4. **自动选中新预警**
   - 点击"查看新预警"按钮后自动选中第一条新预警

**UI组件修改**:

```vue
<!-- 新预警通知 -->
<el-alert
  v-if="pendingNewAlerts.length > 0"
  :title="`收到 ${pendingNewAlerts.length} 条新预警`"
  type="warning"
  show-icon
>
  <el-button @click="handleNewAlerts">查看新预警</el-button>
</el-alert>

<!-- 预警列表项 -->
<div
  class="alert-list-item"
  :class="{ 'alert-list-item--new': isNewAlert(alert.id) }"
>
  <div class="new-alert-badge" v-if="isNewAlert(alert.id)">新</div>
  <!-- ... 其他内容 ... -->
</div>
```

### 4.3 数据库设计

**无需修改数据库结构**

现有 `alerts` 表已包含所有必要字段：

```sql
CREATE TABLE alerts (
  id UUID PRIMARY KEY,
  pregnant_id VARCHAR(64) NOT NULL,
  trigger_source VARCHAR(32),
  rule_id VARCHAR(32),
  level VARCHAR(16),
  message TEXT NOT NULL,
  details JSON,
  status VARCHAR(16) DEFAULT 'PENDING',
  reviewed_by VARCHAR(64),
  reviewed_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (pregnant_id) REFERENCES pregnant(pregnant_id)
);
```

---

## 5. 实现计划

### 5.1 阶段一：后端WebSocket基础设施

**任务列表**:

1. 创建 `backend/app/core/websocket_manager.py`
   - 实现 WebSocketManager 类
   - 实现连接管理、断线处理、广播功能

2. 创建 `backend/app/routers/websocket.py`
   - 实现 WebSocket 端点
   - 处理连接、断开、心跳

3. 修改 `backend/app/main.py`
   - 注册 WebSocket 路由

**预计工时**: 2小时

### 5.2 阶段二：修改预警创建逻辑

**任务列表**:

1. 修改 `backend/app/routers/alerts.py`
   - 新增创建预警端点
   - 集成 WebSocket 推送

2. 修改 `backend/app/routers/nurse_ai.py`
   - 修改护士AI分析逻辑
   - 高风险时创建并推送预警

**预计工时**: 1.5小时

### 5.3 阶段三：前端WebSocket客户端

**任务列表**:

1. 创建 `frontend/src/utils/websocket.ts`
   - 实现 WebSocketClient 类
   - 实现连接管理、重连、心跳

**预计工时**: 1.5小时

### 5.4 阶段四：修改医生工作台

**任务列表**:

1. 修改 `frontend/src/views/doctor/DoctorDashboard.vue`
   - 添加WebSocket连接状态指示器
   - 添加新预警通知横幅
   - 实现新预警高亮显示
   - 实现通知提示功能

**预计工时**: 2小时

### 5.5 阶段五：修改异常审核工作台

**任务列表**:

1. 修改 `frontend/src/views/doctor/ReviewWorkbench.vue`
   - 添加WebSocket连接状态指示器
   - 添加新预警通知横幅
   - 实现新预警标记
   - 实现自动选中新预警

**预计工时**: 2小时

### 5.6 阶段六：测试和优化

**任务列表**:

1. 单元测试
   - WebSocket Manager 测试
   - WebSocket Client 测试

2. 集成测试
   - 预警创建和推送流程测试
   - 断线重连测试

3. 性能优化
   - 连接池管理
   - 消息压缩

**预计工时**: 2小时

**总计预计工时**: 11小时

---

## 6. 测试策略

### 6.1 单元测试

#### 6.1.1 WebSocket Manager 测试

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.app.core.websocket_manager import WebSocketManager

@pytest.fixture
def ws_manager():
    return WebSocketManager()

@pytest.mark.asyncio
async def test_connect(ws_manager):
    """测试连接注册"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    assert ws_manager.get_active_connections_count() == 1

@pytest.mark.asyncio
async def test_disconnect(ws_manager):
    """测试断开连接"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    ws_manager.disconnect("doctor-1")
    assert ws_manager.get_active_connections_count() == 0

@pytest.mark.asyncio
async def test_broadcast_alert(ws_manager):
    """测试广播预警"""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    await ws_manager.connect(websocket1, "doctor-1")
    await ws_manager.connect(websocket2, "doctor-2")
    
    alert_data = {"id": "alert-1", "message": "测试预警"}
    await ws_manager.broadcast_alert(alert_data)
    
    websocket1.send_json.assert_called_once()
    websocket2.send_json.assert_called_once()
```

#### 6.1.2 WebSocket Client 测试

```typescript
import { describe, it, expect, vi } from 'vitest';
import WebSocketClient from '../websocket';

describe('WebSocketClient', () => {
  it('should create instance', () => {
    const client = new WebSocketClient('doctor-1');
    expect(client).toBeDefined();
  });
  
  it('should register alert callback', () => {
    const client = new WebSocketClient('doctor-1');
    const callback = vi.fn();
    client.onAlert(callback);
    // 验证回调已注册
  });
});
```

### 6.2 集成测试

#### 6.2.1 预警创建和推送流程

```python
import pytest
from httpx import AsyncClient
from backend.app.main import app

@pytest.mark.asyncio
async def test_alert_creation_with_push():
    """测试预警创建和WebSocket推送"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. 创建预警
        response = await client.post("/api/v1/alerts", json={
            "pregnant_id": "test-pregnant-1",
            "level": "RED",
            "message": "测试预警"
        })
        assert response.status_code == 200
        
        # 2. 验证预警已保存
        alert_id = response.json()["id"]
        response = await client.get(f"/api/v1/alerts/{alert_id}")
        assert response.status_code == 200
```

### 6.3 端到端测试

```typescript
describe('E2E: Alert Real-time Push', () => {
  it('should receive new alert in doctor dashboard', async () => {
    // 1. 打开医生工作台
    // 2. 建立WebSocket连接
    // 3. 在护士端创建预警
    // 4. 验证医生端收到通知
    // 5. 验证预警列表更新
  });
});
```

---

## 7. 风险和缓解措施

### 7.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| WebSocket连接不稳定 | 医生端无法收到推送 | 中 | 实现自动重连机制，最多重试5次 |
| 并发连接数过多 | 服务器资源耗尽 | 低 | 当前单医生账号，无此风险 |
| 消息丢失 | 预警推送丢失 | 低 | 结合数据库持久化，支持手动刷新 |
| 浏览器兼容性 | 部分浏览器不支持WebSocket | 低 | 使用标准WebSocket API，兼容性好 |

### 7.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 医生端未在线 | 无法实时接收预警 | 中 | 保留手动刷新功能作为兜底 |
| 预警过于频繁 | 影响医生工作 | 低 | 当前单医生账号，预警频率可控 |

### 7.3 缓解措施总结

1. **断线重连**: 自动重连机制，最大重试5次
2. **心跳保活**: 每30秒发送心跳，保持连接活跃
3. **兜底方案**: 保留手动刷新功能
4. **日志记录**: 记录连接和推送日志，便于排查问题
5. **状态显示**: 前端显示连接状态，便于用户了解

---

## 8. 附录

### 8.1 参考文档

- [FastAPI WebSocket文档](https://fastapi.tiangolo.com/advanced/websockets/)
- [Element Plus通知组件](https://element-plus.org/zh-CN/component/notification.html)
- [MDN WebSocket API](https://developer.mozilla.org/zh-CN/docs/Web/API/WebSocket)

### 8.2 术语表

| 术语 | 说明 |
|------|------|
| WebSocket | 全双工通信协议，支持服务器主动推送 |
| 心跳 | 定期发送的消息，用于保持连接活跃 |
| 断线重连 | 连接断开后自动重新建立连接 |
| 广播 | 向所有连接的客户端发送消息 |

### 8.3 变更记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-05-14 | AI Assistant | 初始版本 |
