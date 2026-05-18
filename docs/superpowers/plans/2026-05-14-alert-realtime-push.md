# 预警实时推送给医生端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现预警的实时推送功能，当护士创建预警后，立即通过 WebSocket 推送到医生端

**Architecture:** 使用 FastAPI 原生 WebSocket 支持，实现后端 WebSocket Manager 管理连接，前端 WebSocket Client 接收推送并更新 UI

**Tech Stack:** FastAPI, WebSocket, Vue 3, TypeScript, Element Plus

---

## File Structure

### 后端文件

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/core/websocket_manager.py` | 创建 | WebSocket 连接管理器，管理医生端连接和广播 |
| `backend/app/routers/websocket.py` | 创建 | WebSocket 端点，处理连接、断开、心跳 |
| `backend/app/routers/alerts.py` | 修改 | 集成 WebSocket 推送到预警创建流程 |
| `backend/app/routers/nurse_ai.py` | 修改 | 护士 AI 分析高风险时创建并推送预警 |
| `backend/app/main.py` | 修改 | 注册 WebSocket 路由 |
| `backend/tests/test_websocket_manager.py` | 创建 | WebSocket Manager 单元测试 |

### 前端文件

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/src/utils/websocket.ts` | 创建 | WebSocket 客户端管理器 |
| `frontend/src/views/doctor/DoctorDashboard.vue` | 修改 | 添加实时预警通知和高亮 |
| `frontend/src/views/doctor/ReviewWorkbench.vue` | 修改 | 添加实时预警通知和标记 |
| `frontend/src/utils/__tests__/websocket.test.ts` | 创建 | WebSocket Client 单元测试 |

---

## Task 1: 创建 WebSocket Manager（后端）

**Files:**
- Create: `backend/app/core/websocket_manager.py`
- Test: `backend/tests/test_websocket_manager.py`

- [ ] **Step 1: 创建 WebSocket Manager 测试文件**

```python
# backend/tests/test_websocket_manager.py
"""WebSocket Manager 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.websocket_manager import WebSocketManager


@pytest.fixture
def ws_manager():
    """创建 WebSocket Manager 实例"""
    return WebSocketManager()


@pytest.mark.asyncio
async def test_connect(ws_manager):
    """测试连接注册"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    assert ws_manager.get_active_connections_count() == 1
    assert "doctor-1" in ws_manager.active_connections


@pytest.mark.asyncio
async def test_disconnect(ws_manager):
    """测试断开连接"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    ws_manager.disconnect("doctor-1")
    assert ws_manager.get_active_connections_count() == 0
    assert "doctor-1" not in ws_manager.active_connections


@pytest.mark.asyncio
async def test_disconnect_nonexistent(ws_manager):
    """测试断开不存在的连接"""
    # 不应该抛出异常
    ws_manager.disconnect("nonexistent")
    assert ws_manager.get_active_connections_count() == 0


@pytest.mark.asyncio
async def test_send_alert_to_doctor_success(ws_manager):
    """测试发送预警给指定医生成功"""
    websocket = AsyncMock()
    await ws_manager.connect(websocket, "doctor-1")
    
    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("doctor-1", alert_data)
    
    assert result is True
    websocket.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })


@pytest.mark.asyncio
async def test_send_alert_to_doctor_not_found(ws_manager):
    """测试发送预警给不存在的医生"""
    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("nonexistent", alert_data)
    
    assert result is False


@pytest.mark.asyncio
async def test_send_alert_to_doctor_failure(ws_manager):
    """测试发送预警失败时清理连接"""
    websocket = AsyncMock()
    websocket.send_json.side_effect = Exception("Connection closed")
    await ws_manager.connect(websocket, "doctor-1")
    
    alert_data = {"id": "alert-1", "message": "测试预警"}
    result = await ws_manager.send_alert_to_doctor("doctor-1", alert_data)
    
    assert result is False
    assert ws_manager.get_active_connections_count() == 0


@pytest.mark.asyncio
async def test_broadcast_alert(ws_manager):
    """测试广播预警给所有连接的医生"""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    await ws_manager.connect(websocket1, "doctor-1")
    await ws_manager.connect(websocket2, "doctor-2")
    
    alert_data = {"id": "alert-1", "message": "测试预警"}
    await ws_manager.broadcast_alert(alert_data)
    
    websocket1.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })
    websocket2.send_json.assert_called_once_with({
        "type": "NEW_ALERT",
        "data": alert_data
    })


@pytest.mark.asyncio
async def test_broadcast_alert_with_failure(ws_manager):
    """测试广播时部分连接失败"""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    websocket2.send_json.side_effect = Exception("Connection closed")
    await ws_manager.connect(websocket1, "doctor-1")
    await ws_manager.connect(websocket2, "doctor-2")
    
    alert_data = {"id": "alert-1", "message": "测试预警"}
    await ws_manager.broadcast_alert(alert_data)
    
    # doctor-1 应该收到
    websocket1.send_json.assert_called_once()
    # doctor-2 应该被清理
    assert ws_manager.get_active_connections_count() == 1
    assert "doctor-2" not in ws_manager.active_connections


@pytest.mark.asyncio
async def test_get_active_connections_count(ws_manager):
    """测试获取活跃连接数"""
    assert ws_manager.get_active_connections_count() == 0
    
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    await ws_manager.connect(websocket1, "doctor-1")
    assert ws_manager.get_active_connections_count() == 1
    
    await ws_manager.connect(websocket2, "doctor-2")
    assert ws_manager.get_active_connections_count() == 2
    
    ws_manager.disconnect("doctor-1")
    assert ws_manager.get_active_connections_count() == 1
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend && python -m pytest tests/test_websocket_manager.py -v
```

预期输出：FAIL - ModuleNotFoundError: No module named 'app.core.websocket_manager'

- [ ] **Step 3: 创建 WebSocket Manager 实现**

```python
# backend/app/core/websocket_manager.py
"""WebSocket 连接管理器"""
from fastapi import WebSocket
from typing import Dict
from loguru import logger


class WebSocketManager:
    """管理医生端的 WebSocket 连接"""
    
    def __init__(self):
        # 存储活跃的连接: {doctor_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, doctor_id: str):
        """接受新的 WebSocket 连接"""
        await websocket.accept()
        self.active_connections[doctor_id] = websocket
        logger.info(f"医生 {doctor_id} 已连接 WebSocket")
    
    def disconnect(self, doctor_id: str):
        """断开 WebSocket 连接"""
        if doctor_id in self.active_connections:
            del self.active_connections[doctor_id]
            logger.info(f"医生 {doctor_id} 已断开 WebSocket")
    
    async def send_alert_to_doctor(self, doctor_id: str, alert_data: dict) -> bool:
        """发送预警给指定医生
        
        Args:
            doctor_id: 医生ID
            alert_data: 预警数据
            
        Returns:
            bool: 发送成功返回 True，失败返回 False
        """
        if doctor_id not in self.active_connections:
            logger.warning(f"医生 {doctor_id} 未连接，无法发送预警")
            return False
        
        websocket = self.active_connections[doctor_id]
        try:
            await websocket.send_json({
                "type": "NEW_ALERT",
                "data": alert_data
            })
            logger.info(f"已发送预警给医生 {doctor_id}")
            return True
        except Exception as e:
            logger.error(f"发送预警给医生 {doctor_id} 失败: {e}")
            # 清理断开的连接
            self.disconnect(doctor_id)
            return False
    
    async def broadcast_alert(self, alert_data: dict):
        """广播预警给所有连接的医生
        
        Args:
            alert_data: 预警数据
        """
        if not self.active_connections:
            logger.info("没有医生在线，跳过广播")
            return
        
        disconnected = []
        for doctor_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json({
                    "type": "NEW_ALERT",
                    "data": alert_data
                })
                logger.info(f"已广播预警给医生 {doctor_id}")
            except Exception as e:
                logger.error(f"广播预警给医生 {doctor_id} 失败: {e}")
                disconnected.append(doctor_id)
        
        # 清理断开的连接
        for doctor_id in disconnected:
            self.disconnect(doctor_id)
        
        logger.info(f"预警广播完成，成功发送给 {len(self.active_connections)} 位医生")
    
    def get_active_connections_count(self) -> int:
        """获取活跃连接数"""
        return len(self.active_connections)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend && python -m pytest tests/test_websocket_manager.py -v
```

预期输出：PASS - 所有测试通过

- [ ] **Step 5: 提交代码**

```bash
git add backend/app/core/websocket_manager.py backend/tests/test_websocket_manager.py
git commit -m "feat: add WebSocket Manager for alert push"
```

---

## Task 2: 创建 WebSocket 端点（后端）

**Files:**
- Create: `backend/app/routers/websocket.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 WebSocket 端点**

```python
# backend/app/routers/websocket.py
"""WebSocket API 端点"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.websocket_manager import ws_manager
from loguru import logger

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/alerts/{doctor_id}")
async def websocket_alerts(websocket: WebSocket, doctor_id: str):
    """
    医生端 WebSocket 连接端点
    
    用于接收实时预警推送
    
    Args:
        websocket: WebSocket 连接
        doctor_id: 医生ID
    """
    await ws_manager.connect(websocket, doctor_id)
    try:
        while True:
            # 保持连接活跃，接收客户端消息
            data = await websocket.receive_text()
            
            # 处理心跳消息
            if data == "ping":
                await websocket.send_text("pong")
                logger.debug(f"收到来自医生 {doctor_id} 的心跳")
            
            # 可以处理其他客户端消息
            # 例如：确认收到预警、标记已读等
            
    except WebSocketDisconnect:
        logger.info(f"医生 {doctor_id} 主动断开 WebSocket 连接")
        ws_manager.disconnect(doctor_id)
    except Exception as e:
        logger.error(f"医生 {doctor_id} WebSocket 连接异常: {e}")
        ws_manager.disconnect(doctor_id)
```

- [ ] **Step 2: 修改 main.py 注册 WebSocket 路由**

```python
# backend/app/main.py (修改部分)
from .routers import chat, schedule, followup, alerts, fgr, orders, dashboard
from .routers import pregnant, recommend, nurse_ai, doctor_ai, auth, fetal_movement, feedback, mental_health, health_trends
from .routers import websocket  # 新增导入

# ... 其他代码 ...

# 注册路由
app.include_router(chat.router)
app.include_router(schedule.router)
app.include_router(followup.router)
app.include_router(alerts.router)
app.include_router(fgr.router)
app.include_router(orders.router)
app.include_router(dashboard.router)
app.include_router(pregnant.router)
app.include_router(recommend.router)
app.include_router(nurse_ai.router)
app.include_router(doctor_ai.router)
app.include_router(auth.router)
app.include_router(fetal_movement.router)
app.include_router(feedback.router)
app.include_router(mental_health.router)
app.include_router(health_trends.router)
app.include_router(websocket.router)  # 新增 WebSocket 路由
```

- [ ] **Step 3: 验证后端启动**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

预期输出：应用启动成功，无报错

- [ ] **Step 4: 提交代码**

```bash
git add backend/app/routers/websocket.py backend/app/main.py
git commit -m "feat: add WebSocket endpoint for alert push"
```

---

## Task 3: 修改预警创建逻辑（后端）

**Files:**
- Modify: `backend/app/routers/alerts.py`

- [ ] **Step 1: 创建预警请求模型**

```python
# backend/app/routers/alerts.py (新增部分)
from pydantic import BaseModel
from typing import Optional


class CreateAlertRequest(BaseModel):
    """创建预警请求"""
    pregnant_id: str
    level: str  # RED, ORANGE, YELLOW
    message: str
    trigger_source: str = "MANUAL"  # MANUAL, RULE_ENGINE, FGR_ALGORITHM
    rule_id: Optional[str] = None
    details: Optional[dict] = None
```

- [ ] **Step 2: 添加创建预警端点**

```python
# backend/app/routers/alerts.py (新增端点)
from ..core.websocket_manager import ws_manager


@router.post("", response_model=AlertResponse)
async def create_alert(
    req: CreateAlertRequest,
    db: Session = Depends(get_db)
):
    """
    创建预警记录并推送给医生端
    
    护士确认后调用此接口创建预警
    """
    # 1. 创建预警记录
    alert = Alert(
        pregnant_id=req.pregnant_id,
        trigger_source=req.trigger_source,
        rule_id=req.rule_id,
        level=req.level,
        message=req.message,
        details=req.details or {},
        status="PENDING",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    # 2. 获取孕妇信息
    pregnant = db.query(Pregnant).filter(
        Pregnant.pregnant_id == req.pregnant_id
    ).first()
    
    # 3. 构建推送数据
    alert_data = {
        "id": str(alert.id),
        "pregnant_id": req.pregnant_id,
        "patient_name": pregnant.display_name if pregnant else "未知",
        "level": req.level,
        "message": req.message,
        "trigger_source": req.trigger_source,
        "status": alert.status,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "gestational_age_days": pregnant.gestational_age_days if pregnant else None,
    }
    
    # 4. 实时推送给医生端
    await ws_manager.broadcast_alert(alert_data)
    
    # 5. 返回预警响应
    return AlertResponse(
        **{c.name: getattr(alert, c.name) for c in alert.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
        gestational_age_days=pregnant.gestational_age_days if pregnant else None,
    )
```

- [ ] **Step 3: 验证 API 可用**

```bash
# 启动后端
cd backend && python -m uvicorn app.main:app --reload --port 8000

# 测试创建预警
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"pregnant_id": "test-1", "level": "RED", "message": "测试预警"}'
```

预期输出：返回创建的预警 JSON

- [ ] **Step 4: 提交代码**

```bash
git add backend/app/routers/alerts.py
git commit -m "feat: integrate WebSocket push to alert creation"
```

---

## Task 4: 修改护士 AI 分析逻辑（后端）

**Files:**
- Modify: `backend/app/routers/nurse_ai.py`

- [ ] **Step 1: 导入 WebSocket Manager**

```python
# backend/app/routers/nurse_ai.py (新增导入)
from ..core.websocket_manager import ws_manager
```

- [ ] **Step 2: 修改 nurse_analyze 函数**

```python
# backend/app/routers/nurse_ai.py (修改 nurse_analyze 函数)
async def nurse_analyze(req: NurseAnalyzeRequest):
    """AI分析孕妇数据，返回护理建议"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7
        risk_tags = pregnant.risk_tags or []

        # 收集孕妇数据
        patient_data = _collect_patient_data_for_nurse(db, req.pregnant_id, gest_week, gest_day)

        # 尝试LLM分析
        llm_result = await _try_llm_nurse_analyze(pregnant, gest_week, gest_day, risk_tags, patient_data)
        if llm_result:
            result = llm_result
        else:
            # 模板兜底
            result = _fallback_nurse_analyze(pregnant, gest_week, gest_day, risk_tags, patient_data)

        # 分析完成后自动创建预警（如果检测到高风险）
        if "高风险" in (result.risk_assessment or "") or "异常" in (result.risk_assessment or ""):
            # 创建预警记录
            alert = Alert(
                pregnant_id=req.pregnant_id,
                trigger_source="MANUAL",
                level="ORANGE",
                message=f"护士AI分析提示：{result.risk_assessment[:100]}",
                status="PENDING",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            
            # 构建推送数据
            alert_data = {
                "id": str(alert.id),
                "pregnant_id": req.pregnant_id,
                "patient_name": pregnant.display_name,
                "level": "ORANGE",
                "message": f"护士AI分析提示：{result.risk_assessment[:100]}",
                "trigger_source": "MANUAL",
                "status": alert.status,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "gestational_age_days": pregnant.gestational_age_days,
            }
            
            # 推送给医生端
            await ws_manager.broadcast_alert(alert_data)

        # 生成随访排期推荐
        schedule_result = tool_recommend_followup_schedule(db, req.pregnant_id)
        if "error" not in schedule_result:
            result.followup_schedule = FollowupScheduleResponse(**schedule_result)

        return result
    finally:
        db.close()
```

- [ ] **Step 3: 验证修改**

```bash
# 运行后端测试
cd backend && python -m pytest tests/ -v -k "nurse"
```

预期输出：测试通过

- [ ] **Step 4: 提交代码**

```bash
git add backend/app/routers/nurse_ai.py
git commit -m "feat: push alert when nurse AI detects high risk"
```

---

## Task 5: 创建 WebSocket 客户端（前端）

**Files:**
- Create: `frontend/src/utils/websocket.ts`
- Test: `frontend/src/utils/__tests__/websocket.test.ts`

- [ ] **Step 1: 创建 WebSocket 客户端测试**

```typescript
// frontend/src/utils/__tests__/websocket.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import WebSocketClient, { getWebSocketClient } from '../websocket';

describe('WebSocketClient', () => {
  let client: WebSocketClient;
  
  beforeEach(() => {
    client = new WebSocketClient('doctor-1');
  });
  
  afterEach(() => {
    client.disconnect();
  });
  
  it('should create instance', () => {
    expect(client).toBeDefined();
  });
  
  it('should register and call alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);
    
    // 模拟触发回调
    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));
    
    expect(callback).toHaveBeenCalledWith({ id: 'alert-1' });
  });
  
  it('should remove alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);
    client.offAlert(callback);
    
    // 模拟触发回调
    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));
    
    expect(callback).not.toHaveBeenCalled();
  });
  
  it('should return connection state', () => {
    expect(client.getConnectionState()).toBe('CLOSED');
  });
});

describe('getWebSocketClient', () => {
  it('should return singleton instance', () => {
    const client1 = getWebSocketClient('doctor-1');
    const client2 = getWebSocketClient('doctor-1');
    expect(client1).toBe(client2);
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd frontend && npm test -- websocket.test.ts
```

预期输出：FAIL - Cannot find module '../websocket'

- [ ] **Step 3: 创建 WebSocket 客户端实现**

```typescript
// frontend/src/utils/websocket.ts
/**
 * WebSocket 客户端管理器
 * 用于接收实时预警推送
 */

type AlertCallback = (alert: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private doctorId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000; // 3秒
  private alertCallbacks: AlertCallback[] = [];
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;

  constructor(doctorId: string) {
    this.doctorId = doctorId;
  }

  /**
   * 连接 WebSocket
   */
  connect(): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts/${this.doctorId}`;
    
    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket 连接成功');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'NEW_ALERT') {
            // 触发所有注册的回调
            this.alertCallbacks.forEach(callback => callback(data.data));
          }
        } catch (error) {
          console.error('解析 WebSocket 消息失败:', error);
        }
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket 连接关闭:', event.code, event.reason);
        this.stopHeartbeat();
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
      };
    } catch (error) {
      console.error('创建 WebSocket 连接失败:', error);
      this.attemptReconnect();
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * 尝试重连
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      
      setTimeout(() => {
        this.connect();
      }, this.reconnectInterval);
    } else {
      console.error('达到最大重连次数，停止重连');
    }
  }

  /**
   * 开始心跳
   */
  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000); // 每30秒发送心跳
  }

  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * 注册预警回调
   */
  onAlert(callback: AlertCallback): void {
    this.alertCallbacks.push(callback);
  }

  /**
   * 移除预警回调
   */
  offAlert(callback: AlertCallback): void {
    this.alertCallbacks = this.alertCallbacks.filter(cb => cb !== callback);
  }

  /**
   * 获取连接状态
   */
  getConnectionState(): string {
    if (!this.ws) return 'CLOSED';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'OPEN';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'CLOSED';
      default:
        return 'UNKNOWN';
    }
  }
}

// 创建单例实例
let wsClient: WebSocketClient | null = null;

/**
 * 获取 WebSocket 客户端实例
 */
export function getWebSocketClient(doctorId: string): WebSocketClient {
  if (!wsClient) {
    wsClient = new WebSocketClient(doctorId);
  }
  return wsClient;
}

export default WebSocketClient;
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd frontend && npm test -- websocket.test.ts
```

预期输出：PASS - 所有测试通过

- [ ] **Step 5: 提交代码**

```bash
git add frontend/src/utils/websocket.ts frontend/src/utils/__tests__/websocket.test.ts
git commit -m "feat: add WebSocket client for alert push"
```

---

## Task 6: 修改医生工作台（前端）

**Files:**
- Modify: `frontend/src/views/doctor/DoctorDashboard.vue`

- [ ] **Step 1: 添加 WebSocket 连接状态和新预警状态**

```vue
<!-- frontend/src/views/doctor/DoctorDashboard.vue (script 部分新增) -->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Bell, Document, MagicStick, Guide, FirstAidKit } from '@element-plus/icons-vue'
import { dashboardApi, alertApi, orderApi, doctorAiApi } from '@/api/endpoints'
import { getWebSocketClient } from '@/utils/websocket'
import type { Pregnant } from '@/types'
import type { Alert, MedicalOrder, DashboardStats } from '@/types'
import StatCard from '@/components/common/StatCard.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import AgentAvatar from '@/components/common/AgentAvatar.vue'
import { ElNotification } from 'element-plus'

const router = useRouter()
const loading = ref(false)
const stats = ref<DashboardStats>({
  total_pregnant: 0,
  pending_alerts: 0,
  today_followups: 0,
  pending_reviews: 0,
  high_risk_count: 0,
  weekly_new_pregnant: 0,
})
const recentAlerts = ref<Alert[]>([])
const pendingOrders = ref<MedicalOrder[]>([])

// WebSocket 相关状态
const wsConnected = ref(false)
const newAlert = ref<Alert | null>(null)
const newAlertIds = ref<Set<string>>(new Set())
const wsClient = ref<ReturnType<typeof getWebSocketClient> | null>(null)

// ... 其他代码 ...

/**
 * 初始化 WebSocket
 */
function initWebSocket() {
  const doctorId = 'current-doctor' // 当前医生ID
  wsClient.value = getWebSocketClient(doctorId)
  
  // 注册预警回调
  wsClient.value.onAlert((alert: Alert) => {
    console.log('收到新预警:', alert)
    
    // 更新状态
    newAlert.value = alert
    newAlertIds.value.add(alert.id)
    
    // 添加到列表顶部
    recentAlerts.value.unshift(alert)
    
    // 更新统计
    stats.value.pending_alerts++
    if (alert.level === 'RED' || alert.level === 'ORANGE') {
      stats.value.high_risk_count++
    }
    
    // 显示通知
    ElNotification({
      title: '新预警通知',
      message: `${alert.patient_name}: ${alert.message}`,
      type: getAlertType(alert.level),
      duration: 5000,
    })
  })
  
  // 连接 WebSocket
  wsClient.value.connect()
  
  // 监听连接状态
  checkConnectionState()
}

/**
 * 检查连接状态
 */
function checkConnectionState() {
  if (wsClient.value) {
    const state = wsClient.value.getConnectionState()
    wsConnected.value = state === 'OPEN'
  }
}

/**
 * 判断是否是新预警
 */
function isNewAlert(alertId: string): boolean {
  return newAlertIds.value.has(alertId)
}

/**
 * 获取预警类型
 */
function getAlertType(level: string): 'success' | 'warning' | 'info' | 'error' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'error'> = {
    RED: 'error',
    ORANGE: 'warning',
    YELLOW: 'info',
  }
  return map[level] || 'info'
}

/**
 * 跳转到审核页面
 */
function goToReview(alert: Alert) {
  router.push(`/doctor/review/${alert.id}`)
}

onMounted(() => {
  loadAllData()
  initWebSocket()
})

onUnmounted(() => {
  // 清理 WebSocket 连接
  if (wsClient.value) {
    wsClient.value.disconnect()
  }
})
</script>
```

- [ ] **Step 2: 添加 WebSocket 连接状态指示器**

```vue
<!-- frontend/src/views/doctor/DoctorDashboard.vue (template 部分修改) -->
<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">医生工作台</h1>
      <div class="page-header__actions">
        <!-- WebSocket 连接状态指示器 -->
        <el-tag 
          :type="wsConnected ? 'success' : 'danger'" 
          size="small"
          effect="plain"
        >
          {{ wsConnected ? '实时连接' : '连接断开' }}
        </el-tag>
        <el-button type="primary" :icon="Refresh" @click="loadAllData" :loading="loading">
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 新预警通知横幅 -->
    <el-alert
      v-if="newAlert"
      :title="`新预警: ${newAlert.patient_name}`"
      :description="newAlert.message"
      :type="getAlertType(newAlert.level)"
      show-icon
      :closable="true"
      @close="newAlert = null"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>{{ newAlert.message }}</span>
          <el-button type="primary" size="small" @click="goToReview(newAlert)">
            立即处理
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-grid-row">
      <!-- ... 原有代码 ... -->
    </el-row>

    <!-- 主要内容区域 -->
    <el-row :gutter="16">
      <!-- 高危预警概览 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="content-card__header">
            <span class="content-card__title">高危预警概览</span>
            <el-tag v-if="alertStats.highCount" type="danger" size="small">
              待处理 {{ alertStats.highCount }} 条
            </el-tag>
          </div>
          <div class="content-card__body" v-loading="loading">
            <el-table :data="recentAlerts" stripe style="width: 100%" size="small" @row-click="handleAlertClick">
              <!-- 新预警高亮显示 -->
              <el-table-column label="风险级别" width="100">
                <template #default="{ row }">
                  <div :class="{ 'new-alert-highlight': isNewAlert(row.id) }">
                    <RiskBadge :level="mapRiskLevel(row.level)" />
                  </div>
                </template>
              </el-table-column>
              <!-- ... 其他列 ... -->
            </el-table>
          </div>
        </div>
      </el-col>

      <!-- ... 其他内容 ... -->
    </el-row>

    <!-- ... 其他组件 ... -->
  </div>
</template>
```

- [ ] **Step 3: 添加新预警高亮样式**

```vue
<!-- frontend/src/views/doctor/DoctorDashboard.vue (style 部分新增) -->
<style scoped>
/* 新预警高亮样式 */
.new-alert-highlight {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ... 其他样式 ... */
</style>
```

- [ ] **Step 4: 验证修改**

```bash
# 启动前端开发服务器
cd frontend && npm run dev
```

预期输出：页面正常显示，WebSocket 连接状态指示器显示

- [ ] **Step 5: 提交代码**

```bash
git add frontend/src/views/doctor/DoctorDashboard.vue
git commit -m "feat: add real-time alert notification to doctor dashboard"
```

---

## Task 7: 修改异常审核工作台（前端）

**Files:**
- Modify: `frontend/src/views/doctor/ReviewWorkbench.vue`

- [ ] **Step 1: 添加 WebSocket 连接状态和新预警状态**

```vue
<!-- frontend/src/views/doctor/ReviewWorkbench.vue (script 部分新增) -->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Refresh, WarningFilled, Edit, FolderAdd,
  Select, ChatDotSquare, User, CircleCheck,
  MagicStick, Guide, FirstAidKit,
} from '@element-plus/icons-vue'
import { alertApi, orderApi, followUpApi, doctorAiApi } from '@/api/endpoints'
import { getWebSocketClient } from '@/utils/websocket'
import type { Alert, MedicalOrder, FollowUpRecord } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { ElNotification } from 'element-plus'

const route = useRoute()
const router = useRouter()

// 数据状态
const loading = ref(false)
const detailLoading = ref(false)
const pregnantInfoLoading = ref(false)
const submitting = ref(false)
const alertList = ref<Alert[]>([])
const selectedAlert = ref<Alert | null>(null)
const pregnantFollowUps = ref<FollowUpRecord[]>([])

// WebSocket 相关状态
const wsConnected = ref(false)
const pendingNewAlerts = ref<Alert[]>([])
const newAlertIds = ref<Set<string>>(new Set())
const wsClient = ref<ReturnType<typeof getWebSocketClient> | null>(null)

// ... 其他代码 ...

/**
 * 初始化 WebSocket
 */
function initWebSocket() {
  const doctorId = 'current-doctor'
  wsClient.value = getWebSocketClient(doctorId)
  
  // 注册预警回调
  wsClient.value.onAlert((alert: Alert) => {
    console.log('审核工作台收到新预警:', alert)
    
    // 添加到待处理列表
    pendingNewAlerts.value.push(alert)
    newAlertIds.value.add(alert.id)
    
    // 添加到预警列表顶部
    alertList.value.unshift(alert)
    
    // 显示通知
    ElNotification({
      title: '新预警通知',
      message: `${alert.patient_name}: ${alert.message}`,
      type: getAlertType(alert.level),
      duration: 5000,
    })
  })
  
  // 连接 WebSocket
  wsClient.value.connect()
  
  // 监听连接状态
  checkConnectionState()
}

/**
 * 检查连接状态
 */
function checkConnectionState() {
  if (wsClient.value) {
    const state = wsClient.value.getConnectionState()
    wsConnected.value = state === 'OPEN'
  }
}

/**
 * 判断是否是新预警
 */
function isNewAlert(alertId: string): boolean {
  return newAlertIds.value.has(alertId)
}

/**
 * 处理新预警
 */
function handleNewAlerts() {
  // 选中第一个新预警
  if (pendingNewAlerts.value.length > 0) {
    const firstNewAlert = pendingNewAlerts.value[0]
    selectAlert(firstNewAlert)
    
    // 清空待处理列表
    pendingNewAlerts.value = []
  }
}

/**
 * 获取预警类型
 */
function getAlertType(level: string): 'success' | 'warning' | 'info' | 'error' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'error'> = {
    RED: 'error',
    ORANGE: 'warning',
    YELLOW: 'info',
  }
  return map[level] || 'info'
}

onMounted(async () => {
  await loadAlerts()
  initWebSocket()
  
  // 根据路由参数选中预警
  const alertId = route.params.alertId as string
  if (alertId) {
    const found = alertList.value.find((a) => a.id === alertId)
    if (found) {
      await selectAlert(found)
    }
  }
})

onUnmounted(() => {
  // 清理 WebSocket 连接
  if (wsClient.value) {
    wsClient.value.disconnect()
  }
})
</script>
```

- [ ] **Step 2: 添加 WebSocket 连接状态指示器和新预警通知**

```vue
<!-- frontend/src/views/doctor/ReviewWorkbench.vue (template 部分修改) -->
<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">异常审核工作台</h1>
      <div class="page-header__actions">
        <!-- WebSocket 连接状态 -->
        <el-tag 
          :type="wsConnected ? 'success' : 'danger'" 
          size="small"
          effect="plain"
        >
          {{ wsConnected ? '实时连接' : '连接断开' }}
        </el-tag>
        
        <el-tag v-if="selectedAlert" type="danger" effect="plain" size="default">
          审核中: {{ selectedAlert.patient_name }}
        </el-tag>
        <el-button text type="primary" :icon="Refresh" @click="loadAlerts" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 新预警通知 -->
    <el-alert
      v-if="pendingNewAlerts.length > 0"
      :title="`收到 ${pendingNewAlerts.length} 条新预警`"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>有新的预警需要处理</span>
          <el-button type="primary" size="small" @click="handleNewAlerts">
            查看新预警
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 三栏布局 -->
    <el-row :gutter="16" style="height: calc(100vh - 180px)">
      <!-- 左侧：高危预警列表 -->
      <el-col :span="7" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">高危预警列表</span>
            <el-tag size="small">{{ alertList.length }}条</el-tag>
          </div>
          <div class="content-card__body" style="flex: 1; overflow-y: auto; padding: 0" v-loading="loading">
            <div
              v-for="alert in alertList"
              :key="alert.id"
              class="alert-list-item"
              :class="{ 
                'alert-list-item--active': selectedAlert?.id === alert.id,
                'alert-list-item--new': isNewAlert(alert.id)
              }"
              @click="selectAlert(alert)"
            >
              <div class="alert-list-item__header">
                <span class="alert-list-item__name">{{ alert.patient_name }}</span>
                <RiskBadge :level="mapRiskLevel(alert.level)" />
              </div>
              <p class="alert-list-item__msg">{{ alert.message }}</p>
              <div class="alert-list-item__meta">
                <span class="text-light">
                  {{ calcGestationalWeek(alert.gestational_age_days) }}周
                </span>
                <span class="text-light">{{ formatTime(alert.created_at) }}</span>
              </div>
              <!-- 新预警标记 -->
              <div v-if="isNewAlert(alert.id)" class="new-alert-badge">新</div>
            </div>
            <div v-if="!alertList.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><CircleCheck /></el-icon>
              <p>暂无待审核预警</p>
            </div>
          </div>
        </div>
      </el-col>

      <!-- ... 其他内容 ... -->
    </el-row>

    <!-- ... 其他组件 ... -->
  </div>
</template>
```

- [ ] **Step 3: 添加新预警样式**

```vue
<!-- frontend/src/views/doctor/ReviewWorkbench.vue (style 部分新增) -->
<style scoped>
/* 新预警样式 */
.alert-list-item--new {
  border-left: 3px solid var(--warning);
  background: var(--warning-light);
}

.new-alert-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--warning);
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ... 其他样式 ... */
</style>
```

- [ ] **Step 4: 验证修改**

```bash
# 启动前端开发服务器
cd frontend && npm run dev
```

预期输出：页面正常显示，新预警标记和通知正常工作

- [ ] **Step 5: 提交代码**

```bash
git add frontend/src/views/doctor/ReviewWorkbench.vue
git commit -m "feat: add real-time alert notification to review workbench"
```

---

## Task 8: 端到端测试

**Files:**
- Test: 手动测试

- [ ] **Step 1: 启动后端服务**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

预期输出：应用启动成功

- [ ] **Step 2: 启动前端服务**

```bash
cd frontend && npm run dev
```

预期输出：前端开发服务器启动成功

- [ ] **Step 3: 测试 WebSocket 连接**

1. 打开浏览器访问医生工作台
2. 检查 WebSocket 连接状态指示器显示"实时连接"
3. 打开浏览器开发者工具，查看 WebSocket 连接

预期结果：WebSocket 连接成功建立

- [ ] **Step 4: 测试预警推送**

1. 使用 curl 或 Postman 创建预警：

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"pregnant_id": "test-1", "level": "RED", "message": "测试预警推送"}'
```

2. 观察医生工作台是否收到通知
3. 检查预警列表是否更新

预期结果：医生工作台收到实时通知，预警列表显示新预警

- [ ] **Step 5: 测试断线重连**

1. 停止后端服务
2. 观察前端 WebSocket 连接状态变为"连接断开"
3. 重新启动后端服务
4. 观察前端是否自动重连

预期结果：前端自动重连成功，连接状态恢复为"实时连接"

- [ ] **Step 6: 提交最终代码**

```bash
git add .
git commit -m "feat: complete alert real-time push feature"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** 所有需求都已在任务中实现
  - FR-001: Task 3, Task 4
  - FR-002: Task 5, Task 6, Task 7
  - FR-003: Task 6, Task 7
  - FR-004: Task 6, Task 7
  - FR-005: Task 5
  - FR-006: Task 6, Task 7

- [x] **Placeholder scan:** 没有发现 TBD、TODO 等占位符

- [x] **Type consistency:** 类型、方法签名、属性名称在所有任务中保持一致
  - WebSocketManager: connect, disconnect, send_alert_to_doctor, broadcast_alert, get_active_connections_count
  - WebSocketClient: connect, disconnect, onAlert, offAlert, getConnectionState
  - Alert 数据结构: id, pregnant_id, patient_name, level, message, trigger_source, status, created_at, gestational_age_days

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-14-alert-realtime-push.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
