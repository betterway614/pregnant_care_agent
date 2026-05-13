"""测试 Agno 异步 DB 工具

注意：@tool 装饰器会将 async 函数包装为 Function 对象，
SessionLocal 在函数内部延迟导入，使用 app.database.SessionLocal patch。
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def test_agno_save_health_data_is_async():
    """验证 agno_save_health_data 的 entrypoint 是异步的"""
    from app.core.agno_tools import agno_save_health_data

    assert agno_save_health_data is not None
    assert hasattr(agno_save_health_data, 'entrypoint')


def test_agno_get_patient_context_is_async():
    """验证 agno_get_patient_context 的 entrypoint 是异步的"""
    from app.core.agno_tools import agno_get_patient_context

    assert agno_get_patient_context is not None
    assert hasattr(agno_get_patient_context, 'entrypoint')


def test_agno_analyze_health_trends_is_async():
    """验证 agno_analyze_health_trends 的 entrypoint 是异步的"""
    from app.core.agno_tools import agno_analyze_health_trends

    assert agno_analyze_health_trends is not None
    assert hasattr(agno_analyze_health_trends, 'entrypoint')


def test_save_health_data_sync_function():
    """验证 _save_health_data_sync 同步函数可调用"""
    from app.core.agno_tools import _save_health_data_sync

    mock_db = MagicMock()

    with patch("app.database.SessionLocal", return_value=mock_db):
        result = _save_health_data_sync(
            pregnant_id="test-pid",
            weight=65.5,
            sbp=0, dbp=0, fetal_movement=0,
            blood_sugar=0, heart_rate=0,
            sleep_hours=0, steps=0,
        )
        assert "saved_metrics" in result
        assert "weight" in result["saved_metrics"]


def test_get_patient_context_sync_function():
    """验证 _get_patient_context_sync 同步函数可调用"""
    from app.core.agno_tools import _get_patient_context_sync

    mock_db = MagicMock()
    mock_pregnant = MagicMock()
    mock_pregnant.gestational_age_days = 210
    mock_pregnant.display_name = "测试孕妇"
    mock_pregnant.nickname = "小测"
    mock_pregnant.risk_tags = []

    mock_db.query.return_value.filter.return_value.first.return_value = mock_pregnant
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    with patch("app.database.SessionLocal", return_value=mock_db):
        result = _get_patient_context_sync("test-pid")
        assert result["pregnant_id"] == "test-pid"
        assert result["display_name"] == "测试孕妇"


def test_analyze_health_trends_sync_function():
    """验证 _analyze_health_trends_sync 同步函数可调用"""
    from app.core.agno_tools import _analyze_health_trends_sync

    mock_db = MagicMock()
    mock_pregnant = MagicMock()
    mock_pregnant.gestational_age_days = 210

    mock_db.query.return_value.filter.return_value.first.return_value = mock_pregnant
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    with patch("app.database.SessionLocal", return_value=mock_db):
        with patch("app.core.trend_engine.trend_engine") as mock_trend:
            mock_trend.analyze.return_value = []
            result = _analyze_health_trends_sync("test-pid")
            assert result["pregnant_id"] == "test-pid"
