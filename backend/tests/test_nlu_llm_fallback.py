"""测试 NLU LLM 分类 fallback"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def test_classify_with_llm_returns_valid_intent():
    """验证 LLM 分类返回合法 intent"""
    from app.core.nlu_engine import nlu_engine

    mock_response = MagicMock()
    mock_response.content = "EMOTION_EXPRESS"

    mock_model = MagicMock()
    mock_model.generate.return_value = mock_response

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("我今天感觉不太好")
        assert result == "EMOTION_EXPRESS"


def test_classify_with_llm_returns_unknown_for_invalid():
    """验证 LLM 返回非法值时 fallback 到 UNKNOWN"""
    from app.core.nlu_engine import nlu_engine

    mock_response = MagicMock()
    mock_response.content = "some random text"

    mock_model = MagicMock()
    mock_model.generate.return_value = mock_response

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("随便说点什么")
        assert result == "UNKNOWN"


def test_classify_with_llm_handles_exception():
    """验证 LLM 调用异常时 fallback 到 UNKNOWN"""
    from app.core.nlu_engine import nlu_engine

    mock_model = MagicMock()
    mock_model.generate.side_effect = Exception("LLM unavailable")

    with patch("app.core.agno_client.get_agno_model", return_value=mock_model):
        result = nlu_engine.classify_with_llm("测试消息")
        assert result == "UNKNOWN"
