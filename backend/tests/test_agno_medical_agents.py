"""测试护士/医生 Agent 工具化"""
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
