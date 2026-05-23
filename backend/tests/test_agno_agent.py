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
            assert "小安" in agent.name


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


# ==================== Agent 变体测试 ====================

AGENT_FACTORIES = []


def _get_factories():
    """懒加载 Agent 工厂列表（需要 mock model）"""
    global AGENT_FACTORIES
    if AGENT_FACTORIES:
        return AGENT_FACTORIES

    mock_model = _make_mock_model()
    # 创建带 mock 的工厂闭包
    from functools import partial
    import app.core.agno_agent as agno_agent_mod

    orig_get_model = agno_agent_mod.get_agno_model
    agno_agent_mod.get_agno_model = lambda **kw: mock_model

    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            from app.core.agno_agent import (
                get_chat_agent, get_record_agent, get_qa_agent,
                get_emergency_agent, get_main_agent, AGENT_VARIANT_MAP,
            )
            AGENT_FACTORIES = [
                ("chat", get_chat_agent, 3, 3),
                ("record", get_record_agent, 4, 4),
                ("qa", get_qa_agent, 3, 4),
                ("emergency", get_emergency_agent, 2, 1),
                ("complex", get_main_agent, 10, 8),
            ]
    return AGENT_FACTORIES


@pytest.mark.parametrize("variant_name,factory,expected_tools,expected_limit", [
    ("chat", None, 3, 3),
    ("record", None, 4, 4),
    ("qa", None, 3, 4),
    ("emergency", None, 2, 1),
    ("complex", None, 10, 8),
])
def test_agent_variant_tool_count_and_limit(variant_name, factory, expected_tools, expected_limit):
    """验证各变体的工具数量和 tool_call_limit"""
    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            from app.core.agno_agent import (
                get_chat_agent, get_record_agent, get_qa_agent,
                get_emergency_agent, get_main_agent,
            )
            factories = {
                "chat": get_chat_agent,
                "record": get_record_agent,
                "qa": get_qa_agent,
                "emergency": get_emergency_agent,
                "complex": get_main_agent,
            }
            agent = factories[variant_name]()
            assert len(agent.tools) == expected_tools, f"{variant_name}: expected {expected_tools} tools, got {len(agent.tools)}"
            assert agent.tool_call_limit == expected_limit, f"{variant_name}: expected limit {expected_limit}, got {agent.tool_call_limit}"


def test_agent_variant_map_keys():
    """验证 AGENT_VARIANT_MAP 包含 5 个变体"""
    from app.core.agno_agent import AGENT_VARIANT_MAP
    assert set(AGENT_VARIANT_MAP.keys()) == {"chat", "record", "qa", "emergency", "complex"}


def test_agent_variant_names():
    """验证各变体的 name 属性"""
    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            from app.core.agno_agent import (
                get_chat_agent, get_record_agent, get_qa_agent,
                get_emergency_agent, get_main_agent,
            )
            assert get_chat_agent().name == "小安-chat"
            assert get_record_agent().name == "小安-record"
            assert get_qa_agent().name == "小安-qa"
            assert get_emergency_agent().name == "小安-emergency"
            assert get_main_agent().name == "小安-main"


def test_main_agent_unchanged():
    """验证 get_main_agent() 向后兼容 — 仍返回 10 tools"""
    mock_model = _make_mock_model()
    with patch("app.core.agno_agent.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            from app.core.agno_agent import get_main_agent, MEDICAL_TOOLS
            agent = get_main_agent()
            assert agent.tools == MEDICAL_TOOLS
            assert agent.tool_call_limit == 8


def test_agent_variant_get_main_agent_docstring():
    """验证 get_main_agent 有文档字符串"""
    from app.core.agno_agent import get_main_agent
    assert get_main_agent.__doc__ is not None
    assert "全量兜底" in get_main_agent.__doc__
