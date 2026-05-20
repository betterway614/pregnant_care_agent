"""测试 Agno 主 Agent"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def _make_mock_model():
    """创建一个模拟 Model 实例，绕过 Agno 的类型检查"""
    mock = MagicMock()
    mock.__class__.__name__ = "MockModel"
    return mock


def test_create_main_agent():
    """验证主 Agent 创建成功"""
    from app.core.agno_agent import create_main_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_main_agent()
            assert agent is not None
            assert agent.name == "小安"


def test_create_followup_generate_agent():
    """验证随访生成 Agent 创建成功"""
    from app.core.agno_medical_agents import create_followup_generate_agent, FollowUpGenerateOutput

    mock_model = _make_mock_model()
    with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent = create_followup_generate_agent()
            assert agent is not None
            assert agent.name == "小安-随访生成"
            assert agent.output_schema == FollowUpGenerateOutput
