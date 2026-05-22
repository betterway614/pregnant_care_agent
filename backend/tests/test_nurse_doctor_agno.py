"""测试护士/医生 AI Router Agno 集成（专用 Agent 路径）"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_nurse_analyze_uses_dedicated_agent():
    """验证护士分析在 agno_enabled=True 时使用专用 Nurse Agent"""
    from app.routers.nurse_ai import _try_llm_nurse_analyze
    from app.models import Pregnant

    mock_pregnant = MagicMock(spec=Pregnant)
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"
    mock_pregnant.nickname = "小明"

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "summary": "孕妇整体状况良好",
        "risk_assessment": "低风险",
        "nursing_suggestions": "建议适当运动",
        "followup_focus": ["饮食", "运动", "睡眠"]
    })

    with patch("app.routers.nurse_ai.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.core.agno_medical_agents.get_nurse_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.arun = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent
            result = await _try_llm_nurse_analyze(mock_pregnant, 30, 2, [], {})
            assert result is not None
            assert result.summary == "孕妇整体状况良好"
            assert "饮食" in result.followup_focus


@pytest.mark.asyncio
async def test_doctor_analyze_uses_dedicated_agent():
    """验证医生分析在 agno_enabled=True 时使用专用 Doctor Agent"""
    from app.routers.doctor_ai import _try_llm_doctor_analyze
    from app.models import Pregnant

    mock_pregnant = MagicMock(spec=Pregnant)
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "analysis": "孕妇状况稳定",
        "evidence_references": ["ACOG指南"],
        "suggested_orders": "建议定期产检",
        "risk_summary": "低风险",
        "differential_diagnosis": [],
        "reasoning_chain": [],
    })

    with patch("app.routers.doctor_ai.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.core.agno_medical_agents.get_doctor_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.arun = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent
            result = await _try_llm_doctor_analyze(mock_pregnant, 30, 2, [], {}, "")
            assert result is not None
            assert "稳定" in result.analysis
            assert "ACOG指南" in result.evidence_references


@pytest.mark.asyncio
async def test_followup_generate_uses_dedicated_agent():
    """验证随访生成在 agno_enabled=True 时使用专用 FollowUp Agent"""
    from app.routers.nurse_ai import _try_llm_followup_generate
    from app.models import Pregnant

    mock_pregnant = MagicMock(spec=Pregnant)
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"

    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "opening_message": "您好，我是随访护士",
        "questions": [{"question": "最近感觉如何？", "purpose": "了解身体状况"}],
        "closing_message": "祝您健康",
    })

    with patch("app.routers.nurse_ai.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.core.agno_medical_agents.create_followup_generate_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.arun = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent
            result = await _try_llm_followup_generate(mock_pregnant, 30, 2, [], {}, "standard")
            assert result is not None
            assert "随访护士" in result.opening_message
            assert len(result.questions) > 0
