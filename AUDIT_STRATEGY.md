# 审计增强策略 — 工具调用追踪 + 用户反馈关联

## 问题背景

原有审计系统存在以下不足：
1. `tool_calls_json` 仅记录 `{name, success}`，无入参、耗时、错误详情
2. 用户反馈 (`Feedback`) 与审计日志 (`AgentAuditLog`) 完全隔离，无法追溯"哪次 AI 回复获得了差评"
3. 无工具调用次数统计、失败率分析
4. 仪表盘缺少工具维度和反馈维度

## 设计参考

| 成熟方案 | 借鉴点 |
|---------|--------|
| **LangFuse** | Run → Span 两级追踪；工具调用作为子 Span |
| **OpenTelemetry** | Trace → Span 树形结构；属性 (attributes) 脱敏 |
| **LangSmith** | Run-level feedback 关联；工具入参/出参记录 |

## 变更概览

### 1. 数据模型层

#### `AgentAuditLog` 新增字段
```python
tool_call_count = Column(Integer, default=0)      # 工具调用总次数
tool_error_count = Column(Integer, default=0)      # 工具调用失败次数
feedback_rating = Column(String(16))               # 冗余：thumbs_up/thumbs_down
feedback_comment = Column(Text)                    # 冗余：用户评论
```

#### 新增 `ToolCallDetail` 表（子表，1:N 关联）
```python
class ToolCallDetail(Base):
    __tablename__ = "tool_call_details"
    id              = Integer, PK
    audit_log_id    = Integer, Index  # → agent_audit_logs.id
    tool_name       = String(64)      # 工具名称
    tool_args_json  = JSON            # 入参（脱敏：长值截断至 200 字符）
    success         = Boolean         # 是否成功
    error_message   = Text            # 失败原因
    latency_ms      = Integer         # 单次耗时（预留，待 Agno 框架支持）
    result_preview  = String(200)     # 返回值预览
    call_order      = Integer         # 调用顺序（从 1 开始）
    created_at      = DateTime
```

#### `Feedback` 新增字段
```python
audit_log_id = Column(Integer, Index)  # → agent_audit_logs.id
```

### 2. 审计写入逻辑

三个 `_save_audit_log()` 函数（pregnant/nurse/doctor）统一增强：
- 从 `run_response.messages[].tool_calls[]` 提取完整工具调用链
- 解析工具入参（JSON 反序列化 + 脱敏截断）
- 检测工具返回值中的 `error` 关键字判断成功/失败
- 写入 `AgentAuditLog`（汇总）+ `ToolCallDetail`（明细）两张表
- 返回审计日志 ID，供反馈关联使用

### 3. 反馈关联

提交反馈时支持 `audit_log_id` 参数：
```
POST /api/v1/feedback
{
  "pregnant_id": "P001",
  "message_id": "msg-123",
  "rating": "thumbs_down",
  "audit_log_id": 42  // ← 新增：关联到具体 Agent 调用
}
```
系统自动反写 `AgentAuditLog.feedback_rating`，实现双向关联。

### 4. 新增管理端 API

| 端点 | 说明 |
|------|------|
| `GET /audit/tool-calls/stats` | 按工具名聚合：调用次数、成功率、平均耗时 |
| `GET /audit/tool-calls/errors` | 工具调用失败详情列表（分页） |
| `GET /audit/tool-calls/by-session/{id}` | 单会话完整工具调用链 |
| `GET /audit/feedback/summary` | 反馈覆盖度 + 按 variant 聚合满意度 |
| `GET /audit/sessions/{id}` | 增强：含 tool_call_count、feedback_rating |
| `GET /audit/dashboard` | 增强：含工具调用统计、反馈关联数 |

### 5. 启动迁移

`main.py` 新增幂等迁移：
- `_ensure_audit_log_table()`: 创建 `tool_call_details` 表 + 为 `agent_audit_logs` 添加新列
- `_ensure_feedback_audit_link()`: 为 `feedback` 表添加 `audit_log_id` 列

### 6. 测试覆盖

- `test_audit_log.py`: 21 个单元测试（模型字段、默认值、新字段）
- `test_audit_integration.py`: 21 个集成测试（路由、写入、API 端点）

## 数据流示意

```
用户消息 → NLU → Agent arun → 工具调用链
                ↓
        _save_audit_log()
        ├── AgentAuditLog (汇总: tokens, latency, tool_call_count, ...)
        └── ToolCallDetail[] (明细: 每个 tool 的 name, args, success, ...)
                ↓
        返回 audit_log_id → 前端
                ↓
        用户点 👎 → POST /feedback { audit_log_id }
                ├── Feedback (rating, comment, audit_log_id)
                └── AgentAuditLog.feedback_rating = "thumbs_down"
                ↓
        管理后台: /audit/feedback/summary → 按 variant 看满意度
                  /audit/tool-calls/stats → 看工具失败率
                  /audit/tool-calls/errors → 排查具体错误
```

## 向后兼容

- `tool_calls_json` 保留原格式 `[{name, success}]`，旧代码不受影响
- `Feedback.audit_log_id` 可选，不传则不关联
- 新增列均设 `DEFAULT 0` 或 `nullable=True`，已有数据无需迁移
