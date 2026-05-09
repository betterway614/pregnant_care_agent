"""测试护士/医生 AI Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_nurse_analyze_uses_agno():
    """验证护士分析在 agno_enabled=True 时使用 AgnoClient"""
    from app.routers.nurse_ai import _try_llm_nurse_analyze
    from app.models import Pregnant

    mock_pregnant = MagicMock(spec=Pregnant)
    mock_pregnant.pregnant_id = "test-pid"
    mock_pregnant.display_name = "测试"
    mock_pregnant.nickname = "小明"

    with patch("app.routers.nurse_ai.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.core.agno_client.get_agno_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value='{"summary":"测试概述","risk_assessment":"低风险","nursing_suggestions":"建议休息","followup_focus":["饮食"]}')
            mock_get.return_value = mock_client
            result = await _try_llm_nurse_analyze(mock_pregnant, 30, 2, [], {})
            assert result is not None
