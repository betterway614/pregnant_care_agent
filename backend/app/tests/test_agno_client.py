"""测试 agno_client.py 的异步修复"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_model():
    """Mock Agno 模型，避免网络请求"""
    with patch("app.core.agno_client.get_agno_model") as mock:
        mock.return_value = MagicMock()
        yield mock


class TestAgnoClientChat:
    """测试 chat() 异步不阻塞"""

    @pytest.mark.asyncio
    async def test_chat_does_not_block_event_loop(self, mock_model):
        """chat() 应使用 await arun()，不阻塞事件循环"""
        from app.core.agno_client import AgnoClient

        mock_response = MagicMock()
        mock_response.content = "测试回复"

        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=mock_response)
        mock_agent.instructions = ["测试指令"]

        client = AgnoClient(agent=mock_agent)
        messages = [
            {"role": "system", "content": "你是小安"},
            {"role": "user", "content": "你好"},
        ]

        # patch _create_agent 避免创建真实 Agent 对象
        with patch.object(client, '_create_agent') as mock_create:
            new_agent = MagicMock()
            new_agent.arun = AsyncMock(return_value=mock_response)
            mock_create.return_value = new_agent

            result = await asyncio.wait_for(client.chat(messages), timeout=2.0)
            assert result == "测试回复"
            mock_create.assert_called_once_with(["你是小安"])

    @pytest.mark.asyncio
    async def test_chat_creates_new_agent_with_system_instructions(self, mock_model):
        """当消息包含 system 指令时，应创建新 Agent 实例"""
        from app.core.agno_client import AgnoClient

        mock_response = MagicMock()
        mock_response.content = "回复"

        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=mock_response)
        mock_agent.instructions = []

        client = AgnoClient(agent=mock_agent)

        with patch.object(client, '_create_agent') as mock_create:
            new_agent = MagicMock()
            new_agent.arun = AsyncMock(return_value=mock_response)
            mock_create.return_value = new_agent

            messages = [
                {"role": "system", "content": "自定义指令"},
                {"role": "user", "content": "测试"},
            ]
            await client.chat(messages)
            mock_create.assert_called_once_with(["自定义指令"])


class TestAgnoClientChatStream:
    """测试 chat_stream() 异步流式输出"""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_content(self):
        """chat_stream() 应异步产出内容"""
        from app.core.agno_client import AgnoClient

        event1 = MagicMock()
        event1.content = "你"
        event2 = MagicMock()
        event2.content = "好"
        event3 = MagicMock()
        event3.content = ""

        async def mock_stream(msg):
            for e in [event1, event2, event3]:
                yield e

        mock_agent = MagicMock()
        mock_agent.arun_stream = mock_stream
        mock_agent.instructions = []

        client = AgnoClient(agent=mock_agent)
        messages = [{"role": "user", "content": "你好"}]

        chunks = []
        async for chunk in client.chat_stream(messages):
            chunks.append(chunk)

        assert chunks == ["你", "好"]

    @pytest.mark.asyncio
    async def test_chat_stream_does_not_block(self):
        """chat_stream() 不应阻塞事件循环"""
        from app.core.agno_client import AgnoClient

        async def mock_stream(msg):
            yield MagicMock(content="流式内容")

        mock_agent = MagicMock()
        mock_agent.arun_stream = mock_stream
        mock_agent.instructions = []

        client = AgnoClient(agent=mock_agent)
        messages = [{"role": "user", "content": "测试"}]

        result = []
        async def collect():
            async for chunk in client.chat_stream(messages):
                result.append(chunk)

        await asyncio.wait_for(collect(), timeout=2.0)
        assert result == ["流式内容"]


class TestAgnoClientChatWithTools:
    """测试 chat_with_tools() 返回格式"""

    @pytest.mark.asyncio
    async def test_chat_with_tools_returns_dict(self):
        """chat_with_tools() 应返回标准格式 dict"""
        from app.core.agno_client import AgnoClient

        mock_response = MagicMock()
        mock_response.content = "工具调用结果"

        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=mock_response)
        mock_agent.instructions = []

        client = AgnoClient(agent=mock_agent)
        messages = [{"role": "user", "content": "分析数据"}]

        result = await client.chat_with_tools(messages, tools=[])
        assert result["role"] == "assistant"
        assert result["content"] == "工具调用结果"

    @pytest.mark.asyncio
    async def test_chat_with_tools_uses_async_arun(self):
        """chat_with_tools() 应使用 await arun() 而非同步 run()"""
        from app.core.agno_client import AgnoClient

        mock_response = MagicMock()
        mock_response.content = ""

        mock_agent = MagicMock()
        mock_agent.arun = AsyncMock(return_value=mock_response)
        mock_agent.run = MagicMock()
        mock_agent.instructions = []

        client = AgnoClient(agent=mock_agent)
        messages = [{"role": "user", "content": "测试"}]

        await client.chat_with_tools(messages, tools=[])
        mock_agent.arun.assert_awaited_once()
        mock_agent.run.assert_not_called()
