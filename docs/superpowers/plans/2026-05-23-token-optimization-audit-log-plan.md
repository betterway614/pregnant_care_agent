# Token 优化与 Agent 审计日志 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为小安智能体实施工具路由（4场景变体），建立 Agent 审计日志系统（会话/智能体/日三层统计），压缩 system prompt

**Architecture:** 在 agno_chat_handler 预处理层做 NLU 意图分类 → 路由到对应 Agent 变体（chat/record/qa/emergency/complex），每次 arun 后同步写入 AgentAuditLog 表；所有变体共享同一 SqliteDb 保持 session 连续

**Tech Stack:** Agno Framework, SQLAlchemy (SQLite), FastAPI, Pydantic v2, Loguru

---

### Task 1: 新增 AgentAuditLog 数据模型 + 数据库迁移

**Files:**
- Modify: `backend/app/models/models.py`（末尾追加）
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/main.py`（添加迁移函数）

- [ ] **Step 1: 在 models.py 末尾添加 AgentAuditLog 模型**

```python
class AgentAuditLog(Base):
    """Agent 审计日志 — 每次 arun 一条记录"""
    __tablename__ = "agent_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True, comment="对话会话ID")
    user_id = Column(String(64), nullable=False, index=True, comment="用户ID")
    agent_role = Column(String(16), nullable=False, index=True, comment="pregnant|nurse|doctor")
    agent_variant = Column(String(16), nullable=False, comment="chat|record|qa|emergency|complex|main")
    intent_classification = Column(String(32), nullable=True, comment="NLU识别的意图")
    routed_agent = Column(String(32), nullable=False, comment="最终路由的Agent变体")
    input_tokens = Column(Integer, default=0, comment="输入token数")
    output_tokens = Column(Integer, default=0, comment="输出token数")
    total_tokens = Column(Integer, default=0, comment="总token数")
    tool_calls_json = Column(JSON, nullable=True, comment="工具调用链")
    model_id = Column(String(64), nullable=False, comment="模型ID")
    provider = Column(String(32), nullable=False, comment="模型提供商")
    total_latency_ms = Column(Integer, default=0, comment="总耗时ms")
    llm_latency_ms = Column(Integer, nullable=True, comment="LLM耗时ms")
    guardrail_triggered = Column(Boolean, default=False, comment="安全护栏触发")
    response_preview = Column(String(200), nullable=True, comment="回复预览(前200字)")
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
```

- [ ] **Step 2: 更新 models/__init__.py 导出**

在 import 行追加 `AgentAuditLog`：
```python
from .models import (
    Pregnant, HealthDataPoint, ScheduleNode,
    FollowUpRecord, FgrAssessment, Alert, MedicalOrder,
    FetalMovementSession, Feedback, MentalHealthScreening,
    ConversationMessage, DailyHealthSummary,
    NurseDoctorIssue, AgentAuditLog,
)
```

在 `__all__` 列表追加 `"AgentAuditLog"`。

- [ ] **Step 3: 在 main.py 添加迁移函数**

在 `_ensure_order_columns` 之后、`lifespan` 之前添加：

```python
def _ensure_audit_log_table():
    """为已有数据库添加 agent_audit_logs 表（幂等）"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        if "agent_audit_logs" not in inspector.get_table_names():
            Base.metadata.create_all(bind=engine, tables=[AgentAuditLog.__table__])
            logger.info("agent_audit_logs 表创建完成")
        else:
            logger.info("agent_audit_logs 表已存在，跳过创建")
    except Exception as e:
        logger.warning("agent_audit_logs 迁移跳过: {}", e)
```

并在 `lifespan` 中 `_ensure_order_columns()` 之后调用 `_ensure_audit_log_table()`。

注意 `main.py` 顶部的 model import 需要加上 `AgentAuditLog`：
```python
from .models import Pregnant, HealthDataPoint, ScheduleNode, FollowUpRecord, FgrAssessment, Alert, MedicalOrder, AgentAuditLog
```

- [ ] **Step 4: 验证表创建**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

---

### Task 2: 添加 TOOL_GROUPS 字典 + resolve_tools_by_intent()

**Files:**
- Modify: `backend/app/core/agno_tools.py`（末尾追加）

- [ ] **Step 1: 在 MEDICAL_TOOLS 定义之后添加 TOOL_GROUPS**

在 `MEDICAL_TOOLS = [...]` 之后（约第 411 行后）添加：

```python
# ==================== 工具子集分组（工具路由） ====================

TOOL_GROUPS: dict[str, list] = {
    "chat": [
        agno_parse_nlu,
        agno_check_emergency,
        agno_get_patient_context,
    ],
    "record": [
        agno_parse_nlu,
        agno_save_health_data,
        agno_evaluate_vital_rules,
        agno_get_patient_context,
    ],
    "qa": [
        agno_search_knowledge,
        agno_get_patient_context,
        agno_analyze_health_trends,
    ],
    "emergency": [
        agno_check_emergency,
        agno_get_patient_context,
    ],
}
```

- [ ] **Step 2: 添加 resolve_tools_by_intent() 函数**

紧接着添加：

```python
# 意图 → 工具组路由映射
INTENT_TO_GROUP: dict[str, str] = {
    "chat": "chat",
    "greeting": "chat",
    "emotion": "chat",
    "record_weight": "record",
    "record_bp": "record",
    "record_glucose": "record",
    "record_fetal_movement": "record",
    "ask_knowledge": "qa",
    "ask_symptom": "qa",
    "ask_exam": "qa",
    "emergency": "emergency",
}


def resolve_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回工具子集和 variant 名称。

    Returns:
        (tools_list, variant_name)
        variant_name: "chat" | "record" | "qa" | "emergency" | "complex"
    """
    if nlu_result is None or not nlu_result.get("intent"):
        return (MEDICAL_TOOLS, "complex")

    intent = nlu_result.get("intent", "")
    group_name = INTENT_TO_GROUP.get(intent)

    if group_name and group_name in TOOL_GROUPS:
        return (TOOL_GROUPS[group_name], group_name)

    return (MEDICAL_TOOLS, "complex")
```

---

### Task 3: 扩展 Agent 工厂为 4 变体

**Files:**
- Modify: `backend/app/core/agno_agent.py`

- [ ] **Step 1: 重写 agno_agent.py**

将当前只有 `create_main_agent()` + `get_main_agent()` 的文件扩展为多变体工厂。同时共享同一个 SqliteDb 实例。

```python
"""Agno Agent 定义 - 主 Agent（小安）+ 场景变体（工具路由）

Agent 变体:
- chat: 闲聊/情绪安抚（3 tools）
- record: 健康数据记录（4 tools）
- qa: 孕期知识问答（3 tools）
- emergency: 紧急检测（2 tools）
- main: 全量兜底（10 tools）

安全设计：所有变体共享同一个 SqliteDb（session 跨变体连续）
"""
from functools import lru_cache

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from .agno_client import get_agno_model
from .agno_knowledge import agno_knowledge
from .prompts import get_pregnant_system_prompt_instructions
from .agno_tools import MEDICAL_TOOLS, TOOL_GROUPS
from .agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail
from ..config import settings

import os

_db_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)
_pregnant_db_path = os.path.join(_db_dir, "agent_sessions_pregnant.db")


def _create_pregnant_db():
    return SqliteDb(db_file=_pregnant_db_path)


def _build_agent(variant_name: str, tools: list, tool_call_limit: int) -> Agent:
    """通用 Agent 构造器"""
    return Agent(
        name=f"小安-{variant_name}",
        model=get_agno_model(role="pregnant"),
        instructions=get_pregnant_system_prompt_instructions(),
        tools=tools,
        knowledge=agno_knowledge,
        search_knowledge=False,
        db=_create_pregnant_db(),
        add_history_to_context=True,
        num_history_runs=8,
        enable_agentic_memory=True,
        add_datetime_to_context=True,
        pre_hooks=[EmergencyGuardrail()],
        post_hooks=[MedicalSafetyGuardrail()],
        markdown=True,
        tool_call_limit=tool_call_limit,
        debug_mode=False,
    )


def create_main_agent() -> Agent:
    """全量兜底 Agent（10 tools）"""
    return _build_agent("main", MEDICAL_TOOLS, tool_call_limit=8)


@lru_cache(maxsize=1)
def get_main_agent() -> Agent:
    return create_main_agent()


@lru_cache(maxsize=1)
def get_chat_agent() -> Agent:
    return _build_agent("chat", TOOL_GROUPS["chat"], tool_call_limit=3)


@lru_cache(maxsize=1)
def get_record_agent() -> Agent:
    return _build_agent("record", TOOL_GROUPS["record"], tool_call_limit=4)


@lru_cache(maxsize=1)
def get_qa_agent() -> Agent:
    return _build_agent("qa", TOOL_GROUPS["qa"], tool_call_limit=4)


@lru_cache(maxsize=1)
def get_emergency_agent() -> Agent:
    return _build_agent("emergency", TOOL_GROUPS["emergency"], tool_call_limit=1)


# variant → factory 映射
AGENT_VARIANT_MAP = {
    "chat": get_chat_agent,
    "record": get_record_agent,
    "qa": get_qa_agent,
    "emergency": get_emergency_agent,
    "complex": get_main_agent,
}
```

- [ ] **Step 2: 验证 Agent 创建**

```bash
cd backend && python -c "
from app.core.agno_agent import get_chat_agent, get_record_agent, get_qa_agent, get_emergency_agent, get_main_agent
for name, factory in [('chat', get_chat_agent), ('record', get_record_agent), ('qa', get_qa_agent), ('emergency', get_emergency_agent), ('main', get_main_agent)]:
    a = factory()
    print(f'{name}: {len(a.tools)} tools, tool_call_limit={a.tool_call_limit}')
"
```

---

### Task 4: 更新 agno_chat_handler — 意图路由 + metrics + 审计日志

**Files:**
- Modify: `backend/app/core/agno_chat_handler.py`

这是最核心的改动。需要将当前 `handle_chat_with_agno` 和 `handle_chat_with_agno_stream` 中的直接 `get_main_agent()` 替换为"NLU 意图分类 → Agent 路由 → metrics 收集 → 审计写入"流程。

- [ ] **Step 1: 更新 imports**

在现有 import 区域追加：

```python
import time
from ..models import AgentAuditLog
from ..database import SessionLocal
```

- [ ] **Step 2: 添加审计日志写入函数**

在 `_generate_session_id` 之后添加：

```python
def _save_audit_log(
    session_id: str,
    user_id: str,
    agent_role: str,
    agent_variant: str,
    intent_classification: str | None,
    response: Any,
    tool_steps: list[str],
    total_latency_ms: int,
    guardrail_triggered: bool = False,
) -> None:
    """同步写入 Agent 审计日志（可靠优先）"""
    try:
        metrics = getattr(response, "metrics", None)

        # 提取工具调用详情
        tool_calls_detail = []
        if hasattr(response, "messages") and response.messages:
            for msg in response.messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_calls_detail.append({
                            "name": getattr(tc, "name", ""),
                            "success": True,
                            "result_preview": "",
                        })

        db = SessionLocal()
        try:
            log_entry = AgentAuditLog(
                session_id=session_id,
                user_id=user_id,
                agent_role=agent_role,
                agent_variant=agent_variant,
                intent_classification=intent_classification,
                routed_agent=f"小安-{agent_variant}",
                input_tokens=metrics.input_tokens if metrics else 0,
                output_tokens=metrics.output_tokens if metrics else 0,
                total_tokens=metrics.total_tokens if metrics else 0,
                tool_calls_json=tool_calls_detail if tool_calls_detail else None,
                model_id=getattr(response, "model", "") or "",
                provider="openai",
                total_latency_ms=total_latency_ms,
                guardrail_triggered=guardrail_triggered,
                response_preview=(response.content or "")[:200] if response.content else None,
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("审计日志写入失败 session_id={}", session_id, exc_info=True)
        finally:
            db.close()
    except Exception:
        logger.warning("审计日志构建失败 session_id={}", session_id, exc_info=True)
```

- [ ] **Step 3: 重写 handle_chat_with_agno（非流式）**

```python
async def handle_chat_with_agno(req: ChatSendRequest) -> ChatResponse:
    """主对话 Agno Agent 处理（非流式）— 工具路由 + 审计日志"""
    from .agno_agent import AGENT_VARIANT_MAP, get_main_agent

    session_id = req.session_id or _generate_session_id(req.pregnant_id)
    start_time = time.time()

    # ASR 预处理
    transcribed_text = None
    if req.message_type == "AUDIO" and req.audio_data:
        transcribed_text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)

    agent_input = _build_multimodal_input(req, transcribed_text)

    # 1. 快速意图分类（复用 agno_parse_nlu 底层的 NLU 引擎，不通过 Agent）
    nlu_result = None
    intent_variant = "complex"
    try:
        from ..core.nlu_engine import nlu_engine
        nlu_result = nlu_engine.parse(req.message.strip() if req.message else "")
        nlu_dict = {
            "intent": nlu_result.intent,
            "entities": nlu_result.entities,
            "emotion": nlu_result.emotion,
            "is_emergency": nlu_result.is_emergency,
        }
        from .agno_tools import resolve_tools_by_intent
        _, intent_variant = resolve_tools_by_intent(nlu_dict)
    except Exception:
        logger.warning("NLU意图分类失败，使用兜底Agent", exc_info=True)

    # 2. Agent 路由
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()

    # 3. arun
    response = await agent.arun(
        input=agent_input,
        user_id=req.pregnant_id,
        session_id=session_id,
    )

    elapsed_ms = int((time.time() - start_time) * 1000)
    content = response.content or ""

    # 4. 审计日志
    _save_audit_log(
        session_id=session_id,
        user_id=req.pregnant_id,
        agent_role="pregnant",
        agent_variant=intent_variant,
        intent_classification=nlu_result.intent if nlu_result else None,
        response=response,
        tool_steps=[],
        total_latency_ms=elapsed_ms,
    )

    # 5. 对话持久化
    if settings.persist_chat_messages:
        try:
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "user", req.message,
            )
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "assistant", content,
            )
        except Exception:
            logger.warning("非流式对话持久化失败 session_id={}", session_id, exc_info=True)

    return ChatResponse(
        content=content,
        session_id=session_id,
        source="AI_CARE",
    )
```

- [ ] **Step 4: 重写 handle_chat_with_agno_stream（流式）**

核心逻辑同上，但在流式循环结束后收集 metrics 并写入审计日志。

```python
async def handle_chat_with_agno_stream(req: ChatSendRequest) -> AsyncGenerator[dict, None]:
    """主对话 Agno Agent 流式处理 — 工具路由 + 审计日志"""
    from .agno_agent import AGENT_VARIANT_MAP, get_main_agent

    session_id = req.session_id or _generate_session_id(req.pregnant_id)
    start_time = time.time()

    # ASR 预处理
    transcribed_text = None
    if req.message_type == "AUDIO" and req.audio_data:
        transcribed_text = await _transcribe_audio_pregnant(req.audio_data, req.audio_format)

    agent_input = _build_multimodal_input(req, transcribed_text)

    # 1. 快速意图分类
    nlu_result = None
    intent_variant = "complex"
    try:
        from ..core.nlu_engine import nlu_engine
        nlu_result = nlu_engine.parse(req.message.strip() if req.message else "")
        nlu_dict = {
            "intent": nlu_result.intent,
            "entities": nlu_result.entities,
            "emotion": nlu_result.emotion,
            "is_emergency": nlu_result.is_emergency,
        }
        from .agno_tools import resolve_tools_by_intent
        _, intent_variant = resolve_tools_by_intent(nlu_dict)
    except Exception:
        logger.warning("NLU意图分类失败，使用兜底Agent", exc_info=True)

    # 2. Agent 路由
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()

    # 初始思考状态
    yield {"event": "thinking", "data": "小安正在思考..."}

    full_response = ""
    tool_steps: list[str] = []
    run_response = None

    try:
        async for chunk in agent.arun(
            input=agent_input,
            stream=True,
            stream_events=True,
            user_id=req.pregnant_id,
            session_id=session_id,
        ):
            event = chunk.event

            if event == RunEvent.tool_call_started and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                thinking_msg = TOOL_THINKING_MAP.get(
                    tool_name, f"正在处理（{tool_name}）..."
                )
                yield {"event": "thinking", "data": thinking_msg}

            elif event == RunEvent.tool_call_completed and chunk.tool is not None:
                tool_name = getattr(chunk.tool, "tool_name", "") or ""
                step_desc = TOOL_THINKING_MAP.get(tool_name, "")
                if step_desc and step_desc not in tool_steps:
                    tool_steps.append(step_desc)

            elif event == RunEvent.run_content:
                if chunk.content and isinstance(chunk.content, str):
                    full_response += chunk.content
                    yield {"event": "chunk", "data": chunk.content}

            elif event == RunEvent.run_completed:
                # 捕获 run_response 用于提取 metrics
                run_response = chunk

    except Exception:
        import traceback
        logger.error("Agno stream error: {}", traceback.format_exc())
        yield {"event": "chunk", "data": "\n\n抱歉，我遇到了问题，请稍后再试。"}

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 发送完成事件
    yield {
        "event": "done",
        "data": json.dumps({
            "session_id": session_id,
            "source": "AI_CARE",
            "nlu_result": None,
            "memory_updated": [],
            "tool_steps": tool_steps,
            "transcribed_text": transcribed_text,
        }),
    }

    # 审计日志（使用流式捕获的 run_response）
    _save_audit_log(
        session_id=session_id,
        user_id=req.pregnant_id,
        agent_role="pregnant",
        agent_variant=intent_variant,
        intent_classification=nlu_result.intent if nlu_result else None,
        response=run_response,
        tool_steps=tool_steps,
        total_latency_ms=elapsed_ms,
    )

    # 对话持久化
    if settings.persist_chat_messages:
        try:
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "user", req.message,
            )
            await conversation_store.async_save_single(
                session_id, req.pregnant_id, "assistant", full_response,
            )
        except Exception:
            logger.warning("流式对话持久化失败 session_id={}", session_id, exc_info=True)
```

**关键变更**：流式场景中，`RunEvent.run_completed` 事件的 `chunk` 对象包含 `RunResponse` 的 metrics。如果 Agno 版本不直接支持，回退为使用 `agent.get_last_run_output()` 获取 metrics。

---

### Task 5: 压缩 System Prompt

**Files:**
- Modify: `backend/app/core/prompts.py`

- [ ] **Step 1: 压缩 get_pregnant_system_prompt_instructions()**

替换为精简版本（保留所有语义规则，压缩措辞）：

```python
def get_pregnant_system_prompt_instructions() -> list[str]:
    """小安 - 孕妇端 Agno Agent 指令列表（压缩版）"""
    return [
        "你是'小安'，温暖、专业的孕期智能助手。",
        "【职责】",
        "1. 用温暖语气回答孕期问题",
        "2. 帮助记录健康数据（体重、血压、胎动等）",
        "3. 提供情绪安抚和支持",
        "4. 回答孕期基础生理知识",
        "5. 不出具诊断结论或用药建议",
        "6. 知识性回答末尾标注『知识来源：<指南/文献名称>』",
        "7. 识别紧急情况时引导就医",
        "8. 超范围问题回复：'建议咨询产检医生，小安暂时无法提供确切答案'",
        "【上下文】孕妇ID由系统自动注入工具，无需向用户询问任何身份信息。",
        "用户问'我的数据'等个人问题时直接调用工具获取。",
        "【任务规划】复杂问题：先调用 agno_search_knowledge + agno_get_patient_context，"
        "必要时调用 agno_analyze_health_trends，综合后给出有依据的回复。"
        "每次回复前先获取用户上下文以个性化调整。",
        "记住：你是辅助工具，不能替代医生专业判断。",
    ]
```

---

### Task 6: 新增审计查询 API 路由

**Files:**
- Create: `backend/app/routers/admin.py`

- [ ] **Step 1: 创建 admin.py 路由文件**

```python
"""Agent 审计日志查询 API"""
from datetime import datetime, date
from fastapi import APIRouter, Query
from sqlalchemy import func, desc
from ..database import SessionLocal
from ..models import AgentAuditLog

router = APIRouter(prefix="/api/v1/admin", tags=["审计日志"])


@router.get("/audit/token/daily")
def get_token_daily(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """日级别 token 消耗汇总"""
    db = SessionLocal()
    try:
        from datetime import timedelta
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

        rows = (
            db.query(
                func.date(AgentAuditLog.created_at).label("date"),
                func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
                func.sum(AgentAuditLog.input_tokens).label("input_tokens"),
                func.sum(AgentAuditLog.output_tokens).label("output_tokens"),
                func.count(AgentAuditLog.id).label("call_count"),
                func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
            )
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .group_by(func.date(AgentAuditLog.created_at))
            .order_by(func.date(AgentAuditLog.created_at))
            .all()
        )

        return {
            "data": [
                {
                    "date": str(row.date),
                    "total_tokens": row.total_tokens or 0,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "call_count": row.call_count,
                    "avg_latency_ms": round(row.avg_latency_ms or 0, 1),
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@router.get("/audit/token/by-agent")
def get_token_by_agent(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """按智能体角色 + 变体汇总 token"""
    db = SessionLocal()
    try:
        from datetime import timedelta
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

        rows = (
            db.query(
                AgentAuditLog.agent_role,
                AgentAuditLog.agent_variant,
                func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
                func.count(AgentAuditLog.id).label("call_count"),
                func.avg(AgentAuditLog.input_tokens).label("avg_input_tokens"),
                func.avg(AgentAuditLog.output_tokens).label("avg_output_tokens"),
                func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
            )
            .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
            .group_by(AgentAuditLog.agent_role, AgentAuditLog.agent_variant)
            .order_by(AgentAuditLog.agent_role, func.sum(AgentAuditLog.total_tokens).desc())
            .all()
        )

        return {
            "data": [
                {
                    "agent_role": row.agent_role,
                    "agent_variant": row.agent_variant,
                    "total_tokens": row.total_tokens or 0,
                    "call_count": row.call_count,
                    "avg_input_tokens": round(row.avg_input_tokens or 0, 1),
                    "avg_output_tokens": round(row.avg_output_tokens or 0, 1),
                    "avg_latency_ms": round(row.avg_latency_ms or 0, 1),
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@router.get("/audit/sessions/{session_id}")
def get_session_audit(session_id: str):
    """单次会话完整审计链"""
    db = SessionLocal()
    try:
        logs = (
            db.query(AgentAuditLog)
            .filter(AgentAuditLog.session_id == session_id)
            .order_by(AgentAuditLog.created_at)
            .all()
        )

        return {
            "session_id": session_id,
            "run_count": len(logs),
            "runs": [
                {
                    "id": log.id,
                    "agent_role": log.agent_role,
                    "agent_variant": log.agent_variant,
                    "intent_classification": log.intent_classification,
                    "routed_agent": log.routed_agent,
                    "input_tokens": log.input_tokens,
                    "output_tokens": log.output_tokens,
                    "total_tokens": log.total_tokens,
                    "tool_calls": log.tool_calls_json,
                    "model_id": log.model_id,
                    "total_latency_ms": log.total_latency_ms,
                    "guardrail_triggered": log.guardrail_triggered,
                    "response_preview": log.response_preview,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        }
    finally:
        db.close()
```

---

### Task 7: 注册路由

**Files:**
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 更新 routers/__init__.py**

```python
from . import chat, schedule, followup, alerts, fgr, orders, dashboard
from . import pregnant, recommend, nurse_ai, doctor_ai, auth, fetal_movement, tts
from . import admin

__all__ = ["chat", "schedule", "followup", "alerts", "fgr", "orders", "dashboard",
           "pregnant", "recommend", "nurse_ai", "doctor_ai", "auth", "fetal_movement", "tts",
           "admin"]
```

- [ ] **Step 2: 更新 main.py**

在 import 行添加 `admin`：
```python
from .routers import chat, schedule, followup, alerts, fgr, orders, dashboard
from .routers import pregnant, recommend, nurse_ai, doctor_ai, auth, fetal_movement, feedback, mental_health, health_trends
from .routers import websocket, tts, admin
```

在路由注册区域末尾添加：
```python
app.include_router(admin.router)
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 启动服务**

```bash
cd backend && python run.py
```

- [ ] **Step 2: 验证 agent_audit_logs 表创建**

检查日志输出中是否有 `agent_audit_logs 表创建完成`

- [ ] **Step 3: 发送测试对话并验证审计日志**

```bash
curl -X POST http://localhost:9999/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{"pregnant_id": "P001", "message": "我最近有点焦虑怎么办？", "message_type": "TEXT"}'
```

预期：
- 路由到 `chat` variant（3 tools）
- `agent_audit_logs` 表写入一条记录
- `agent_variant` = "chat"

- [ ] **Step 4: 测试健康数据记录**

```bash
curl -X POST http://localhost:9999/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{"pregnant_id": "P001", "message": "我今天体重55公斤，血压120/80", "message_type": "TEXT"}'
```

预期：
- 路由到 `record` variant（4 tools）
- 数据保存成功

- [ ] **Step 5: 测试审计 API**

```bash
curl "http://localhost:9999/api/v1/admin/audit/token/daily?date_from=2026-05-23&date_to=2026-05-23"
curl "http://localhost:9999/api/v1/admin/audit/token/by-agent?date_from=2026-05-23&date_to=2026-05-23"
```

预期：返回 JSON 数组，包含刚才的调用记录

- [ ] **Step 6: 验证流式对话**

```bash
curl -N -X POST http://localhost:9999/api/v1/chat/send-stream \
  -H "Content-Type: application/json" \
  -d '{"pregnant_id": "P001", "message": "孕期可以喝咖啡吗？", "message_type": "TEXT"}'
```

预期：
- SSE 事件流正常输出
- 完成后 `agent_audit_logs` 表有对应记录
- `agent_variant` = "qa"

---

### 完成自检清单

- [ ] Agent 变体正确路由（chat/record/qa/emergency/complex）
- [ ] 审计日志每次调用写入一条记录（非流式 + 流式）
- [ ] 审计 API 三个端点正常返回数据
- [ ] System prompt 压缩后 Agent 行为无退化（回复质量不低于压缩前）
- [ ] `agent_sessions_pregnant.db` Session 跨变体连续（同一 session_id 的对话历史保持）
- [ ] 流式对话 thinking 事件正常展示
