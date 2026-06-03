# SOLID 原则重构方案

> 基于 Agno 框架约束和 Python 语言特性设计

## 核心约束分析

### Agno 框架约束
1. **`@tool` 不支持依赖注入** — 工具函数只接收 LLM 参数 + 按名称注入的 `run_context`
2. **`RunContext.dependencies`** 是自定义对象注入的唯一通道（`Agent(dependencies={...})`）
3. **`RunContext` 结构固定** — 不能添加泛型字段
4. **Guardrails** 必须遵循 `BaseGuardrail` 的 `check`/`async_check` 契约
5. **Hooks** 支持签名过滤，只传入声明的参数
6. **`Team`** 需要预先构建的 `Agent` 实例
7. **`Workflow`** 是线性步骤管道

### Python 语言特性
1. **`Protocol`** — 结构化子类型（鸭子类型），无需继承
2. **`dataclass`** — 轻量级配置对象
3. **`contextvars`** — 异步安全的上下文传播
4. **`singledispatch`** — 可扩展的分发机制
5. **模块级工厂函数** — Python 惯用的 DI 模式
6. **`lru_cache`** — 已有的单例缓存（保留）

---

## 阶段一：基础设施 — 服务接口 + DI 容器

### 1.1 创建服务接口层 (`app/interfaces/`)

**原则**: DIP — 高层模块依赖抽象，而非具体实现

```python
# app/interfaces/__init__.py
from .repositories import PatientRepository, AlertRepository, FollowUpRepository
from .storage import KeyValueStore
from .llm_service import LLMServiceProtocol
from .notification import NotificationService

# app/interfaces/repositories.py
from __future__ import annotations
from typing import Protocol, Optional
from datetime import date

class PatientRepository(Protocol):
    """患者数据仓储抽象"""
    def get_by_id(self, patient_id: str) -> Optional[dict]: ...
    def get_recent_health_data(self, patient_id: str, days: int = 7) -> list[dict]: ...
    def get_active_alerts(self, patient_id: str) -> list[dict]: ...

class AlertRepository(Protocol):
    """预警数据仓储抽象"""
    def create(self, pregnant_id: str, rule_id: str, domain: str,
               level: str, message: str, **kwargs) -> dict: ...
    def find_duplicate(self, pregnant_id: str, domain: str) -> Optional[dict]: ...
    def update_details(self, alert_id: str, details: dict) -> bool: ...

class FollowUpRepository(Protocol):
    """随访记录仓储抽象"""
    def get_by_id(self, record_id: str) -> Optional[dict]: ...
    def update_status(self, record_id: str, new_status: str) -> bool: ...
    def save_answers(self, record_id: str, answers: dict) -> bool: ...

# app/interfaces/storage.py
from typing import Protocol, Optional

class KeyValueStore(Protocol):
    """键值存储抽象 — 替代 MemoryManager 中的 Redis/内存分支"""
    def get(self, namespace: str, key: str) -> Optional[str]: ...
    def set(self, namespace: str, key: str, value: str, ttl: int | None = None) -> None: ...
    def delete(self, namespace: str, key: str) -> None: ...
    def get_all(self, namespace: str) -> dict[str, str]: ...
    def clear(self, namespace: str) -> None: ...

# app/interfaces/notification.py
from typing import Protocol

class NotificationService(Protocol):
    """通知服务抽象 — 替代直接依赖 ws_manager"""
    async def send_alert_to_doctor(self, doctor_id: str, alert_data: dict) -> None: ...
    async def broadcast_alert(self, alert_data: dict) -> None: ...
```

**为什么用 `Protocol` 而非 `ABC`**:
- Python 的 `Protocol` 是**结构化子类型**（鸭子类型的正式化）
- 实现类**不需要继承**任何东西，只要方法签名匹配即可
- 与 Agno 框架的 `@tool` 装饰器兼容（无 MRO 冲突）
- 更 Pythonic，符合"请求宽恕比许可更容易"的文化

### 1.2 创建轻量级 DI 容器 (`app/container.py`)

**原则**: 不引入第三方 DI 框架（如 `dependency-injector`），用 Python 原生方式

```python
# app/container.py
"""
轻量级依赖注入容器

设计理念:
- 使用 Python 模块级单例 + 工厂函数（Python 惯用模式）
- 不引入第三方 DI 框架，保持简单
- 通过 Agent(dependencies={...}) 桥接到 Agno 的 RunContext
"""
from __future__ import annotations
from typing import TypeVar, Type, Callable, Any
from functools import lru_cache
from loguru import logger

T = TypeVar("T")

class Container:
    """服务容器 — 管理服务实例的创建和生命周期"""

    def __init__(self) -> None:
        self._factories: dict[type, Callable] = {}
        self._singletons: dict[type, Any] = {}
        self._initialized = False

    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """注册工厂函数（每次调用创建新实例）"""
        self._factories[interface] = factory

    def register_singleton(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """注册单例工厂（首次调用后缓存）"""
        self._factories[interface] = factory

    def resolve(self, interface: Type[T]) -> T:
        """解析服务实例"""
        if interface in self._singletons:
            return self._singletons[interface]
        if interface in self._factories:
            instance = self._factories[interface]()
            # 如果是通过 register_singleton 注册的，缓存它
            # （通过 _is_singleton 标记区分）
            if getattr(self._factories[interface], '_singleton', False):
                self._singletons[interface] = instance
            return instance
        raise ValueError(f"未注册的服务: {interface.__name__}")

    def initialize(self) -> None:
        """初始化所有单例服务（应用启动时调用）"""
        if self._initialized:
            return
        for interface, factory in self._factories.items():
            if getattr(factory, '_singleton', False):
                self.resolve(interface)
        self._initialized = True
        logger.info("服务容器初始化完成")


def singleton(factory: Callable[[...], T]) -> Callable[[...], T]:
    """装饰器：标记工厂函数为单例"""
    factory._singleton = True
    return factory


# 全局容器实例
container = Container()


def setup_container() -> None:
    """配置所有服务绑定 — 应用启动时调用一次"""
    from .services.patient_repo_impl import SqlAlchemyPatientRepo
    from .services.alert_repo_impl import SqlAlchemyAlertRepo
    from .services.followup_repo_impl import SqlAlchemyFollowUpRepo
    from .services.redis_store import RedisKeyValueStore
    from .services.memory_store import InMemoryKeyValueStore
    from .services.notification_impl import WebSocketNotificationService
    from .config import settings

    # 注册仓储实现
    @singleton
    def make_patient_repo() -> PatientRepository:
        return SqlAlchemyPatientRepo()

    @singleton
    def make_alert_repo() -> AlertRepository:
        return SqlAlchemyAlertRepo()

    @singleton
    def make_followup_repo() -> FollowUpRepository:
        return SqlAlchemyFollowUpRepo()

    # 注册存储实现（根据配置选择 Redis 或内存）
    @singleton
    def make_kv_store() -> KeyValueStore:
        if settings.redis_url:
            return RedisKeyValueStore(settings.redis_url)
        return InMemoryKeyValueStore()

    # 注册通知服务
    @singleton
    def make_notification_service() -> NotificationService:
        return WebSocketNotificationService()

    container.register_singleton(PatientRepository, make_patient_repo)
    container.register_singleton(AlertRepository, make_alert_repo)
    container.register_singleton(FollowUpRepository, make_followup_repo)
    container.register_singleton(KeyValueStore, make_kv_store)
    container.register_singleton(NotificationService, make_notification_service)

    container.initialize()
```

### 1.3 桥接到 Agno 的 `RunContext`

**关键设计**: 通过 `Agent(dependencies={...})` 将服务注入到 Agno 工具中

```python
# app/core/agent_deps.py
"""
Agno Agent 依赖注入桥接层

将 DI 容器中的服务注入到 Agent 的 dependencies dict，
使 @tool 函数可以通过 run_context.dependencies 访问服务实例。
"""
from __future__ import annotations
from typing import Any
from ..container import container
from ..interfaces import PatientRepository, AlertRepository, KeyValueStore

def build_agent_dependencies() -> dict[str, Any]:
    """构建 Agent(dependencies={...}) 所需的字典"""
    return {
        "patient_repo": container.resolve(PatientRepository),
        "alert_repo": container.resolve(AlertRepository),
        "kv_store": container.resolve(KeyValueStore),
    }

# 工具函数中的使用模式:
# @tool
# def agno_save_health_data(run_context: RunContext, pregnant_id: str, weight: float = 0):
#     repo = run_context.dependencies["patient_repo"]
#     repo.save_health_data(pregnant_id, weight=weight)
```

**Agno 约束适配**: `@tool` 装饰器不支持构造器注入，但 `run_context.dependencies` 提供了等效的运行时注入通道。

---

## 阶段二：拆分 God Modules

### 2.1 拆分 `agno_tools.py` (1060行 → 8个模块)

**原则**: SRP — 每个模块一个职责

```
app/core/tools/
├── __init__.py              # 统一导出 MEDICAL_TOOLS, NURSE_TOOLS, DOCTOR_TOOLS
├── nlu_tools.py             # NLU 解析 + 急诊检测（3个工具）
├── health_data_tools.py     # 健康数据持久化 + 查询（5个工具）
├── vital_rules_tools.py     # 生命体征规则评估（1个工具）
├── trend_tools.py           # 趋势分析 + EPDS 心理筛查（2个工具）
├── nurse_tools.py           # 护士专用工具（3个工具）
├── doctor_tools.py          # 医生专用工具（4个工具）
├── clinical_tools.py        # 临床指南查询（1个工具）
├── nlu_context.py           # NLU 上下文管理（线程安全）
└── routing.py               # 工具路由 + 意图映射
```

**重构示例** — `health_data_tools.py`:

```python
# app/core/tools/health_data_tools.py
"""
健康数据工具 — 负责健康指标的持久化和查询

职责: 体重/血压/胎动/血糖/心率/睡眠数据的保存、查询、提醒
"""
from agno.tools import tool
from agno.run import RunContext

@tool
async def agno_save_health_data(
    run_context: RunContext,
    pregnant_id: str,
    weight: float = 0, sbp: float = 0, dbp: float = 0,
    fetal_movement: int = 0, blood_sugar: float = 0,
    heart_rate: float = 0, sleep_hours: float = 0, steps: int = 0,
) -> dict:
    """保存孕妇健康数据（体重、血压、胎动、血糖、心率、睡眠、步数）"""
    import asyncio
    from ..health_data_service import save_health_metrics

    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"success": False, "error": "缺少孕妇ID"}

    metrics = {}
    if weight > 0: metrics["weight"] = weight
    if sbp > 0: metrics["sbp"] = sbp
    # ... 其余指标

    result = await asyncio.to_thread(save_health_metrics, pid, metrics, "CHAT")
    return {"success": True, "saved": list(metrics.keys())}


@tool
async def agno_get_patient_context(run_context: RunContext, pregnant_id: str = "") -> dict:
    """获取孕妇完整上下文（基本信息 + 近期数据 + 活跃预警）"""
    import asyncio
    from ..patient_context_service import get_patient_basic, get_recent_health_data, get_active_alerts

    pid = _resolve_pid(pregnant_id, run_context)
    if not pid:
        return {"error": "缺少孕妇ID"}

    basic, recent, alerts = await asyncio.gather(
        asyncio.to_thread(get_patient_basic, pid),
        asyncio.to_thread(get_recent_health_data, pid),
        asyncio.to_thread(get_active_alerts, pid),
    )
    return {"basic_info": basic, "recent_data": recent, "active_alerts": alerts}
```

**工具注册** — `__init__.py`:

```python
# app/core/tools/__init__.py
"""工具注册中心 — 按角色和意图分组"""

from .nlu_tools import agno_parse_nlu, agno_get_nlu_result, agno_check_emergency
from .health_data_tools import (
    agno_save_health_data, agno_get_patient_context,
    agno_should_ask_weight, agno_should_ask_bp,
    agno_analyze_health_trends, agno_get_epds_result,
)
from .vital_rules_tools import agno_evaluate_vital_rules
from .nurse_tools import agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor
from .doctor_tools import (
    agno_analyze_patient_comprehensive, agno_generate_medical_order,
    agno_handle_issue, agno_query_clinical_guideline,
)

# 按角色分组
MEDICAL_TOOLS = [
    agno_parse_nlu, agno_get_nlu_result, agno_check_emergency,
    agno_evaluate_vital_rules, agno_save_health_data, agno_get_patient_context,
    agno_should_ask_weight, agno_should_ask_bp, agno_analyze_health_trends,
    agno_get_epds_result, agno_query_patient_data, agno_create_followup_record,
    agno_report_issue_to_doctor, agno_analyze_patient_comprehensive,
    agno_generate_medical_order, agno_handle_issue, agno_query_clinical_guideline,
]

NURSE_TOOLS = [agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor]
DOCTOR_TOOLS = [agno_analyze_patient_comprehensive, agno_generate_medical_order, agno_handle_issue]

# 意图 → 工具组映射（从 routing.py 导入）
from .routing import TOOL_GROUPS, NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS, resolve_tools_by_intent
```

### 2.2 拆分 `agno_chat_handler.py` — 消除 DRY 违反

**原则**: SRP + DRY — 提取共享逻辑，流式/非流式只负责响应格式

```python
# app/core/chat_handler.py
"""
聊天处理器 — 重构后

核心改进:
- 提取共享的 NLU 分类 + 路由 + 审计逻辑
- 流式和非流式各自只负责响应格式化
- 消除 80% 的代码重复
"""
from __future__ import annotations
from typing import AsyncGenerator
from loguru import logger

async def _classify_and_route(req, transcribed_text: str | None) -> dict:
    """共享: NLU 分类 + Agent 路由"""
    from .nlu_engine import nlu_engine
    from .agno_tools import resolve_tools_by_intent, set_nlu_context
    from .agno_agent import AGENT_VARIANT_MAP, get_main_agent

    text = transcribed_text or req.message
    nlu_result = nlu_engine.parse(text)

    # LLM 辅助意图细化
    if nlu_result.category in (IntentCategory.CHAT, IntentCategory.UNKNOWN):
        refined = nlu_engine.classify_with_llm(text)
        if refined:
            nlu_result.intent = refined

    # 工具路由
    tools, intent_variant = resolve_tools_by_intent(nlu_result)
    set_nlu_context(req.session_id, {"nlu": nlu_result, "tools": tools})

    # Agent 选择
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()

    return {
        "nlu_result": nlu_result,
        "agent": agent,
        "variant": intent_variant,
        "tools": tools,
    }


async def _post_process(response, ctx: dict, req) -> None:
    """共享: 审计日志 + 对话持久化"""
    from ..database import db_call
    from .conversation_store import conversation_store
    await db_call(_save_audit_log, ...)
    await db_call(conversation_store.save_message, ...)


async def handle_chat_with_agno(req) -> ChatResponse:
    """非流式聊天"""
    session_id = _generate_session_id(req.pregnant_id)
    transcribed = await _handle_asr(req)
    ctx = await _classify_and_route(req, transcribed)

    response = await ctx["agent"].arun(
        input=_build_multimodal_input(req, transcribed),
        session_id=session_id,
        user_id=req.pregnant_id,
    )
    await _post_process(response, ctx, req)
    return ChatResponse(reply=response.content, ...)


async def handle_chat_with_agno_stream(req) -> AsyncGenerator[dict, None]:
    """流式聊天 — 只负责 SSE 格式化"""
    session_id = _generate_session_id(req.pregnant_id)
    transcribed = await _handle_asr(req)
    ctx = await _classify_and_route(req, transcribed)

    async for event in ctx["agent"].arun(
        input=_build_multimodal_input(req, transcribed),
        session_id=session_id,
        user_id=req.pregnant_id,
        stream=True,
    ):
        yield _format_sse_event(event, ctx)

    await _post_process(None, ctx, req)
```

### 2.3 拆分 `agno_medical_agents.py` (434行 → 4个模块)

```
app/core/
├── schemas/
│   ├── __init__.py
│   ├── nurse_schemas.py       # NurseAnalysisOutput, FollowUpQuestion
│   ├── doctor_schemas.py      # DoctorAnalysisOutput
│   ├── followup_schemas.py    # FollowUpGenerateOutput, FollowUpAnalysisOutput, FollowUpAiReviewOutput
│   └── chat_schemas.py        # ChatOutput
├── agent_factories/
│   ├── __init__.py            # 统一导出所有 get_*_agent
│   ├── nurse_factory.py       # 护士 Agent 工厂
│   ├── doctor_factory.py      # 医生 Agent 工厂
│   └── followup_factory.py    # 随访 Agent 工厂
└── formatters.py              # format_structured_output_to_markdown
```

**`formatters.py` — 用 `singledispatch` 替代 `isinstance` 链**:

```python
# app/core/formatters.py
"""结构化输出格式化 — 使用 singledispatch 实现 OCP"""
from functools import singledispatch
from .schemas.nurse_schemas import NurseAnalysisOutput
from .schemas.doctor_schemas import DoctorAnalysisOutput
from .schemas.followup_schemas import FollowUpGenerateOutput, FollowUpAnalysisOutput

@singledispatch
def format_to_markdown(content) -> str | None:
    """通用格式化 — 未知类型返回 JSON"""
    import json
    if hasattr(content, "model_dump"):
        return json.dumps(content.model_dump(), ensure_ascii=False, indent=2)
    return str(content)

@format_to_markdown.register
def _(content: NurseAnalysisOutput) -> str:
    lines = [f"## 护理分析报告\n"]
    if content.risk_level:
        lines.append(f"**风险等级**: {content.risk_level}")
    if content.summary:
        lines.append(f"**分析摘要**: {content.summary}")
    # ... 结构化格式化
    return "\n".join(lines)

@format_to_markdown.register
def _(content: DoctorAnalysisOutput) -> str:
    lines = [f"## 医生分析报告\n"]
    # ... 结构化格式化
    return "\n".join(lines)

# 新增输出类型只需:
# @format_to_markdown.register
# def _(content: NewOutputType) -> str: ...
# 无需修改任何已有代码 — OCP 合规
```

### 2.4 拆分 `followup.py` 路由器 (1113行 → 4个模块)

```
app/routers/followup/
├── __init__.py              # 聚合 router
├── crud.py                  # 触发、查询、更新、签名、确认
├── ai_review.py             # AI 审核（3级回退）
├── patient_response.py      # 患者应答工作流
└── health_data.py           # 健康数据提取 + 持久化
```

---

## 阶段三：消除 OCP 违反 — 注册表/策略模式

### 3.1 警报动作注册表

**原则**: OCP — 新增动作只需注册，无需修改 `review_alert`

```python
# app/services/alert_actions.py
"""
警报审核动作注册表

替代 alerts.py 中 review_alert 的 9-branch if/elif 链。
新增动作只需定义类并调用 register_action()。
"""
from __future__ import annotations
from typing import Protocol, Optional
from sqlalchemy.orm import Session
from ..models import Alert

class AlertActionHandler(Protocol):
    """警报动作处理协议"""
    def execute(self, alert: Alert, payload: dict, db: Session) -> dict:
        """
        执行审核动作

        Args:
            alert: 当前预警记录
            payload: 请求体（含 reason, target_level 等）
            db: 数据库会话

        Returns:
            dict: {"new_status": str, "new_level": str, "message": str}
        """
        ...

_registry: dict[str, AlertActionHandler] = {}

def register_action(name: str, handler: AlertActionHandler) -> None:
    """注册警报审核动作"""
    _registry[name] = handler

def get_action(name: str) -> Optional[AlertActionHandler]:
    """获取动作处理器"""
    return _registry.get(name)

def list_actions() -> list[str]:
    """列出所有已注册的动作"""
    return list(_registry.keys())


# --- 内置动作实现 ---

class ConfirmAction:
    """确认预警"""
    def execute(self, alert: Alert, payload: dict, db: Session) -> dict:
        alert.status = "confirmed"
        alert.reviewed_by = payload.get("operator", "doctor")
        return {"new_status": "confirmed", "message": "预警已确认"}

class DismissAction:
    """驳回预警"""
    def execute(self, alert: Alert, payload: dict, db: Session) -> dict:
        alert.status = "dismissed"
        return {"new_status": "dismissed", "message": "预警已驳回"}

class EscalateAction:
    """升级预警"""
    LEVEL_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

    def execute(self, alert: Alert, payload: dict, db: Session) -> dict:
        current = self.LEVEL_ORDER.get(alert.level, 0)
        target = payload.get("target_level", "red")
        target_ord = self.LEVEL_ORDER.get(target, 3)
        if target_ord <= current:
            return {"new_level": alert.level, "message": "目标等级需高于当前等级"}
        alert.level = target
        return {"new_level": target, "message": f"预警已升级至 {target}"}

class NurseEscalateAction:
    """护士逐级升级（YELLOW→ORANGE→RED）"""
    LEVEL_STEPS = {"yellow": "orange", "orange": "red"}

    def execute(self, alert: Alert, payload: dict, db: Session) -> dict:
        next_level = self.LEVEL_STEPS.get(alert.level, "red")
        alert.level = next_level
        return {"new_level": next_level, "message": f"护士升级至 {next_level}"}

# 注册
register_action("confirm", ConfirmAction())
register_action("dismiss", DismissAction())
register_action("escalate", EscalateAction())
register_action("nurse_escalate", NurseEscalateAction())
# register_action("downgrade", DowngradeAction())
# register_action("supplement", SupplementAction())
# register_action("nurse_confirm", NurseConfirmAction())
# register_action("nurse_dismiss", NurseDismissAction())
# register_action("nurse_appeal", NurseAppealAction())
```

**重构后的 `review_alert`**:

```python
# app/routers/alerts.py — review_alert 从 ~100 行简化为 ~20 行
from ..services.alert_actions import get_action, list_actions

@router.patch("/{alert_id}/review")
async def review_alert(alert_id: str, review: AlertReviewRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(404, "预警不存在")

    handler = get_action(review.action)
    if not handler:
        raise HTTPException(400, f"未知动作: {review.action}，可用: {list_actions()}")

    result = handler.execute(alert, review.model_dump(), db)
    _append_history(alert, review.action, review.source_role, alert.level, ...)

    # WebSocket 通知
    ws_data = {"alert_id": str(alert.id), "action": review.action, **result}
    await ws_manager.route_alert(alert.level, ws_data)

    db.commit()
    return {"success": True, **result}
```

### 3.2 ASR 后端策略模式

```python
# app/services/asr_backends.py
"""ASR 后端策略 — 新增后端只需实现 ASRBackend 协议"""
from __future__ import annotations
from typing import Protocol, Optional

class ASRBackend(Protocol):
    """ASR 后端协议"""
    async def transcribe(self, audio_base64: str, audio_format: str) -> str: ...

class DashScopeASRBackend:
    """阿里云 DashScope 语音识别"""
    def __init__(self, api_key: str): ...
    async def transcribe(self, audio_base64: str, audio_format: str) -> str: ...

class FunASRBackend:
    """FunASR 本地服务"""
    def __init__(self, server_url: str): ...
    async def transcribe(self, audio_base64: str, audio_format: str) -> str: ...

class WhisperBackend:
    """Whisper 本地推理"""
    def __init__(self, model_name: str = "base"): ...
    async def transcribe(self, audio_base64: str, audio_format: str) -> str: ...

# app/services/asr_service.py — 重构后
class ASRService:
    """ASR 服务 — 通过注入的后端执行转录"""
    def __init__(self, backend: ASRBackend):
        self._backend = backend

    async def transcribe(self, audio_base64: str, audio_format: str, role: str = "pregnant") -> str:
        return await self._backend.transcribe(audio_base64, audio_format)

# 工厂函数（根据配置选择后端）
def create_asr_service() -> ASRService:
    from ..config import settings
    mode = settings.asr_mode
    if mode == "cloud":
        return ASRService(DashScopeASRBackend(settings.asr_api_key))
    elif mode == "local":
        backend = settings.asr_local_backend
        if backend == "funasr":
            return ASRService(FunASRBackend(settings.funasr_server_url))
        else:
            return ASRService(WhisperBackend(settings.whisper_model))
    return ASRService(MockASRBackend())
```

### 3.3 TTS 后端策略模式（同理）

```python
# app/services/tts_backends.py
class TTSBackend(Protocol):
    async def synthesize(self, text: str) -> bytes: ...

class DashScopeTTSBackend: ...
class EdgeTTSBackend: ...
class BrowserTTSBackend: ...

class TTSService:
    def __init__(self, backend: TTSBackend):
        self._backend = backend

    async def synthesize(self, text: str, role: str = "pregnant") -> bytes:
        return await self._backend.synthesize(text)
```

### 3.4 FollowUp 模板选择器 — 规则表替代 if/elif

```python
# app/services/followup_template_selector.py
"""
随访模板选择器 — 规则表替代 if/elif 链

新增模板只需添加 TemplateRule，无需修改 select_template。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class TemplateRule:
    """模板选择规则"""
    template_id: str
    priority: int
    risk_tag: Optional[str] = None
    gest_week_min: int = 0
    gest_week_max: int = 45

    def matches(self, risk_tags: list[str], gest_week: int) -> bool:
        if self.risk_tag and self.risk_tag not in risk_tags:
            return False
        if not (self.gest_week_min <= gest_week <= self.gest_week_max):
            return False
        return True

# 规则表（按优先级排序，高优先级先匹配）
_TEMPLATE_RULES: list[TemplateRule] = [
    TemplateRule("fgr_high_risk",    priority=100, risk_tag="FGR"),
    TemplateRule("gdm",              priority=90,  risk_tag="GDM"),
    TemplateRule("hypertension",     priority=90,  risk_tag="HYPERTENSION"),
    TemplateRule("mental_health",    priority=80,  risk_tag="MENTAL_HEALTH"),
    TemplateRule("post_discharge",   priority=70,  risk_tag="POST_DISCHARGE"),
    TemplateRule("early_pregnancy",  priority=50,  gest_week_min=0, gest_week_max=12),
    TemplateRule("late_pregnancy",   priority=50,  gest_week_min=28, gest_week_max=45),
    TemplateRule("standard",         priority=0),   # 默认
]

def register_template_rule(rule: TemplateRule) -> None:
    """注册新的模板选择规则"""
    _TEMPLATE_RULES.append(rule)
    _TEMPLATE_RULES.sort(key=lambda r: r.priority, reverse=True)

def select_template(risk_tags: list[str], gest_week: int) -> tuple[str, dict]:
    """选择最匹配的随访模板"""
    for rule in _TEMPLATE_RULES:
        if rule.matches(risk_tags, gest_week):
            return rule.template_id, TEMPLATES[rule.template_id]
    return "standard", TEMPLATES["standard"]
```

---

## 阶段四：配置拆分

**原则**: ISP — 每个消费者只依赖自己需要的配置子集

```python
# app/config.py — 重构为嵌套模型
from pydantic_settings import BaseSettings
from pydantic import Field

class LLMConfig(BaseSettings):
    """LLM 配置"""
    mode: str = "cloud"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048

class PerRoleLLMConfig(BaseSettings):
    """按角色的 LLM 配置"""
    pregnant: LLMConfig = LLMConfig()
    nurse: LLMConfig = LLMConfig()
    doctor: LLMConfig = LLMConfig()

class ASRConfig(BaseSettings):
    """语音识别配置"""
    mode: str = "cloud"
    provider: str = "dashscope"
    api_key: str = ""
    local_backend: str = "funasr"
    funasr_url: str = "http://localhost:10095"

class TTSConfig(BaseSettings):
    """语音合成配置"""
    mode: str = "browser"
    provider: str = "dashscope"
    api_key: str = ""

class DatabaseConfig(BaseSettings):
    """数据库配置"""
    db_type: str = "sqlite"
    database_url: str = "sqlite:///./pregnant_care.db"

class RedisConfig(BaseSettings):
    """Redis 配置"""
    url: str = ""

class RAGConfig(BaseSettings):
    """RAG 知识库配置"""
    enabled: bool = True
    search_type: str = "hybrid"
    embedding_model: str = ""
    embedding_api_key: str = ""

class Settings(BaseSettings):
    """应用配置 — 各域独立，消费者按需访问"""
    app_name: str = "pregnant-care-agent"
    debug: bool = False

    llm: PerRoleLLMConfig = PerRoleLLMConfig()
    asr: ASRConfig = ASRConfig()
    tts: TTSConfig = TTSConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    rag: RAGConfig = RAGConfig()

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"

# 消费者只导入自己需要的:
# from ..config import settings
# db_url = settings.database.database_url  # 只访问数据库配置
# llm_key = settings.llm.pregnant.api_key  # 只访问孕妇 LLM 配置
```

---

## 阶段五：正式状态机

```python
# app/core/state_machine.py
"""
随访记录状态机 — 集中定义所有状态转换

替代散布在 trigger_followup、respond_to_followup、confirm_record、
sign_record 中的 ad-hoc if 检查。
"""
from __future__ import annotations
from enum import Enum
from typing import Callable, Optional
from dataclasses import dataclass, field

class FollowUpStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"

@dataclass
class Transition:
    source: FollowUpStatus
    target: FollowUpStatus
    trigger: str
    guard: Optional[Callable[[dict], bool]] = None
    action: Optional[Callable[[dict], None]] = None

class FollowUpStateMachine:
    def __init__(self):
        self._transitions: list[Transition] = []

    def add(self, source: FollowUpStatus, target: FollowUpStatus,
            trigger: str, guard=None, action=None) -> None:
        self._transitions.append(Transition(source, target, trigger, guard, action))

    def can_transition(self, current: FollowUpStatus, trigger: str, ctx: dict) -> bool:
        for t in self._transitions:
            if t.source == current and t.trigger == trigger:
                return t.guard is None or t.guard(ctx)
        return False

    def transition(self, current: FollowUpStatus, trigger: str, ctx: dict) -> FollowUpStatus:
        for t in self._transitions:
            if t.source == current and t.trigger == trigger:
                if t.guard and not t.guard(ctx):
                    raise InvalidTransition(f"Guard failed: {current} --{trigger}--> {t.target}")
                if t.action:
                    t.action(ctx)
                return t.target
        raise InvalidTransition(f"无效转换: {current} --{trigger}--> ?")

    def allowed_triggers(self, current: FollowUpStatus) -> list[str]:
        return [t.trigger for t in self._transitions if t.source == current]


# 全局状态机实例
followup_fsm = FollowUpStateMachine()

# 注册所有转换
followup_fsm.add(FollowUpStatus.DRAFT,       FollowUpStatus.IN_PROGRESS, "start")
followup_fsm.add(FollowUpStatus.IN_PROGRESS,  FollowUpStatus.COMPLETED,  "complete")
followup_fsm.add(FollowUpStatus.COMPLETED,    FollowUpStatus.CONFIRMED,  "confirm")
followup_fsm.add(FollowUpStatus.CONFIRMED,    FollowUpStatus.ARCHIVED,   "archive")

class InvalidTransition(Exception):
    pass
```

**路由中使用**:

```python
# app/routers/followup/crud.py
from ...core.state_machine import followup_fsm, FollowUpStatus, InvalidTransition

@router.post("/{record_id}/confirm")
def confirm_record(record_id: str, confirm: FollowUpConfirm, db: Session = Depends(get_db)):
    record = db.query(FollowUpRecord).get(record_id)
    if not record:
        raise HTTPException(404, "记录不存在")

    try:
        new_status = followup_fsm.transition(
            FollowUpStatus(record.status),
            "confirm",
            {"operator": confirm.operator}
        )
        record.status = new_status.value
        db.commit()
    except InvalidTransition as e:
        raise HTTPException(400, str(e))

    return {"success": True, "new_status": new_status.value}
```

---

## 实施路线图

```
第1周: 阶段一 (基础设施)
├── 创建 app/interfaces/ — 所有 Protocol 定义
├── 创建 app/container.py — DI 容器
├── 创建 app/core/agent_deps.py — Agno 桥接层
└── 创建仓储实现 app/services/*_repo_impl.py

第2周: 阶段二前半 (拆分 agno_tools.py)
├── 创建 app/core/tools/ 目录结构
├── 拆分 17 个工具函数到 8 个模块
├── 创建 routing.py 路由映射
└── 更新所有 import 路径

第3周: 阶段二后半 (拆分其他 God Modules)
├── 拆分 agno_chat_handler.py — 提取共享逻辑
├── 拆分 agno_medical_agents.py — schemas + factories + formatters
├── 拆分 followup.py — CRUD + AI审核 + 患者应答
└── 更新所有 import 路径

第4周: 阶段三 (OCP 合规)
├── 创建 alert_actions.py 注册表
├── 创建 asr_backends.py / tts_backends.py 策略
├── 创建 followup_template_selector.py 规则表
└── 重构各处 if/elif 链

第5周: 阶段四 + 五 (配置 + 状态机)
├── 重构 config.py 为嵌套模型
├── 创建 state_machine.py
├── 更新所有消费 config 的模块
└── 集成测试
```

---

## 重构前后对比

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| 最大文件行数 | 1113 (followup.py) | ~250 |
| `agno_tools.py` 行数 | 1060 | ~100 (注册 + 导出) |
| if/elif 分发链 | 12+ 处 | 0（全部改为注册表/策略） |
| 全局单例 | 20+ 个 module-level | 通过 DI 容器统一管理 |
| 可测试性 | 无法 mock | 通过 Protocol 注入 mock |
| 新增 LLM 提供商 | 修改 3 个文件 | 实现 LLMClient + 注册 |
| 新增 ASR 后端 | 修改 ASRService 内部 | 实现 ASRBackend + 注册 |
| 新增警报动作 | 修改 review_alert 100 行 | 实现 AlertActionHandler + 注册 |
| 新增随访模板 | 修改 select_template | 添加 TemplateRule |

---

## Python/Agno 特定注意事项

1. **保留 `@lru_cache` 单例** — Agent 工厂函数的 `@lru_cache(maxsize=1)` 是 Agno 的惯用模式，保持不变
2. **保留 `RunContext` 模式** — 工具函数继续通过 `run_context: RunContext | None = None` 接收上下文
3. **通过 `dependencies` 注入服务** — `Agent(dependencies=build_agent_dependencies())` 是 Agno 兼容的 DI 方式
4. **`Protocol` 替代 `ABC`** — 更 Pythonic，无 MRO 冲突，与 Agno 的 `@tool` 装饰器兼容
5. **`singledispatch` 替代 `isinstance` 链** — 格式化函数的 OCP 合规方式
6. **`dataclass` 替代大型 dict 字面量** — 配置和规则的类型安全表示
7. **渐进式重构** — 每个阶段独立可部署，不需要一次性重写
