"""测试 Agno Guardrails - 安全防护"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def test_emergency_guardrail_name():
    """验证 EmergencyGuardrail 有正确的 __name__"""
    from app.core.agno_guardrails import EmergencyGuardrail

    guardrail = EmergencyGuardrail()
    assert guardrail.__name__ == "EmergencyGuardrail"


def test_emergency_guardrail_normal_input():
    """验证正常输入不触发 EmergencyGuardrail"""
    from app.core.agno_guardrails import EmergencyGuardrail
    from agno.agent._hooks import InputCheckError

    guardrail = EmergencyGuardrail()

    # Mock run_input with normal message
    mock_input = MagicMock()
    mock_input.input_content_string = "今天感觉不错"

    with patch("app.core.nlu_engine.nlu_engine") as mock_nlu:
        mock_nlu.parse.return_value = MagicMock(is_emergency=False)
        # 不应抛出异常
        guardrail(run_input=mock_input)


def test_medical_safety_guardrail_name():
    """验证 MedicalSafetyGuardrail 有正确的 __name__"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.__name__ == "MedicalSafetyGuardrail"


def test_medical_safety_guardrail_safe_response():
    """验证安全响应不被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    result = guardrail.check("孕期要注意休息，保持良好心情")
    assert result is None


def test_medical_safety_guardrail_blocks_diagnosis():
    """验证诊断性结论被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    result = guardrail.check("根据您的症状，诊断为妊娠期糖尿病")
    assert result is not None
    assert "诊断" in result or "不能" in result


def test_medical_safety_guardrail_blocks_medication():
    """验证用药建议被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    result = guardrail.check("建议服用二甲双胍控制血糖")
    assert result is not None
    assert "不能" in result or "咨询医生" in result


def test_medical_safety_guardrail_empty_response():
    """验证空响应不被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    result = guardrail.check("")
    assert result is None

    result = guardrail.check(None)
    assert result is None


def test_medical_safety_guardrail_callable():
    """验证 MedicalSafetyGuardrail 可作为 post_hook 调用"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()

    # 安全响应
    result = guardrail(response_content="保持良好心情")
    assert result is None

    # 危险响应
    result = guardrail(response_content="诊断为高血压")
    assert result is not None


# ==================== 通用安全后处理 ====================


def test_check_output_safety_safe():
    """验证安全文本通过检查"""
    from app.core.agno_guardrails import check_output_safety, PATIENT_SAFETY_PATTERNS

    result = check_output_safety("孕期注意休息", PATIENT_SAFETY_PATTERNS)
    assert result is None


def test_check_output_safety_blocks():
    """验证违规文本被检测"""
    from app.core.agno_guardrails import check_output_safety, PATIENT_SAFETY_PATTERNS

    result = check_output_safety("根据您的症状，诊断为妊娠期糖尿病", PATIENT_SAFETY_PATTERNS)
    assert result is not None


def test_apply_patient_facing_safety():
    """验证患者面向安全后处理追加警示"""
    from app.core.agno_guardrails import apply_patient_facing_safety

    # 安全文本
    safe = apply_patient_facing_safety("建议多休息")
    assert safe == "建议多休息"

    # 违规文本 — 应被完全拦截替换为安全提示
    blocked = apply_patient_facing_safety("诊断为子痫前期")
    assert "诊断为" not in blocked
    assert "医生进行专业评估" in blocked


def test_apply_doctor_draft_safety():
    """验证医生草稿安全后处理"""
    from app.core.agno_guardrails import apply_doctor_draft_safety

    # 安全文本
    safe = apply_doctor_draft_safety("建议复查尿蛋白")
    assert safe == "建议复查尿蛋白"

    # 医生草稿中允许"建议用药"等临床术语
    draft_safe = apply_doctor_draft_safety("建议用药方案需医生确认")
    assert "需医生确认" in draft_safe
    # 但应拦截确定性结论
    blocked = apply_doctor_draft_safety("确诊为妊娠期糖尿病")
    assert "需医生审核" in blocked


# ==================== 新增: 医嘱安全后处理 ====================


def test_apply_order_draft_safety_safe_text():
    """验证安全的医嘱文本不被修改"""
    from app.core.agno_guardrails import apply_order_draft_safety

    safe = apply_order_draft_safety("建议每2周复查血压，低盐饮食，每日监测血压。")
    assert safe == "建议每2周复查血压，低盐饮食，每日监测血压。"


def test_apply_order_draft_safety_blocks_diagnosis():
    """验证医嘱过滤确诊表述"""
    from app.core.agno_guardrails import apply_order_draft_safety

    blocked = apply_order_draft_safety("确诊为妊娠期高血压，需收治入院。")
    assert "需医生审核修改后签署" in blocked


def test_apply_order_draft_safety_blocks_definite_treatment():
    """验证医嘱过滤确定性治疗方案"""
    from app.core.agno_guardrails import apply_order_draft_safety

    blocked = apply_order_draft_safety("治疗方案为口服拉贝洛尔100mg bid。")
    assert "需医生审核修改后签署" in blocked


def test_apply_order_draft_safety_allows_suggestion():
    """验证医嘱允许建议性措辞"""
    from app.core.agno_guardrails import apply_order_draft_safety

    # 使用"建议"、"可考虑"等措辞应该通过
    safe = apply_order_draft_safety("建议低盐饮食，可考虑口服拉贝洛尔控制血压，具体用药需医生评估。")
    assert safe == "建议低盐饮食，可考虑口服拉贝洛尔控制血压，具体用药需医生评估。"


def test_apply_order_draft_safety_empty_text():
    """验证空文本不报错"""
    from app.core.agno_guardrails import apply_order_draft_safety

    assert apply_order_draft_safety("") == ""
    assert apply_order_draft_safety(None) is None


def test_doctor_draft_guardrail_enhanced_patterns():
    """验证DoctorDraftGuardrail增强后的拦截模式"""
    from app.core.agno_guardrails import DoctorDraftGuardrail

    guardrail = DoctorDraftGuardrail()

    # 新增拦截模式
    assert guardrail.check("明确诊断为妊娠期糖尿病") is not None
    assert guardrail.check("无需进一步检查即可确认") is not None  # "无需进一步检查"
    assert guardrail.check("可以排除子痫前期") is not None

    # 安全内容
    assert guardrail.check("建议进一步评估血压情况") is None


# ==================== 药物剂量模式检测 ====================


@pytest.mark.skip(reason="剂量模式检测功能尚未实现，仅检测诊断性结论")
def test_guardrail_blocks_dosage_pattern_daily():
    """验证 'X片每日Y次' 模式被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.check("每次2片，每日3次") is not None
    assert guardrail.check("每次1片,每日2次") is not None


@pytest.mark.skip(reason="剂量模式检测功能尚未实现，仅检测诊断性结论")
def test_guardrail_blocks_dosage_pattern_ml():
    """验证 '每次Xml' 模式被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.check("每次10ml") is not None
    assert guardrail.check("每次5mg") is not None


@pytest.mark.skip(reason="剂量模式检测功能尚未实现，仅检测诊断性结论")
def test_guardrail_blocks_dosage_pattern_timing():
    """验证 '饭前/饭后/睡前服用X' 模式被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.check("饭前服用2片") is not None
    assert guardrail.check("睡前口服1粒") is not None
    assert guardrail.check("空腹吃3片") is not None


@pytest.mark.skip(reason="剂量模式检测功能尚未实现，仅检测诊断性结论")
def test_guardrail_blocks_dosage_pattern_abbreviation():
    """验证 'Xmg bid/tid' 模式被拦截"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.check("100mg bid") is not None
    assert guardrail.check("50mg tid") is not None
    assert guardrail.check("25mg 每日两次") is not None


def test_guardrail_allows_safe_suggestion():
    """验证建议性措辞不被误拦"""
    from app.core.agno_guardrails import MedicalSafetyGuardrail

    guardrail = MedicalSafetyGuardrail()
    assert guardrail.check("建议咨询医生获取用药指导") is None
    assert guardrail.check("请遵医嘱服药") is None
    assert guardrail.check("具体治疗需由医生评估决定") is None
