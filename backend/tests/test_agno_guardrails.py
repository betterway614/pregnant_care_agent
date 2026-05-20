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

    # 违规文本
    blocked = apply_patient_facing_safety("诊断为子痫前期")
    assert "请咨询医生" in blocked


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
