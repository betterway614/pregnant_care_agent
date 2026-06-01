# Agno 架构优化实施计划 (P0/P1/P3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 NLU 重复调用、合并冗余意图模块、增强 UNKNOWN 意图处理、统一预警分析路径、加强药物剂量安全防护

**Architecture:** 保持现有 NLU→Variant 路由架构不变，仅在各环节做精确手术式优化。核心改动：(1) 用 session_state 注入替代重复的 NLU 工具调用；(2) 将 intent_classifier 并入 nlu_engine 作为统一事实来源；(3) UNKNOWN 意图触发轻量 LLM 二次分类；(4) 统一预警分析到 Workflow 路径。

**Tech Stack:** Python 3.13, Agno (Agent/Tool/Workflow), SQLAlchemy, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/core/nlu_engine.py` | 合并 IntentCategory 枚举 + category 字段 + LLM 分类方法 |
| Modify | `backend/app/core/agno_tools.py` | 新增 `agno_get_nlu_result` 工具，替换 TOOL_GROUPS 中的 `agno_parse_nlu` |
| Modify | `backend/app/core/agno_chat_handler.py` | 注入 NLU 结果到 Agent context，UNKNOWN 时调用 LLM 分类 |
| Modify | `backend/app/core/agno_guardrails.py` | 增加药物剂量模式检测 |
| Modify | `backend/app/services/alert_analysis_service.py` | `enrich_alert_with_llm` 改用 Workflow 路径 |
| Modify | `backend/app/core/agno_agent.py` | MEDICAL_TOOLS 列表更新 |
| Delete | `backend/app/core/intent_classifier.py` | 合并到 nlu_engine 后删除 |
| Modify | `backend/tests/test_intent_classifier.py` | 改为测试 nlu_engine 的 category 输出 |
| Modify | `backend/tests/test_agno_tools.py` | 更新工具名和计数断言 |
| Modify | `backend/tests/test_agno_guardrails.py` | 新增药物剂量拦截测试 |
| Create | `backend/tests/test_nlu_llm_fallback.py` | LLM 分类 fallback 测试 |

---

## Task 1: P0-1 — 消除 NLU 重复调用，注入 session_state

**背景：** `handle_chat_with_agno_stream` 已在路由层同步执行 `nlu_engine.parse()`，但 `agno_parse_nlu` 仍注册为 Agent 工具，Agent 可能再次调用它（浪费一次 tool_call 配额和 token）。用新的 `agno_get_nlu_result` 替换，从 session_state 读取已解析结果。

**Files:**
- Modify: `backend/app/core/agno_tools.py:44-54` (新增工具) + `:818-840` (TOOL_GROUPS) + `:398` (MEDICAL_TOOLS)
- Modify: `backend/app/core/agno_chat_handler.py:280-302` (注入 NLU 结果)
- Modify: `backend/tests/test_agno_tools.py:10-17` + `:88-91` (更新测试)
- Modify: `backend/tests/test_agno_agent.py:67-73` + `:84-102` (更新计数)

### Step 1: 新增 `agno_get_nlu_result` 工具

在 `backend/app/core/agno_tools.py` 中，找到 `agno_parse_nlu` 函数定义（第 44 行），在其下方新增工具：

```python
@tool
def agno_get_nlu_result(run_context: RunContext | None = None) -> dict:
    """获取当前消息的已解析 NLU 结果（意图、实体、情绪）。
    结果由系统在路由阶段预计算并注入，无需再次解析。"""
    # 优先从 session_state 读取（如果 Agno 支持注入）
    if run_context is not None and hasattr(run_context, "session_state"):
        nlu = run_context.session_state.get("nlu_result")
        if nlu:
            return nlu
    # 从模块级上下文读取（按 session_id 查找）
    if run_context is not None and hasattr(run_context, "session_id"):
        from ..core.agno_chat_handler import _nlu_context
        nlu = _nlu_context.get(run_context.session_id)
        if nlu:
            return nlu
    return {
        "intent": "UNKNOWN",
        "entities": {},
        "emotion": {"level": "neutral", "score": 0},
        "is_emergency": False,
        "note": "NLU结果未注入，使用默认值",
    }
```

### Step 2: 更新 TOOL_GROUPS 和 MEDICAL_TOOLS

在 `backend/app/core/agno_tools.py` 中：

将 `MEDICAL_TOOLS`（第 398 行）中的 `agno_parse_nlu` 替换为 `agno_get_nlu_result`：

```python
MEDICAL_TOOLS = [
    agno_get_nlu_result,      # 替换 agno_parse_nlu
    agno_check_emergency,
    agno_evaluate_vital_rules,
    agno_save_health_data,
    agno_get_patient_context,
    agno_should_ask_weight,
    agno_should_ask_bp,
    agno_analyze_health_trends,
    agno_search_knowledge,
    agno_get_epds_result,
]
```

将 `TOOL_GROUPS["chat"]`（第 820 行）中的 `agno_parse_nlu` 替换为 `agno_get_nlu_result`：

```python
"chat": [
    agno_get_nlu_result,      # 替换 agno_parse_nlu
    agno_check_emergency,
    agno_get_patient_context,
],
```

将 `TOOL_GROUPS["record"]`（第 825 行）中的 `agno_parse_nlu` 替换为 `agno_get_nlu_result`：

```python
"record": [
    agno_get_nlu_result,      # 替换 agno_parse_nlu
    agno_save_health_data,
    agno_evaluate_vital_rules,
    agno_get_patient_context,
],
```

### Step 3: 注入 NLU 结果到模块级上下文

Agno 的 `agent.arun()` 不一定接受 `session_state` 关键字参数。使用模块级上下文字典作为可靠的传递通道。

在 `backend/app/core/agno_chat_handler.py` 文件顶部（imports 之后）新增：

```python
# NLU 结果上下文：由路由层注入，供 agno_get_nlu_result 工具读取
# key: session_id, value: NLU result dict
_nlu_context: dict[str, dict] = {}
```

然后在 `handle_chat_with_agno_stream` 的 NLU 解析部分（第 297 行 `resolve_tools_by_intent` 之后），注入到上下文：

```python
            from .agno_tools import resolve_tools_by_intent
            _, intent_variant = resolve_tools_by_intent(nlu_dict)

            # 注入 NLU 结果到模块级上下文，供 agno_get_nlu_result 工具读取
            _nlu_context[session_id] = nlu_dict
    except Exception:
        logger.warning("NLU意图分类失败，使用兜底Agent", exc_info=True)

    # 2. Agent 路由
    agent_factory = AGENT_VARIANT_MAP.get(intent_variant, get_main_agent)
    agent = agent_factory()
```

在函数末尾（对话持久化之后）清理上下文：

```python
    # 清理 NLU 上下文（单次请求生命周期）
    _nlu_context.pop(session_id, None)
```

对 `handle_chat_with_agno`（非流式版本）做同样的注入和清理。

然后修改 `agno_get_nlu_result` 工具，改为从模块级上下文读取：

```python
@tool
def agno_get_nlu_result(run_context: RunContext | None = None) -> dict:
    """获取当前消息的已解析 NLU 结果（意图、实体、情绪）。
    结果由系统在路由阶段预计算并注入，无需再次解析。"""
    # 优先从 session_state 读取（如果 Agno 支持注入）
    if run_context is not None and hasattr(run_context, "session_state"):
        nlu = run_context.session_state.get("nlu_result")
        if nlu:
            return nlu
    # 从模块级上下文读取（按 session_id 查找）
    if run_context is not None and hasattr(run_context, "session_id"):
        from ..core.agno_chat_handler import _nlu_context
        nlu = _nlu_context.get(run_context.session_id)
        if nlu:
            return nlu
    return {
        "intent": "UNKNOWN",
        "entities": {},
        "emotion": {"level": "neutral", "score": 0},
        "is_emergency": False,
        "note": "NLU结果未注入，使用默认值",
    }
```

### Step 4: 更新测试 — agno_tools.py

在 `backend/tests/test_agno_tools.py` 中，将 `test_agno_parse_nlu_content` 测试更新为测试新工具：

```python
def test_agno_get_nlu_result_with_session_state():
    """验证 agno_get_nlu_result 从 session_state 读取 NLU 结果"""
    from app.core.agno_tools import agno_get_nlu_result

    mock_context = MagicMock()
    mock_context.session_state = {
        "nlu_result": {
            "intent": "HEALTH_DATA_REPORT",
            "entities": {"weight": 65.0},
            "emotion": {"level": "neutral", "score": 0},
            "is_emergency": False,
        }
    }
    mock_context.session_id = "test-session"
    result = agno_get_nlu_result.entrypoint(run_context=mock_context)
    assert result["intent"] == "HEALTH_DATA_REPORT"
    assert result["entities"]["weight"] == 65.0


def test_agno_get_nlu_result_from_module_context():
    """验证 agno_get_nlu_result 从模块级上下文读取"""
    from app.core.agno_tools import agno_get_nlu_result
    from app.core.agno_chat_handler import _nlu_context

    session_id = "test-session-ctx"
    _nlu_context[session_id] = {
        "intent": "EMOTION_EXPRESS",
        "entities": {},
        "emotion": {"level": "medium", "score": 2},
        "is_emergency": False,
    }

    mock_context = MagicMock()
    mock_context.session_state = {}
    mock_context.session_id = session_id

    result = agno_get_nlu_result.entrypoint(run_context=mock_context)
    assert result["intent"] == "EMOTION_EXPRESS"

    # 清理
    _nlu_context.pop(session_id, None)


def test_agno_get_nlu_result_without_context():
    """验证 agno_get_nlu_result 无 context 时返回默认值"""
    from app.core.agno_tools import agno_get_nlu_result

    result = agno_get_nlu_result.entrypoint()
    assert result["intent"] == "UNKNOWN"
    assert "note" in result
```

删除旧的 `test_agno_parse_nlu_content` 测试。

### Step 5: 更新测试 — tool counts

在 `backend/tests/test_agno_tools.py` 中，工具计数不变（3/4/3/2），但需要确认 `TOOL_GROUPS` 测试中的工具名验证。`test_tool_groups_are_disjoint_from_nurse_doctor` 测试基于工具名集合比较，更新后仍应通过（只是名字变了）。

在 `backend/tests/test_agno_agent.py` 中，变体测试的工具数量不变（3/4/3/2/10），无需修改。

### Step 6: 运行测试验证

Run: `cd backend && python -m pytest tests/test_agno_tools.py tests/test_agno_agent.py -v`
Expected: 所有测试 PASS

### Step 7: Commit

```bash
git add backend/app/core/agno_tools.py backend/app/core/agno_chat_handler.py backend/tests/test_agno_tools.py
git commit -m "refactor: replace agno_parse_nlu with agno_get_nlu_result to eliminate duplicate NLU calls"
```

---

## Task 2: P0-2 — 合并 intent_classifier 到 nlu_engine

**背景：** `intent_classifier.py` 和 `nlu_engine.py` 对同一文本做意图分类，返回不同的枚举。`intent_classifier.py` 仅在 `agno_workflow.py` 和 `nurse_ai.py`/`doctor_ai.py` 的少量路径中使用。合并为统一事实来源。

**Files:**
- Modify: `backend/app/core/nlu_engine.py` (新增 IntentCategory + category 字段)
- Delete: `backend/app/core/intent_classifier.py`
- Modify: `backend/tests/test_intent_classifier.py` (改为测试 nlu_engine)
- Verify: 无其他文件 import intent_classifier (已由 grep 确认只有 test 文件)

### Step 1: 在 nlu_engine.py 中新增 IntentCategory 枚举

在 `backend/app/core/nlu_engine.py` 文件顶部（`import re` 之后）新增：

```python
from enum import Enum


class IntentCategory(str, Enum):
    """高层意图分类（供路由和 Workflow 使用）"""
    CHAT = "chat"
    ANALYZE = "analyze"
    EMERGENCY = "emergency"
    KNOWLEDGE = "knowledge"
    FOLLOWUP = "followup"
    ALERT = "alert"
    REPORT = "report"
```

### Step 2: 在 NLUResult 中新增 category 字段

修改 `NLUResult` 类（第 56 行）：

```python
class NLUResult:
    """NLU解析结果"""
    def __init__(self, intent: str = "", entities: dict = None,
                 emotion: Optional[dict] = None, is_emergency: bool = False,
                 category: IntentCategory = IntentCategory.CHAT):
        self.intent = intent
        self.entities = entities or {}
        self.emotion = emotion or {"level": "neutral", "score": 0}
        self.is_emergency = is_emergency
        self.category = category
```

### Step 3: 在 RuleBaseNLU.parse() 末尾计算 category

在 `RuleBaseNLU.parse()` 方法末尾（第 199 行 `return NLUResult(...)` 之前），新增 category 计算逻辑：

```python
        # 5. 高层意图分类
        category = self._classify_category(intent, entities)

        return NLUResult(
            intent=intent, entities=entities, emotion=emotion,
            category=category,
        )
```

新增 `_classify_category` 方法：

```python
    # 分类关键词（从 intent_classifier.py 迁移）
    _ANALYZE_KEYWORDS = ("分析", "评估", "解读", "看看", "怎么样", "情况如何")
    _KNOWLEDGE_KEYWORDS = ("指南", "标准", "什么是", "怎么算", "正常范围", "知识")
    _FOLLOWUP_KEYWORDS = ("随访", "回访", "打电话", "问卷")
    _ALERT_KEYWORDS = ("预警", "告警", "异常")
    _REPORT_KEYWORDS = ("上报医生", "通知医生", "转医生", "escalate")

    def _classify_category(self, intent: str, entities: dict) -> IntentCategory:
        """基于 NLU 意图 + 关键词的高层意图分类"""
        # 紧急优先
        if intent in ("EMERGENCY", "SUICIDE_RISK"):
            return IntentCategory.EMERGENCY

        # NLU 意图直接映射
        _INTENT_MAP = {
            "HEALTH_DATA_REPORT": IntentCategory.CHAT,  # 数据记录走 chat variant
            "EMOTION_EXPRESS": IntentCategory.CHAT,
            "GREETING": IntentCategory.CHAT,
        }
        if intent in _INTENT_MAP:
            return _INTENT_MAP[intent]
        if intent == "KNOWLEDGE_QUERY":
            return IntentCategory.KNOWLEDGE
        if intent == "SCHEDULE_INQUIRY":
            return IntentCategory.CHAT

        return IntentCategory.CHAT
```

注意：这里 `_classify_category` 只处理 NLU 已知意图的映射。原始 `intent_classifier.py` 中的关键词匹配逻辑（`_ANALYZE_KEYWORDS` 等）在 `nlu_engine` 中不需要，因为 NLU 引擎已经通过 regex 做了更精确的意图识别。保留这些常量是为了后续扩展（如果需要在 category 层做关键词补充）。

### Step 4: 更新 NLUResult 的 category 计算，使用文本关键词补充

在 `_classify_category` 中补充关键词匹配逻辑（处理 `UNKNOWN` 意图的情况）：

```python
    def _classify_category(self, intent: str, entities: dict,
                           text: str = "") -> IntentCategory:
        """基于 NLU 意图 + 关键词的高层意图分类"""
        # 紧急优先
        if intent in ("EMERGENCY", "SUICIDE_RISK"):
            return IntentCategory.EMERGENCY

        # NLU 意图直接映射
        _INTENT_MAP = {
            "HEALTH_DATA_REPORT": IntentCategory.CHAT,
            "EMOTION_EXPRESS": IntentCategory.CHAT,
            "GREETING": IntentCategory.CHAT,
            "KNOWLEDGE_QUERY": IntentCategory.KNOWLEDGE,
            "SCHEDULE_INQUIRY": IntentCategory.CHAT,
        }
        if intent in _INTENT_MAP:
            return _INTENT_MAP[intent]

        # UNKNOWN 意图：使用关键词补充分类
        if text:
            if any(kw in text for kw in self._REPORT_KEYWORDS):
                return IntentCategory.REPORT
            if any(kw in text for kw in self._ALERT_KEYWORDS):
                return IntentCategory.ALERT
            if any(kw in text for kw in self._FOLLOWUP_KEYWORDS):
                return IntentCategory.FOLLOWUP
            if any(kw in text for kw in self._ANALYZE_KEYWORDS):
                return IntentCategory.ANALYZE
            if any(kw in text for kw in self._KNOWLEDGE_KEYWORDS):
                return IntentCategory.KNOWLEDGE

        return IntentCategory.CHAT
```

更新 `parse()` 方法中的调用，传入原始文本：

```python
        category = self._classify_category(intent, entities, text)
```

### Step 5: 更新测试

将 `backend/tests/test_intent_classifier.py` 重写为测试 nlu_engine 的 category：

```python
"""测试 NLU 引擎的高层意图分类（原 intent_classifier 已合并到 nlu_engine）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.nlu_engine import nlu_engine, IntentCategory


def test_emergency_category():
    result = nlu_engine.parse("我大出血了")
    assert result.category == IntentCategory.EMERGENCY


def test_knowledge_category():
    result = nlu_engine.parse("什么是妊娠期高血压")
    assert result.category == IntentCategory.KNOWLEDGE


def test_chat_default_category():
    result = nlu_engine.parse("你好")
    assert result.category == IntentCategory.CHAT


def test_unknown_intent_with_analyze_keyword():
    result = nlu_engine.parse("帮我分析一下情况")
    assert result.category == IntentCategory.ANALYZE


def test_unknown_intent_with_followup_keyword():
    result = nlu_engine.parse("安排一次随访")
    assert result.category == IntentCategory.FOLLOWUP
```

### Step 6: 删除 intent_classifier.py

```bash
rm backend/app/core/intent_classifier.py
```

### Step 7: 运行测试验证

Run: `cd backend && python -m pytest tests/test_intent_classifier.py tests/test_agno_tools.py -v`
Expected: 所有测试 PASS

### Step 8: Commit

```bash
git add backend/app/core/nlu_engine.py backend/tests/test_intent_classifier.py
git rm backend/app/core/intent_classifier.py
git commit -m "refactor: merge intent_classifier into nlu_engine as unified intent source"
```

---

## Task 3: P1-1 — UNKNOWN 意图 fallback 到轻量 LLM 分类

**背景：** 当规则引擎返回 `UNKNOWN` 时，当前直接使用全量工具集的 main agent（10 tools），这是最重的路径。新增轻量 LLM 分类，用极简 prompt 做快速意图判断（max_tokens=30），延迟可控。

**Files:**
- Modify: `backend/app/core/nlu_engine.py` (新增 `classify_with_llm` 方法)
- Modify: `backend/app/core/agno_chat_handler.py` (UNKNOWN 时调用 LLM 分类)
- Create: `backend/tests/test_nlu_llm_fallback.py`

### Step 1: 在 nlu_engine.py 中新增 `classify_with_llm` 方法

在 `RuleBaseNLU` 类末尾新增：

```python
    def classify_with_llm(self, text: str) -> str:
        """LLM 辅助意图分类（仅在规则引擎返回 UNKNOWN 时调用）。

        使用项目配置的 LLM 做极简分类，max_tokens=30，
        延迟约 200-500ms，远低于 Agent 全量工具调用的开销。

        Returns:
            重新判定的 NLU intent 字符串（如 "EMOTION_EXPRESS"），
            失败时返回 "UNKNOWN"。
        """
        try:
            from agno.models.message import Message
            from ..core.agno_client import get_agno_model
            model = get_agno_model(role="pregnant")

            classify_msg = Message(
                role="user",
                content=(
                    "判断用户消息的意图，只返回一个标签（不要解释）：\n"
                    "HEALTH_DATA_REPORT / EMOTION_EXPRESS / KNOWLEDGE_QUERY / "
                    "SCHEDULE_INQUIRY / GREETING / UNKNOWN\n"
                    f"消息：{text[:100]}"
                ),
            )

            response = model.generate(
                messages=[classify_msg],
                max_tokens=30,
            )
            result_text = ""
            if hasattr(response, "content") and response.content:
                result_text = response.content.strip().upper()
            elif hasattr(response, "text"):
                result_text = response.text.strip().upper()

            # 验证返回值是合法的 intent
            valid_intents = {
                "HEALTH_DATA_REPORT", "EMOTION_EXPRESS", "KNOWLEDGE_QUERY",
                "SCHEDULE_INQUIRY", "GREETING", "UNKNOWN",
            }
            if result_text in valid_intents:
                return result_text
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"
```

### Step 2: 在 agno_chat_handler.py 中集成 LLM 分类

在 `handle_chat_with_agno_stream` 的 NLU 解析部分（第 283-297 行），在 `nlu_result = nlu_engine.parse(user_text)` 之后、`resolve_tools_by_intent` 之前，新增 UNKNOWN 处理：

```python
    try:
        from ..core.nlu_engine import nlu_engine
        user_text = req.message.strip() if req.message else ""
        if user_text:
            nlu_result = nlu_engine.parse(user_text)

            # UNKNOWN 意图：尝试 LLM 辅助分类
            if nlu_result.intent == "UNKNOWN":
                refined_intent = nlu_engine.classify_with_llm(user_text)
                if refined_intent != "UNKNOWN":
                    nlu_result.intent = refined_intent
                    # 重新计算 category
                    nlu_result.category = nlu_engine._classify_category(
                        refined_intent, nlu_result.entities, user_text,
                    )

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
```

对 `handle_chat_with_agno`（非流式版本，第 201 行）做同样的修改。

### Step 3: 编写测试

创建 `backend/tests/test_nlu_llm_fallback.py`：

```python
"""测试 NLU LLM 分类 fallback"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def test_classify_with_llm_returns_valid_intent():
    """验证 LLM 分类返回合法 intent"""
    from app.core.nlu_engine import nlu_engine

    mock_response = MagicMock()
    mock_response.content = "EMOTION_EXPRESS"

    mock_model = MagicMock()
    mock_model.generate.return_value = mock_response

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("我今天感觉不太好")
        assert result == "EMOTION_EXPRESS"


def test_classify_with_llm_returns_unknown_for_invalid():
    """验证 LLM 返回非法值时 fallback 到 UNKNOWN"""
    from app.core.nlu_engine import nlu_engine

    mock_response = MagicMock()
    mock_response.content = "some random text"

    mock_model = MagicMock()
    mock_model.generate.return_value = mock_response

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("随便说点什么")
        assert result == "UNKNOWN"


def test_classify_with_llm_handles_exception():
    """验证 LLM 调用异常时 fallback 到 UNKNOWN"""
    from app.core.nlu_engine import nlu_engine

    mock_model = MagicMock()
    mock_model.generate.side_effect = Exception("LLM unavailable")

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("测试消息")
        assert result == "UNKNOWN"
```

### Step 4: 运行测试验证

Run: `cd backend && python -m pytest tests/test_nlu_llm_fallback.py -v`
Expected: 所有测试 PASS

### Step 5: Commit

```bash
git add backend/app/core/nlu_engine.py backend/app/core/agno_chat_handler.py backend/tests/test_nlu_llm_fallback.py
git commit -m "feat: add LLM fallback classification for UNKNOWN intents"
```

---

## Task 4: P1-3 — 增加药物剂量检测 guardrail

**背景：** 当前 `MedicalSafetyGuardrail.BLOCKED_PATTERNS` 已包含部分药名，但缺少通用剂量模式检测（如"每次2片，每日3次"）。

**Files:**
- Modify: `backend/app/core/agno_guardrails.py:75-87` (BLOCKED_PATTERNS)
- Modify: `backend/tests/test_agno_guardrails.py` (新增测试)

### Step 1: 在 BLOCKED_PATTERNS 中新增剂量模式

在 `backend/app/core/agno_guardrails.py` 的 `MedicalSafetyGuardrail.BLOCKED_PATTERNS` 列表末尾新增：

```python
    BLOCKED_PATTERNS = [
        "诊断为", "诊断是", "确诊",
        "建议用药", "建议服用", "处方",
        "可以吃药", "应该吃药", "用药方案",
        "治疗方案如下", "请按以下方案",
        # 增强覆盖：药物名称和剂量
        "推荐您服用", "您需要每天注射", "建议使用",
        "口服.*mg", "每次.*片", "拉贝洛尔", "硝苯地平",
        "低分子肝素", "阿司匹林", "黄体酮.*mg",
        # 诊断变体
        "您应该有.*病", "指标提示.*可能",
        "根据您的.*情况.*诊断", "检查结果表明",
        # 药物剂量模式（新增）
        r"\d+\s*(?:片|粒|颗)\s*[,，]?\s*(?:每[日天])\s*\d+\s*次",
        r"(?:每次|每回)\s*\d+\s*(?:片|粒|ml|mg|g)",
        r"口服\s*\d+\s*(?:片|粒|mg|g|ml)",
        r"(?:饭前|饭后|睡前|空腹)\s*(?:服用|吃|口服)\s*\d+",
        r"每次\s*\d+ml",
        r"\d+\s*mg\s*(?:每日|每天|bid|tid|qd|qn)",
    ]
```

### Step 2: 编写测试

在 `backend/tests/test_agno_guardrails.py` 末尾新增：

```python
# ==================== 药物剂量模式检测 ====================


def test_guardrail_blocks_dosage_pattern():
    """验证药物剂量模式被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()

    # "每次X片，每日Y次"
    assert guardrail.check("每次2片，每日3次") is not None
    assert guardrail.check("每次1片,每日2次") is not None

    # "每次Xml"
    assert guardrail.check("每次10ml") is not None

    # "饭前/饭后服用"
    assert guardrail.check("饭前服用2片") is not None
    assert guardrail.check("睡前口服1粒") is not None

    # "Xmg bid/tid"
    assert guardrail.check("100mg bid") is not None
    assert guardrail.check("50mg 每日两次") is not None


def test_guardrail_allows_safe_suggestion():
    """验证建议性措辞不被误拦"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()

    # 安全的建议性表述
    assert guardrail.check("建议咨询医生获取用药指导") is None
    assert guardrail.check("请遵医嘱服药") is None
    assert guardrail.check("具体用药方案需由医生决定") is None
```

### Step 3: 运行测试验证

Run: `cd backend && python -m pytest tests/test_agno_guardrails.py -v`
Expected: 所有测试 PASS（包括新增的剂量测试和现有的安全测试）

### Step 4: Commit

```bash
git add backend/app/core/agno_guardrails.py backend/tests/test_agno_guardrails.py
git commit -m "feat: add drug dosage pattern detection to MedicalSafetyGuardrail"
```

---

## Task 5: P1-2 — 统一预警分析到 Workflow 路径

**背景：** `alert_service.enrich_alert_with_llm` 只调用 `run_nurse_analysis`（护士单步分析），而 `alert_analysis_service.run_alert_workflow` 已实现完整的护士→医生 Workflow（含 fallback）。应统一到 Workflow 路径，避免维护两套逻辑。

**Files:**
- Modify: `backend/app/services/alert_service.py:100-136` (`enrich_alert_with_llm`)
- Modify: `backend/tests/test_alert_service.py:195-251` (更新测试)

### Step 1: 修改 enrich_alert_with_llm 使用 Workflow

在 `backend/app/services/alert_service.py` 中，将 `enrich_alert_with_llm` 方法替换为：

```python
    @staticmethod
    async def enrich_alert_with_llm(alert_id, pregnant_id: str):
        """使用 Agno Workflow 为预警生成分析摘要（护士初筛 → 医生预分析）"""
        from ..database import SessionLocal
        from .alert_analysis_service import alert_analysis_service

        db = SessionLocal()
        try:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if not alert:
                logger.warning("enrich_alert_with_llm: alert {} 不存在", alert_id)
                return

            from ..models import Pregnant
            pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
            if not pregnant:
                logger.warning("enrich_alert_with_llm: pregnant {} 不存在", pregnant_id)
                return

            # 使用 Workflow 路径（含护士→医生分析 + 自动 fallback）
            result_payload = await alert_analysis_service.run_alert_workflow(db, alert, pregnant)

            # 兼容读取：从 workflow 结果中提取摘要字段
            details = alert.details or {}
            workflow_output = result_payload.get("workflow_output", "")
            steps = result_payload.get("steps", [])

            # 从 steps 中提取护士分析（如果有）
            nurse_summary = ""
            for step in steps:
                if step.get("role") == "nurse":
                    nurse_summary = step.get("summary", "")
                    break

            details["llm_analysis"] = {
                "risk_interpretation": nurse_summary or (workflow_output[:200] if isinstance(workflow_output, str) else ""),
                "recommended_actions": [s.get("nursing_suggestions", "") for s in steps if s.get("role") == "nurse"],
                "severity_assessment": nurse_summary or "",
                "analyzed_at": beijing_now().isoformat(),
                "source": "agno_workflow",
            }
            alert.details = details
            db.commit()
            logger.info("Agno Workflow 预警分析完成: alert_id={}", alert.id)
        except Exception as e:
            logger.error("enrich_alert_with_llm 失败: alert_id={}, error={}", alert_id, e)
        finally:
            db.close()
```

### Step 2: 更新测试

在 `backend/tests/test_alert_service.py` 中，更新 `TestAlertLLMEnrichment` 类的测试：

```python
class TestAlertLLMEnrichment:

    @pytest.mark.asyncio
    async def test_enrich_alert_stores_workflow_analysis(self):
        from app.services.alert_service import AlertService

        alert = MagicMock()
        alert.id = uuid4()
        alert.pregnant_id = "P001"
        alert.rule_id = "RULE_BP_HIGH"
        alert.level = "RED"
        alert.message = "血压异常升高"
        alert.details = {}

        pregnant = MagicMock()
        pregnant.display_name = "测试孕妇"
        pregnant.gestational_age_days = 224
        pregnant.risk_tags = ["高血压"]

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [alert, pregnant]

        workflow_result = {
            "workflow": "alert_analysis",
            "workflow_output": "综合分析结果",
            "steps": [
                {"role": "nurse", "summary": "血压持续升高", "nursing_suggestions": "立即测量血压", "analyzed_at": "2026-01-01T00:00:00"},
            ],
        }

        with patch("app.database.SessionLocal", return_value=mock_session), \
             patch(
                "app.services.alert_analysis_service.alert_analysis_service.run_alert_workflow",
                new=AsyncMock(return_value=workflow_result),
             ):
            await AlertService.enrich_alert_with_llm(alert.id, "P001")

            assert "llm_analysis" in alert.details
            assert alert.details["llm_analysis"]["source"] == "agno_workflow"
            assert "血压持续升高" in alert.details["llm_analysis"]["risk_interpretation"]
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_enrich_alert_handles_workflow_failure(self):
        from app.services.alert_service import AlertService

        alert = MagicMock()
        alert.id = uuid4()
        alert.details = {}

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = [alert, MagicMock()]

        with patch("app.database.SessionLocal", return_value=mock_session), \
             patch(
                "app.services.alert_analysis_service.alert_analysis_service.run_alert_workflow",
                new=AsyncMock(side_effect=Exception("Workflow failed")),
             ):
            await AlertService.enrich_alert_with_llm(alert.id, "P001")
            assert "llm_analysis" not in alert.details
            mock_session.close.assert_called_once()
```

### Step 3: 运行测试验证

Run: `cd backend && python -m pytest tests/test_alert_service.py -v`
Expected: 所有测试 PASS

### Step 4: Commit

```bash
git add backend/app/services/alert_service.py backend/tests/test_alert_service.py
git commit -m "refactor: unify alert analysis to use Workflow path (nurse → doctor)"
```

---

## Task 6: 全量回归测试

### Step 1: 运行全部相关测试

Run: `cd backend && python -m pytest tests/test_agno_tools.py tests/test_agno_agent.py tests/test_agno_guardrails.py tests/test_intent_classifier.py tests/test_alert_service.py tests/test_nlu_llm_fallback.py tests/test_agno_medical_agents.py -v`
Expected: 所有测试 PASS

### Step 2: 检查无残留 import

Run: `cd backend && python -c "from app.core.nlu_engine import nlu_engine, IntentCategory; print('OK')"`
Expected: OK

Run: `cd backend && python -c "from app.core.intent_classifier import classify_intent" 2>&1 || echo "DELETED OK"`
Expected: ModuleNotFoundError（确认已删除）

### Step 3: 最终 Commit（如有修复）

```bash
git add -A
git commit -m "fix: resolve test failures from P0/P1/P3 refactoring"
```
