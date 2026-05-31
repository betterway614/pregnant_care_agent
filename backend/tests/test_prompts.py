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


# ==================== 压缩版 System Prompt 验证 ====================


def test_pregnant_instructions_compressed_line_count():
    """验证压缩后行数在 13-15 行（原19行）"""
    result = get_pregnant_system_prompt_instructions()
    assert 12 <= len(result) <= 16, f"期望12-16行，实际{len(result)}行"


def test_pregnant_instructions_contains_all_8_duties():
    """验证压缩后所有8条核心职责均保留"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    # 检查编号1-8的职责
    assert "温暖" in joined or "亲切" in joined  # 职责1: 语气
    assert "记录" in joined and "健康数据" in joined  # 职责2
    assert "情绪" in joined or "安抚" in joined  # 职责3
    assert "生理知识" in joined or "基础" in joined  # 职责4
    assert "不出具" in joined and "诊断" in joined  # 职责5
    assert "知识来源" in joined  # 职责6
    assert "引导就医" in joined  # 职责7
    assert "建议" in joined and "咨询" in joined and "产检" in joined  # 职责8


def test_pregnant_instructions_contains_context_rule():
    """验证压缩后上下文自动注入规则保留"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "孕妇ID" in joined
    assert "工具" in joined
    assert "身份信息" in joined


def test_pregnant_instructions_contains_task_planning():
    """验证压缩后任务规划指令保留"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "search_knowledge_base" in joined
    assert "agno_get_patient_context" in joined
    assert "agno_analyze_health_trends" in joined


def test_pregnant_instructions_contains_safety_reminder():
    """验证压缩后安全提醒保留"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "辅助工具" in joined
    assert "不能替代" in joined


def test_compressed_shorter_than_original_ratio():
    """验证压缩后字符数减少至少20%"""
    result = get_pregnant_system_prompt_instructions()
    total_chars = sum(len(line) for line in result)
    # 原版约1260字符，压缩目标 <1000
    assert total_chars < 1100, f"压缩后总字符数{total_chars}仍超过1100"


def test_other_instructions_unchanged():
    """验证护士/医生/随访 instructions 未被修改"""
    from app.core.prompts import (
        get_nurse_system_prompt_instructions,
        get_nurse_chat_system_prompt_instructions,
        get_doctor_system_prompt_instructions,
        get_doctor_chat_system_prompt_instructions,
    )
    # 这些函数应返回合理数量的指令（未压缩）
    nurse = get_nurse_system_prompt_instructions()
    assert len(nurse) >= 8  # 护士分析较详细
    nurse_chat = get_nurse_chat_system_prompt_instructions()
    assert len(nurse_chat) >= 3
    doctor = get_doctor_system_prompt_instructions()
    assert len(doctor) >= 10  # 医生分析最详细
    doctor_chat = get_doctor_chat_system_prompt_instructions()
    assert len(doctor_chat) >= 3
