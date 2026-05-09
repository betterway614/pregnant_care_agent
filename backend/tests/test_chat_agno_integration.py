"""测试 Chat Router Agno 集成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_send_message_uses_agno_when_enabled():
    """验证 agno_enabled=True 时使用 Agno Agent"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = True
        with patch("app.routers.chat.get_agno_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value="Agno回复")
            mock_get_client.return_value = mock_client
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.SessionLocal") as mock_db:
                    mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                    with patch("app.routers.chat.memory_manager") as mock_mem:
                        mock_mem.should_ask_weight.return_value = False
                        mock_mem.should_ask_bp.return_value = False
                        req = ChatSendRequest(
                            pregnant_id="test-pid",
                            message="你好",
                        )
                        resp = await send_message(req)
                        assert resp.content == "Agno回复"
                        mock_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_uses_original_when_disabled():
    """验证 agno_enabled=False 时使用原始 LLM"""
    from app.routers.chat import send_message
    from app.schemas import ChatSendRequest

    with patch("app.routers.chat.settings") as mock_settings:
        mock_settings.agno_enabled = False
        with patch("app.routers.chat.llm") as mock_llm:
            mock_llm.chat = AsyncMock(return_value="原始回复")
            with patch("app.routers.chat.nlu_engine") as mock_nlu:
                mock_nlu.parse.return_value = MagicMock(
                    intent="GREETING", entities={}, is_emergency=False,
                    emotion={"level": "neutral", "score": 0}
                )
                with patch("app.routers.chat.SessionLocal") as mock_db:
                    mock_db.return_value.query.return_value.filter.return_value.first.return_value = None
                    with patch("app.routers.chat.memory_manager") as mock_mem:
                        mock_mem.should_ask_weight.return_value = False
                        mock_mem.should_ask_bp.return_value = False
                        req = ChatSendRequest(
                            pregnant_id="test-pid",
                            message="你好",
                        )
                        resp = await send_message(req)
                        assert resp.content == "原始回复"
