"""测试 Agno Workflow 编排"""
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


def test_create_prenatal_workflow():
    """验证孕检流程 Workflow 创建成功"""
    from app.core.agno_workflow import create_prenatal_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            workflow = create_prenatal_workflow()
            assert workflow is not None
            assert workflow.name == "孕检流程"


def test_prenatal_workflow_steps():
    """验证孕检流程包含正确的步骤"""
    from app.core.agno_workflow import create_prenatal_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            workflow = create_prenatal_workflow()
            step_names = [s.name for s in workflow.steps]
            assert "健康数据采集" in step_names
            assert "风险评估" in step_names
            assert "报告生成" in step_names


def test_create_followup_workflow():
    """验证随访流程 Workflow 创建成功"""
    from app.core.agno_workflow import create_followup_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            workflow = create_followup_workflow()
            assert workflow is not None
            assert workflow.name == "随访流程"


def test_followup_workflow_steps():
    """验证随访流程包含正确的步骤"""
    from app.core.agno_workflow import create_followup_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            workflow = create_followup_workflow()
            step_names = [s.name for s in workflow.steps]
            assert "随访准备" in step_names
            assert "随访执行" in step_names
            assert "随访总结" in step_names


def test_get_prenatal_workflow_singleton():
    """验证 get_prenatal_workflow 返回单例"""
    from app.core.agno_workflow import get_prenatal_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_prenatal_workflow.cache_clear()
            w1 = get_prenatal_workflow()
            w2 = get_prenatal_workflow()
            assert w1 is w2


def test_get_followup_workflow_singleton():
    """验证 get_followup_workflow 返回单例"""
    from app.core.agno_workflow import get_followup_workflow

    mock_model = _make_mock_model()
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("agno.agent._init.get_model", return_value=mock_model):
            get_followup_workflow.cache_clear()
            w1 = get_followup_workflow()
            w2 = get_followup_workflow()
            assert w1 is w2
