"""测试 Agno 模型适配器"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_get_agno_model_cloud():
    """验证云端模式返回 OpenAIChat 模型"""
    from app.core.agno_client import get_agno_model

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "cloud"
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_base_url = "https://api.test.com/v1"
        mock_settings.llm_model = "deepseek-chat"
        model = get_agno_model()
        assert model is not None


def test_get_agno_model_local():
    """验证本地模式返回 Ollama 模型"""
    from app.core.agno_client import get_agno_model

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "local"
        mock_settings.ollama_host = "http://localhost:11434"
        mock_settings.local_model = "qwen2.5:7b"
        model = get_agno_model()
        assert model is not None


def test_get_agno_model_mock():
    """验证 mock 模式返回 DummyModel"""
    from app.core.agno_client import get_agno_model

    with patch("app.core.agno_client.settings") as mock_settings:
        mock_settings.llm_mode = "mock"
        model = get_agno_model()
        assert model is not None


@pytest.mark.asyncio
async def test_agno_client_chat():
    """验证 AgnoClient.chat 返回字符串"""
    from app.core.agno_client import AgnoClient

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="测试回复")
    client = AgnoClient(agent=mock_agent)
    result = await client.chat([{"role": "user", "content": "你好"}])
    assert isinstance(result, str)
    assert result == "测试回复"


@pytest.mark.asyncio
async def test_agno_client_chat_stream():
    """验证 AgnoClient.chat_stream 异步生成"""
    from app.core.agno_client import AgnoClient

    mock_agent = MagicMock()

    async def mock_response_stream(*args, **kwargs):
        yield MagicMock(content="你")
        yield MagicMock(content="好")

    mock_agent.arun_stream = mock_response_stream
    client = AgnoClient(agent=mock_agent)
    chunks = []
    async for chunk in client.chat_stream([{"role": "user", "content": "你好"}]):
        chunks.append(chunk)
    assert chunks == ["你", "好"]
