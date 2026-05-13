# Agno 框架最大化利用计划

> 日期：2026-05-12
> 目标：将项目从"使用 Agno 的基础功能"升级为"充分利用 Agno 五层架构的生产级多 Agent 系统"

---

## 一、现状评估

### 当前 Agno 使用层级：Level 1 → Level 2 过渡中

| 层级 | 能力 | 当前状态 |
|------|------|----------|
| Level 1 | Agent + Tools + Instructions | ✅ 已实现（主对话/随访 Agent） |
| Level 2 | Knowledge + Storage | ⚠️ 部分实现（Knowledge 适配器已写但未接入） |
| Level 3 | Memory + Reasoning | ❌ 未实现（自行管理 conversation_store） |
| Level 4 | Team 协作 | ❌ 未实现（护士/医生 Agent 独立运行） |
| Level 5 | Workflow 编排 | ❌ 未实现（手动 if/else 管道） |

### 关键问题清单

| # | 问题 | 严重度 | 影响 |
|---|------|--------|------|
| 1 | followup_tools.py 与 agno_tools.py 代码重复 | 高 | 维护成本翻倍，修改易遗漏 |
| 2 | AgnoClient 每次请求重建 Agent | 高 | 无法利用 session/memory，性能浪费 |
| 3 | MedicalSafetyGuardrail 未注册为 post_hook | 高 | 输出层安全检查缺失 |
| 4 | 同步 DB 操作在异步工具中阻塞事件循环 | 高 | 并发性能下降 |
| 5 | Knowledge 适配器已实现但未接入 Agent | 中 | 知识搜索走手动工具而非 Agno 原生 |
| 6 | 护士/医生 Agent 未使用工具能力 | 中 | 需手动拼装上下文，Agent 形同包装器 |
| 7 | 异常处理 bare except: pass | 中 | 医疗数据丢失无感知 |
| 8 | agno_ui.py 与 agno_agent.py 定义不统一 | 低 | 维护混乱 |

---

## 二、优化路线图

### Phase 1：基础清理与修复（1-2天）

**目标**：消除技术债务，为后续升级打基础

#### 1.1 清理 followup_tools.py 重复代码

```
操作步骤：
1. 确认 chat.py 中 followup 分支在 agno_enabled=True 时不执行
2. 将 chat.py 的 import 从 followup_tools 改为 agno_tools
3. 删除 followup_tools.py
4. 运行测试验证
```

**涉及文件**：
- `backend/app/routers/chat.py` 第14行 import
- `backend/app/core/followup_tools.py`（删除）

#### 1.2 修复异常处理

将所有 bare `except Exception: pass` 改为结构化日志：

```python
# agno_chat_handler.py - 对话持久化
try:
    await save_conversation(...)
except Exception:
    logger.warning("对话持久化失败，不影响用户响应", exc_info=True)

# agno_tools.py - 数据库操作
try:
    db.add(health_point)
    db.commit()
except Exception:
    logger.error("健康数据保存失败", exc_info=True)
    return {"success": False, "error": "数据保存失败"}
```

**涉及文件**：
- `backend/app/core/agno_chat_handler.py` 第47-48, 97-98, 143-144, 203-204行
- `backend/app/core/agno_tools.py` 第156-158行

#### 1.3 注册 MedicalSafetyGuardrail

```python
# agno_agent.py
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail

def create_main_agent() -> Agent:
    return Agent(
        ...
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],  # 新增
        ...
    )
```

#### 1.4 统一 agno_ui.py Agent 定义

```python
# agno_ui.py - 复用已有工厂函数
from app.core.agno_agent import create_main_agent
from app.core.agno_medical_agents import (
    create_nurse_agent,
    create_doctor_agent,
    create_followup_generate_agent,
)

# 不再重复定义 create_main_agent()
```

---

### Phase 2：异步与性能优化（2-3天）

**目标**：消除阻塞，提升并发能力

#### 2.1 同步 DB 工具异步化

```python
# agno_tools.py
import asyncio

@tool
async def agno_save_health_data(patient_id: str, ...) -> dict:
    """保存健康数据（异步安全）"""
    def _save():
        db = SessionLocal()
        try:
            # ... 同步 DB 操作
            db.commit()
            return {"success": True}
        finally:
            db.close()

    return await asyncio.to_thread(_save)
```

**涉及文件**：
- `backend/app/core/agno_tools.py` 中所有同步 DB 工具

#### 2.2 Agent 实例缓存

```python
# agno_agent.py
from functools import lru_cache

@lru_cache(maxsize=1)
def get_main_agent() -> Agent:
    """获取主对话 Agent 单例"""
    return create_main_agent()

def get_followup_agent(**kwargs) -> Agent:
    """获取随访 Agent（每次创建，含动态上下文）"""
    return create_followup_agent(**kwargs)
```

**涉及文件**：
- `backend/app/core/agno_agent.py`
- `backend/app/core/agno_chat_handler.py` 第26行

#### 2.3 模型实例复用

```python
# agno_client.py
_model_instance = None

def get_agno_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = _create_model()
    return _model_instance
```

---

### Phase 3：Agno 原生能力集成（3-5天）

**目标**：从"手动工具调用"升级为"Agno 原生 Knowledge + Memory"

#### 3.1 接入 Agno Knowledge

```python
# agno_agent.py
from .agno_knowledge import get_knowledge

def create_main_agent() -> Agent:
    return Agent(
        ...
        knowledge=get_knowledge(),
        search_knowledge=True,  # Agno 自动在需要时检索
        ...
    )
```

**移除**：`agno_tools.py` 中的 `agno_search_knowledge` 工具（Agno 会自动处理）

#### 3.2 启用 Agno Memory

```python
# agno_agent.py
def create_main_agent() -> Agent:
    return Agent(
        ...
        enable_agentic_memory=True,
        add_history_to_context=True,
        num_history_runs=5,
        ...
    )
```

**保留**：`conversation_store.py` 用于业务侧的历史记录展示，但 Agent 对话上下文由 Agno 管理

#### 3.3 利用 Agno Session

```python
# agno_chat_handler.py
async def handle_chat_with_agno(request, ...):
    agent = get_main_agent()
    # 使用 Agno session_id 管理会话
    response = await agent.arun(
        message,
        session_id=f"pregnant_{patient_id}",
        user_id=patient_id,
    )
```

---

### Phase 4：多 Agent 协作升级（5-7天）

**目标**：从"独立 Agent"升级为"Team 协作"

#### 4.1 护士/医生 Agent 工具化

```python
# agno_medical_agents.py
from .agno_tools import (
    agno_get_patient_context,
    agno_analyze_health_trends,
    agno_evaluate_vital_rules,
)

def create_nurse_agent() -> Agent:
    return Agent(
        name="小护",
        model=get_agno_model(),
        instructions=[...],
        tools=[
            agno_get_patient_context,
            agno_analyze_health_trends,
            agno_evaluate_vital_rules,
        ],
        output_schema=NurseAnalysisOutput,
    )
```

**涉及文件**：
- `backend/app/core/agno_medical_agents.py`
- `backend/app/routers/nurse_ai.py`（简化上下文拼装逻辑）
- `backend/app/routers/doctor_ai.py`（简化上下文拼装逻辑）

#### 4.2 引入 Team 模式

```python
# backend/app/core/agno_team.py（新建）
from agno.team import Team
from .agno_agent import create_main_agent
from .agno_medical_agents import create_nurse_agent, create_doctor_agent

def create_care_team() -> Team:
    """创建孕期护理团队"""
    return Team(
        name="AI-Care 孕期护理团队",
        members=[
            create_main_agent(),      # 小安 - 日常对话
            create_nurse_agent(),     # 小护 - 护理分析
            create_doctor_agent(),    # 智医 - 医疗分析
        ],
        instructions="""
        你是孕期护理团队的协调者。
        - 日常健康咨询由小安处理
        - 需要护理分析时调用小护
        - 需要医疗分析时调用智医
        - 紧急情况直接引导就医
        """,
        show_members_responses=True,
        get_member_information_tool=True,
    )
```

#### 4.3 前端 Team 对话展示

```vue
<!-- 支持多 Agent 响应展示 -->
<div v-for="member in teamMembers" :key="member.name">
  <AgentAvatar :agent="member.avatarKey" :size="20" />
  <span>{{ member.name }}:</span>
  <div v-html="member.response" />
</div>
```

---

### Phase 5：Workflow 编排（5-7天）

**目标**：从"if/else 管道"升级为"确定性 Workflow"

#### 5.1 孕检流程 Workflow

```python
# backend/app/core/agno_workflow.py（新建）
from agno.workflow import Step, Workflow, Router

def create_prenatal_workflow() -> Workflow:
    return Workflow(
        name="孕检流程",
        description="标准化孕检流程编排",
        steps=[
            # Step 1: 数据收集
            Step(
                name="健康数据采集",
                agent=data_collection_agent,
            ),
            # Step 2: 风险评估
            Step(
                name="风险评估",
                agent=risk_assessment_agent,
            ),
            # Step 3: 路由决策
            Router(
                name="处理路由",
                selector="session_state.risk_level",
                choices=[
                    Step(name="常规处理", agent=routine_agent),
                    Step(name="高危处理", agent=high_risk_agent),
                    Step(name="紧急处理", agent=emergency_agent),
                ],
            ),
            # Step 4: 报告生成
            Step(
                name="报告生成",
                agent=report_agent,
            ),
        ],
    )
```

#### 5.2 随访 Workflow

```python
def create_followup_workflow() -> Workflow:
    return Workflow(
        name="随访流程",
        steps=[
            Step(name="随访准备", agent=followup_prep_agent),
            Step(name="随访执行", agent=followup_exec_agent),
            Step(name="随访总结", agent=followup_summary_agent),
        ],
    )
```

---

## 三、技术架构演进图

```
当前架构（Level 1-2）                    目标架构（Level 4-5）
┌─────────────────────┐                ┌─────────────────────────────┐
│   chat.py           │                │   chat.py                   │
│   ├── agno_enabled? │                │   ├── Team/Workflow 路由    │
│   │   ├── Yes → Agent(arun)          │   │   ├── 日常对话 → Team   │
│   │   └── No  → 原始管道             │   │   ├── 孕检流程 → Workflow│
│   └── 手动拼装上下文  │                │   │   └── 随访流程 → Workflow│
├─────────────────────┤                ├─────────────────────────────┤
│   5个独立 Agent      │                │   Team（小安+小护+智医）    │
│   各自独立运行        │                │   ├── Route 路由模式        │
│   无协作机制          │                │   └── 成员工具共享          │
├─────────────────────┤                ├─────────────────────────────┤
│   手动 Knowledge     │                │   Agno 原生 Knowledge       │
│   agno_search_knowledge│              │   Agent 自动检索            │
├─────────────────────┤                ├─────────────────────────────┤
│   自行管理 conversation│               │   Agno Session + Memory     │
│   conversation_store │                │   跨会话持久化              │
└─────────────────────┘                └─────────────────────────────┘
```

---

## 四、实施优先级与依赖关系

```
Phase 1（基础清理）
  ├── 1.1 清理 followup_tools.py ──────────┐
  ├── 1.2 修复异常处理 ────────────────────┤
  ├── 1.3 注册 MedicalSafetyGuardrail ─────┤
  └── 1.4 统一 agno_ui.py ────────────────┤
                                           ▼
Phase 2（异步与性能）                    无依赖，可并行
  ├── 2.1 同步 DB 异步化 ────────────────┐
  ├── 2.2 Agent 实例缓存 ────────────────┤
  └── 2.3 模型实例复用 ──────────────────┤
                                           ▼
Phase 3（原生能力集成）              依赖 Phase 2.2
  ├── 3.1 接入 Knowledge ────────────────┐
  ├── 3.2 启用 Memory ───────────────────┤
  └── 3.3 利用 Session ──────────────────┤
                                           ▼
Phase 4（多 Agent 协作）            依赖 Phase 2 + 3
  ├── 4.1 Agent 工具化 ──────────────────┐
  ├── 4.2 Team 模式 ─────────────────────┤
  └── 4.3 前端 Team 展示 ────────────────┤
                                           ▼
Phase 5（Workflow 编排）            依赖 Phase 4
  ├── 5.1 孕检 Workflow ─────────────────┐
  └── 5.2 随访 Workflow ─────────────────┘
```

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Agno 版本升级破坏 API | 高 | 锁定 agno>=2.6.0，升级前测试 |
| Team 模式增加 LLM 调用次数 | 中 | 设置 tool_call_limit，监控成本 |
| Knowledge 接入后检索质量下降 | 中 | 保留手动工具作为 fallback |
| Workflow 过度工程化 | 低 | 先在随访场景验证，再推广 |

---

## 六、验收标准

### Phase 1 完成标准
- [ ] followup_tools.py 已删除，chat.py 使用 agno_tools
- [ ] 所有 bare except 改为结构化日志
- [ ] MedicalSafetyGuardrail 注册为 post_hook
- [ ] agno_ui.py 复用 agno_agent.py 工厂

### Phase 2 完成标准
- [ ] 所有 DB 工具使用 asyncio.to_thread
- [ ] 主对话 Agent 使用单例缓存
- [ ] 模型实例全局复用

### Phase 3 完成标准
- [ ] Agent 使用 knowledge 参数自动检索
- [ ] Agent 启用 agentic_memory
- [ ] 使用 Agno session_id 管理会话

### Phase 4 完成标准
- [ ] 护士/医生 Agent 配备工具集
- [ ] Team 模式在至少一个场景上线
- [ ] 前端支持多 Agent 响应展示

### Phase 5 完成标准
- [ ] 孕检 Workflow 可运行
- [ ] 随访 Workflow 可运行
- [ ] Workflow 支持状态持久化
