"""
工具注册中心 — 按角色和意图分组

本模块从各子模块收集所有 @tool 函数并导出，
供 agno_tools.py 重新导出以保持向后兼容。
"""
from .nlu_tools import agno_parse_nlu, agno_get_nlu_result, agno_check_emergency
from .health_data_tools import (
    agno_save_health_data,
    agno_get_patient_context,
    agno_should_ask_weight,
    agno_should_ask_bp,
    agno_analyze_health_trends,
    agno_get_epds_result,
)
from .vital_rules_tools import agno_evaluate_vital_rules
from .nurse_tools import agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor
from .doctor_tools import (
    agno_analyze_patient_comprehensive,
    agno_generate_medical_order,
    agno_handle_issue,
    agno_query_clinical_guideline,
)
from .nlu_context import set_nlu_context, get_nlu_context, pop_nlu_context, cleanup_expired_nlu_context
from .routing import (
    MEDICAL_TOOLS, NURSE_TOOLS, DOCTOR_TOOLS,
    TOOL_GROUPS, NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS,
    INTENT_TO_GROUP,
    resolve_tools_by_intent, resolve_nurse_tools_by_intent, resolve_doctor_tools_by_intent,
)
from .common import _resolve_pid
from .health_data_tools import _save_health_data_sync, _get_patient_context_sync, _analyze_health_trends_sync

__all__ = [
    # NLU
    "agno_parse_nlu", "agno_get_nlu_result", "agno_check_emergency",
    # 健康数据
    "agno_save_health_data", "agno_get_patient_context",
    "agno_should_ask_weight", "agno_should_ask_bp",
    "agno_analyze_health_trends", "agno_get_epds_result",
    # 规则引擎
    "agno_evaluate_vital_rules",
    # 护士
    "agno_query_patient_data", "agno_create_followup_record", "agno_report_issue_to_doctor",
    # 医生
    "agno_analyze_patient_comprehensive", "agno_generate_medical_order",
    "agno_handle_issue", "agno_query_clinical_guideline",
    # NLU 上下文
    "set_nlu_context", "get_nlu_context", "pop_nlu_context", "cleanup_expired_nlu_context",
    # 路由
    "MEDICAL_TOOLS", "NURSE_TOOLS", "DOCTOR_TOOLS",
    "TOOL_GROUPS", "NURSE_TOOL_GROUPS", "DOCTOR_TOOL_GROUPS",
    "INTENT_TO_GROUP",
    "resolve_tools_by_intent", "resolve_nurse_tools_by_intent", "resolve_doctor_tools_by_intent",
    # 通用
    "_resolve_pid",
]
