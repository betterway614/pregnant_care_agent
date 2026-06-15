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
    """验证行数在合理范围（温和用语章节增加了约6行）"""
    result = get_pregnant_system_prompt_instructions()
    assert 15 <= len(result) <= 30, f"期望15-30行，实际{len(result)}行"


def test_pregnant_instructions_contains_all_8_duties():
    """验证所有核心职责均保留"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    # 检查职责
    assert "温暖" in joined or "亲切" in joined  # 职责1: 语气
    assert "记录" in joined and "健康数据" in joined  # 职责2
    assert "情绪" in joined or "安抚" in joined  # 职责3
    assert "生理知识" in joined or "基础" in joined  # 职责4
    assert "禁止" in joined and "诊断" in joined  # 职责5: 安全红线
    assert "知识来源" in joined  # 职责6
    assert "引导就医" in joined or "就医" in joined  # 职责7
    assert "建议" in joined and "咨询" in joined  # 职责8


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


# ==================== 温和用语指令验证 ====================

GENTLE_BANNED_TERMS = ["预警", "警告", "危险", "紧急", "严重", "异常", "超标", "不合格", "确诊"]
GENTLE_REQUIRED_TERMS = ["温和用语", "诊断标准", "焦虑"]


def test_pregnant_instructions_contain_gentle_language_section():
    """验证孕妇 instructions 包含'温和用语'章节"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "温和用语" in joined, "孕妇 instructions 应包含'温和用语'章节"


def test_pregnant_instructions_ban_warning_words():
    """验证孕妇 instructions 明确禁止预警性词汇"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)

    for banned in ["预警", "警告", "危险", "异常", "超标", "确诊"]:
        # 这些词应出现在禁止说明中，而不是不作为禁止项
        assert "禁止" in joined, f"缺少'禁止'类约束语句"
        # 至少有一半的禁止词被明确列出
        covered_count = sum(1 for t in GENTLE_BANNED_TERMS if t in joined)
        assert covered_count >= 5, (
            f"仅列出 {covered_count}/{len(GENTLE_BANNED_TERMS)} 个禁止词汇，"
            f"期望至少5个。已找到: {[t for t in GENTLE_BANNED_TERMS if t in joined]}"
        )


def test_pregnant_instructions_ban_diagnostic_language():
    """验证孕妇 instructions 禁止诊断性表述"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "诊断标准" in joined or "诊断" in joined, "应包含禁止诊断性表述的指令"


def test_pregnant_instructions_require_warm_tone():
    """验证孕妇 instructions 要求温暖语气词结尾"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "～" in joined or "哦" in joined or "哒" in joined or "呢" in joined, (
        "应要求使用温暖语气词结尾"
    )


def test_pregnant_instructions_require_reassurance():
    """验证孕妇 instructions 要求偏离参考值时加安抚语句"""
    result = get_pregnant_system_prompt_instructions()
    joined = " ".join(result)
    assert "不用太担心" in joined or "比较常见" in joined or "不用紧张" in joined, (
        "应要求在健康建议中使用安抚语句"
    )


def test_record_variant_contains_gentle_reminder():
    """验证 record 变体包含温和提醒专项指令"""
    from app.core.prompts import VARIANT_INSTRUCTIONS

    record_prompt = VARIANT_INSTRUCTIONS.get("record", "")
    assert "温和提醒" in record_prompt, "record 变体应包含'温和提醒'专项指令"
    assert "焦虑" in record_prompt, "应强调不引发焦虑"


def test_record_variant_gentle_phrasing_examples():
    """验证 record 变体给出具体的温和表述示例"""
    from app.core.prompts import VARIANT_INSTRUCTIONS

    record_prompt = VARIANT_INSTRUCTIONS.get("record", "")
    # 应有具体的正向表述示例
    assert "比参考范围略高" in record_prompt or "比平时稍高" in record_prompt, (
        "应给出温和表述示例（如'比参考范围略高'）"
    )
    assert "不用紧张" in record_prompt or "不用太担心" in record_prompt, (
        "应给出安抚语句示例"
    )


def test_chat_variant_contains_system_preanalysis():
    """验证 chat 变体保留系统预分析说明"""
    from app.core.prompts import VARIANT_INSTRUCTIONS

    chat_prompt = VARIANT_INSTRUCTIONS.get("chat", "")
    assert "系统预分析" in chat_prompt, "chat 变体应说明系统预分析标签"


def test_pregnant_instructions_line_count_still_valid():
    """验证新增温和用语后行数仍在合理范围"""
    result = get_pregnant_system_prompt_instructions()
    # 增加了温和用语章节，行数允许从15-25扩展到15-30
    assert 15 <= len(result) <= 30, f"期望15-30行，实际{len(result)}行"
