# 护士/医生智能体 Token 优化 + 审计日志 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 为护士(小护)和医生(Dr.智)智能体实施工具路由和审计日志，复用 Phase 1 基础设施

**Architecture:** 固定意图端点（/analyze）直接路由到对应变体；chat/stream 端点需要 NLU 意图分类；所有端点写入 AgentAuditLog

**Tech Stack:** Agno Framework, SQLAlchemy (SQLite), FastAPI

---

### Task 1: 添加护士/医生 TOOL_GROUPS + resolve 函数

**File:** Modify `backend/app/core/agno_tools.py`

在文件末尾追加：

```python
# ==================== 护士端工具子集分组（工具路由） ====================

NURSE_TOOL_GROUPS: dict[str, list] = {
    "analyze": [
        agno_query_patient_data,
        agno_analyze_health_trends,
        agno_evaluate_vital_rules,
        agno_search_knowledge,
    ],
    "followup": [
        agno_create_followup_record,
        agno_query_patient_data,
    ],
    "report": [
        agno_report_issue_to_doctor,
        agno_query_patient_data,
    ],
    "chat": [
        agno_query_patient_data,
        agno_search_knowledge,
        agno_analyze_health_trends,
    ],
}

# ==================== 医生端工具子集分组（工具路由） ====================

DOCTOR_TOOL_GROUPS: dict[str, list] = {
    "analyze": [
        agno_analyze_patient_comprehensive,
        agno_analyze_health_trends,
        agno_evaluate_vital_rules,
        agno_search_knowledge,
        agno_query_clinical_guideline,
    ],
    "order": [
        agno_generate_medical_order,
        agno_analyze_patient_comprehensive,
    ],
    "issue": [
        agno_handle_issue,
        agno_analyze_patient_comprehensive,
    ],
    "chat": [
        agno_search_knowledge,
        agno_analyze_health_trends,
        agno_evaluate_vital_rules,
    ],
}


def resolve_nurse_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据意图返回护士工具子集"""
    if nlu_result is None or not nlu_result.get("intent"):
        return (NURSE_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
    # 护士意图映射
    nurse_intent_map = {
        "analyze": "analyze", "nurse_analyze": "analyze",
        "followup": "followup", "create_followup": "followup",
        "report": "report", "report_issue": "report",
        "chat": "chat", "greeting": "chat", "emotion": "chat",
        "ask_knowledge": "chat", "ask_symptom": "chat",
    }
    group_name = nurse_intent_map.get(intent)
    if group_name and group_name in NURSE_TOOL_GROUPS:
        return (NURSE_TOOL_GROUPS[group_name], group_name)
    return (NURSE_TOOLS, "complex")


def resolve_doctor_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据意图返回医生工具子集"""
    if nlu_result is None or not nlu_result.get("intent"):
        return (DOCTOR_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
    doctor_intent_map = {
        "analyze": "analyze", "doctor_analyze": "analyze",
        "order": "order", "generate_order": "order",
        "handle_issue": "issue", "resolve_issue": "issue",
        "chat": "chat", "greeting": "chat",
        "ask_knowledge": "chat", "guideline": "analyze",
    }
    group_name = doctor_intent_map.get(intent)
    if group_name and group_name in DOCTOR_TOOL_GROUPS:
        return (DOCTOR_TOOL_GROUPS[group_name], group_name)
    return (DOCTOR_TOOLS, "complex")
```

---

### Task 2: 扩展 agno_medical_agents.py — 多变体工厂

**File:** Rewrite Agent factory section of `backend/app/core/agno_medical_agents.py`

Change the agent factory section (lines 135-278) to add variants and AUDIT LOGGING to agent runs.

Key changes:
1. Import `NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS` from agno_tools
2. Replace `create_nurse_agent()` → `_build_nurse_agent(variant, tools, limit)`
3. Replace `create_doctor_agent()` → `_build_doctor_agent(variant, tools, limit)`
4. Add `NURSE_AGENT_VARIANT_MAP` and `DOCTOR_AGENT_VARIANT_MAP`
5. Keep all existing `get_*` functions for backward compatibility

---

### Task 3: 护士端点路由 + 审计日志

**File:** Modify `backend/app/routers/nurse_ai.py`

Changes:
1. Audit log imports (AgentAuditLog, SessionLocal, time)
2. `_save_nurse_audit_log()` helper (same pattern as Phase 1)
3. `_try_llm_nurse_analyze()` → 直接路由到 nurse "analyze" variant
4. `nurse_chat_stream()` → NLU 分类 + 路由 + 审计日志

---

### Task 4: 医生端点路由 + 审计日志

**File:** Modify `backend/app/routers/doctor_ai.py`

Changes: Same pattern as Task 3 but for doctor endpoints.

---

### Task 5: 测试

**Files:**
- Extend `tests/test_agno_tools.py` — NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS, resolve functions
- Extend `tests/test_agno_medical_agents.py` — Variant creation tests
- New `tests/test_nurse_doctor_audit.py` — Integration tests

---

### Task 6: 端到端验证
