# Token 消耗优化与 Agent 审计日志系统设计

**日期**：2026-05-23  
**状态**：已确认  
**范围**：Phase 1 — 小安（孕妇端），Phase 2 推广到护士/医生

---

## 1. 问题与目标

### 1.1 当前 Token 消耗分布（单次对话首轮）

| 组成部分 | Token 估算 | 占比 |
|----------|-----------|------|
| System Prompt | ~400-500 | 15% |
| 12 Tools 定义（JSON Schema） | ~2,500-3,000 | **75%** |
| User Message | ~30 | 1% |
| 历史记录（会话后续轮次） | 可变 | ~10% |

**核心结论**：Tools 定义是最大成本项，平均 10 tools 全部注入但实际每轮只用 1-3 个。

### 1.2 目标

1. **工具路由**：按用户意图动态注入 tools 子集（3-4 tools），目标节省 60-70% tool token
2. **审计日志**：每次 Agent 调用记录完整审计链（token、工具调用、路由决策）
3. **三层统计**：会话级 / 智能体级 / 日级别 token 消耗可查询

---

## 2. 模块 A：工具路由

### 2.1 架构

```
用户消息
  │
  ▼
agno_chat_handler.py（预处理层）
  │
  ├─ 1. 快速意图分类（复用 agno_parse_nlu）
  │     intent ∈ {chat, record, qa, emergency, complex}
  │
  ├─ 2. Agent 路由
  │     chat      → get_chat_agent()      3 tools
  │     record    → get_record_agent()    4 tools
  │     qa        → get_qa_agent()        3 tools
  │     emergency → get_emergency_agent() 2 tools
  │     complex   → get_main_agent()     10 tools（兜底）
  │
  └─ 3. arun() + 审计日志记录
```

### 2.2 工具子集划分

在 `agno_tools.py` 中定义 `TOOL_GROUPS` 字典：

```python
TOOL_GROUPS = {
    "chat":      ["agno_parse_nlu", "agno_check_emergency", "agno_get_patient_context"],
    "record":    ["agno_parse_nlu", "agno_save_health_data", "agno_evaluate_vital_rules", "agno_get_patient_context"],
    "qa":        ["agno_search_knowledge", "agno_get_patient_context", "agno_analyze_health_trends"],
    "emergency": ["agno_check_emergency", "agno_get_patient_context"],
    "complex":   "ALL",  # 使用完整 MEDICAL_TOOLS
}
```

### 2.3 意图映射规则

| NLU Intent | 路由 Agent | 说明 |
|------------|-----------|------|
| `chat` / `greeting` / `emotion` | chat | 闲聊、打招呼、情绪安抚 |
| `record_weight` / `record_bp` / `record_glucose` / `record_fetal_movement` | record | 健康数据记录 |
| `ask_knowledge` / `ask_symptom` / `ask_exam` | qa | 孕期知识问答 |
| `emergency` | emergency | 紧急情况，立即引导就医 |
| 其他 / 多意图 / 不确定 | complex | 兜底，全量 tools |

### 2.4 Agent 工厂扩展（agno_agent.py）

```
当前：get_main_agent() → 1 Agent, 10 tools

优化后：
  get_chat_agent()      → 3 tools, tool_call_limit=3
  get_record_agent()    → 4 tools, tool_call_limit=4
  get_qa_agent()        → 3 tools, tool_call_limit=4
  get_emergency_agent() → 2 tools, tool_call_limit=1
  get_main_agent()      → 10 tools, tool_call_limit=8（兜底）

所有变体共享同一个 SqliteDb（session 跨变体连续）
@lru_cache(maxsize=1) 缓存每个变体
```

### 2.5 预期效果

| 场景 | 优化前 Tool Token | 优化后 Tool Token | 节省 |
|------|-------------------|-------------------|------|
| chat | ~2,500 | ~600 | 76% |
| record | ~2,500 | ~800 | 68% |
| qa | ~2,500 | ~700 | 72% |
| emergency | ~2,500 | ~400 | 84% |
| complex | ~2,500 | ~2,500 | 0%（兜底） |

假设 80% 请求命中前 4 个场景，**平均 tool token 节省 ~74%**。

---

## 3. 模块 B：Agent 审计日志系统

### 3.1 数据模型

```python
# backend/app/models.py

class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"

    id: int (PK, auto)
    session_id: str (indexed)
    user_id: str (indexed)
    agent_role: str          # pregnant | nurse | doctor
    agent_variant: str       # chat | record | qa | emergency | complex | main

    # 路由
    intent_classification: str | None
    routed_agent: str

    # Token
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # 工具调用链（JSON）
    tool_calls_json: str | None  # [{"name": "...", "duration_ms": 123, "success": true, "result_preview": "..."}]

    # 模型与耗时
    model_id: str
    provider: str
    total_latency_ms: int
    llm_latency_ms: int | None

    # 安全
    guardrail_triggered: bool (default False)
    response_preview: str | None  # 前 200 字

    # 时间戳
    created_at: datetime (indexed)
```

### 3.2 写入策略

**同步写入**（可靠优先）。每次 `arun()` 完成后立即 `await` 写入 DB。预计增加 5-15ms 延迟，医疗场景下审计完整性优先。

### 3.3 三层统计视图

| 层级 | 聚合维度 | 典型查询 |
|------|---------|---------|
| 会话级 | `session_id` | 单次对话的完整审计链（用户消息 → 意图 → 路由 → 工具调用 → 响应 → token） |
| 智能体级 | `agent_role` + `agent_variant` | 各角色/场景的 token 消耗对比 |
| 日级别 | `DATE(created_at)` | 每日总 token、调用次数、平均延迟 |

### 3.4 API 端点

```
GET /api/v1/admin/audit/token/daily?date_from=2026-05-01&date_to=2026-05-23
  → [{date, total_tokens, input_tokens, output_tokens, call_count, avg_latency_ms}]

GET /api/v1/admin/audit/token/by-agent?date_from=&date_to=
  → [{agent_role, agent_variant, total_tokens, call_count, avg_tool_count}]

GET /api/v1/admin/audit/sessions/{session_id}
  → 单次会话完整审计链（所有 run 记录按时间排序）
```

### 3.5 数据来源

Agno 框架 `RunResponse.metrics` 原生提供：

- `metrics.input_tokens` / `metrics.output_tokens` / `metrics.total_tokens`
- 从 `RunResponse.messages` 提取工具调用元数据
- 在 `agno_chat_handler.py` 中计算 `total_latency_ms`

---

## 4. System Prompt 优化（轻量）

在 `prompts.py` 中压缩 30-40% 措辞，指令条目数不变，语义等价。通过去除重复表述、合并相似规则实现。

示例：

```python
# 优化前
"你是'小安'，一位温暖、专业的孕期智能助手。"
"【用户上下文自动注入】"
"当前登录用户的孕妇ID会被系统自动注入到所有工具调用中，无需传入 pregnant_id 参数。"

# 优化后
"你是'小安'，温暖、专业的孕期智能助手。"
"【上下文】孕妇ID由系统自动注入工具调用，无需用户提供。"
```

预期节省 ~150 tokens（system prompt 层面约 35% 压缩）。

---

## 5. 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/core/agno_tools.py` | 新增 `TOOL_GROUPS` 字典 + `resolve_tools_by_intent()` |
| `backend/app/core/agno_agent.py` | Agent 工厂扩展为 4 变体 + LRU 缓存 |
| `backend/app/core/agno_chat_handler.py` | 意图预处理 + Agent 路由 + metrics 收集 + 审计写入 |
| `backend/app/core/prompts.py` | System prompt 轻量压缩 |
| `backend/app/models.py` | 新增 `AgentAuditLog` 模型 |
| `backend/app/routers/admin.py` | 新增审计查询 API（3 个端点） |
| `backend/app/core/agno_medical_agents.py` | **不改动**（Phase 2 推广） |
| `backend/app/core/agno_client.py` | **不改动** |

---

## 6. 风险与约束

- **NLU 意图分类准确率**：`agno_parse_nlu` 本身需要 LLM 调用，会额外消耗 ~200-300 tokens。方案是通过一次轻量调用换后续 tool token 的大幅节省。如果 NLU 误分类，`complex` 兜底保证功能不丢失
- **跨变体 session 连续性**：所有变体共享同一个 `SqliteDb`，Agno 通过 `session_id` 加载历史。已验证可行
- **流式场景工具调用事件提取**：当前 `handle_chat_with_agno_stream` 已捕获 `RunEvent.tool_call_started/completed`，审计日志复用同一逻辑

---

## 7. Phase 2 展望（不在本次范围）

- 护士/医生 Agent 同理拆分工具子集
- 审计 Dashboard 前端页面
- Token 消耗告警（日消耗超阈值通知）
- 工具调用成功率统计
