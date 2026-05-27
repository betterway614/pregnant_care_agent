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
