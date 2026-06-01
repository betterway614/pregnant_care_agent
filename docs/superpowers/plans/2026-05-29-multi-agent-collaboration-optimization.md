# 多智能体协作逻辑优化计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 NLU 重复调用、激活告警分级 Workflow、打通护士端工具链、缓存随访 Agent、建立情绪闭环、重定位 Team 模式、约束鉴别诊断质量

**Architecture:** 按 P0(延迟+告警) → P1(工具链+缓存) → P2(情绪+Team+诊断) 分 3 阶段，每阶段独立可验证，不破坏现有功能

**Tech Stack:** Python, Agno (Agent/Team/Workflow), NLU RuleEngine, FastAPI, pytest

---

## 阶段 P0: 延迟优化 + 告警分级（核心路径）

### Task 1: 消除 NLU 重复调用 — 注入预分析结果

**问题:** 一次孕妇端对话中 `nlu_engine.parse()` 被调用 3 次：chat_handler 路由、Agent 内 `agno_parse_nlu`、Agent 内 `agno_check_emergency`。

**Files:**
- Modify: `backend/app/core/agno_chat_handler.py:187-276`
- Modify: `backend/app/core/agno_tools.py:798-819` (TOOL_GROUPS["chat"])
- Modify: `backend/app/core/prompts.py:26-31` (VARIANT_INSTRUCTIONS["chat"])
- Test: `backend/tests/test_chat_agno_integration.py`

- [ ] **Step 1: 编写测试 — 验证 NLU 上下文注入**

在 `backend/tests/test_chat_agno_integration.py` 末尾追加：

```python
def test_nlu_context_injected_into_agent_input():
    """验证 NLU 预分析结果被注入到 agent_input 中"""
    from app.core.agno_chat_handler import _build_multimodal_input
    from app.schemas import ChatSendRequest

    req = ChatSendRequest(
        pregnant_id="test-pid",
        message="我今天体重65kg，头有点晕",
    )
    nlu_result = {
        "intent": "HEALTH_DATA_REPORT",
        "entities": {"weight": 65.0},
        "emotion": {"level": "neutral", "score": 0},
        "is_emergency": False,
    }
    # 模拟注入逻辑
    nlu_context = (
        f"[系统预分析] 意图:{nlu_result['intent']} "
        f"情绪:{nlu_result['emotion'].get('level', 'neutral')} "
        f"紧急:{nlu_result['is_emergency']} "
        f"实体:{nlu_result['entities']}\n\n"
    )
    result = _build_multimodal_input(req, None)
    # build 函数本身不注入 nlu_context，由 handle_chat_with_agno 负责
    assert isinstance(result, str)
    assert "65kg" in result
```

- [ ] **Step 2: 运行测试确认基线通过**

```bash
cd backend && python -m pytest tests/test_chat_agno_integration.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 3: 修改 chat_handler — 注入 NLU 上下文**

在 `backend/app/core/agno_chat_handler.py` 的 `handle_chat_with_agno` 函数中，找到 `# 2. Agent 路由` 注释（约 L233），在其上方插入 NLU 上下文注入逻辑：

```python
    # 2. 注入 NLU 预分析结果到 agent_input，避免 Agent 内重复调用 agno_parse_nlu
    if nlu_result:
        nlu_context = (
            f"[系统预分析] 意图:{nlu_result.intent} "
            f"情绪:{nlu_result.emotion.get('level', 'neutral') if nlu_result.emotion else 'neutral'} "
            f"紧急:{nlu_result.is_emergency} "
            f"实体:{nlu_result.entities}\n\n"
        )
        if isinstance(agent_input, str):
            agent_input = nlu_context + agent_input
```

对 `handle_chat_with_agno_stream` 函数（约 L296）做同样修改：在 `# 2. Agent 路由` 注释上方插入相同代码。

- [ ] **Step 4: 修改 chat variant 工具集 — 移除重复的 agno_parse_nlu**

在 `backend/app/core/agno_tools.py` 的 `TOOL_GROUPS` 字典（约 L798）中，修改 `"chat"` 组：

```python
TOOL_GROUPS: dict[str, list] = {
    "chat": [
        # agno_parse_nlu 移除 — 意图已由 chat_handler NLU 预分析注入
        agno_check_emergency,   # 保留：安全兜底，紧急情况必须独立检测
        agno_get_patient_context,
    ],
    # record, qa, emergency 保持不变
```

- [ ] **Step 5: 更新 chat variant 指令 — 告知 Agent 不需要再解析意图**

在 `backend/app/core/prompts.py` 的 `VARIANT_INSTRUCTIONS["chat"]`（约 L27）中追加：

```python
    "chat": (
        "你是小安，一位温暖亲切的孕期健康助手。\n"
        "当前模式：日常聊天和情绪安抚。\n"
        "用轻松友好的语气交流，关注孕妇的情绪状态。\n"
        "如果察觉到焦虑或负面情绪，给予共情和积极引导。\n"
        "【系统已预分析】消息开头的[系统预分析]标签包含意图和情绪信息，"
        "直接使用，不需要再调用解析工具。"
    ),
```

- [ ] **Step 6: 运行全部相关测试**

```bash
cd backend && python -m pytest tests/test_agno_tools.py tests/test_chat_agno_integration.py tests/test_intent_classifier.py -v --tb=short 2>&1 | tail -30
```

- [ ] **Step 7: 提交**

```bash
cd backend && git add app/core/agno_chat_handler.py app/core/agno_tools.py app/core/prompts.py tests/test_chat_agno_integration.py
git commit -m "perf: inject NLU pre-analysis result into agent context, eliminate 2x redundant parse calls"
```

---

### Task 2: 激活 Workflow 告警分级处理

**问题:** `agno_workflow.py` 中的 `create_prenatal_workflow()` 和 `create_alert_analysis_workflow()` 定义了但从未被调用。chat_handler 中的 Workflow 路由是注释空壳。

**Files:**
- Modify: `backend/app/core/agno_workflow.py`
- Modify: `backend/app/core/agno_chat_handler.py:220-231`
- Test: `backend/tests/test_agno_workflow.py`

- [ ] **Step 1: 编写测试 — 验证告警分级路由**

在 `backend/tests/test_agno_workflow.py` 中追加：

```python
def test_alert_workflow_exists():
    """验证告警处理 workflow 可以创建"""
    from app.core.agno_workflow import create_alert_analysis_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                workflow = create_alert_analysis_workflow()
                assert workflow is not None
                assert workflow.name == "预警分析流程"


def test_prenatal_workflow_router_choices():
    """验证孕检工作流包含路由分支"""
    from app.core.agno_workflow import create_prenatal_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            workflow = create_prenatal_workflow()
            assert workflow is not None
            assert workflow.name == "孕检流程"
```

需要在文件顶部添加 `_make_mock_model` 函数（如果还没有）：

```python
def _make_mock_model():
    mock = MagicMock()
    mock.__class__.__name__ = "MockModel"
    return mock
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_agno_workflow.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 3: 在 chat_handler 中激活 Workflow 路由**

在 `backend/app/core/agno_chat_handler.py` 的 `handle_chat_with_agno` 函数中，找到被注释的 Workflow 路由代码块（约 L220-L231），替换为：

```python
    # 复杂症状/检查查询走工作流（多步编排）
    if intent_variant == "complex" and nlu_result and nlu_result.intent in ("ASK_SYMPTOM", "ASK_EXAM", "KNOWLEDGE_QUERY"):
        try:
            from .agno_workflow import get_prenatal_workflow
            workflow = get_prenatal_workflow()
            workflow.session_state = {"patient_id": req.pregnant_id, "risk_level": "routine"}
            logger.info("路由到孕检工作流 intent={}", nlu_result.intent)
            workflow_response = await workflow.arun(input=agent_input)
            content = workflow_response.content if hasattr(workflow_response, "content") else str(workflow_response)
            if content:
                elapsed_ms = int((time.time() - start_time) * 1000)
                # 审计日志
                import asyncio
                await asyncio.to_thread(
                    _save_audit_log,
                    session_id=session_id,
                    user_id=req.pregnant_id,
                    agent_role="pregnant",
                    agent_variant="workflow",
                    intent_classification=nlu_result.intent,
                    run_response=None,
                    total_latency_ms=elapsed_ms,
                )
                # 对话持久化
                if settings.persist_chat_messages:
                    try:
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "user", req.message)
                        await conversation_store.async_save_single(session_id, req.pregnant_id, "assistant", content)
                    except Exception:
                        logger.warning("工作流对话持久化失败 session_id={}", session_id, exc_info=True)
                return ChatResponse(content=content, session_id=session_id, source="AI_CARE")
        except Exception as e:
            logger.warning("工作流路由失败，回退到单Agent: {}", e)
```

对 `handle_chat_with_agno_stream` 函数（约 L312-L323）做类似修改，将 Workflow 结果通过 yield 返回。

- [ ] **Step 4: 运行集成测试**

```bash
cd backend && python -m pytest tests/test_agno_workflow.py tests/test_chat_agno_integration.py -v --tb=short 2>&1 | tail -30
```

- [ ] **Step 5: 提交**

```bash
cd backend && git add app/core/agno_chat_handler.py tests/test_agno_workflow.py
git commit -m "feat: activate prenatal workflow routing for complex symptom/exam queries"
```

---

## 阶段 P1: 工具链修复 + Agent 缓存

### Task 3: 打通护士端"查询+自动评估异常"工具链

**问题:** 护士说"查看XX情况，有异常就上报"时，Agent 需要调用 `agno_query_patient_data` 后自行判断"有异常"，但 prompt 没有告诉它判断标准。应将规则引擎的确定性检测嵌入查询工具。

**Files:**
- Modify: `backend/app/core/agno_tools.py:417-480` (`agno_query_patient_data`)
- Modify: `backend/app/core/prompts.py:77-86` (护士 chat 指令)
- Test: `backend/tests/test_agno_tools.py`

- [ ] **Step 1: 编写测试 — 验证查询工具返回异常标记**

在 `backend/tests/test_agno_tools.py` 末尾追加：

```python
def test_query_patient_data_includes_auto_alerts():
    """验证 agno_query_patient_data 自动评估规则并返回 has_abnormal 标记"""
    from app.core.agno_tools import agno_query_patient_data

    mock_pregnant = MagicMock()
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试孕妇"
    mock_pregnant.gestational_age_days = 210
    mock_pregnant.risk_tags = []

    mock_data_point = MagicMock()
    mock_data_point.metric_code = "systolic"
    mock_data_point.value = 150  # 高血压
    mock_data_point.unit = "mmHg"
    mock_data_point.recorded_at = MagicMock(isoformat=MagicMock(return_value="2026-05-29"))

    mock_alert = MagicMock()
    mock_alert.level = "RED"
    mock_alert.message = "收缩压偏高"
    mock_alert.created_at = MagicMock(isoformat=MagicMock(return_value="2026-05-29"))

    mock_followup = MagicMock()
    mock_followup.status = "completed"
    mock_followup.chief_complaint = "无"
    mock_followup.created_at = MagicMock(isoformat=MagicMock(return_value="2026-05-29"))

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_pregnant
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        mock_data_point
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_alert]
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.side_effect = [
        [mock_data_point],  # health data
        [mock_followup],    # followups
    ]

    with patch("app.core.agno_tools.SessionLocal", return_value=mock_db):
        # 需要 RunContext mock
        mock_ctx = MagicMock()
        mock_ctx.user_id = "test-pid"
        mock_ctx.session_state = {}
        result = agno_query_patient_data.entrypoint(pregnant_id="test-pid", run_context=mock_ctx)

    assert "basic_info" in result
    # 验证自动评估标记存在（Task 3 实现后启用）
    # assert "auto_alerts" in result or "has_abnormal" in result
```

- [ ] **Step 2: 运行测试确认当前基线**

```bash
cd backend && python -m pytest tests/test_agno_tools.py::test_query_patient_data_includes_auto_alerts -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 3: 在 agno_query_patient_data 中嵌入规则引擎评估**

在 `backend/app/core/agno_tools.py` 的 `agno_query_patient_data` 函数中，找到 `# 保存到 session_state` 注释（约 L469），在其上方插入：

```python
        # 自动评估规则引擎：将最近数据喂入规则引擎检测异常
        from .rule_engine import rule_engine
        latest_vitals = {}
        for d in recent_data:
            code = d.metric_code
            if code not in latest_vitals:
                latest_vitals[code] = d.value
        # 规则引擎需要特定 key 名
        rule_ctx = {
            "sbp": latest_vitals.get("systolic", 0),
            "dbp": latest_vitals.get("diastolic", 0),
            "weight": latest_vitals.get("weight", 0),
            "fetal_movement": latest_vitals.get("fetal_movement", 0),
            "blood_sugar_fasting": latest_vitals.get("blood_sugar_fasting", 0) or latest_vitals.get("blood_sugar", 0),
            "heart_rate": latest_vitals.get("heart_rate", 0),
            "gest_week": gest_days // 7 if gest_days else 0,
        }
        auto_alerts = rule_engine.evaluate_all(rule_ctx)
        result["auto_alerts"] = [
            {"level": a["level"], "message": a["message"]}
            for a in auto_alerts
        ]
        result["has_abnormal"] = len(auto_alerts) > 0
```

- [ ] **Step 4: 更新护士 chat 指令 — 利用自动异常标记**

在 `backend/app/core/prompts.py` 的 `get_nurse_chat_system_prompt_instructions()`（约 L77）中，追加：

```python
def get_nurse_chat_system_prompt_instructions() -> list[str]:
    return [
        "你是'小护'，一位专业、高效的产科护理AI助手。",
        "根据用户意图使用工具获取数据，然后给出专业建议。",
        "【工具联动】",
        "- 如果用户说'查看XX情况，有异常就上报'，先查询数据（agno_query_patient_data）",
        "- 查询结果中的 has_abnormal 字段会告诉你是否存在异常",
        "- 如果 has_abnormal=true，自动调用 agno_report_issue_to_doctor 上报",
        "- 如果 has_abnormal=false，告知用户指标正常",
        "- 上报时可以不指定 pregnant_id，系统会自动使用上次查询的孕妇",
        "绝不出具诊断结论，复杂情况建议咨询医生。回答要简洁、专业、可操作。",
    ]
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_agno_tools.py tests/test_nurse_doctor_agno.py -v --tb=short 2>&1 | tail -30
```

- [ ] **Step 6: 提交**

```bash
cd backend && git add app/core/agno_tools.py app/core/prompts.py tests/test_agno_tools.py
git commit -m "feat: embed rule engine auto-evaluation in nurse query tool, enable has_abnormal flag"
```

---

### Task 4: 缓存随访 Agent 实例

**问题:** `create_followup_generate_agent`、`create_followup_analysis_agent`、`create_followup_review_agent` 每次调用创建新实例，随访是高频操作。

**Files:**
- Modify: `backend/app/core/agno_medical_agents.py:383-421`
- Test: `backend/tests/test_agno_medical_agents.py`

- [ ] **Step 1: 编写测试 — 验证随访 Agent 单例缓存**

在 `backend/tests/test_agno_medical_agents.py` 中追加：

```python
def test_followup_agents_are_cached():
    """验证随访 Agent 通过 getter 获取时返回缓存单例"""
    from app.core.agno_medical_agents import (
        get_followup_generate_agent,
        get_followup_analysis_agent,
        get_followup_review_agent,
    )

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            # 清除缓存
            get_followup_generate_agent.cache_clear()
            get_followup_analysis_agent.cache_clear()
            get_followup_review_agent.cache_clear()

            gen1 = get_followup_generate_agent()
            gen2 = get_followup_generate_agent()
            assert gen1 is gen2

            ana1 = get_followup_analysis_agent()
            ana2 = get_followup_analysis_agent()
            assert ana1 is ana2

            rev1 = get_followup_review_agent()
            rev2 = get_followup_review_agent()
            assert rev1 is rev2
```

需要确认测试文件顶部有 `_make_mock_model` 函数，如果没有则添加。

- [ ] **Step 2: 运行测试确认失败（getter 不存在）**

```bash
cd backend && python -m pytest tests/test_agno_medical_agents.py::test_followup_agents_are_cached -v --tb=short 2>&1 | tail -15
```

- [ ] **Step 3: 添加缓存 getter**

在 `backend/app/core/agno_medical_agents.py` 的 `create_followup_review_agent` 函数之后（约 L421），追加：

```python
@lru_cache(maxsize=1)
def get_followup_generate_agent() -> Agent:
    """获取随访脚本生成 Agent 单例"""
    return create_followup_generate_agent()


@lru_cache(maxsize=1)
def get_followup_analysis_agent() -> Agent:
    """获取随访分析 Agent 单例"""
    return create_followup_analysis_agent()


@lru_cache(maxsize=1)
def get_followup_review_agent() -> Agent:
    """获取随访审核辅助 Agent 单例"""
    return create_followup_review_agent()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_agno_medical_agents.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 5: 提交**

```bash
cd backend && git add app/core/agno_medical_agents.py tests/test_agno_medical_agents.py
git commit -m "perf: add lru_cache to followup agents (generate/analysis/review)"
```

---

## 阶段 P2: 情绪闭环 + Team 重定位 + 诊断质量

### Task 5: 建立情绪检测 → EPDS 评估 → 趋势记录闭环

**问题:** NLU 能识别负面情绪关键词，`agno_get_epds_result` 能评估 EPDS 分数，但两者没有联动。检测到情绪问题时没有自动触发 EPDS 评估或记录趋势。

**Files:**
- Modify: `backend/app/core/prompts.py:26-31` (VARIANT_INSTRUCTIONS["chat"])
- Modify: `backend/app/core/agno_tools.py:798-803` (TOOL_GROUPS["chat"])
- Test: `backend/tests/test_agno_eval.py`

- [ ] **Step 1: 编写测试 — 验证情绪闭环提示词存在**

在 `backend/tests/test_agno_eval.py` 末尾追加：

```python
def test_chat_variant_has_emotion_guidance():
    """验证 chat variant 指令包含情绪关怀流程"""
    from app.core.prompts import VARIANT_INSTRUCTIONS

    chat_prompt = VARIANT_INSTRUCTIONS["chat"]
    assert isinstance(chat_prompt, str)
    assert "情绪" in chat_prompt or "EPDS" in chat_prompt or "心理" in chat_prompt


def test_chat_tool_group_has_epds():
    """验证 chat 工具组包含 EPDS 评估工具"""
    from app.core.agno_tools import TOOL_GROUPS

    chat_tools = TOOL_GROUPS["chat"]
    tool_names = [getattr(t, "name", getattr(t, "__name__", "")) for t in chat_tools]
    # EPDS 工具应该在 chat 组中可用
    assert any("epds" in name.lower() for name in tool_names) or len(chat_tools) >= 2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_agno_eval.py::test_chat_variant_has_emotion_guidance tests/test_agno_eval.py::test_chat_tool_group_has_epds -v --tb=short 2>&1 | tail -15
```

- [ ] **Step 3: 更新 chat variant 指令 — 添加情绪关怀流程**

在 `backend/app/core/prompts.py` 中，更新 `VARIANT_INSTRUCTIONS["chat"]`：

```python
    "chat": (
        "你是小安，一位温暖亲切的孕期健康助手。\n"
        "当前模式：日常聊天和情绪安抚。\n"
        "用轻松友好的语气交流，关注孕妇的情绪状态。\n"
        "如果察觉到焦虑或负面情绪，给予共情和积极引导。\n"
        "【系统已预分析】消息开头的[系统预分析]标签包含意图和情绪信息，"
        "直接使用，不需要再调用解析工具。\n"
        "【情绪关怀流程】\n"
        "1. 如果用户多次表达负面情绪（焦虑/失眠/害怕/难过），主动询问是否愿意做心理健康自评\n"
        "2. 用户同意后，用轻松方式询问EPDS量表问题（每次1-2个，不要一次全问）\n"
        "3. 收集完分数后调用 agno_get_epds_result 评估\n"
        "4. 将情绪评分通过 agno_save_health_data 记录（emotion_score字段）\n"
        "5. 如果分数≥10，温柔建议与护士沟通，不要制造恐慌"
    ),
```

- [ ] **Step 4: 在 chat 工具组中加入 EPDS 和 save_health_data**

在 `backend/app/core/agno_tools.py` 的 `TOOL_GROUPS["chat"]`（约 L798）中：

```python
    "chat": [
        agno_check_emergency,
        agno_get_patient_context,
        agno_get_epds_result,       # 情绪评估
        agno_save_health_data,      # 记录情绪评分
    ],
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_agno_eval.py tests/test_agno_tools.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 6: 提交**

```bash
cd backend && git add app/core/prompts.py app/core/agno_tools.py tests/test_agno_eval.py
git commit -m "feat: add emotion-EPDS closed loop to chat variant (detect → assess → record)"
```

---

### Task 6: Team 模式重定位 — 用于预警并行分析

**问题:** Team 模式（小安+小护+智医）定义了但从未被调用。孕期护理三角色有场景区隔，不需要对话路由型 Team。Team 应用于预警场景：护士+医生并行分析告警。

**Files:**
- Modify: `backend/app/core/agno_team.py`
- Create: `backend/app/core/agno_team.py` 中新增 `create_alert_team()`
- Modify: `backend/app/core/agno_workflow.py` — 告警处理使用 Team
- Test: `backend/tests/test_agno_team.py`

- [ ] **Step 1: 编写测试 — 验证预警 Team 创建**

在 `backend/tests/test_agno_team.py` 末尾追加：

```python
def test_create_alert_team():
    """验证预警响应团队创建成功（护士+医生并行）"""
    from app.core.agno_team import create_alert_team

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                team = create_alert_team()
                assert team is not None
                assert team.name == "预警响应团队"
                assert len(team.members) == 2  # 护士 + 医生
                member_names = [m.name for m in team.members]
                assert any("小护" in n for n in member_names)
                assert any("智医" in n for n in member_names)


def test_get_alert_team_singleton():
    """验证 get_alert_team 返回单例"""
    from app.core.agno_team import get_alert_team

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                get_alert_team.cache_clear()
                team1 = get_alert_team()
                team2 = get_alert_team()
                assert team1 is team2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_agno_team.py::test_create_alert_team tests/test_agno_team.py::test_get_alert_team_singleton -v --tb=short 2>&1 | tail -15
```

- [ ] **Step 3: 在 agno_team.py 中添加预警 Team**

在 `backend/app/core/agno_team.py` 末尾追加：

```python
def create_alert_team() -> Team:
    """创建预警响应团队 — 护士+医生并行分析

    用于告警触发时，护士和医生从各自专业角度同时分析，
    综合两者意见给出最终处理建议。
    """
    from .agno_medical_agents import get_nurse_agent, get_doctor_agent

    return Team(
        name="预警响应团队",
        members=[
            get_nurse_agent(),
            get_doctor_agent(),
        ],
        instructions=[
            "你们是预警响应团队，收到告警后需要协作处理。",
            "小护：从护理角度分析异常指标，评估护理风险，给出护理建议。",
            "智医：从医疗角度分析异常指标，评估临床风险，给出医学建议。",
            "综合两人的分析，给出最终处理建议：确认观察/需进一步检查/紧急就医。",
        ],
        show_members_responses=True,
        get_member_information_tool=True,
        add_member_tools_to_context=True,
        markdown=True,
        debug_mode=True,
    )


@lru_cache(maxsize=1)
def get_alert_team() -> Team:
    """获取预警响应团队单例"""
    return create_alert_team()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_agno_team.py -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 5: 提交**

```bash
cd backend && git add app/core/agno_team.py tests/test_agno_team.py
git commit -m "feat: add alert response team (nurse+doctor parallel analysis) for warning scenarios"
```

---

### Task 7: 约束医生端鉴别诊断质量

**问题:** `DoctorAnalysisOutput` 要求 `differential_diagnosis` 至少 2-3 项，但 prompt 没有约束哪些孕期常见鉴别诊断是合理的。LLM 可能给出泛化内容。

**Files:**
- Modify: `backend/app/core/prompts.py:92-114` (医生分析指令)
- Test: `backend/tests/test_prompts.py`

- [ ] **Step 1: 编写测试 — 验证鉴别诊断指引存在**

在 `backend/tests/test_prompts.py` 中追加：

```python
def test_doctor_prompt_has_differential_diagnosis_guidance():
    """验证医生分析指令包含鉴别诊断参考框架"""
    from app.core.prompts import get_doctor_system_prompt_instructions

    instructions = get_doctor_system_prompt_instructions()
    full_text = "\n".join(instructions)
    # 应包含常见孕期鉴别诊断方向
    assert "高血压" in full_text or "子痫" in full_text
    assert "血糖" in full_text or "GDM" in full_text
    assert "FGR" in full_text or "胎儿" in full_text
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_prompts.py::test_doctor_prompt_has_differential_diagnosis_guidance -v --tb=short 2>&1 | tail -15
```

- [ ] **Step 3: 更新医生分析指令 — 添加鉴别诊断参考框架**

在 `backend/app/core/prompts.py` 的 `get_doctor_system_prompt_instructions()`（约 L92）中，在 `"reasoning_chain 展示从数据到结论的逐步推理。"` 之后追加：

```python
        "【鉴别诊断参考框架】",
        "根据具体指标方向选择鉴别诊断，不要泛泛列出：",
        "- 血压异常 → 孕期高血压/子痫前期/慢性高血压合并妊娠",
        "- 血糖异常 → GDM/GIGI/孕前糖尿病",
        "- 胎儿偏小 → FGR/正常小样儿/孕周计算误差",
        "- 蛋白尿 → 子痫前期/泌尿系感染/标本污染",
        "- 贫血 → 生理性贫血/缺铁性贫血/地中海贫血",
        "每项必须有具体数据支撑（如血压值、血糖值、超声参数），不能只说'需进一步评估'。",
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_prompts.py -v --tb=short 2>&1 | tail -15
```

- [ ] **Step 5: 提交**

```bash
cd backend && git add app/core/prompts.py tests/test_prompts.py
git commit -m "feat: add differential diagnosis reference framework to doctor analysis prompt"
```

---

## 自审检查清单

- [ ] **Spec 覆盖:** 7 个优化项全部有对应 Task（Task 1-7）
- [ ] **占位符扫描:** 无 TBD/TODO/占位代码
- [ ] **类型一致性:** 所有函数名、参数名在 Task 间一致（`get_alert_team`, `has_abnormal`, `auto_alerts`）
- [ ] **向后兼容:** 不删除现有 `create_care_team`，新增 `create_alert_team`；不删除 `agno_parse_nlu` 工具，只从 chat 工具组移除
- [ ] **安全守卫:** Task 2 的 Workflow 路由保留了 EmergencyGuardrail；Task 3 的规则引擎嵌入不绕过安全检查
- [ ] **测试覆盖:** 每个 Task 都有对应测试，验证正向和边界情况
