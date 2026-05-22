"""测试护士/医生 Agent 工具化 + 冒烟测试 + instructions 来源校验"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def _make_mock_model():
    """创建一个模拟 Model 实例"""
    mock = MagicMock()
    mock.__class__.__name__ = "MockModel"
    return mock


def test_nurse_agent_has_tools():
    """验证护士 Agent 配备了工具"""
    from app.core.agno_medical_agents import create_nurse_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_agent()
            assert agent.name == "小护"
            assert len(agent.tools) > 0


def test_nurse_agent_uses_tool_only_knowledge():
    """验证护士 Agent 通过工具检索知识，不启用 Agent 内置 search_knowledge"""
    from app.core.agno_medical_agents import create_nurse_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_agent()
            assert agent.search_knowledge is False


def test_nurse_agent_has_output_schema():
    """验证护士 Agent 使用结构化输出"""
    from app.core.agno_medical_agents import create_nurse_agent, NurseAnalysisOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_agent()
            assert agent.output_schema == NurseAnalysisOutput


def test_doctor_agent_has_tools():
    """验证医生 Agent 配备了工具"""
    from app.core.agno_medical_agents import create_doctor_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_agent()
            assert agent.name == "智医"
            assert len(agent.tools) > 0


def test_doctor_agent_uses_tool_only_knowledge():
    """验证医生 Agent 通过工具检索知识"""
    from app.core.agno_medical_agents import create_doctor_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_agent()
            assert agent.search_knowledge is False


def test_doctor_agent_has_output_schema():
    """验证医生 Agent 使用结构化输出"""
    from app.core.agno_medical_agents import create_doctor_agent, DoctorAnalysisOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_agent()
            assert agent.output_schema == DoctorAnalysisOutput


def test_followup_generate_agent():
    """验证随访生成 Agent 创建成功"""
    from app.core.agno_medical_agents import create_followup_generate_agent, FollowUpGenerateOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_generate_agent()
            assert agent.name == "小安-随访生成"
            assert agent.output_schema == FollowUpGenerateOutput


# ==================== 缺失的冒烟测试 ====================


def test_nurse_chat_agent_smoke():
    """护士对话 Agent 可正常实例化"""
    from app.core.agno_medical_agents import create_nurse_chat_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_chat_agent()
            assert agent.name == "小护-对话"
            assert len(agent.tools) > 0
            assert agent.output_schema is None  # 对话 Agent 不使用结构化输出


def test_doctor_chat_agent_smoke():
    """医生对话 Agent 可正常实例化"""
    from app.core.agno_medical_agents import create_doctor_chat_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_chat_agent()
            assert agent.name == "智医-对话"
            assert len(agent.tools) > 0
            assert agent.output_schema is None


def test_followup_analysis_agent_smoke():
    """随访分析 Agent 可正常实例化"""
    from app.core.agno_medical_agents import create_followup_analysis_agent, FollowUpAnalysisOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_analysis_agent()
            assert agent.name == "小安-随访分析"
            assert agent.output_schema == FollowUpAnalysisOutput


def test_followup_review_agent_smoke():
    """随访审核辅助 Agent 可正常实例化"""
    from app.core.agno_medical_agents import create_followup_review_agent, FollowUpAiReviewOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_review_agent()
            assert agent.name == "小护-审核辅助"
            assert agent.output_schema == FollowUpAiReviewOutput


# ==================== Instructions 来源校验 ====================


def test_nurse_agent_instructions_from_prompts():
    """护士分析 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_nurse_agent
    from app.core.prompts import get_nurse_system_prompt_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_agent()
            assert agent.instructions == get_nurse_system_prompt_instructions()


def test_doctor_agent_instructions_from_prompts():
    """医生分析 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_doctor_agent
    from app.core.prompts import get_doctor_system_prompt_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_agent()
            assert agent.instructions == get_doctor_system_prompt_instructions()


def test_nurse_chat_agent_instructions_from_prompts():
    """护士对话 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_nurse_chat_agent
    from app.core.prompts import get_nurse_chat_system_prompt_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_nurse_chat_agent()
            assert agent.instructions == get_nurse_chat_system_prompt_instructions()


def test_doctor_chat_agent_instructions_from_prompts():
    """医生对话 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_doctor_chat_agent
    from app.core.prompts import get_doctor_chat_system_prompt_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_doctor_chat_agent()
            assert agent.instructions == get_doctor_chat_system_prompt_instructions()


def test_followup_generate_agent_instructions_from_prompts():
    """随访生成 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_followup_generate_agent
    from app.core.prompts import get_followup_generate_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_generate_agent()
            assert agent.instructions == get_followup_generate_instructions()


def test_followup_analysis_agent_instructions_from_prompts():
    """随访分析 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_followup_analysis_agent
    from app.core.prompts import get_followup_analysis_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_analysis_agent()
            assert agent.instructions == get_followup_analysis_instructions()


def test_followup_review_agent_instructions_from_prompts():
    """随访审核辅助 Agent 的 instructions 来自 prompts.py"""
    from app.core.agno_medical_agents import create_followup_review_agent
    from app.core.prompts import get_followup_review_instructions

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_review_agent()
            assert agent.instructions == get_followup_review_instructions()


# ==================== 全量 Agent instructions 非空 ====================


@pytest.mark.parametrize("factory_name", [
    "create_nurse_agent",
    "create_doctor_agent",
    "create_nurse_chat_agent",
    "create_doctor_chat_agent",
    "create_followup_generate_agent",
    "create_followup_analysis_agent",
    "create_followup_review_agent",
])
def test_all_agents_have_nonempty_instructions(factory_name):
    """所有 Agent 工厂函数都注入了非空 instructions"""
    from app.core import agno_medical_agents as mod

    factory = getattr(mod, factory_name)
    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = factory()
            assert agent.instructions is not None
            assert len(agent.instructions) > 0
            assert isinstance(agent.instructions, list)
