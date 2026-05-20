"""测试 Agno 工具函数"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def test_agno_parse_nlu_content():
    """验证 agno_parse_nlu 工具返回正确格式"""
    from app.core.agno_tools import agno_parse_nlu

    result = agno_parse_nlu.entrypoint("你好")
    assert "intent" in result
    assert "entities" in result
    assert "is_emergency" in result


def test_agno_check_emergency_normal():
    """验证 agno_check_emergency 对正常消息返回非紧急"""
    from app.core.agno_tools import agno_check_emergency

    result = agno_check_emergency.entrypoint("你好，今天感觉不错")
    assert result["is_emergency"] is False


def test_agno_get_epds_low():
    """验证 EPDS 工具低风险结果"""
    from app.core.agno_tools import agno_get_epds_result

    result = agno_get_epds_result.entrypoint(total_score=5)
    assert result["risk_level"] == "low"


def test_agno_get_epds_high():
    """验证 EPDS 工具高风险结果"""
    from app.core.agno_tools import agno_get_epds_result

    result = agno_get_epds_result.entrypoint(total_score=14)
    assert result["risk_level"] == "high"


@pytest.mark.asyncio
async def test_agno_get_patient_context():
    """验证 agno_get_patient_context 异步工具"""
    from app.core.agno_tools import agno_get_patient_context

    mock_pregnant = MagicMock()
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"
    mock_pregnant.nickname = "小明"
    mock_pregnant.gestational_age_days = 210
    mock_pregnant.risk_tags = ["GDM"]

    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = mock_pregnant
    mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    with patch("app.database.SessionLocal", return_value=mock_db):
        result = await agno_get_patient_context.entrypoint("test-pid")
        assert result["pregnant_id"] == "test-pid"
        assert result["gestational_week"] == "30+0"
        assert "GDM" in result["risk_tags"]
