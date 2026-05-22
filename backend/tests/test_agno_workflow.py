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


def test_get_alert_analysis_workflow():
    from app.core.agno_workflow import create_alert_analysis_workflow

    mock_model = _make_mock_model()
    mock_nurse = MagicMock()
    mock_nurse.name = "小护"
    mock_doctor = MagicMock()
    mock_doctor.name = "智医"
    with patch("app.core.agno_workflow.get_agno_model", return_value=mock_model):
        with patch("app.core.agno_workflow.get_nurse_agent", return_value=mock_nurse):
            with patch("app.core.agno_workflow.get_doctor_agent", return_value=mock_doctor):
                with patch("agno.agent._init.get_model", return_value=mock_model):
                    workflow = create_alert_analysis_workflow()
                    assert workflow.name == "预警分析流程"
                    assert len(workflow.steps) == 2


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
