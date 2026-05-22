"""Agno Guardrails - 医疗安全防护

三层防御：
1. pre-hook (EmergencyGuardrail): 确定性紧急检测，不依赖 LLM
2. 指令强化: 系统提示词中强调安全规则
3. MedicalSafetyGuardrail: 输出层拦截诊断性结论
4. 通用安全后处理：供护士/医生分析路径复用
"""
from __future__ import annotations

from typing import Optional

from agno.agent._hooks import InputCheckError


class EmergencyGuardrail:
    """Agent pre-hook: 在 LLM 推理前检查紧急情况

    使用确定性 NLU 引擎（非 LLM）检测紧急关键词，
    确保紧急情况不依赖 LLM 的判断能力。

    检测到紧急情况时抛出 InputCheckError，终止 Agent 循环。
    """

    __name__ = "EmergencyGuardrail"

    def __call__(self, run_input=None, **kwargs):
        """同步 guardrail 检查"""
        user_message = self._extract_message(run_input, kwargs)
        if not user_message:
            return

        from .nlu_engine import nlu_engine
        result = nlu_engine.parse(user_message)

        if not result.is_emergency:
            return

        if result.intent == "SUICIDE_RISK":
            raise InputCheckError(
                message="⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，"
                        "或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。",
            )

        raise InputCheckError(
            message="⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。"
                    "如果情况紧急，请拨打120急救电话！",
        )

    async def async_check(self, run_input=None, **kwargs):
        """异步 guardrail 检查"""
        self.__call__(run_input=run_input, **kwargs)

    def _extract_message(self, run_input, kwargs) -> str:
        """从 run_input 或 kwargs 中提取用户消息"""
        if run_input and hasattr(run_input, "input_content_string"):
            return run_input.input_content_string or ""
        if run_input and hasattr(run_input, "content"):
            return run_input.content or ""
        run_context = kwargs.get("run_context")
        if run_context and hasattr(run_context, "user_message"):
            return run_context.user_message or ""
        return ""


class MedicalSafetyGuardrail:
    """输出层安全防护 - 拦截诊断性结论或用药建议

    作为 Agent post_hook 使用，在 LLM 输出后检查内容安全性。
    """

    __name__ = "MedicalSafetyGuardrail"

    BLOCKED_PATTERNS = [
        "诊断为", "诊断是", "确诊",
        "建议用药", "建议服用", "处方",
        "可以吃药", "应该吃药", "用药方案",
    ]

    def __call__(self, response_content: str = "", **kwargs) -> Optional[str]:
        """检查 LLM 输出是否包含违规内容

        Returns:
            拦截提示词（如果检测到违规）
            None（如果安全）
        """
        return self.check(response_content)

    async def async_check(self, response_content: str = "", **kwargs) -> Optional[str]:
        """异步版本的安全检查"""
        return self.check(response_content)

    def check(self, response: str) -> Optional[str]:
        """检查 LLM 输出是否包含违规内容

        Returns:
            拦截提示词（如果检测到违规）
            None（如果安全）
        """
        if not response:
            return None
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in response:
                return "小安不能提供诊断或用药建议。请咨询医生获取专业意见。"
        return None


class NurseSafetyGuardrail(MedicalSafetyGuardrail):
    """护士端输出安全 - 与患者面向规则一致"""

    __name__ = "NurseSafetyGuardrail"


class DoctorDraftGuardrail:
    """医生端草稿输出安全 - 允许更多医学表述，禁止确定性结论"""

    __name__ = "DoctorDraftGuardrail"

    BLOCKED_PATTERNS = [
        "确诊", "确定诊断",
        "无需进一步检查",
        "没有风险", "完全正常",
    ]

    def __call__(self, response_content: str = "", **kwargs) -> Optional[str]:
        return self.check(response_content)

    async def async_check(self, response_content: str = "", **kwargs) -> Optional[str]:
        return self.check(response_content)

    def check(self, response: str) -> Optional[str]:
        if not response:
            return None
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in response:
                return "以上分析需医生审核确认，不能替代临床决策。"
        return None


# ==================== 通用安全后处理 ====================

# 面向患者的输出不可含诊断性结论
PATIENT_SAFETY_PATTERNS = [
    "诊断为", "诊断是", "确诊",
    "建议用药", "建议服用", "处方",
    "可以吃药", "应该吃药", "用药方案",
    "治疗方案如下", "请按以下方案",
]

# 医生工作台草稿允许更多医学内容，但仍禁止确定性诊断
DOCTOR_SAFETY_PATTERNS = [
    "确诊", "确定诊断",
    "无需进一步检查",
    "没有风险", "完全正常",
]


def check_output_safety(text: str, patterns: list[str]) -> Optional[str]:
    """通用输出安全检查

    Args:
        text: 待检查文本
        patterns: 违规关键词列表

    Returns:
        违规提示词（检测到违规时）
        None（安全时）
    """
    if not text:
        return None
    for pattern in patterns:
        if pattern in text:
            return f"输出包含受限内容（{pattern}），已拦截"
    return None


def apply_patient_facing_safety(text: str) -> str:
    """面向患者的输出安全检查，违规时追加警示"""
    result = check_output_safety(text, PATIENT_SAFETY_PATTERNS)
    if result:
        return text + f"\n\n⚠️ {result}。请咨询医生获取专业意见。"
    return text


def apply_doctor_draft_safety(text: str) -> str:
    """医生工作台草稿的安全检查，违规时追加提醒"""
    result = check_output_safety(text, DOCTOR_SAFETY_PATTERNS)
    if result:
        return text + f"\n\n⚠️ {result}。以上分析需医生审核确认。"
    return text
