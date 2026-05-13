"""测试 Agno 缓存机制 - Agent 单例 + 模型复用"""
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


def test_get_main_agent_singleton():
    """验证 get_main_agent 返回单例"""
    from app.core.agno_agent import get_main_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_main_agent.cache_clear()
            agent1 = get_main_agent()
            agent2 = get_main_agent()
            assert agent1 is agent2


def test_get_main_agent_has_tools():
    """验证缓存的主 Agent 包含工具"""
    from app.core.agno_agent import get_main_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_main_agent.cache_clear()
            agent = get_main_agent()
            assert agent.name == "小安"
            assert len(agent.tools) > 0


def test_get_main_agent_has_hooks():
    """验证缓存的主 Agent 包含 guardrail hooks"""
    from app.core.agno_agent import get_main_agent
    from app.core.agno_guardrails import EmergencyGuardrail, MedicalSafetyGuardrail

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_main_agent.cache_clear()
            agent = get_main_agent()
            # 检查 pre_hooks 包含 EmergencyGuardrail
            pre_hook_names = [h.__name__ for h in agent.pre_hooks]
            assert "EmergencyGuardrail" in pre_hook_names
            # 检查 post_hooks 包含 MedicalSafetyGuardrail
            post_hook_names = [h.__name__ for h in agent.post_hooks]
            assert "MedicalSafetyGuardrail" in post_hook_names


def test_get_main_agent_has_knowledge():
    """验证缓存的主 Agent 集成了 Knowledge"""
    from app.core.agno_agent import get_main_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_main_agent.cache_clear()
            agent = get_main_agent()
            assert agent.knowledge is not None


def test_get_main_agent_has_memory():
    """验证缓存的主 Agent 启用了 Memory"""
    from app.core.agno_agent import get_main_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_main_agent.cache_clear()
            agent = get_main_agent()
            assert agent.enable_agentic_memory is True
            assert agent.add_history_to_context is True
            assert agent.num_history_runs == 5


def test_followup_agent_not_cached():
    """验证随访 Agent 每次创建新实例（含动态上下文）"""
    from app.core.agno_agent import create_followup_agent

    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            agent1 = create_followup_agent(patient_name="张三")
            agent2 = create_followup_agent(patient_name="李四")
            assert agent1 is not agent2
