"""测试 Agno Workflow 编排"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_model():
    """创建一个模拟 Model 实例"""
    mock = MagicMock()
    mock.__class__.__name__ = "MockModel"
    return mock


def test_create_alert_analysis_workflow():
    """验证预警分析流程创建成功"""
    from app.core.agno_workflow import create_alert_analysis_workflow

    mock_model = _make_mock_model()
    mock_nurse = MagicMock()
    mock_nurse.name = "小护-main"
    mock_doctor = MagicMock()
    mock_doctor.name = "智医-main"
    with patch("app.core.agno_medical_agents.get_nurse_agent", return_value=mock_nurse):
        with patch("app.core.agno_medical_agents.get_doctor_agent", return_value=mock_doctor):
            workflow = create_alert_analysis_workflow()
            assert workflow.name == "预警分析流程"
            assert len(workflow.steps) == 2


def test_get_alert_analysis_workflow_singleton():
    """验证 get_alert_analysis_workflow 返回单例"""
    from app.core.agno_workflow import get_alert_analysis_workflow

    mock_model = _make_mock_model()
    mock_nurse = MagicMock()
    mock_nurse.name = "小护-main"
    mock_doctor = MagicMock()
    mock_doctor.name = "智医-main"
    with patch("app.core.agno_medical_agents.get_nurse_agent", return_value=mock_nurse):
        with patch("app.core.agno_medical_agents.get_doctor_agent", return_value=mock_doctor):
            get_alert_analysis_workflow.cache_clear()
            w1 = get_alert_analysis_workflow()
            w2 = get_alert_analysis_workflow()
            assert w1 is w2


# ── Workflow routing integration tests ──


def _make_mock_nlu(intent="ASK_SYMPTOM"):
    """创建模拟 NLU 结果"""
    mock_nlu = MagicMock()
    mock_nlu.intent = intent
    mock_nlu.entities = {}
    mock_nlu.emotion = {"level": "neutral"}
    mock_nlu.is_emergency = False
    return mock_nlu


def _patch_nlu_and_tools(intent_variant="complex"):
    """返回一组 patch 上下文管理器，用于 NLU 和 resolve_tools_by_intent"""
    mock_nlu_mod = MagicMock()
    mock_nlu_mod.nlu_engine.parse.return_value = _make_mock_nlu()
    mock_resolve = MagicMock(return_value=(["agno_parse_nlu"], intent_variant))
    return (
        patch.dict("sys.modules", {"app.core.nlu_engine": mock_nlu_mod}),
        patch("app.core.agno_tools.resolve_tools_by_intent", mock_resolve),
    )


@pytest.mark.asyncio
async def test_non_stream_routes_to_workflow_for_complex_symptom():
    """验证复杂症状查询路由到工作流（非流式）"""
    from app.core.agno_chat_handler import handle_chat_with_agno
    from app.schemas import ChatSendRequest

    mock_workflow_response = MagicMock()
    mock_workflow_response.content = "工作流返回的风险评估结果"

    mock_workflow = MagicMock()
    mock_workflow.arun = AsyncMock(return_value=mock_workflow_response)

    nlu_ctx, tools_ctx = _patch_nlu_and_tools("complex")
    with nlu_ctx, tools_ctx, \
         patch("app.core.agno_chat_handler.settings") as mock_settings, \
         patch("app.core.agno_chat_handler.conversation_store") as mock_store, \
         patch("app.core.agno_chat_handler._save_audit_log"), \
         patch("app.core.agno_workflow.create_prenatal_workflow", return_value=mock_workflow), \
         patch("app.core.agno_chat_handler.create_prenatal_workflow", return_value=mock_workflow, create=True):

        mock_settings.persist_chat_messages = False

        req = ChatSendRequest(
            pregnant_id="test-pid-123",
            message="我最近头晕，需要做什么检查？",
        )
        resp = await handle_chat_with_agno(req)

    assert resp.content == "工作流返回的风险评估结果"
    assert resp.source == "AI_CARE"
    mock_workflow.arun.assert_called_once()


@pytest.mark.asyncio
async def test_non_stream_workflow_failure_falls_back_to_agent():
    """验证工作流失败时回退到单Agent路径（非流式）"""
    from app.core.agno_chat_handler import handle_chat_with_agno
    from app.schemas import ChatSendRequest

    mock_workflow = MagicMock()
    mock_workflow.arun = AsyncMock(side_effect=RuntimeError("workflow failed"))

    mock_agent_response = MagicMock()
    mock_agent_response.content = "Agent兜底回复"
    mock_agent_response.metrics = None
    mock_agent_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_agent_response)

    nlu_ctx, tools_ctx = _patch_nlu_and_tools("complex")
    with nlu_ctx, tools_ctx, \
         patch("app.core.agno_chat_handler.settings") as mock_settings, \
         patch("app.core.agno_chat_handler.conversation_store") as mock_store, \
         patch("app.core.agno_chat_handler._save_audit_log"), \
         patch("app.core.agno_workflow.create_prenatal_workflow", return_value=mock_workflow), \
         patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"complex": lambda: mock_agent}), \
         patch("app.core.agno_agent.get_main_agent", return_value=mock_agent):

        mock_settings.persist_chat_messages = False

        req = ChatSendRequest(
            pregnant_id="test-pid-456",
            message="我最近头晕，需要做什么检查？",
        )
        resp = await handle_chat_with_agno(req)

    assert resp.content == "Agent兜底回复"
    mock_workflow.arun.assert_called_once()
    mock_agent.arun.assert_called_once()


@pytest.mark.asyncio
async def test_non_stream_skips_workflow_for_simple_intent():
    """验证简单意图不走工作流（非流式）"""
    from app.core.agno_chat_handler import handle_chat_with_agno
    from app.schemas import ChatSendRequest

    mock_agent_response = MagicMock()
    mock_agent_response.content = "你好！"
    mock_agent_response.metrics = None
    mock_agent_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_agent_response)

    mock_workflow = MagicMock()

    nlu_ctx, tools_ctx = _patch_nlu_and_tools("simple")
    with nlu_ctx, tools_ctx, \
         patch("app.core.agno_chat_handler.settings") as mock_settings, \
         patch("app.core.agno_chat_handler.conversation_store") as mock_store, \
         patch("app.core.agno_chat_handler._save_audit_log"), \
         patch("app.core.agno_workflow.create_prenatal_workflow", return_value=mock_workflow), \
         patch("app.core.agno_agent.AGENT_VARIANT_MAP", {"simple": lambda: mock_agent}), \
         patch("app.core.agno_agent.get_main_agent", return_value=mock_agent):

        mock_settings.persist_chat_messages = False

        req = ChatSendRequest(
            pregnant_id="test-pid-789",
            message="你好",
        )
        resp = await handle_chat_with_agno(req)

    assert resp.content == "你好！"
    mock_workflow.arun.assert_not_called()
    mock_agent.arun.assert_called_once()
