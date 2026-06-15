"""Agno @tool 医疗工具集合（门面模块）

本模块从 core/tools/ 子包重新导出所有工具函数和路由逻辑，
保持向后兼容。实际实现已拆分到 core/tools/ 下的各子模块中。

拆分结构:
- core/tools/nlu_tools.py       — NLU 解析、急诊检测
- core/tools/health_data_tools.py — 健康数据持久化、查询、趋势
- core/tools/vital_rules_tools.py — 生命体征规则评估
- core/tools/nurse_tools.py     — 护士专用工具
- core/tools/doctor_tools.py    — 医生专用工具
- core/tools/nlu_context.py     — NLU 上下文管理
- core/tools/routing.py         — 工具路由映射
- core/tools/common.py          — 通用辅助函数
"""
from __future__ import annotations

# 从子包重新导出所有内容，保持向后兼容
from .tools import (
    # NLU
    agno_get_nlu_result, agno_check_emergency,
    # 健康数据
    agno_save_health_data, agno_get_patient_context,
    agno_get_pending_prompts,
    agno_analyze_health_trends, agno_get_epds_result,
    # 规则引擎
    agno_evaluate_vital_rules,
    # 护士
    agno_list_patients, agno_query_patient_data, agno_create_followup_record, agno_report_issue_to_doctor,
    # 医生
    agno_analyze_patient_comprehensive, agno_generate_medical_order,
    agno_handle_issue, agno_query_clinical_guideline,
    # NLU 上下文
    set_nlu_context, get_nlu_context, pop_nlu_context, cleanup_expired_nlu_context,
    # 路由
    MEDICAL_TOOLS, NURSE_TOOLS, DOCTOR_TOOLS,
    TOOL_GROUPS, NURSE_TOOL_GROUPS, DOCTOR_TOOL_GROUPS,
    INTENT_TO_GROUP,
    resolve_tools_by_intent, resolve_nurse_tools_by_intent, resolve_doctor_tools_by_intent,
    # 通用
    _resolve_pid,
    truncate_tool_result,
    tool_metrics,
)

# 重新导出内部辅助函数和模块级变量（测试可能直接导入）
from .tools.health_data_tools import (
    _save_health_data_sync,
    _get_patient_context_sync,
    _analyze_health_trends_sync,
)
from .tools.nlu_context import (
    _nlu_context,
    _nlu_context_lock,
    _NLU_CONTEXT_TTL,
)

__all__ = [
    "agno_get_nlu_result", "agno_check_emergency",
    "agno_evaluate_vital_rules",
    "agno_save_health_data", "agno_get_patient_context",
    "agno_get_pending_prompts",
    "agno_analyze_health_trends", "agno_get_epds_result",
    "agno_list_patients", "agno_query_patient_data", "agno_create_followup_record", "agno_report_issue_to_doctor",
    "agno_analyze_patient_comprehensive", "agno_generate_medical_order",
    "agno_handle_issue", "agno_query_clinical_guideline",
    "set_nlu_context", "get_nlu_context", "pop_nlu_context", "cleanup_expired_nlu_context",
    "MEDICAL_TOOLS", "NURSE_TOOLS", "DOCTOR_TOOLS",
    "TOOL_GROUPS", "NURSE_TOOL_GROUPS", "DOCTOR_TOOL_GROUPS",
    "INTENT_TO_GROUP",
    "resolve_tools_by_intent", "resolve_nurse_tools_by_intent", "resolve_doctor_tools_by_intent",
    "_resolve_pid",
    "truncate_tool_result",
    "tool_metrics",
]
