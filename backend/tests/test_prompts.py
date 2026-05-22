"""测试 prompts.py — 单一事实来源的 instructions 验证"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.core.prompts import (
    get_pregnant_system_prompt_instructions,
    get_nurse_system_prompt_instructions,
    get_nurse_chat_system_prompt_instructions,
    get_doctor_system_prompt_instructions,
    get_doctor_chat_system_prompt_instructions,
    get_followup_generate_instructions,
    get_followup_analysis_instructions,
    get_followup_review_instructions,
)

# 全部 8 个 instructions 函数
ALL_INSTRUCTION_FUNCS = [
    get_pregnant_system_prompt_instructions,
    get_nurse_system_prompt_instructions,
    get_nurse_chat_system_prompt_instructions,
    get_doctor_system_prompt_instructions,
    get_doctor_chat_system_prompt_instructions,
    get_followup_generate_instructions,
    get_followup_analysis_instructions,
    get_followup_review_instructions,
]


@pytest.mark.parametrize("fn", ALL_INSTRUCTION_FUNCS, ids=lambda f: f.__name__)
def test_returns_list(fn):
    """每个 instructions 函数返回 list[str]"""
    result = fn()
    assert isinstance(result, list)
    assert all(isinstance(line, str) for line in result)


@pytest.mark.parametrize("fn", ALL_INSTRUCTION_FUNCS, ids=lambda f: f.__name__)
def test_non_empty(fn):
    """每个 instructions 函数返回非空列表"""
    result = fn()
    assert len(result) > 0


@pytest.mark.parametrize("fn", ALL_INSTRUCTION_FUNCS, ids=lambda f: f.__name__)
def test_has_substantive_content(fn):
    """每个 instructions 列表至少有 2 行非空内容"""
    result = fn()
    non_empty = [line for line in result if line.strip()]
    assert len(non_empty) >= 2


# ==================== 内容关键词验证 ====================

def test_pregnant_instructions_contain_role_name():
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "小安" in joined

def test_pregnant_instructions_contain_safety_rules():
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "诊断" in joined or "用药" in joined

def test_nurse_instructions_contain_role_name():
    result = get_nurse_system_prompt_instructions()
    joined = " ".join(result)
    assert "小护" in joined

def test_nurse_instructions_contain_tool_workflow():
    """护士分析 instructions 包含工具调用流程"""
    result = get_nurse_system_prompt_instructions()
    joined = " ".join(result)
    assert "agno_query_patient_data" in joined
    assert "agno_evaluate_vital_rules" in joined

def test_nurse_chat_instructions_contain_role_name():
    result = get_nurse_chat_system_prompt_instructions()
    joined = " ".join(result)
    assert "小护" in joined

def test_doctor_instructions_contain_role_name():
    result = get_doctor_system_prompt_instructions()
    joined = " ".join(result)
    assert "智" in joined

def test_doctor_instructions_contain_tool_workflow():
    """医生分析 instructions 包含工具调用流程"""
    result = get_doctor_system_prompt_instructions()
    joined = " ".join(result)
    assert "agno_analyze_patient_comprehensive" in joined
    assert "agno_evaluate_vital_rules" in joined

def test_doctor_chat_instructions_contain_role_name():
    result = get_doctor_chat_system_prompt_instructions()
    joined = " ".join(result)
    assert "智" in joined

def test_followup_generate_instructions_is_concise():
    """随访生成 instructions 较短（任务简单）"""
    result = get_followup_generate_instructions()
    assert len(result) <= 5

def test_followup_analysis_instructions_contain_normal_ranges():
    """随访分析 instructions 包含正常范围参考值"""
    result = get_followup_analysis_instructions()
    joined = " ".join(result)
    assert "140/90" in joined or "5.3" in joined

def test_followup_review_instructions_contain_review_levels():
    """随访审核 instructions 包含审核建议级别"""
    result = get_followup_review_instructions()
    joined = " ".join(result)
    assert "确认通过" in joined
    assert "紧急上报" in joined


# ==================== 安全规则一致性 ====================

SAFETY_KEYWORDS = ["诊断", "用药"]

@pytest.mark.parametrize("fn", [
    get_nurse_system_prompt_instructions,
    get_nurse_chat_system_prompt_instructions,
    get_followup_analysis_instructions,
    get_followup_review_instructions,
], ids=lambda f: f.__name__)
def test_nurse_family_instructions_contain_safety_rules(fn):
    """所有护士/随访指令都包含安全规则（不出具诊断/用药建议）"""
    result = fn()
    joined = " ".join(result)
    has_safety = any(kw in joined for kw in SAFETY_KEYWORDS)
    assert has_safety, f"{fn.__name__} 缺少安全规则关键词"
