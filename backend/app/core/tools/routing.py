"""
工具路由 — 意图到工具组的映射

职责: 根据 NLU 意图选择合适的工具子集。

关于 search_knowledge_base 工具:
    知识检索工具由 Agno 框架在 Agent 创建时根据 search_knowledge=True 参数
    自动注入 (参见 agno_agent.py 和 agno_medical_agents.py 中的 _build_agent /
    _build_nurse_agent_variant / _build_doctor_agent_variant)。
    该工具调用 knowledge.search() 执行 PgVector 向量/混合检索，
    因此 TOOL_GROUPS 各分组中不需要（也不应该）显式包含此工具。
    框架注入的工具名称为 'search_knowledge_base'，与系统提示词中的引用一致。
"""
from __future__ import annotations

from .nlu_tools import agno_check_emergency, agno_get_nlu_result
from .health_data_tools import (
    agno_save_health_data, agno_get_patient_context,
    agno_get_pending_prompts,
    agno_analyze_health_trends, agno_get_epds_result,
)
from .vital_rules_tools import agno_evaluate_vital_rules
from .nurse_tools import agno_list_patients, agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor
from .doctor_tools import (
    agno_analyze_patient_comprehensive, agno_generate_medical_order,
    agno_handle_issue, agno_query_clinical_guideline,
)

# ==================== 主对话 Agent 工具集 ====================

MEDICAL_TOOLS = [
    agno_get_nlu_result, agno_check_emergency,
    agno_evaluate_vital_rules, agno_save_health_data, agno_get_patient_context,
    agno_get_pending_prompts,
    agno_analyze_health_trends, agno_get_epds_result,
]

# ==================== 护士端 Agent 工具集 ====================

NURSE_TOOLS = [
    agno_list_patients, agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor,
    agno_analyze_health_trends, agno_evaluate_vital_rules,
]

# ==================== 医生端 Agent 工具集 ====================

DOCTOR_TOOLS = [
    agno_list_patients, agno_query_patient_data,
    agno_analyze_patient_comprehensive, agno_generate_medical_order,
    agno_handle_issue, agno_query_clinical_guideline,
    agno_analyze_health_trends, agno_evaluate_vital_rules,
]

# ==================== 工具子集分组 ====================

# 知识检索工具 search_knowledge_base 由 Agno 框架根据 search_knowledge=True 自动注入，不在此处显式列出

TOOL_GROUPS: dict[str, list] = {
    "chat": [agno_get_patient_context, agno_get_pending_prompts, agno_get_epds_result, agno_save_health_data],
    "record": [agno_get_nlu_result, agno_save_health_data, agno_evaluate_vital_rules, agno_get_patient_context],
    "qa": [agno_get_patient_context, agno_analyze_health_trends],
    "emergency": [agno_check_emergency, agno_get_patient_context],
    "complex": MEDICAL_TOOLS,
}

# 意图 → variant 路由 (RAG 灵敏度门控策略)
#   qa:      仅高置信度医学知识查询 (NLU 已确认含医学主题词)
#   complex: 症状/检查等复杂场景 (有 search_knowledge 但 LLM 自主决定是否检索)
#   chat:    闲聊/情绪/日常操作 (无 search_knowledge，不触发 RAG)
#   record:  数据记录 (无 search_knowledge)
INTENT_TO_GROUP: dict[str, str] = {
    "health_data_report": "record", "emotion_express": "chat",
    "knowledge_query": "qa", "schedule_inquiry": "chat",
    "emergency": "emergency", "suicide_risk": "emergency",
    "greeting": "chat", "unknown": "complex",
    "chat": "chat", "emotion": "chat",
    "record_weight": "record", "record_bp": "record",
    "record_glucose": "record", "record_fetal_movement": "record",
    # LLM 辅助分类的意图:
    "ask_knowledge": "qa",       # LLM 明确判定为知识问题 → qa
    "ask_symptom": "complex",    # 症状咨询 → 复杂兜底 (全量工具+知识)
    "ask_exam": "complex",       # 检查解读 → 复杂兜底 (可能需趋势+知识)
}

# 知识检索工具 search_knowledge_base 由 Agno 框架根据 search_knowledge=True 自动注入，不在此处显式列出

NURSE_TOOL_GROUPS: dict[str, list] = {
    "analyze": [agno_query_patient_data, agno_analyze_health_trends, agno_evaluate_vital_rules],
    "followup": [agno_create_followup_record, agno_query_patient_data],
    "report": [agno_report_issue_to_doctor, agno_query_patient_data],
    "chat": [agno_list_patients, agno_query_patient_data, agno_analyze_health_trends],
}

# 知识检索工具 search_knowledge_base 由 Agno 框架根据 search_knowledge=True 自动注入，不在此处显式列出

DOCTOR_TOOL_GROUPS: dict[str, list] = {
    "analyze": [agno_analyze_patient_comprehensive, agno_analyze_health_trends, agno_evaluate_vital_rules, agno_query_clinical_guideline],
    "order": [agno_generate_medical_order, agno_analyze_patient_comprehensive],
    "issue": [agno_handle_issue, agno_analyze_patient_comprehensive],
    "chat": [agno_list_patients, agno_query_patient_data, agno_analyze_health_trends, agno_evaluate_vital_rules, agno_query_clinical_guideline],
}


# ==================== 路由函数 ====================

def resolve_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回工具子集和 variant 名称"""
    if nlu_result is None or not nlu_result.get("intent"):
        return (MEDICAL_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
    group_name = INTENT_TO_GROUP.get(intent)
    if group_name and group_name in TOOL_GROUPS:
        return (TOOL_GROUPS[group_name], group_name)
    # UNKNOWN 回退到 chat 变体（对话式交互，非结构化分析）
    return (TOOL_GROUPS.get("chat", MEDICAL_TOOLS), "chat")


def resolve_nurse_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回护士工具子集和 variant 名称"""
    if nlu_result is None or not nlu_result.get("intent"):
        return (NURSE_TOOLS, "complex")
    intent = nlu_result.get("intent", "").lower()
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
    # UNKNOWN 回退到 chat 变体（对话式交互，非结构化分析）
    return (NURSE_TOOL_GROUPS.get("chat", NURSE_TOOLS), "chat")


def resolve_doctor_tools_by_intent(nlu_result: dict | None) -> tuple[list, str]:
    """根据 NLU 意图返回医生工具子集和 variant 名称"""
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
    # UNKNOWN 回退到 chat 变体（对话式交互，非结构化分析）
    return (DOCTOR_TOOL_GROUPS.get("chat", DOCTOR_TOOLS), "chat")
