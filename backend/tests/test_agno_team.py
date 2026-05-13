"""测试 Agno Team 模式 - 多 Agent 协作"""
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


def test_create_care_team():
    """验证孕期护理团队创建成功"""
    from app.core.agno_team import create_care_team

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                team = create_care_team()
                assert team is not None
                assert team.name == "AI-Care 孕期护理团队"
                assert len(team.members) == 3


def test_care_team_members():
    """验证团队成员包含小安、小护、智医"""
    from app.core.agno_team import create_care_team

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                team = create_care_team()
                member_names = [m.name for m in team.members]
                assert "小安" in member_names
                assert "小护" in member_names
                assert "智医" in member_names


def test_get_care_team_singleton():
    """验证 get_care_team 返回单例"""
    from app.core.agno_team import get_care_team

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                # 清除缓存
                get_care_team.cache_clear()
                team1 = get_care_team()
                team2 = get_care_team()
                assert team1 is team2
